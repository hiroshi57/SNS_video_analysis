"""SNS動画分析ツール — Streamlit UI。

実行: python -m streamlit run app.py
"""
from __future__ import annotations

import html
import math
import threading
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from src import analyze, compare, config, store
from src.ingest import SUPPORTED_VIDEO_EXTS, ingest, source_cache_key
from src.progress import PIPELINE_STEPS

# 別スレッドで実処理を回しつつ進捗バーを動かすため、スレッドに
# ScriptRunContext を引き継ぐ。古い/異なるStreamlitでも落ちないようフォールバックする。
try:
    from streamlit.runtime.scriptrunner import (
        add_script_run_ctx,
        get_script_run_ctx,
    )
except Exception:  # noqa: BLE001
    add_script_run_ctx = None
    get_script_run_ctx = None

st.set_page_config(page_title="SNS動画分析ツール", page_icon="🎬", layout="wide")

UPLOAD_DIR = config.VIDEO_CACHE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


# ============================================================ スタイル
def inject_css() -> None:
    st.markdown(
        """
        <style>
        /* ---- 全体の余白を詰めてコンテンツ密度を上げる ---- */
        .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }

        /* ---- ヒーロー ---- */
        .hero {
            background: linear-gradient(120deg, #7c3aed 0%, #4f46e5 50%, #0ea5e9 100%);
            padding: 22px 28px; border-radius: 16px; margin-bottom: 20px;
            box-shadow: 0 10px 34px rgba(79,70,229,.30);
        }
        .hero h1 { color:#fff; margin:0; font-size:1.55rem; font-weight:800; }
        .hero p  { color:#eef2ff; margin:.45rem 0 0; font-size:.92rem; line-height:1.65; }

        /* ---- セクション見出し ---- */
        .sec { font-size:1.08rem; font-weight:800; color:#f8fafc;
               border-left:4px solid #a78bfa; padding-left:11px;
               margin:18px 0 12px; }

        /* ---- 動画下のタイトル＆メタ ---- */
        .vtitle { font-size:1.05rem; font-weight:700; color:#f1f5f9;
                  line-height:1.5; margin:14px 0 8px; }
        .metarow { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:6px; }
        .chip { display:inline-flex; align-items:center; gap:5px;
                background:#232b3e; color:#cbd5e1; border:1px solid #374151;
                border-radius:8px; padding:5px 11px; font-size:.8rem; font-weight:600; }
        .chip b { color:#fff; font-weight:700; }
        .tag  { display:inline-block; background:#4338ca; color:#fff;
                border-radius:999px; padding:4px 13px; font-size:.78rem;
                font-weight:600; margin:3px 5px 3px 0; }

        /* ---- 映像特徴カード(2列グリッド) ---- */
        .vgrid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .vcard { background:#171e2e; border:1px solid #2c3650; border-radius:12px;
                 padding:15px 17px; }
        .vcard .lbl { color:#c4b5fd; font-weight:800; font-size:.82rem;
                      display:flex; align-items:center; gap:6px; }
        .vcard .txt { color:#e6e9f2; margin-top:7px; font-size:.9rem; line-height:1.7; }

        /* ---- 文字起こし行 ---- */
        .ts { display:flex; gap:12px; padding:7px 0; border-bottom:1px solid #1e2740; }
        .ts .t { color:#818cf8; font-weight:700; font-size:.82rem; min-width:96px;
                 font-variant-numeric:tabular-nums; }
        .ts .x { color:#e6e9f2; font-size:.92rem; line-height:1.55; }

        /* ---- 要約の大きめ表示 ---- */
        .sumline { background:#171e2e; border-left:3px solid #34d399;
                   border-radius:8px; padding:11px 15px; margin-bottom:9px;
                   color:#f1f5f9; font-size:.96rem; line-height:1.6; }

        /* ---- 箇条書きカード(強み・提案など) ---- */
        .pill { background:#171e2e; border:1px solid #2c3650; border-radius:9px;
                padding:10px 14px; margin-bottom:8px; color:#e6e9f2;
                font-size:.9rem; line-height:1.6; }

        /* ---- 進捗 ---- */
        .pct { font-size:2.6rem; font-weight:800; color:#fff; line-height:1; }
        .pct small { font-size:.95rem; color:#94a3b8; font-weight:500; }
        .steps { display:flex; gap:7px; margin:14px 0 6px; }
        .stepchip { flex:1; text-align:center; font-size:.78rem; padding:9px 4px;
                    border-radius:9px; background:#171e2e; color:#94a3b8;
                    border:1px solid #2c3650; font-weight:600; }
        .stepchip.active { background:#4338ca; color:#fff; border-color:#818cf8; }
        .stepchip.done   { background:#047857; color:#d1fae5; border-color:#10b981; }

        /* ---- タブ ---- */
        .stTabs [data-baseweb="tab-list"] { gap:4px; }
        .stTabs [data-baseweb="tab"] { font-weight:600; }

        /* ---- データフレーム見やすく ---- */
        [data-testid="stDataFrame"] { border:1px solid #2c3650; border-radius:10px; }

        /* ============ Design.md デザインシステム ============ */
        /* タイポ階層 */
        .eyebrow { font-size:.72rem; font-weight:700; letter-spacing:.12em;
                   text-transform:uppercase; color:#94a3b8; margin:18px 0 8px; }
        .lead { font-size:1.05rem; font-weight:600; line-height:1.6; color:#f1f5f9; }

        /* 要点バンド(結果上部): 訴求 / 強み / ひとこと */
        .keypoints { display:grid; grid-template-columns:repeat(3,1fr); gap:14px;
                     margin:6px 0 22px; }
        .kp { position:relative; background:#171e2e; border:1px solid #2c3650;
              border-radius:14px; padding:18px 18px 16px; overflow:hidden; }
        .kp::before { content:""; position:absolute; top:0; left:0; right:0; height:4px; }
        .kp.appeal::before  { background:linear-gradient(90deg,#7c3aed,#818cf8); }
        .kp.strength::before{ background:linear-gradient(90deg,#059669,#34d399); }
        .kp.gist::before    { background:linear-gradient(90deg,#0ea5e9,#38bdf8); }
        .kp .kp-label { font-size:.78rem; font-weight:800; letter-spacing:.04em;
                        display:flex; align-items:center; gap:7px; margin-bottom:9px; }
        .kp.appeal   .kp-label { color:#c4b5fd; }
        .kp.strength .kp-label { color:#6ee7b7; }
        .kp.gist     .kp-label { color:#7dd3fc; }
        .kp .kp-text { color:#f1f5f9; font-size:1rem; font-weight:600;
                       line-height:1.55; }

        /* 要約ヒーロー(番号付き3行要約) */
        .sumrow { display:flex; gap:13px; align-items:flex-start;
                  background:#171e2e; border:1px solid #2c3650;
                  border-left:3px solid #34d399; border-radius:10px;
                  padding:13px 16px; margin-bottom:10px; }
        .sumrow .n { flex:none; width:26px; height:26px; border-radius:50%;
                     background:#065f46; color:#d1fae5; font-weight:800;
                     font-size:.85rem; display:flex; align-items:center;
                     justify-content:center; }
        .sumrow .s { color:#f1f5f9; font-size:1.02rem; font-weight:600;
                     line-height:1.55; }

        /* 強み(緑) / 改善(琥珀) カード */
        .good, .warn { display:flex; gap:10px; align-items:flex-start;
                       border-radius:10px; padding:12px 15px; margin-bottom:9px;
                       font-size:.94rem; line-height:1.6; }
        .good { background:rgba(16,185,129,.08); border:1px solid #1e6f56; color:#e6f8f1; }
        .warn { background:rgba(245,158,11,.08); border:1px solid #8a6326; color:#fcefdb; }
        .good .ic, .warn .ic { flex:none; font-size:1.05rem; line-height:1.5; }

        /* 競合比較カード(軸ごと) */
        .cmp { background:#171e2e; border:1px solid #2c3650; border-radius:13px;
               padding:16px 18px; margin-bottom:14px; }
        .cmp .axis { font-size:1rem; font-weight:800; color:#f8fafc; margin-bottom:11px;
                     display:flex; align-items:center; gap:8px; }
        .cmp .axis .pin { width:9px; height:9px; border-radius:50%;
                          background:#818cf8; flex:none; }
        .cmp .vs { display:grid; grid-template-columns:1fr 1fr; gap:11px; margin-bottom:11px; }
        .cmp .col { background:#0f1626; border:1px solid #232b3e; border-radius:9px;
                    padding:10px 13px; }
        .cmp .col .t { font-size:.74rem; font-weight:800; letter-spacing:.03em;
                       margin-bottom:5px; }
        .cmp .col.me .t   { color:#7dd3fc; }
        .cmp .col.them .t { color:#94a3b8; }
        .cmp .col .x { color:#e6e9f2; font-size:.9rem; line-height:1.55; }
        .cmp .diff { background:rgba(124,58,237,.12); border:1px solid #4338ca;
                     border-radius:9px; padding:11px 14px; }
        .cmp .diff .t { font-size:.74rem; font-weight:800; color:#c4b5fd;
                        letter-spacing:.03em; margin-bottom:4px; }
        .cmp .diff .x { color:#f1f5f9; font-size:.95rem; font-weight:600; line-height:1.55; }

        /* 独自の強み(星) */
        .star { display:flex; gap:10px; align-items:flex-start;
                background:linear-gradient(90deg,rgba(124,58,237,.14),rgba(124,58,237,.04));
                border:1px solid #4338ca; border-radius:10px; padding:12px 15px;
                margin-bottom:9px; color:#f1f5f9; font-size:.96rem; font-weight:600;
                line-height:1.6; }
        .star .ic { flex:none; }

        /* 文字起こし: 主役ではない参照資料として静かに見せる */
        .ts { display:flex; gap:14px; padding:8px 2px; border-bottom:1px solid #1a2236; }
        .ts .t { color:#64748b; font-weight:600; font-size:.78rem; min-width:92px;
                 font-variant-numeric:tabular-nums; padding-top:2px; }
        .ts .sp { color:#818cf8; font-weight:600; font-size:.76rem; }
        .ts .x { color:#cbd5e1; font-size:.9rem; line-height:1.6; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    st.markdown(
        """
        <div class="hero">
          <h1>🎬 SNS動画分析ツール</h1>
          <p>YouTube・Instagram・X・Facebook・TikTok のURL、または動画ファイルから
          <b>要約 / 文字起こし / 映像の特徴・詳細 / 競合との差別化</b> を分析します。</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================ 進捗UI
def render_step_indicator(active_key: str) -> None:
    order = [s[0] for s in PIPELINE_STEPS]
    try:
        active_idx = order.index(active_key)
    except ValueError:
        active_idx = len(order) if active_key == "done" else -1
    short = {"ingest": "① 取込", "stage1": "② 要約・文字起こし",
             "stage2": "③ 映像深掘り", "compare": "④ 競合差別化"}
    chips = []
    for i, key in enumerate(order):
        cls = "stepchip"
        if i < active_idx or active_key == "done":
            cls += " done"
        elif i == active_idx:
            cls += " active"
        chips.append(f'<div class="{cls}">{short[key]}</div>')
    st.markdown(f'<div class="steps">{"".join(chips)}</div>',
                unsafe_allow_html=True)


# 段階ごとの累積パーセント・レンジ (開始%, 完了%)。
# 段階をまたいで単調増加するので「③に来たのに5%」のような後戻り感が出ない。
# 各段階の作業中は lo→hi の間をアニメーションさせ「進んでいる感」を出す。
_STAGE_RANGE = {
    "ingest":  (0, 10),
    "stage1":  (10, 40),
    "stage2":  (40, 85),   # ③深掘りはここから始まるので 40% 以上から動く
    "compare": (85, 100),
}
# 各段階の所要目安(秒)。アニメーションの減速カーブの形に使うだけで、
# 実際の完了はスレッドの終了で判定する(目安より長引いても hi 手前で動き続ける)。
_STAGE_EXPECTED_SEC = {"ingest": 12, "stage1": 35, "stage2": 80, "compare": 20}
# 「実行中の段階」の表示ラベルと所要目安
_STAGE_LABEL = {
    "ingest": "① 動画を取り込み中",
    "stage1": "② 要約・文字起こしを生成中(高速)",
    "stage2": "③ 映像を深掘り分析中(フック・テロップ・構成)",
    "compare": "④ 競合との差別化を分析中",
}
_STAGE_HINT = {
    "ingest": "動画のダウンロード中です(数秒〜数十秒)。",
    "stage1": "動画全体を読んで要約・文字起こしを生成中です。"
              "動画の長さに応じて数十秒〜数分かかります。",
    "stage2": "映像の演出を1カットずつ分析中です。動画の長さに応じて1〜数分かかります。",
    "compare": "過去の分析と照合して差別化点を抽出中です(数十秒)。",
}
_STAGE_ORDER = ["ingest", "stage1", "stage2", "compare"]


def start_pipeline(source, cache_key: str | None = None) -> None:
    """パイプラインを開始する。実体は run_pending_stage が1段ずつ進める。"""
    st.session_state["pipe"] = {"stage": "ingest", "source": str(source),
                                "is_path": not str(source).startswith("http"),
                                "cache_key": cache_key}
    st.rerun()


def _render_stage_meta(stage: str, fast_mode: bool | None) -> None:
    """モードのバッジと所要目安のキャプションを描く。"""
    if fast_mode is not None:
        if fast_mode:
            st.markdown(
                '<span class="tag" style="background:#0e7490">⚡ 速度優先モード'
                '(長時間動画:要約・代表シーン中心)</span>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                '<span class="tag" style="background:#4338ca">🎯 高品質モード'
                '(全文文字起こし・全シーン分析)</span>',
                unsafe_allow_html=True)
    st.caption("⏳ " + _STAGE_HINT[stage] + " このまま画面を開いたままお待ちください。")


def _run_stage_animated(stage: str, work_fn, fast_mode: bool | None):
    """work_fn を別スレッドで実行し、その間 % をレンジ内で滑らかに前進させる。

    - 数字とバーは lo% から始まり、経過時間に応じて hi% へ漸近する
      (最初は速く、徐々に減速)。完了まで hi-1% を超えないので「もうすぐ」感を保つ。
    - work_fn がスレッド内で投げた例外はメインスレッドへ送出し直す
      (呼び出し側の AnalysisError / Exception ハンドリングをそのまま活かす)。
    """
    lo, hi = _STAGE_RANGE[stage]
    expected = _STAGE_EXPECTED_SEC[stage]

    box: dict = {}

    def worker():
        try:
            box["result"] = work_fn()
        except BaseException as e:  # noqa: BLE001 - メインへ転送して扱う
            box["error"] = e

    t = threading.Thread(target=worker, daemon=True)
    if add_script_run_ctx and get_script_run_ctx:
        add_script_run_ctx(t, get_script_run_ctx())

    num_ph = st.empty()
    render_step_indicator(stage)
    bar = st.progress(lo)
    _render_stage_meta(stage, fast_mode)

    t.start()
    start = time.time()
    pct = lo
    while t.is_alive():
        elapsed = time.time() - start
        # 漸近カーブ: elapsed=expected で約63%, 2倍で約86% まで進む
        frac = 1.0 - math.exp(-elapsed / expected)
        pct = min(hi - 1, int(lo + (hi - lo) * frac))
        num_ph.markdown(
            f'<div class="pct">{pct}%<small>　{_STAGE_LABEL[stage]}…</small></div>',
            unsafe_allow_html=True)
        bar.progress(pct)
        time.sleep(0.2)

    if "error" in box:
        raise box["error"]

    # 完了: レンジ上限まで一気に詰めて「この段階は終わった」感を出す
    num_ph.markdown(
        f'<div class="pct">{hi}%<small>　{_STAGE_LABEL[stage]} 完了</small></div>',
        unsafe_allow_html=True)
    bar.progress(hi)
    return box.get("result")


def run_pending_stage() -> None:
    """session_state の現在段階を1つだけ実行し、rerunで画面を返す。

    1段ごとに rerun することで、Streamlitのブロッキングを避け
    進捗%が確実に前進する。深掘りはanalyze側でリトライ・検証付き。
    """
    pipe = st.session_state["pipe"]
    stage = pipe["stage"]
    fast_mode = pipe.get("fast_mode")

    try:
        if stage == "ingest":
            src = pipe["source"]
            is_path = pipe["is_path"]
            vs = _run_stage_animated(
                "ingest", lambda: ingest(Path(src) if is_path else src), fast_mode)
            st.session_state["_vs"] = vs
            pipe["fast_mode"] = analyze.is_fast_mode(vs)
            pipe["stage"] = "stage1"

        elif stage == "stage1":
            vs = st.session_state["_vs"]
            stage1 = _run_stage_animated(
                "stage1", lambda: analyze.run_stage1(vs), fast_mode)
            pipe["analysis_id"] = store.save_analysis(
                vs, stage1, cache_key=pipe.get("cache_key"))
            pipe["stage"] = "stage2"

        elif stage == "stage2":
            vs = st.session_state["_vs"]
            stage2 = _run_stage_animated(
                "stage2", lambda: analyze.run_stage2_visual(vs), fast_mode)
            store.update_stage2(pipe["analysis_id"], stage2)
            pipe["stage"] = "compare"

        elif stage == "compare":
            aid = pipe["analysis_id"]
            _run_stage_animated(
                "compare", lambda: compare.run_comparison(aid), fast_mode)
            pipe["stage"] = "done"
    except analyze.AnalysisError as e:
        st.error(f"深掘り分析を完遂できませんでした(自動リトライ済み): {e}")
        if st.button("🔁 この段階をやり直す", type="primary"):
            st.rerun()
        st.stop()
    except Exception as e:  # noqa: BLE001 - UIにはあらゆる失敗を表示する
        st.error(f"分析に失敗しました: {e}")
        if st.button("🔁 やり直す", type="primary"):
            st.rerun()
        st.stop()

    if pipe["stage"] == "done":
        st.session_state["current_id"] = pipe["analysis_id"]
        st.session_state.pop("pipe", None)
        st.session_state.pop("_vs", None)
    st.rerun()


# ============================================================ サイドバー
def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 📋 分析履歴")
        if st.button("➕ 新規分析", use_container_width=True, type="primary"):
            st.session_state.pop("current_id", None)
            st.rerun()
        st.divider()
        items = store.list_analyses()
        if not items:
            st.caption("まだ分析履歴はありません")
        for item in items:
            done = "🟢" if item.get("compare_json") else "🟡"
            label = f"{done} {item['title'][:22]}"
            if st.button(label, key=f"hist_{item['id']}",
                         use_container_width=True):
                st.session_state["current_id"] = item["id"]
                st.rerun()
        st.divider()
        st.caption("🟢 全分析完了　🟡 深掘り未完")


# ============================================================ 入力フォーム
def render_input_form() -> None:
    hero()
    url = st.text_input(
        "🔗 動画URL",
        placeholder="https://www.youtube.com/watch?v=... など",
    )
    uploaded = st.file_uploader(
        "📁 またはファイルをドラッグ&ドロップ",
        type=[e.lstrip(".") for e in SUPPORTED_VIDEO_EXTS],
    )
    force = st.checkbox(
        "キャッシュを無視して再分析する",
        help="同じ動画を過去に分析済みの場合、既定では保存結果を再表示して"
             "API消費を抑えます。チェックすると毎回新しく分析します。")
    start = st.button("🚀 分析開始", type="primary", use_container_width=True)
    st.caption("分析の流れ：① 取込 → ② 要約・文字起こし(高速) → "
               "③ 映像深掘り(フック・テロップ・構成) → ④ 競合差別化")

    if start:
        source: str | Path | None = None
        if url.strip():
            source = url.strip()
        elif uploaded is not None:
            dest = UPLOAD_DIR / uploaded.name
            dest.write_bytes(uploaded.getbuffer())
            source = dest
        if source is None:
            st.warning("URLを入力するか、ファイルをアップロードしてください。")
            return

        # --- 結果キャッシュ: 完遂済みの同一動画があればAPIを使わず再表示 ---
        cache_key = None
        try:
            cache_key = source_cache_key(source)
        except OSError:
            cache_key = None  # ハッシュ失敗時はキャッシュ無しで続行
        if not force and cache_key:
            cached = store.find_by_cache_key(cache_key)
            if cached:
                st.session_state["current_id"] = cached["id"]
                st.session_state["_from_cache"] = True
                st.rerun()
        start_pipeline(source, cache_key)


# ============================================================ 結果表示
def render_video(item: dict) -> None:
    if item["platform"] == "youtube" and item["source_url"]:
        st.video(item["source_url"])
    elif item["local_path"] and Path(item["local_path"]).exists():
        st.video(item["local_path"])
    elif item["source_url"]:
        st.markdown(f"[元動画を開く]({item['source_url']})")
    else:
        st.info("動画ファイルが見つかりません(分析結果のみ表示)")

    st.markdown(f'<div class="vtitle">{item["title"]}</div>',
                unsafe_allow_html=True)
    chips = [f'<span class="chip">🌐 <b>{item["platform"]}</b></span>']
    if item["duration_sec"]:
        m, s = divmod(int(item["duration_sec"]), 60)
        chips.append(f'<span class="chip">⏱ <b>{m}分{s:02d}秒</b></span>')
    st.markdown(f'<div class="metarow">{"".join(chips)}</div>',
                unsafe_allow_html=True)
    if item["genre_tags"]:
        st.markdown(
            "".join(f'<span class="tag">{t}</span>' for t in item["genre_tags"]),
            unsafe_allow_html=True,
        )


def _esc(text) -> str:
    """モデル出力をHTMLに安全に埋め込む(タグ崩れ防止)。"""
    return html.escape(str(text)) if text is not None else ""


def render_highlights(item: dict) -> None:
    """結果の最上部に「この動画は何を訴え、強みはどこか」を3枚で要点提示する。"""
    s1 = item.get("stage1_json") or {}
    s2 = item.get("stage2_json") or {}
    cmp = item.get("compare_json") or {}

    summary = s1.get("summary_3lines") or []
    feats = s2.get("visual_features") or {}
    strengths = s2.get("strengths") or []
    uniques = cmp.get("unique_points") or []

    # 訴求: 訴求構成 → 冒頭フック → ジャンルの順で拾う
    appeal = (feats.get("appeal_structure") or feats.get("hook")
              or "、".join(s1.get("genre_tags") or []) or "分析中…")
    # 一番の強み: 映像の強み → 競合比較の独自性
    strength = (strengths[0] if strengths else
                (uniques[0] if uniques else "深掘り分析の完了後に表示されます"))
    gist = summary[0] if summary else "要約を生成中…"

    cards = [
        ("appeal", "🎯 この動画が訴えること", appeal),
        ("strength", "✨ 一番の強み", strength),
        ("gist", "📝 ひとことで", gist),
    ]
    html_cards = "".join(
        f'<div class="kp {cls}"><div class="kp-label">{label}</div>'
        f'<div class="kp-text">{_esc(text)}</div></div>'
        for cls, label, text in cards
    )
    st.markdown(f'<div class="keypoints">{html_cards}</div>',
                unsafe_allow_html=True)


def render_summary_tab(stage1: dict) -> None:
    st.markdown('<div class="eyebrow">SUMMARY</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec">📝 3行でわかる、この動画</div>',
                unsafe_allow_html=True)
    lines = stage1.get("summary_3lines", [])
    if lines:
        rows = "".join(
            f'<div class="sumrow"><div class="n">{i}</div>'
            f'<div class="s">{_esc(line)}</div></div>'
            for i, line in enumerate(lines, 1)
        )
        st.markdown(rows, unsafe_allow_html=True)
    else:
        st.caption("要約なし")

    tags = stage1.get("genre_tags", [])
    if tags:
        st.markdown('<div class="eyebrow">GENRE</div>', unsafe_allow_html=True)
        st.markdown(
            "".join(f'<span class="tag">#{_esc(t)}</span>' for t in tags),
            unsafe_allow_html=True)

    st.markdown('<div class="eyebrow">CHAPTERS</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec">📑 章立て(流れ)</div>', unsafe_allow_html=True)
    chapters = stage1.get("chapters", [])
    if chapters:
        df = pd.DataFrame([{"時刻": c.get("start"), "章タイトル": c.get("title"),
                            "内容": c.get("summary")} for c in chapters])
        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={"内容": st.column_config.TextColumn(width="large")})
    else:
        st.caption("章立てなし")


def render_transcript_tab(stage1: dict) -> None:
    transcript = stage1.get("transcript", [])
    st.markdown('<div class="eyebrow">TRANSCRIPT</div>', unsafe_allow_html=True)
    if not transcript:
        st.caption("発話なし(BGMのみ等)")
        return
    # 参照資料なので装飾は最小限・トーンを落として「静かに」見せる(Design.md)。
    st.caption(f"🎙️ 全 {len(transcript)} 発話　時刻クリックで頭出し…の予定")
    rows = []
    for seg in transcript:
        speaker = _esc(seg.get("speaker") or "")
        sp = f'<span class="sp">{speaker}</span>' if speaker else ""
        rows.append(
            f'<div class="ts"><div class="t">{_esc(seg.get("time"))} {sp}</div>'
            f'<div class="x">{_esc(seg.get("text", ""))}</div></div>')
    st.markdown("".join(rows), unsafe_allow_html=True)


_VLABELS = {
    "hook": "🎯 冒頭フック", "telop": "💬 テロップ・字幕",
    "editing": "✂️ 編集・カット割り", "bgm_sound": "🎵 BGM・効果音",
    "visual_style": "🎨 画作り", "appeal_structure": "📐 訴求構成",
}


def render_visual_tab(stage2: dict | None) -> None:
    if not stage2:
        st.info("深掘り分析(映像の特徴・詳細)を実行中です...")
        return

    # --- まず「強み / 改善」を上に、色付きで強調(結論ファースト) ---
    strengths = stage2.get("strengths", [])
    improvements = stage2.get("improvements", [])
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="eyebrow">STRENGTHS</div>', unsafe_allow_html=True)
        st.markdown('<div class="sec">✅ この動画の強み</div>', unsafe_allow_html=True)
        for s in strengths:
            st.markdown(f'<div class="good"><span class="ic">✅</span>'
                        f'<span>{_esc(s)}</span></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="eyebrow">IMPROVEMENTS</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="sec">💡 伸ばすための改善提案</div>',
                    unsafe_allow_html=True)
        for s in improvements:
            st.markdown(f'<div class="warn"><span class="ic">⚠️</span>'
                        f'<span>{_esc(s)}</span></div>', unsafe_allow_html=True)

    # --- 映像の特徴(6観点) ---
    features = stage2.get("visual_features", {})
    st.markdown('<div class="eyebrow">CREATIVE BREAKDOWN</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="sec">🎞️ 映像の特徴</div>', unsafe_allow_html=True)
    cards = "".join(
        f'<div class="vcard"><div class="lbl">{label}</div>'
        f'<div class="txt">{_esc(features[key])}</div></div>'
        for key, label in _VLABELS.items() if features.get(key)
    )
    st.markdown(f'<div class="vgrid">{cards}</div>', unsafe_allow_html=True)

    st.markdown('<div class="eyebrow">SCENE BY SCENE</div>',
                unsafe_allow_html=True)
    st.markdown('<div class="sec">🔍 映像の詳細(シーン別)</div>',
                unsafe_allow_html=True)
    scenes = stage2.get("scenes", [])
    if scenes:
        df = pd.DataFrame([{"開始": s.get("start"), "終了": s.get("end"),
                            "内容": s.get("description"),
                            "演出の詳細": s.get("visual_detail")} for s in scenes])
        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={
                         "内容": st.column_config.TextColumn(width="medium"),
                         "演出の詳細": st.column_config.TextColumn(width="large")})


def render_compare_tab(cmp: dict | None) -> None:
    if not cmp:
        st.info("競合比較を実行中です...")
        return
    compared = cmp.get("_compared_with", [])
    if compared:
        st.info("比較対象(過去の分析): "
                + " / ".join(c["title"] for c in compared))
    else:
        st.info("同ジャンルの過去分析が0件のため、ジャンル一般の傾向と比較しています。"
                "分析を蓄積すると比較の具体性が上がります。")

    # --- 独自の強みを最上部に強調(差別化の結論) ---
    uniques = cmp.get("unique_points", [])
    if uniques:
        st.markdown('<div class="eyebrow">WHAT MAKES IT STAND OUT</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="sec">🏆 この動画だけの独自性</div>',
                    unsafe_allow_html=True)
        for p in uniques:
            st.markdown(f'<div class="star"><span class="ic">⭐</span>'
                        f'<span>{_esc(p)}</span></div>', unsafe_allow_html=True)

    # --- 軸ごとの対比カード(この動画 vs 競合 → 差別化ポイントを強調) ---
    table = cmp.get("comparison_table", [])
    if table:
        st.markdown('<div class="eyebrow">HEAD TO HEAD</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="sec">⚔️ 軸ごとの比較</div>', unsafe_allow_html=True)
        for r in table:
            comp_text = r.get("competitors") or "(ジャンル一般の傾向)"
            st.markdown(
                f'<div class="cmp">'
                f'<div class="axis"><span class="pin"></span>{_esc(r.get("axis"))}</div>'
                f'<div class="vs">'
                f'<div class="col me"><div class="t">この動画</div>'
                f'<div class="x">{_esc(r.get("this_video"))}</div></div>'
                f'<div class="col them"><div class="t">競合の傾向</div>'
                f'<div class="x">{_esc(comp_text)}</div></div>'
                f'</div>'
                f'<div class="diff"><div class="t">→ 差別化ポイント</div>'
                f'<div class="x">{_esc(r.get("differentiation"))}</div></div>'
                f'</div>',
                unsafe_allow_html=True)

    if cmp.get("gaps"):
        st.markdown('<div class="eyebrow">GAPS</div>', unsafe_allow_html=True)
        st.markdown('<div class="sec">⚠️ 競合に劣る点</div>', unsafe_allow_html=True)
        for p in cmp["gaps"]:
            st.markdown(f'<div class="warn"><span class="ic">⚠️</span>'
                        f'<span>{_esc(p)}</span></div>', unsafe_allow_html=True)

    st.markdown('<div class="eyebrow">NEXT ACTIONS</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec">📈 差別化を強化する提案</div>',
                unsafe_allow_html=True)
    for p in cmp.get("recommendations", []):
        st.markdown(f'<div class="star"><span class="ic">📈</span>'
                    f'<span>{_esc(p)}</span></div>', unsafe_allow_html=True)


def render_result(item: dict) -> None:
    hero()
    if st.session_state.pop("_from_cache", False):
        st.success("✅ この動画は分析済みです。保存結果を表示しました"
                   "(API呼び出しなし・無料枠を消費していません)。"
                   "再分析するには「➕ 新規分析」→「キャッシュを無視して再分析する」。")
    render_highlights(item)
    col_video, col_tabs = st.columns([5, 7], gap="large")
    with col_video:
        render_video(item)
    with col_tabs:
        tab1, tab2, tab3, tab4 = st.tabs(
            ["📝 要約", "🎙️ 文字起こし", "🎞️ 映像分析", "⚔️ 競合比較"]
        )
        with tab1:
            render_summary_tab(item["stage1_json"] or {})
        with tab2:
            render_transcript_tab(item["stage1_json"] or {})
        with tab3:
            render_visual_tab(item["stage2_json"])
        with tab4:
            render_compare_tab(item["compare_json"])


# ============================================================ メイン
def main() -> None:
    inject_css()
    render_sidebar()

    # パイプライン進行中: 1段ずつ実行(各段でrerunして%が前進する)
    if "pipe" in st.session_state:
        hero()
        st.markdown('<div class="sec">分析を実行しています</div>',
                    unsafe_allow_html=True)
        run_pending_stage()
        return

    current_id = st.session_state.get("current_id")
    if current_id is None:
        render_input_form()
        return
    item = store.get_analysis(current_id)
    if item is None:
        st.session_state.pop("current_id", None)
        render_input_form()
        return
    render_result(item)


main()
