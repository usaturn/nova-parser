"""パフォーマンス計測モジュール。"""

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass

RETRY_WAIT_STEP = "retry wait"


@dataclass
class TimingEvent:
    """1 ステップ/待機の計測結果。"""

    step_name: str
    file_key: str
    elapsed: float
    kind: str
    outcome: str


class PerfTracker:
    """スレッドセーフなパフォーマンス計測コレクター。"""

    def __init__(self):
        self._events: list[TimingEvent] = []
        self._lock = threading.Lock()
        self._run_start: float | None = None

    def start_run(self):
        """run 単位の計測を開始する。"""
        with self._lock:
            self._events.clear()
            self._run_start = time.perf_counter()

    def reset(self):
        """全状態をクリアする（テスト用）。"""
        with self._lock:
            self._events.clear()
            self._run_start = None

    def event_count(self) -> int:
        """現在までに記録されたイベント数を返す。"""
        with self._lock:
            return len(self._events)

    def record(
        self,
        step_name: str,
        file_key: str,
        elapsed: float,
        *,
        outcome: str = "success",
    ):
        """ステップの計測結果を記録する。"""
        self._record_event(
            TimingEvent(
                step_name=step_name,
                file_key=file_key,
                elapsed=elapsed,
                kind="step",
                outcome=outcome,
            )
        )

    def record_wait(self, file_key: str, elapsed: float, *, reason: str = RETRY_WAIT_STEP):
        """待機時間を記録する。"""
        self._record_event(
            TimingEvent(
                step_name=reason,
                file_key=file_key,
                elapsed=elapsed,
                kind="wait",
                outcome="wait",
            )
        )

    def latest_failure(self, file_key: str, *, since_index: int = 0) -> TimingEvent | None:
        """指定範囲内の直近失敗イベントを返す。"""
        with self._lock:
            for event in reversed(self._events[since_index:]):
                if event.file_key == file_key and event.kind == "step" and event.outcome == "error":
                    return event
        return None

    @contextmanager
    def timer(self, step_name: str, file_key: str):
        """API 呼び出しの所要時間を計測するコンテキストマネージャ。"""
        start = time.perf_counter()
        try:
            yield
        except Exception:
            self.record(step_name, file_key, time.perf_counter() - start, outcome="error")
            raise
        else:
            self.record(step_name, file_key, time.perf_counter() - start)

    def format_file_summary(self, file_key: str) -> str | None:
        """ファイル単位の計測サマリー文字列を返す。"""
        with self._lock:
            entries = [event for event in self._events if event.file_key == file_key]

        if not entries:
            return None

        parts, _, _ = _format_summary_parts(entries)
        return ", ".join(parts)

    def print_summary(self):
        """ステップ別の統計と総経過時間を表示する。"""
        with self._lock:
            events = list(self._events)
            run_start = self._run_start

        if not events:
            return

        print("\n--- パフォーマンスサマリー ---")

        step_names = dict.fromkeys(event.step_name for event in events if event.kind == "step")
        for step in step_names:
            values = [event for event in events if event.kind == "step" and event.step_name == step]
            real_total = sum(event.elapsed for event in values)
            success_values = [event.elapsed for event in values if event.outcome == "success"]
            success_total = sum(success_values)
            attempts = len(values)
            failures = sum(1 for event in values if event.outcome == "error")
            real_avg = real_total / attempts
            success_avg = success_total / len(success_values) if success_values else 0.0
            print(
                f"  {step}: 実 合計 {real_total:.1f}s / 平均 {real_avg:.1f}s, "
                f"成功 合計 {success_total:.1f}s / 平均 {success_avg:.1f}s, "
                f"試行 {attempts}回, 失敗 {failures}回"
            )

        wait_values = [event.elapsed for event in events if event.kind == "wait"]
        if wait_values:
            wait_total = sum(wait_values)
            wait_avg = wait_total / len(wait_values)
            print(f"  {RETRY_WAIT_STEP}: 合計 {wait_total:.1f}s / 平均 {wait_avg:.1f}s ({len(wait_values)} 回)")

        _, total_real, total_success = _format_summary_parts(events)
        print(f"  計測内訳 実計: {total_real:.1f}s")
        print(f"  計測内訳 成功計: {total_success:.1f}s")
        if run_start is not None:
            print(f"  総経過時間: {time.perf_counter() - run_start:.1f}s")

    def _record_event(self, event: TimingEvent):
        with self._lock:
            self._events.append(event)


def _format_summary_parts(events: list[TimingEvent]) -> tuple[list[str], float, float]:
    parts: list[str] = []
    total_real = 0.0
    total_success = 0.0

    step_names = dict.fromkeys(event.step_name for event in events if event.kind == "step")
    for step in step_names:
        values = [event for event in events if event.kind == "step" and event.step_name == step]
        real_total = sum(event.elapsed for event in values)
        success_total = sum(event.elapsed for event in values if event.outcome == "success")
        attempts = len(values)
        failures = sum(1 for event in values if event.outcome == "error")
        total_real += real_total
        total_success += success_total
        parts.append(f"{step} 実 {real_total:.1f}s / 成功 {success_total:.1f}s ({attempts}回, {failures}失敗)")

    wait_total = sum(event.elapsed for event in events if event.kind == "wait")
    if wait_total:
        parts.append(f"{RETRY_WAIT_STEP} {wait_total:.1f}s")
        total_real += wait_total

    parts.append(f"実計 {total_real:.1f}s")
    parts.append(f"成功計 {total_success:.1f}s")
    return parts, total_real, total_success


tracker = PerfTracker()
