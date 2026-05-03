"""Tests for probes.kundur.probe_state._gate_eval.evaluate_gates.

Covers:
  1. PASS path with real P2 harness snapshots (skipped if files absent).
  2. FAIL path with synthetic data (dispatch delta above tolerance).
  3. Schema mismatch raises ValueError.
  4. Missing wall data yields gate_wall.verdict == 'INFO', overall may still PASS.
  5. Verdict drift in G15 (G3 prev=PASS -> curr=REJECT).
  6. CLI exit codes via subprocess.
  7. Missing file raises FileNotFoundError.

No MATLAB engine required — pure Python.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from probes.kundur.probe_state._gate_eval import evaluate_gates

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent

_SERIAL_SNAP = (
    _REPO_ROOT
    / "results/harness/kundur/probe_state/p2_post_l2h1_serial/state_snapshot_latest.json"
)
_PARALLEL_SNAP = (
    _REPO_ROOT
    / "results/harness/kundur/probe_state/p2_post_l2h1_parallel/state_snapshot_latest.json"
)


def _minimal_snapshot(
    schema_version: int = 1,
    *,
    dispatches: dict | None = None,
    gate_overrides: dict | None = None,
    wall_s: float | None = None,
) -> dict:
    """Build a minimal valid snapshot dict for testing."""
    base_dispatches = dispatches if dispatches is not None else {}
    gates: dict = {
        "G1_signal": {"verdict": "PASS"},
        "G2_measurement": {"verdict": "PASS"},
        "G3_gradient": {"verdict": "PASS"},
        "G4_position": {"verdict": "REJECT"},
        "G5_trace": {"verdict": "PASS"},
    }
    if gate_overrides:
        for gid, fields in gate_overrides.items():
            gates[gid] = fields

    return {
        "schema_version": schema_version,
        "phase4_per_dispatch": {
            "wall_s": wall_s,
            "dispatches": base_dispatches,
        },
        "falsification_gates": gates,
    }


def _dispatch_entry(
    global_val: float = 0.1,
    per_agent: list[float] | None = None,
    responding: int = 4,
) -> dict:
    return {
        "max_abs_f_dev_hz_global": global_val,
        "max_abs_f_dev_hz_per_agent": per_agent if per_agent is not None else [global_val] * 4,
        "agents_responding_above_1mHz": responding,
    }


# ---------------------------------------------------------------------------
# §1 — PASS path with real P2 harness snapshots
# ---------------------------------------------------------------------------


class TestRealSnapshotPass:
    @pytest.mark.skipif(
        not (_SERIAL_SNAP.exists() and _PARALLEL_SNAP.exists()),
        reason="P2 harness snapshot files not present (gitignored); skipping",
    )
    def test_overall_verdict_pass(self) -> None:
        result = evaluate_gates(_SERIAL_SNAP, _PARALLEL_SNAP)
        assert result["overall_verdict"] == "PASS", (
            f"Expected PASS; got {result['overall_verdict']}. "
            f"gate_phys.failures={result['gate_phys']['failures']}, "
            f"gate_g15.drift={result['gate_g15']['drift']}"
        )

    @pytest.mark.skipif(
        not (_SERIAL_SNAP.exists() and _PARALLEL_SNAP.exists()),
        reason="P2 harness snapshot files not present (gitignored); skipping",
    )
    def test_gate_phys_all_15_dispatches_pass(self) -> None:
        result = evaluate_gates(_SERIAL_SNAP, _PARALLEL_SNAP)
        phys = result["gate_phys"]
        assert phys["n_passed"] == 15, (
            f"Expected 15 dispatches PASS; got n_passed={phys['n_passed']}, "
            f"n_total={phys['n_total']}, failures={phys['failures']}"
        )

    @pytest.mark.skipif(
        not (_SERIAL_SNAP.exists() and _PARALLEL_SNAP.exists()),
        reason="P2 harness snapshot files not present (gitignored); skipping",
    )
    def test_gate_phys_max_delta_is_zero(self) -> None:
        result = evaluate_gates(_SERIAL_SNAP, _PARALLEL_SNAP)
        assert result["gate_phys"]["max_delta"] == 0.0, (
            f"Expected max_delta==0.0; got {result['gate_phys']['max_delta']}"
        )

    @pytest.mark.skipif(
        not (_SERIAL_SNAP.exists() and _PARALLEL_SNAP.exists()),
        reason="P2 harness snapshot files not present (gitignored); skipping",
    )
    def test_gate_g15_pass(self) -> None:
        result = evaluate_gates(_SERIAL_SNAP, _PARALLEL_SNAP)
        assert result["gate_g15"]["verdict"] == "PASS", (
            f"gate_g15 drift: {result['gate_g15']['drift']}"
        )

    @pytest.mark.skipif(
        not (_SERIAL_SNAP.exists() and _PARALLEL_SNAP.exists()),
        reason="P2 harness snapshot files not present (gitignored); skipping",
    )
    def test_gate_wall_speedup_approx_3x(self) -> None:
        """Wall speedup should be in a reasonable range (>= 2.0x for parallel benefit)."""
        result = evaluate_gates(_SERIAL_SNAP, _PARALLEL_SNAP)
        gw = result["gate_wall"]
        if gw["speedup"] is None:
            pytest.skip("No wall data available in snapshots; skipping speedup check")
        # P2 expected ~3.18x; accept 2.0x-5.0x range to avoid fragility.
        assert 2.0 <= gw["speedup"] <= 5.0, (
            f"Speedup out of expected range: {gw['speedup']:.2f}x. "
            f"prev_wall={gw['prev_wall_s']:.1f}s, curr_wall={gw['curr_wall_s']:.1f}s"
        )


# ---------------------------------------------------------------------------
# §2 — FAIL path with synthetic data
# ---------------------------------------------------------------------------


class TestSyntheticFail:
    def test_single_dispatch_above_tolerance_fails(self, tmp_path: Path) -> None:
        """A dispatch differing by 1e-6 (> 1e-9 tol) causes FAIL."""
        prev_snap = _minimal_snapshot(
            dispatches={"bus14_loadstep": _dispatch_entry(global_val=0.1)}
        )
        curr_snap = _minimal_snapshot(
            dispatches={"bus14_loadstep": _dispatch_entry(global_val=0.1 + 1e-6)}
        )
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)

        assert result["overall_verdict"] == "FAIL"
        assert result["gate_phys"]["verdict"] == "FAIL"
        assert len(result["gate_phys"]["failures"]) >= 1
        assert any("bus14_loadstep" in f for f in result["gate_phys"]["failures"])

    def test_delta_exactly_at_tolerance_passes(self, tmp_path: Path) -> None:
        """Delta exactly at tol (1e-9) must PASS."""
        prev_snap = _minimal_snapshot(
            dispatches={"d1": _dispatch_entry(global_val=0.0)}
        )
        curr_snap = _minimal_snapshot(
            dispatches={"d1": _dispatch_entry(global_val=1e-9)}
        )
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)
        assert result["gate_phys"]["verdict"] == "PASS"

    def test_responding_count_mismatch_fails(self, tmp_path: Path) -> None:
        """agents_responding_above_1mHz mismatch (exact match required) must FAIL."""
        prev_snap = _minimal_snapshot(
            dispatches={"d1": _dispatch_entry(responding=4)}
        )
        curr_snap = _minimal_snapshot(
            dispatches={"d1": _dispatch_entry(responding=3)}
        )
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)
        assert result["gate_phys"]["verdict"] == "FAIL"
        assert any("d1" in f for f in result["gate_phys"]["failures"])

    def test_missing_dispatch_in_curr_fails(self, tmp_path: Path) -> None:
        """A dispatch present in prev but absent in curr must be reported as failure."""
        prev_snap = _minimal_snapshot(
            dispatches={
                "d1": _dispatch_entry(),
                "d2": _dispatch_entry(),
            }
        )
        curr_snap = _minimal_snapshot(
            dispatches={"d1": _dispatch_entry()}
        )
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)
        assert result["gate_phys"]["verdict"] == "FAIL"
        assert any("d2" in f for f in result["gate_phys"]["failures"])


# ---------------------------------------------------------------------------
# §3 — Schema mismatch raises ValueError
# ---------------------------------------------------------------------------


class TestSchemaMismatch:
    def test_schema_version_mismatch_raises(self, tmp_path: Path) -> None:
        prev_snap = _minimal_snapshot(schema_version=1)
        curr_snap = _minimal_snapshot(schema_version=2)
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        with pytest.raises(ValueError, match="schema_version mismatch"):
            evaluate_gates(prev_path, curr_path)

    def test_same_schema_version_does_not_raise(self, tmp_path: Path) -> None:
        prev_snap = _minimal_snapshot(schema_version=1)
        curr_snap = _minimal_snapshot(schema_version=1)
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)
        assert result["schema_version"] == 1


# ---------------------------------------------------------------------------
# §4 — Missing wall data yields gate_wall.verdict == 'INFO'
# ---------------------------------------------------------------------------


class TestMissingWallData:
    def test_no_wall_s_yields_info(self, tmp_path: Path) -> None:
        """Snapshots without wall_s produce INFO verdict; overall determined by PHYS+G15."""
        prev_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()}, wall_s=None)
        curr_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()}, wall_s=None)
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)

        assert result["gate_wall"]["verdict"] == "INFO"
        assert result["gate_wall"]["speedup"] is None
        assert "missing" in result["gate_wall"]["note"].lower()
        # WALL INFO does not block overall PASS when PHYS+G15 pass.
        assert result["overall_verdict"] == "PASS"

    def test_wall_data_present_computes_speedup(self, tmp_path: Path) -> None:
        """When wall_s is available, speedup is computed."""
        prev_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()}, wall_s=100.0)
        curr_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()}, wall_s=40.0)
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)

        gw = result["gate_wall"]
        assert gw["speedup"] == pytest.approx(100.0 / 40.0)
        assert gw["verdict"] == "PASS"  # 40/100 = 0.40 <= 0.55

    def test_wall_insufficient_speedup_is_fail(self, tmp_path: Path) -> None:
        """curr/prev > threshold_ratio -> FAIL verdict (informational)."""
        prev_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()}, wall_s=100.0)
        curr_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()}, wall_s=80.0)
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)

        gw = result["gate_wall"]
        # 80/100 = 0.80 > 0.55 -> FAIL on wall
        assert gw["verdict"] == "FAIL"
        # But overall_verdict is PASS because WALL doesn't block.
        assert result["overall_verdict"] == "PASS"


# ---------------------------------------------------------------------------
# §5 — Verdict drift in G15
# ---------------------------------------------------------------------------


class TestG15VerdictDrift:
    def test_g3_drift_causes_g15_fail(self, tmp_path: Path) -> None:
        """G3 prev=PASS, curr=REJECT -> gate_g15.verdict==FAIL, 'G3' in drift."""
        prev_snap = _minimal_snapshot(
            dispatches={"d1": _dispatch_entry()},
            gate_overrides={"G3_gradient": {"verdict": "PASS"}},
        )
        curr_snap = _minimal_snapshot(
            dispatches={"d1": _dispatch_entry()},
            gate_overrides={"G3_gradient": {"verdict": "REJECT"}},
        )
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)

        g15 = result["gate_g15"]
        assert g15["verdict"] == "FAIL"
        assert "G3_gradient" in g15["drift"]
        assert result["overall_verdict"] == "FAIL"

    def test_no_drift_all_match(self, tmp_path: Path) -> None:
        """Identical gate verdicts -> gate_g15.verdict==PASS, empty drift."""
        prev_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()})
        curr_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()})
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)

        assert result["gate_g15"]["verdict"] == "PASS"
        assert result["gate_g15"]["drift"] == []

    def test_all_five_gates_tracked(self, tmp_path: Path) -> None:
        """per_gate must have exactly G1..G5 entries (G6 excluded)."""
        prev_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()})
        curr_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()})
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        result = evaluate_gates(prev_path, curr_path)

        per_gate = result["gate_g15"]["per_gate"]
        assert set(per_gate.keys()) == {
            "G1_signal", "G2_measurement", "G3_gradient", "G4_position", "G5_trace"
        }
        assert "G6_trained_policy" not in per_gate


# ---------------------------------------------------------------------------
# §6 — CLI exit codes
# ---------------------------------------------------------------------------


class TestCLIExitCodes:
    def _write_pair(
        self, tmp_path: Path, fail: bool = False
    ) -> tuple[Path, Path]:
        """Write a matching pair (PASS) or a mismatched pair (FAIL)."""
        prev_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry(global_val=0.1)})
        if fail:
            curr_snap = _minimal_snapshot(
                dispatches={"d1": _dispatch_entry(global_val=0.1 + 1e-6)}
            )
        else:
            curr_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry(global_val=0.1)})
        prev_path = tmp_path / "prev.json"
        curr_path = tmp_path / "curr.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")
        return prev_path, curr_path

    def test_exit_code_0_on_pass(self, tmp_path: Path) -> None:
        prev, curr = self._write_pair(tmp_path, fail=False)
        proc = subprocess.run(
            [sys.executable, "-m", "probes.kundur.probe_state",
             "--gate-eval", str(prev), str(curr)],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert proc.returncode == 0, (
            f"Expected exit code 0 on PASS; got {proc.returncode}.\n"
            f"stdout: {proc.stdout[:500]}\nstderr: {proc.stderr[:200]}"
        )
        # Stdout must be valid JSON with overall_verdict PASS.
        out = json.loads(proc.stdout)
        assert out["overall_verdict"] == "PASS"

    def test_exit_code_1_on_fail(self, tmp_path: Path) -> None:
        prev, curr = self._write_pair(tmp_path, fail=True)
        proc = subprocess.run(
            [sys.executable, "-m", "probes.kundur.probe_state",
             "--gate-eval", str(prev), str(curr)],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert proc.returncode == 1, (
            f"Expected exit code 1 on FAIL; got {proc.returncode}.\n"
            f"stdout: {proc.stdout[:500]}\nstderr: {proc.stderr[:200]}"
        )
        out = json.loads(proc.stdout)
        assert out["overall_verdict"] == "FAIL"

    def test_gate_eval_tol_flag_overrides_tolerance(self, tmp_path: Path) -> None:
        """--gate-eval-tol 1e-3 should accept a delta of 1e-6 (PASS)."""
        prev, curr = self._write_pair(tmp_path, fail=True)  # delta = 1e-6
        proc = subprocess.run(
            [sys.executable, "-m", "probes.kundur.probe_state",
             "--gate-eval", str(prev), str(curr),
             "--gate-eval-tol", "1e-3"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert proc.returncode == 0, (
            f"Expected exit code 0 with tol=1e-3 for delta=1e-6; "
            f"got {proc.returncode}.\nstdout: {proc.stdout[:500]}"
        )


# ---------------------------------------------------------------------------
# §7 — Missing file raises FileNotFoundError
# ---------------------------------------------------------------------------


class TestMissingFile:
    def test_missing_prev_raises(self, tmp_path: Path) -> None:
        curr_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()})
        curr_path = tmp_path / "curr.json"
        curr_path.write_text(json.dumps(curr_snap), encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="not found"):
            evaluate_gates(tmp_path / "nonexistent_prev.json", curr_path)

    def test_missing_curr_raises(self, tmp_path: Path) -> None:
        prev_snap = _minimal_snapshot(dispatches={"d1": _dispatch_entry()})
        prev_path = tmp_path / "prev.json"
        prev_path.write_text(json.dumps(prev_snap), encoding="utf-8")

        with pytest.raises(FileNotFoundError, match="not found"):
            evaluate_gates(prev_path, tmp_path / "nonexistent_curr.json")

    def test_both_missing_raises_for_prev(self, tmp_path: Path) -> None:
        """FileNotFoundError is raised for prev path first."""
        with pytest.raises(FileNotFoundError):
            evaluate_gates(
                tmp_path / "no_prev.json",
                tmp_path / "no_curr.json",
            )
