"""SNS動画分析ツール — Streamlit UI。

実行: python -m streamlit run app.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src import analyze, compare, config, store
from src.ingest import SUPPORTED_VIDEO_EXTS, ingest
from src.progress import PIPELINE_STEPS

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


# 段階ごとの到達後パーセント(進捗バー表示用)
# 各段階の (作業中に見せる%, 完了到達%)。作業中は中間値を出して「動いている」感を出す。
_STAGE_PCT = {"ingest": 10, "stage1": 35, "stage2": 75, "compare": 100}
_STAGE_WORKING_PCT = {"ingest": 5, "stage1": 22, "stage2": 55, "compare": 88}
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


def start_pipeline(source) -> None:
    """パイプラインを開始する。実体は run_pending_stage が1段ずつ進める。"""
    st.session_state["pipe"] = {"stage": "ingest", "source": str(source),
                                "is_path": not str(source).startswith("http")}
    st.rerun()


def render_progress(stage: str, fast_mode: bool | None = None) -> None:
    """実行中の段階の作業中%・ステップ表示・所要目安を描く。"""
    pct = _STAGE_WORKING_PCT[stage]
    st.markdown(
        f'<div class="pct">{pct}%<small>　{_STAGE_LABEL[stage]}…</small></div>',
        unsafe_allow_html=True,
    )
    render_step_indicator(stage)
    st.progress(pct)
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


def run_pending_stage() -> None:
    """session_state の現在段階を1つだけ実行し、rerunで画面を返す。

    1段ごとに rerun することで、Streamlitのブロッキングを避け
    進捗%が確実に前進する。深掘りはanalyze側でリトライ・検証付き。
    """
    pipe = st.session_state["pipe"]
    stage = pipe["stage"]

    render_progress(stage, pipe.get("fast_mode"))
    spin = st.empty()

    try:
        with spin, st.spinner(f"{_STAGE_LABEL[stage]}… ({_STAGE_HINT[stage]})"):
            if stage == "ingest":
                src = pipe["source"]
                vs = ingest(Path(src) if pipe["is_path"] else src)
                st.session_state["_vs"] = vs
                pipe["fast_mode"] = analyze.is_fast_mode(vs)
                pipe["stage"] = "stage1"

            elif stage == "stage1":
                vs = st.session_state["_vs"]
                stage1 = analyze.run_stage1(vs)
                pipe["analysis_id"] = store.save_analysis(vs, stage1)
                pipe["stage"] = "stage2"

            elif stage == "stage2":
                vs = st.session_state["_vs"]
                stage2 = analyze.run_stage2_visual(vs)
                store.update_stage2(pipe["analysis_id"], stage2)
                pipe["stage"] = "compare"

            elif stage == "compare":
                compare.run_comparison(pipe["analysis_id"])
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
        start_pipeline(source)


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


def render_summary_tab(stage1: dict) -> None:
    st.markdown('<div class="sec">📝 3行要約</div>', unsafe_allow_html=True)
    for line in stage1.get("summary_3lines", []):
        st.markdown(f'<div class="sumline">{line}</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec">📑 章立て</div>', unsafe_allow_html=True)
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
    if not transcript:
        st.caption("発話なし(BGMのみ等)")
        return
    rows = []
    for seg in transcript:
        speaker = seg.get("speaker") or ""
        head = f'[{seg.get("time")}] {speaker}'.strip()
        rows.append(f'<div class="ts"><div class="t">{head}</div>'
                    f'<div class="x">{seg.get("text", "")}</div></div>')
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
    features = stage2.get("visual_features", {})
    st.markdown('<div class="sec">🎞️ 映像の特徴</div>', unsafe_allow_html=True)
    cards = "".join(
        f'<div class="vcard"><div class="lbl">{label}</div>'
        f'<div class="txt">{features[key]}</div></div>'
        for key, label in _VLABELS.items() if features.get(key)
    )
    st.markdown(f'<div class="vgrid">{cards}</div>', unsafe_allow_html=True)

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

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="sec">✅ 強み</div>', unsafe_allow_html=True)
        for s in stage2.get("strengths", []):
            st.markdown(f'<div class="pill">{s}</div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="sec">💡 改善提案</div>', unsafe_allow_html=True)
        for s in stage2.get("improvements", []):
            st.markdown(f'<div class="pill">{s}</div>', unsafe_allow_html=True)


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
    table = cmp.get("comparison_table", [])
    if table:
        df = pd.DataFrame([{"比較軸": r.get("axis"), "この動画": r.get("this_video"),
                            "競合の傾向": r.get("competitors"),
                            "差別化ポイント": r.get("differentiation")}
                           for r in table])
        st.dataframe(df, hide_index=True, use_container_width=True,
                     column_config={
                         "比較軸": st.column_config.TextColumn(width="small"),
                         "この動画": st.column_config.TextColumn(width="medium"),
                         "競合の傾向": st.column_config.TextColumn(width="medium"),
                         "差別化ポイント": st.column_config.TextColumn(width="large")})

    st.markdown('<div class="sec">🏆 独自の強み</div>', unsafe_allow_html=True)
    for p in cmp.get("unique_points", []):
        st.markdown(f'<div class="pill">{p}</div>', unsafe_allow_html=True)
    if cmp.get("gaps"):
        st.markdown('<div class="sec">⚠️ 競合に劣る点</div>', unsafe_allow_html=True)
        for p in cmp["gaps"]:
            st.markdown(f'<div class="pill">{p}</div>', unsafe_allow_html=True)
    st.markdown('<div class="sec">📈 差別化強化の提案</div>', unsafe_allow_html=True)
    for p in cmp.get("recommendations", []):
        st.markdown(f'<div class="pill">{p}</div>', unsafe_allow_html=True)


def render_result(item: dict) -> None:
    hero()
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
