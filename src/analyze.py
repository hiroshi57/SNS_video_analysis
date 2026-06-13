"""Gemini呼び出し: Stage 1(Flash高速一次分析) / Stage 2(Pro深掘り) / 長尺分割。

深掘り(映像・競合)は「失敗を許さない」方針:
- リトライ(指数バックオフ)
- 出力スキーマの検証(必須キー・非空チェック)
- 検証不合格なら自動で再生成。規定回数尽きたら明示的に例外を送出する
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from . import config
from .ingest import VideoSource, to_gemini_part

_client: genai.Client | None = None

# ステップ内進捗(0.0〜1.0)を受け取るコールバック。長尺セグメントの可視化に使う。
SubProgress = Callable[[float, str], None]


class AnalysisError(RuntimeError):
    """分析が規定回数のリトライ後も完遂できなかったことを表す。"""


def get_client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError(
                ".env に GEMINI_API_KEY が設定されていません。"
                ".env.example をコピーして .env を作成してください。"
            )
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _load_prompt(name: str) -> str:
    return (config.PROMPTS_DIR / name).read_text(encoding="utf-8")


def _parse_json(text: str) -> dict:
    """モデル出力からJSONを取り出す(コードブロックで囲まれた場合も救済)。"""
    if not text:
        raise ValueError("モデルが空の応答を返しました")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?\s*|\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


# ---------------------------------------------------------------- 出力検証
def _non_empty(value) -> bool:
    if value is None:
        return False
    if isinstance(value, (str, list, dict)):
        return len(value) > 0
    return True


def _validate_stage1(data: dict) -> list[str]:
    problems = []
    if not _non_empty(data.get("summary_3lines")):
        problems.append("summary_3lines が空")
    if "transcript" not in data and "chapters" not in data:
        problems.append("transcript も chapters も無い")
    return problems


def _validate_visual(data: dict) -> list[str]:
    """映像深掘りの完遂条件。必須キーが揃い中身があることを厳格に確認する。"""
    problems = []
    features = data.get("visual_features")
    if not isinstance(features, dict):
        problems.append("visual_features が無い")
    else:
        required = ["hook", "telop", "editing", "bgm_sound",
                    "visual_style", "appeal_structure"]
        empty = [k for k in required if not _non_empty(features.get(k))]
        if empty:
            problems.append("visual_features の未記入: " + ", ".join(empty))
    if not _non_empty(data.get("scenes")):
        problems.append("scenes(シーン別の映像詳細)が空")
    if not _non_empty(data.get("strengths")):
        problems.append("strengths が空")
    if not _non_empty(data.get("improvements")):
        problems.append("improvements が空")
    return problems


def _validate_compare(data: dict) -> list[str]:
    """競合差別化の完遂条件。"""
    problems = []
    if not _non_empty(data.get("comparison_table")):
        problems.append("comparison_table(比較表)が空")
    else:
        for i, row in enumerate(data["comparison_table"]):
            if not all(_non_empty(row.get(k)) for k in
                       ("axis", "this_video", "differentiation")):
                problems.append(f"comparison_table[{i}] の必須項目が欠落")
                break
    if not _non_empty(data.get("recommendations")):
        problems.append("recommendations(差別化提案)が空")
    return problems


# ---------------------------------------------------------------- 生成本体
_RETRYABLE = (
    genai_errors.ServerError,
    genai_errors.ClientError,
    json.JSONDecodeError,
    ValueError,
    ConnectionError,
    TimeoutError,
)


def _generate(model: str, parts: list, low_res: bool,
              validator: Callable[[dict], list[str]] | None = None,
              max_attempts: int = 4) -> dict:
    """JSON生成 + 検証 + リトライ。

    検証関数が問題を返した場合、その指摘を次回プロンプトに添えて再生成する。
    全試行が失敗したら AnalysisError を送出する(深掘りを必ず完遂させるため)。
    """
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json",
        media_resolution=(
            types.MediaResolution.MEDIA_RESOLUTION_LOW if low_res else None
        ),
    )
    last_error = ""
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        call_parts = list(parts)
        if feedback:
            call_parts.append(
                "前回の出力には以下の不備がありました。必ず全項目を埋めて、"
                "規定のJSONスキーマで完全な出力を返してください:\n" + feedback
            )
        try:
            response = get_client().models.generate_content(
                model=model, contents=call_parts, config=cfg
            )
            data = _parse_json(response.text)
            problems = validator(data) if validator else []
            if not problems:
                return data
            feedback = "・" + "\n・".join(problems)
            last_error = f"出力検証に失敗: {feedback}"
        except _RETRYABLE as e:
            last_error = f"{type(e).__name__}: {e}"
        except genai_errors.APIError as e:  # 想定外のAPIエラー
            last_error = f"APIError: {e}"
        if attempt < max_attempts:
            time.sleep(min(2 ** attempt, 12))  # 指数バックオフ(最大12秒)

    raise AnalysisError(
        f"{max_attempts}回試行しましたが分析を完遂できませんでした。"
        f"最後のエラー: {last_error}"
    )


def _segments(duration: float | None) -> list[tuple[float, float | None]]:
    """長尺動画を video_metadata の時間オフセットで区切る(ffmpeg分割不要)。"""
    if duration is None or duration <= config.SEGMENT_THRESHOLD_SEC:
        return [(0, None)]
    segs, start = [], 0.0
    while start < duration:
        end = min(start + config.SEGMENT_LENGTH_SEC, duration)
        segs.append((start, end))
        start = end
    return segs


def _is_low_res(vs: VideoSource) -> bool:
    return bool(vs.duration_sec and vs.duration_sec > config.LOW_RES_THRESHOLD_SEC)


def _analyze_segmented(vs: VideoSource, prompt_file: str, model: str,
                       merge_instruction: str,
                       validator: Callable[[dict], list[str]] | None,
                       sub_progress: SubProgress | None) -> dict:
    """セグメントごとに分析し、複数セグメントなら結果をマージする。

    sub_progress(fraction, detail) を渡すと区間進捗を通知する。
    """
    client = get_client()
    prompt = _load_prompt(prompt_file)
    segs = _segments(vs.duration_sec)
    low_res = _is_low_res(vs)
    n = len(segs)

    results = []
    for i, (start, end) in enumerate(segs):
        if sub_progress:
            detail = f"区間 {i + 1}/{n}" if n > 1 else ""
            sub_progress(i / n, detail)
        part = to_gemini_part(client, vs, start_sec=start if end else None,
                              end_sec=end)
        seg_prompt = prompt
        if end is not None:
            seg_prompt += (
                f"\n\n※これは長時間動画の {int(start // 60)}分〜{int(end // 60)}分 の"
                "区間です。タイムスタンプは動画全体の実時刻で記載してください。"
            )
        results.append(_generate(model, [part, seg_prompt], low_res, validator))
        if sub_progress:
            sub_progress((i + 1) / n, f"区間 {i + 1}/{n} 完了" if n > 1 else "")

    if len(results) == 1:
        return results[0]

    merge_prompt = (
        f"{merge_instruction}\n\n"
        "以下は1本の長時間動画を区間ごとに分析した結果(JSON配列)です。"
        "重複を除き、時系列を保って1つのJSONに統合してください。"
        "すべての必須項目を保持し、出力形式は各要素と同じJSONスキーマで、"
        "JSONのみを出力してください。\n\n"
        + json.dumps(results, ensure_ascii=False)
    )
    # マージ結果も検証する(統合で必須項目が落ちないことを保証)
    return _generate(config.MODEL_DEEP, [merge_prompt], False, validator)


def is_fast_mode(vs: VideoSource) -> bool:
    """長時間動画は速度優先モード(要約・代表シーン中心)に切り替える。"""
    return bool(vs.duration_sec
                and vs.duration_sec > config.FAST_MODE_THRESHOLD_SEC)


def run_stage1(vs: VideoSource, sub_progress: SubProgress | None = None) -> dict:
    """一次分析(Flash): 3行要約・ジャンルタグ・章立て・文字起こし。

    長時間動画では全文逐語をやめ、章要約＋要点抜粋に切り替えて高速化する。
    """
    prompt = "stage1_fast_long.md" if is_fast_mode(vs) else "stage1_fast.md"
    return _analyze_segmented(
        vs, prompt, config.MODEL_FAST,
        "summary_3lines は動画全体の要約として作り直すこと。",
        _validate_stage1, sub_progress,
    )


def run_stage2_visual(vs: VideoSource,
                      sub_progress: SubProgress | None = None) -> dict:
    """深掘り分析: 映像の特徴・シーン詳細・強み/改善点。失敗は許さない。

    長時間動画では全シーン列挙をやめ、代表シーンに絞って高速化する。
    """
    prompt = "stage2_visual_long.md" if is_fast_mode(vs) else "stage2_visual.md"
    return _analyze_segmented(
        vs, prompt, config.MODEL_DEEP,
        "visual_features は動画全体の傾向として統合し、全項目を埋めること。",
        _validate_visual, sub_progress,
    )


def run_compare(new_analysis: dict, past_analyses: list[dict]) -> dict:
    """競合差別化(Pro): 今回の分析結果と過去の同ジャンル分析を比較する。失敗は許さない。"""
    prompt = _load_prompt("stage2_compare.md")
    payload = {
        "今回の動画": new_analysis,
        "競合・参考動画(過去の分析)": past_analyses if past_analyses
        else "過去の分析が0件",
    }
    contents = [prompt + "\n\n" + json.dumps(payload, ensure_ascii=False)]
    return _generate(config.MODEL_DEEP, contents, False, _validate_compare)
