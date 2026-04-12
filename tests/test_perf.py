"""perf モジュールのユニットテスト。"""

import pytest

import nova_parser.perf as perf_mod


@pytest.fixture(autouse=True)
def reset_global_tracker():
    perf_mod.tracker.reset()
    yield
    perf_mod.tracker.reset()


def test_timer_records_success_error_and_wait():
    tracker = perf_mod.PerfTracker()

    tracker.record("DocAI OCR", "file-1", 1.5)
    tracker.record("Gemini JSON", "file-1", 3.0, outcome="error")
    tracker.record_wait("file-1", 30.0)

    assert tracker.format_file_summary("file-1") == (
        "DocAI OCR 実 1.5s / 成功 1.5s (1回, 0失敗), "
        "Gemini JSON 実 3.0s / 成功 0.0s (1回, 1失敗), "
        "retry wait 30.0s, 実計 34.5s, 成功計 1.5s"
    )


def test_start_run_resets_previous_events():
    tracker = perf_mod.PerfTracker()

    tracker.record("DocAI OCR", "file-1", 2.0)
    assert tracker.format_file_summary("file-1") is not None

    tracker.start_run()

    assert tracker.format_file_summary("file-1") is None


def test_timer_records_failure_event_and_latest_failure():
    tracker = perf_mod.PerfTracker()

    with pytest.raises(RuntimeError, match="boom"):
        with tracker.timer("Gemini JSON", "file-1"):
            raise RuntimeError("boom")

    failure = tracker.latest_failure("file-1")
    assert failure is not None
    assert failure.step_name == "Gemini JSON"
    assert failure.kind == "step"
    assert failure.outcome == "error"
