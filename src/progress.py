"""分析パイプラインのステップ定義。

app.py の進捗表示(_STAGE_PCT / render_step_indicator)が、この定義の
キーと順序を参照する。パーセントの実計算はUI側で行うため、ここでは
ステップの一覧(キー・ラベル・重み)だけを持つ。

※以前ここにあった ProgressTracker / ProgressState は未使用だったため削除した。
  ステップ内進捗(長尺セグメント)の通知が必要になった場合は、analyze 側の
  SubProgress コールバックを使うこと。
"""
from __future__ import annotations

# パイプライン全体のステップ定義(key, label, weight)。
# weight は将来パーセントを重み付けするための目安(深掘りを重く配分)。
PIPELINE_STEPS: list[tuple[str, str, int]] = [
    ("ingest", "動画を取り込み中", 10),
    ("stage1", "一次分析中(要約・文字起こし)", 25),
    ("stage2", "映像を深掘り分析中(フック・テロップ・構成)", 40),
    ("compare", "競合との差別化を分析中", 25),
]
