"""Integration tests for Phase 2 sidecar (rules + tail-reader).

Tests cover:
  - All 6 event-based rules
  - Metric-based reward decline rule (slope + cooldown)
  - _read_new_lines incremental tail behaviour
  - notifier fallback path (no PowerShell spawn in tests)
"""
from __future__ import annotations

import json
import sys
import tempfile
from collections import deque
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.sidecar_rules import (
    Notification,
    SidecarContext,
    EVENT_RULES,
    rule_reward_decline,
    _ols_slope,
)
from utils.sidecar import _read_new_lines


# ── helpers ───────────────────────────────────────────────────────────────────

def _ctx(scenario_id: str = "sim_test") -> SidecarContext:
    return SidecarContext(scenario_id=scenario_id)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# ── _ols_slope ────────────────────────────────────────────────────────────────

def test_ols_slope_rising():
    assert _ols_slope([1.0, 2.0, 3.0, 4.0]) == pytest.approx(1.0)


def test_ols_slope_flat():
    assert _ols_slope([5.0, 5.0, 5.0]) == pytest.approx(0.0)


def test_ols_slope_short():
    assert _ols_slope([10.0]) == pytest.approx(0.0)


# ── rule_training_start ───────────────────────────────────────────────────────

def test_rule_training_start_basic():
    ctx = _ctx("sim_kundur")
    ev = {"type": "training_start", "total_episodes": 500, "mode": "simulink"}
    notif = EVENT_RULES["training_start"](ev, ctx)
    assert isinstance(notif, Notification)
    assert "sim_kundur" in notif.title
    assert "500" in notif.body
    assert "simulink" in notif.body


# ── rule_eval_improvement ─────────────────────────────────────────────────────

def test_rule_eval_first_eval_always_notifies():
    ctx = _ctx()
    ev = {"type": "eval", "episode": 50, "eval_reward": -20000.0}
    notif = EVENT_RULES["eval"](ev, ctx)
    assert notif is not None
    assert "首次" in notif.title
    assert ctx.last_eval_reward == pytest.approx(-20000.0)


def test_rule_eval_improvement_above_threshold():
    ctx = _ctx()
    ctx.last_eval_reward = -20000.0
    ctx.last_eval_episode = 50
    ev = {"type": "eval", "episode": 100, "eval_reward": -18000.0}  # 10% improvement
    notif = EVENT_RULES["eval"](ev, ctx)
    assert notif is not None
    assert "→" in notif.body
    assert ctx.last_eval_reward == pytest.approx(-18000.0)


def test_rule_eval_improvement_below_threshold_no_notify():
    ctx = _ctx()
    ctx.last_eval_reward = -20000.0
    ctx.last_eval_episode = 50
    ev = {"type": "eval", "episode": 100, "eval_reward": -19500.0}  # 2.5% — below 5%
    notif = EVENT_RULES["eval"](ev, ctx)
    assert notif is None


def test_rule_eval_missing_field_returns_none():
    ctx = _ctx()
    ev = {"type": "eval", "episode": 50}  # no eval_reward key
    notif = EVENT_RULES["eval"](ev, ctx)
    assert notif is None


# ── rule_monitor_alert ────────────────────────────────────────────────────────

def test_rule_monitor_alert_fires():
    ctx = _ctx()
    ev = {"type": "monitor_alert", "episode": 42, "rule": "reward_diverging"}
    notif = EVENT_RULES["monitor_alert"](ev, ctx)
    assert notif is not None
    assert "42" in notif.title
    assert "reward_diverging" in notif.body


def test_rule_monitor_stop_also_dispatched():
    ctx = _ctx()
    ev = {"type": "monitor_stop", "episode": 99, "triggered_by": "monitor"}
    notif = EVENT_RULES["monitor_stop"](ev, ctx)
    assert notif is not None


# ── rule_checkpoint ───────────────────────────────────────────────────────────

def test_rule_checkpoint_fires():
    ctx = _ctx()
    ev = {"type": "checkpoint", "episode": 100, "file": "ep100.pt"}
    notif = EVENT_RULES["checkpoint"](ev, ctx)
    assert notif is not None
    assert "100" in notif.title
    assert "ep100.pt" in notif.body


# ── rule_training_end ─────────────────────────────────────────────────────────

def test_rule_training_end_pass():
    ctx = _ctx("sim_ne39")
    ev = {"type": "training_end", "episode": 500, "verdict": "PASS", "elapsed_min": 47.3}
    notif = EVENT_RULES["training_end"](ev, ctx)
    assert notif is not None
    assert "PASS" in notif.title
    assert "47.3 min" in notif.body
    assert "sim_ne39" in notif.body


def test_rule_training_end_fail_no_elapsed():
    ctx = _ctx()
    ev = {"type": "training_end", "episode": 200, "verdict": "FAIL"}
    notif = EVENT_RULES["training_end"](ev, ctx)
    assert notif is not None
    assert "FAIL" in notif.title


# ── rule_reward_decline ───────────────────────────────────────────────────────

def test_rule_reward_decline_fires_on_sustained_drop():
    ctx = _ctx()
    ctx.reward_window = deque(maxlen=30)
    # Feed 30 strongly declining rewards
    for i in range(30):
        notif = rule_reward_decline(i, -1000.0 - i * 100.0, ctx)
    # Last call should have fired
    assert notif is not None
    assert "持续下降" in notif.title


def test_rule_reward_decline_no_fire_on_rising():
    ctx = _ctx()
    ctx.reward_window = deque(maxlen=30)
    notif = None
    for i in range(30):
        notif = rule_reward_decline(i, -1000.0 + i * 50.0, ctx)  # improving
    assert notif is None


def test_rule_reward_decline_cooldown_prevents_repeat():
    ctx = _ctx()
    ctx.reward_window = deque(maxlen=30)
    fired = []
    for i in range(90):
        n = rule_reward_decline(i, -1000.0 - i * 100.0, ctx)
        if n is not None:
            fired.append(i)
    # 90 declining episodes: fires at ep 29 (window full), then again at ep 79 (29+50)
    assert len(fired) >= 2, f"Expected >= 2 notifications, got {len(fired)}: {fired}"
    assert fired[1] - fired[0] >= ctx.decline_cooldown_eps


def test_rule_reward_decline_needs_full_window_before_firing():
    ctx = _ctx()
    ctx.reward_window = deque(maxlen=30)
    # Only 29 data points — window not full yet
    notif = None
    for i in range(29):
        notif = rule_reward_decline(i, -1000.0 - i * 100.0, ctx)
    assert notif is None  # 29 < maxlen=30, should not fire


# ── _read_new_lines (incremental tail) ───────────────────────────────────────

def test_read_new_lines_reads_all_from_empty():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "metrics.jsonl"
        _write_jsonl(path, [{"episode": 0, "reward": -1000.0}])
        records, offset = _read_new_lines(path, 0)
        assert len(records) == 1
        assert records[0]["episode"] == 0
        assert offset == path.stat().st_size


def test_read_new_lines_incremental():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "metrics.jsonl"
        _write_jsonl(path, [{"episode": 0, "reward": -1000.0}])
        _, offset = _read_new_lines(path, 0)

        _write_jsonl(path, [{"episode": 1, "reward": -900.0}])
        records, offset2 = _read_new_lines(path, offset)
        assert len(records) == 1
        assert records[0]["episode"] == 1


def test_read_new_lines_missing_file_returns_empty():
    records, offset = _read_new_lines(Path("/nonexistent/metrics.jsonl"), 0)
    assert records == []
    assert offset == 0


def test_read_new_lines_skips_malformed_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        path.write_text('{"episode": 0, "type": "ok"}\n{bad json\n', encoding="utf-8")
        records, _ = _read_new_lines(path, 0)
        assert len(records) == 1
        assert records[0]["type"] == "ok"


def test_read_new_lines_partial_write_not_consumed():
    """Partial line (no trailing newline) must not advance offset.

    Simulates the writer flushing an incomplete JSON object mid-episode.
    The sidecar should hold its offset and pick up the complete line on
    the next poll, after the writer finishes and appends the newline.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "metrics.jsonl"

        # First: write one complete line
        path.write_bytes(b'{"episode": 0, "reward": -1000.0}\n')
        records, offset = _read_new_lines(path, 0)
        assert len(records) == 1
        assert records[0]["episode"] == 0

        # Second: append a partial line (no closing newline — mid-write state)
        with path.open("ab") as f:
            f.write(b'{"episode": 1, "reward": -90')   # truncated, no "\n"
        records2, offset2 = _read_new_lines(path, offset)
        assert records2 == []           # must NOT return partial record
        assert offset2 == offset        # must NOT advance offset

        # Third: complete the line
        with path.open("ab") as f:
            f.write(b'0.0}\n')
        records3, offset3 = _read_new_lines(path, offset2)
        assert len(records3) == 1       # now picks it up
        assert records3[0]["episode"] == 1
        assert offset3 > offset2


# ── notifier fallback (no PowerShell in CI) ───────────────────────────────────

def test_notifier_fallback_prints_to_stderr(capsys):
    from utils.notifier import _console_fallback
    _console_fallback("Test Title", "Test Body")
    captured = capsys.readouterr()
    assert "Test Title" in captured.err
    assert "Test Body" in captured.err


def test_notifier_non_windows_uses_fallback(monkeypatch, capsys):
    import utils.notifier as notifier_mod
    monkeypatch.setattr(notifier_mod.sys, "platform", "linux")
    notifier_mod.notify("Hello", "World")
    captured = capsys.readouterr()
    assert "Hello" in captured.err


# ── full-chain synthetic integration test ────────────────────────────────────

def test_full_chain_synthetic_3_episodes(tmp_path, monkeypatch, capsys):
    """Write 3 synthetic episodes + 2 events; verify rules fire correctly."""
    import utils.notifier as notifier_mod
    monkeypatch.setattr(notifier_mod.sys, "platform", "linux")  # suppress PowerShell

    metrics_path = tmp_path / "metrics.jsonl"
    events_path = tmp_path / "events.jsonl"

    # Write training_start event
    _write_jsonl(events_path, [
        {"episode": 0, "ts": "t0", "type": "training_start",
         "total_episodes": 3, "mode": "standalone"},
    ])
    # Write 3 episode metrics
    _write_jsonl(metrics_path, [
        {"episode": 0, "ts": "t1", "reward": -5000.0, "alpha": 0.3},
        {"episode": 1, "ts": "t2", "reward": -4500.0, "alpha": 0.28},
        {"episode": 2, "ts": "t3", "reward": -4000.0, "alpha": 0.26},
    ])
    # Write eval + training_end events
    _write_jsonl(events_path, [
        {"episode": 2, "ts": "t4", "type": "eval", "eval_reward": -4000.0},
        {"episode": 2, "ts": "t5", "type": "training_end",
         "verdict": "MARGINAL", "elapsed_min": 0.5},
    ])

    ctx = SidecarContext(scenario_id="sim_test")

    # Replay events
    notifications = []
    for ev in [
        {"episode": 0, "type": "training_start", "total_episodes": 3, "mode": "standalone"},
        {"episode": 2, "type": "eval", "eval_reward": -4000.0},
        {"episode": 2, "type": "training_end", "verdict": "MARGINAL", "elapsed_min": 0.5},
    ]:
        fn = EVENT_RULES.get(ev["type"])
        if fn:
            n = fn(ev, ctx)
            if n:
                notifications.append(n)

    titles = [n.title for n in notifications]
    assert any("训练开始" in t for t in titles)
    assert any("首次 Eval" in t or "Eval" in t for t in titles)
    assert any("MARGINAL" in t for t in titles)
