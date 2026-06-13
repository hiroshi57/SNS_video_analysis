"""競合差別化: 過去の同ジャンル分析と比較し、差別化レポートを生成する。"""
from __future__ import annotations

from . import analyze, store


def _summary_for_compare(item: dict) -> dict:
    """比較プロンプトに渡す要点だけを抽出する(トークン節約)。"""
    s1 = item.get("stage1_json") or {}
    s2 = item.get("stage2_json") or {}
    return {
        "タイトル": item.get("title"),
        "プラットフォーム": item.get("platform"),
        "尺(秒)": item.get("duration_sec"),
        "ジャンル": item.get("genre_tags"),
        "3行要約": s1.get("summary_3lines"),
        "章立て": s1.get("chapters"),
        "映像の特徴": s2.get("visual_features"),
        "強み": s2.get("strengths"),
    }


def run_comparison(analysis_id: int) -> dict:
    """指定IDの動画を、同ジャンルの過去分析と比較して結果を保存・返却する。

    映像深掘り(stage2)の結果が無いと比較の質が落ちるため、その有無を確認する。
    analyze.run_compare はリトライ・検証付きなので、失敗時は AnalysisError を送出する。
    """
    item = store.get_analysis(analysis_id)
    if item is None:
        raise ValueError(f"分析ID {analysis_id} が見つかりません")

    past = store.find_same_genre(item["genre_tags"], exclude_id=analysis_id)
    result = analyze.run_compare(
        new_analysis=_summary_for_compare(item),
        past_analyses=[_summary_for_compare(p) for p in past],
    )
    result["_compared_with"] = [
        {"id": p["id"], "title": p["title"]} for p in past
    ]
    store.update_compare(analysis_id, result)
    return result
