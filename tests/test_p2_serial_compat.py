"""M1 anchor: workers=1 produces the same serial flow as pre-γ.

Tests verify:
- Default construction gives workers=1 (serial semantics).
- workers=1 path does NOT enter _run_parallel (no subprocess spawned).
- dispatch_subset field is preserved independently.

No MATLAB is invoked. All tests are pure-Python construction checks.
"""
from __future__ import annotations

import pytest
from probes.kundur.probe_state.probe_state import ModelStateProbe


def test_workers_1_default_is_serial():
    """Default ModelStateProbe has workers=1 (serial mode)."""
    p = ModelStateProbe(workers=1)
    assert p.workers == 1


def test_workers_1_explicit():
    """Explicitly set workers=1 with no dispatch_subset."""
    p = ModelStateProbe(workers=1, dispatch_subset=None)
    assert p.workers == 1
    assert p.dispatch_subset is None


def test_workers_1_with_subset():
    """workers=1 with a dispatch_subset string stored correctly."""
    p = ModelStateProbe(workers=1, dispatch_subset="pm_step_proxy_g1")
    assert p.workers == 1
    assert p.dispatch_subset == "pm_step_proxy_g1"


def test_workers_1_snapshot_config_records_workers():
    """snapshot.config.workers mirrors the constructor arg."""
    p = ModelStateProbe(workers=1)
    assert p.snapshot["config"]["workers"] == 1


def test_workers_1_snapshot_config_records_dispatch_subset_none():
    """snapshot.config.dispatch_subset is None when not set."""
    p = ModelStateProbe(workers=1, dispatch_subset=None)
    assert p.snapshot["config"]["dispatch_subset"] is None


def test_workers_1_snapshot_config_records_dispatch_subset_string():
    """snapshot.config.dispatch_subset records raw string spec."""
    p = ModelStateProbe(workers=1, dispatch_subset="pm_step_proxy_g1")
    # dispatch_subset is stored as a string (raw CLI spec) in config.
    assert p.snapshot["config"]["dispatch_subset"] == "pm_step_proxy_g1"


def test_workers_default_is_1():
    """ModelStateProbe() with no args defaults workers=1."""
    p = ModelStateProbe()
    assert p.workers == 1


def test_workers_2_stored():
    """workers=2 is stored (γ path is entered at runtime, not construction)."""
    p = ModelStateProbe(workers=2)
    assert p.workers == 2
    assert p.snapshot["config"]["workers"] == 2


def test_serial_does_not_invoke_run_parallel(monkeypatch):
    """workers=1 run() does NOT call _run_parallel (M1 anchor)."""
    parallel_called = []

    def fake_run_parallel(self, phases, wall_t0):
        parallel_called.append(True)
        return self.snapshot

    monkeypatch.setattr(ModelStateProbe, "_run_parallel", fake_run_parallel)

    # Stub _run_phase so no MATLAB is called and snapshot stays dict-typed.
    def fake_run_phase(self, key, fn, *args, **kwargs):
        self.snapshot[key] = {"stub": True}

    monkeypatch.setattr(ModelStateProbe, "_run_phase", fake_run_phase)

    # Stub _report.write so we don't need to render real gate dicts.
    import probes.kundur.probe_state._report as _report_mod
    monkeypatch.setattr(
        _report_mod, "write", lambda snap, output_dir: {"json": "stub.json", "md": "stub.md"}
    )

    p = ModelStateProbe(workers=1)
    p.run(phases=(1,))

    assert not parallel_called, (
        "_run_parallel was called despite workers=1 — M1 serial path broken"
    )


def test_parallel_does_invoke_run_parallel(monkeypatch):
    """workers=2 run() DOES call _run_parallel (γ path wired correctly)."""
    parallel_called = []

    def fake_run_parallel(self, phases, wall_t0):
        parallel_called.append(True)
        return self.snapshot

    monkeypatch.setattr(ModelStateProbe, "_run_parallel", fake_run_parallel)

    # Stub _ensure_build_current so no MATLAB is needed.
    monkeypatch.setattr(ModelStateProbe, "_ensure_build_current", lambda self: None)

    # Stub _run_phase for phase 1 (runs in parent for parallel mode).
    def fake_run_phase(self, key, fn, *args, **kwargs):
        self.snapshot[key] = {"stub": True}

    monkeypatch.setattr(ModelStateProbe, "_run_phase", fake_run_phase)

    p = ModelStateProbe(workers=2)
    p.run(phases=(1, 4))

    assert parallel_called, (
        "_run_parallel was NOT called despite workers=2 — γ parallel branch not entered"
    )
