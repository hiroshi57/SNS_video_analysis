"""分析パイプラインの進捗管理。各ステップの重みからパーセントを算出する。

UIに依存しない。コールバック(on_update)を渡すと進捗が変わるたびに呼ばれる。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# パイプライン全体のステップ定義(label, weight)。weightの合計で100%に正規化する。
# 深掘り(映像・競合)を重く配分し、体感の納得感を合わせる。
PIPELINE_STEPS: list[tuple[str, str, int]] = [
    ("ingest", "動画を取り込み中", 10),
    ("stage1", "一次分析中(要約・文字起こし)", 25),
    ("stage2", "映像を深掘り分析中(フック・テロップ・構成)", 40),
    ("compare", "競合との差別化を分析中", 25),
]

ProgressCallback = Callable[["ProgressState"], None]


@dataclass
class ProgressState:
    """現在の進捗。percent は 0〜100。"""
    step_key: str = ""
    step_label: str = ""
    percent: int = 0
    detail: str = ""  # 「区間 2/3」などの補足
    done: bool = False
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "step_key": self.step_key,
            "step_label": self.step_label,
            "percent": self.percent,
            "detail": self.detail,
            "done": self.done,
            "error": self.error,
        }


@dataclass
class ProgressTracker:
    """ステップの開始・完了を受け取り、累積パーセントを計算する。

    1ステップ内で複数区間(長尺動画のセグメント)がある場合は
    advance_within() でステップ内進捗を細かく反映する。
    """
    on_update: ProgressCallback | None = None
    _steps: list[tuple[str, str, int]] = field(
        default_factory=lambda: list(PIPELINE_STEPS)
    )
    state: ProgressState = field(default_factory=ProgressState)

    @property
    def _total_weight(self) -> int:
        return sum(w for _, _, w in self._steps)

    def _completed_weight_before(self, step_key: str) -> int:
        acc = 0
        for key, _, w in self._steps:
            if key == step_key:
                break
            acc += w
        return acc

    def _step(self, step_key: str) -> tuple[str, str, int]:
        for s in self._steps:
            if s[0] == step_key:
                return s
        raise KeyError(step_key)

    def start(self, step_key: str, detail: str = "") -> None:
        key, label, _ = self._step(step_key)
        base = self._completed_weight_before(key)
        self.state = ProgressState(
            step_key=key, step_label=label, detail=detail,
            percent=round(base / self._total_weight * 100),
        )
        self._emit()

    def advance_within(self, step_key: str, fraction: float,
                       detail: str = "") -> None:
        """ステップ内の進捗(0.0〜1.0)を反映する。長尺セグメント用。"""
        key, label, weight = self._step(step_key)
        base = self._completed_weight_before(key)
        pct = (base + weight * max(0.0, min(1.0, fraction))) / self._total_weight * 100
        self.state = ProgressState(
            step_key=key, step_label=label, detail=detail, percent=round(pct),
        )
        self._emit()

    def complete(self, step_key: str) -> None:
        key, label, weight = self._step(step_key)
        base = self._completed_weight_before(key) + weight
        self.state = ProgressState(
            step_key=key, step_label=label,
            percent=round(base / self._total_weight * 100),
        )
        self._emit()

    def finish(self) -> None:
        self.state = ProgressState(
            step_key="done", step_label="完了", percent=100, done=True,
        )
        self._emit()

    def fail(self, step_key: str, message: str) -> None:
        self.state.step_key = step_key
        self.state.error = message
        self._emit()

    def _emit(self) -> None:
        if self.on_update:
            self.on_update(self.state)
