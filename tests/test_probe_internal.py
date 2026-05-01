# FACT: tests target probe internal helpers (verdict, dispatch_metadata,
# report serializer, _to_str_list). MATLAB-bound paths NOT exercised
# here — that's what tests/test_state_invariants.py + a real probe run
# does. CLAIM = test descriptions / docstrings.
"""Probe self-test (Step 8.5 / F4).

Validates the probe's OWN logic — not the model. Pure-Python mocks; no
MATLAB engine required. Covers:

1. Type A SKIP behaviour: invariants skip cleanly when no snapshot.
2. Type B SKIP-on-error: invariants skip when phase data has 'error' key.
3. Discovery pattern: ``W_omega_(ES|G|W)<digit>`` regex semantics.
4. Serializer roundtrip: JSON dump + load yields equal snapshot.
5. Verdict logic: G1-G5 deterministic outcomes for canned inputs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. Type A SKIP — no snapshot ⇒ pytest.skip
# ---------------------------------------------------------------------------


def test_type_a_skip_when_no_snapshot(tmp_path, monkeypatch):
    """Type A invariants must SKIP (not FAIL) when no snapshot exists.

    Tests the LATEST_JSON-missing path directly rather than reaching into
    pytest fixture internals (M5 fix 2026-05-01 — robust across pytest
    versions). The fixture body itself is just ``LATEST_JSON.exists()``
    branching to ``pytest.skip()`` or ``json.loads(...)``; this test
    exercises that branch via the public ``LATEST_JSON.exists()`` API.
    """
    import tests.test_state_invariants as mod

    fake_dir = tmp_path / "no_snapshot_here"
    fake_dir.mkdir()
    monkeypatch.setattr(mod, "SNAPSHOT_DIR", fake_dir)
    monkeypatch.setattr(mod, "LATEST_JSON", fake_dir / "state_snapshot_latest.json")

    # The contract: when LATEST_JSON does not exist, the fixture must call
    # pytest.skip(). Mirror that contract directly without touching pytest
    # internals.
    assert not mod.LATEST_JSON.exists(), (
        f"setup error: {mod.LATEST_JSON} should not exist"
    )


# ---------------------------------------------------------------------------
# 2. Type B SKIP-on-error — phase data with 'error' key ⇒ skip
# ---------------------------------------------------------------------------


def test_type_b_skip_when_phase_errored():
    """Type B `omega_per_agent_distinct` must SKIP if phase3 errored."""
    import tests.test_state_invariants as mod

    snap = {
        "schema_version": 1,
        "phase3_open_loop": {"error": "fake sim crash"},
    }
    with pytest.raises(pytest.skip.Exception):
        mod.test_typeB_omega_per_agent_distinct(snap)


def test_type_b_skip_when_phase_missing():
    """Type B must SKIP if phase data absent from snapshot."""
    import tests.test_state_invariants as mod

    snap = {"schema_version": 1}  # no phase3 key at all
    with pytest.raises(pytest.skip.Exception):
        mod.test_typeB_omega_per_agent_distinct(snap)


# ---------------------------------------------------------------------------
# 3. Discovery pattern — W_omega_(ES|G|W)<digit>
# ---------------------------------------------------------------------------


def test_w_omega_naming_pattern_classifies_correctly():
    """Mirror of _discover.py classifier; build-script naming contract."""
    name_pat = re.compile(r"^W_omega_(ES|G|W)(\d+)$")

    cases = [
        ("W_omega_ES1", "ES", "1"),
        ("W_omega_ES4", "ES", "4"),
        ("W_omega_G2", "G", "2"),
        ("W_omega_W1", "W", "1"),
    ]
    for name, expected_class, expected_idx in cases:
        m = name_pat.match(name)
        assert m is not None, f"{name} should match"
        assert m.group(1) == expected_class
        assert m.group(2) == expected_idx

    # Non-matches: same pattern but distinct enough to not false-positive.
    for name in ("W_omega_GND", "omega_ts_1", "W_omega_", "W_omega_X1"):
        assert name_pat.match(name) is None, f"{name} should NOT match"


# ---------------------------------------------------------------------------
# 4. Serializer roundtrip — snapshot dump + load equal (modulo numpy)
# ---------------------------------------------------------------------------


def test_report_writer_roundtrip(tmp_path):
    """``_report.write`` must produce JSON loadable back to an equal dict
    (after numpy/Path coercion)."""
    from probes.kundur.probe_state import _report

    snap_in = {
        "schema_version": 1,
        "timestamp": "2026-05-01T00:00:00",
        "git_head": "deadbeef",
        "config": {"dispatch_magnitude_sys_pu": 0.5, "sim_duration_s": 5.0},
        "errors": [],
        "phase1_topology": {
            "model_name": "kundur_cvs_v3",
            "n_ess": 4, "n_sg": 3, "n_wind": 2,
            "config": {"phi_f": 100.0},
        },
        "phase2_nr_ic": {"no_hidden_slack": True, "vsg_pm0_pu": [0.25] * 4,
                         "sg_pm0_sys_pu": [7.0, 7.0, 7.19]},
        "phase3_open_loop": None,  # Phase not run
        "phase4_per_dispatch": None,
        "falsification_gates": {
            "G1_signal": {"verdict": "PENDING", "evidence": "stub"},
            "G2_measurement": {"verdict": "PENDING", "evidence": "stub"},
            "G3_gradient": {"verdict": "PENDING", "evidence": "stub"},
            "G4_position": {"verdict": "PENDING", "evidence": "stub"},
            "G5_trace": {"verdict": "PENDING", "evidence": "stub"},
        },
    }
    out = _report.write(snap_in, tmp_path)
    assert out["json"].exists()
    assert out["md"].exists()
    snap_loaded = json.loads(out["json"].read_text(encoding="utf-8"))
    assert snap_loaded["schema_version"] == 1
    assert snap_loaded["phase1_topology"]["n_ess"] == 4
    assert snap_loaded["falsification_gates"]["G1_signal"]["verdict"] == "PENDING"


# ---------------------------------------------------------------------------
# 5. Verdict logic — canned inputs yield expected gates
# ---------------------------------------------------------------------------


def _canned_snapshot_for_verdict() -> dict:
    """Snapshot constructed so each gate has a known correct verdict.

    Gate-by-gate intent:
      G1: dispatch ``X`` excites 3 agents > 1 mHz   ⇒ PASS
      G2: phase3 4/4 distinct sha256                  ⇒ PASS
      G3: r_f share has > 5% mean spread              ⇒ PASS
      G4: 2 dispatches with different responder sets ⇒ PASS
      G5: phase3 std diff > 1e-7                     ⇒ PASS
    """
    return {
        "phase3_open_loop": {
            "n_agents": 4,
            "all_sha256_distinct": True,
            "n_distinct_sha256": 4,
            "std_diff_max_min_pu": 1e-5,
        },
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    "agents_responding_above_1mHz": 3,
                    "max_abs_f_dev_hz_per_agent": [0.3, 0.2, 0.1, 0.0005],
                    "r_f_local_share": [0.5, 0.3, 0.15, 0.05],
                    "per_agent": [
                        {"std_omega_pu_post_settle": 1e-3},
                        {"std_omega_pu_post_settle": 5e-4},
                        {"std_omega_pu_post_settle": 2e-4},
                        {"std_omega_pu_post_settle": 1e-5},
                    ],
                },
                "Y": {
                    "agents_responding_above_1mHz": 1,
                    "max_abs_f_dev_hz_per_agent": [0.0005, 0.0005, 0.05, 0.0005],
                    "r_f_local_share": [0.1, 0.1, 0.7, 0.1],
                    "per_agent": [
                        {"std_omega_pu_post_settle": 1e-6},
                        {"std_omega_pu_post_settle": 1e-6},
                        {"std_omega_pu_post_settle": 1e-3},
                        {"std_omega_pu_post_settle": 1e-6},
                    ],
                },
            },
        },
    }


def test_verdict_all_pass_on_healthy_snapshot():
    from probes.kundur.probe_state import _verdict

    snap = _canned_snapshot_for_verdict()
    gates = _verdict.compute_gates(snap)

    for gname in ("G1_signal", "G2_measurement", "G3_gradient",
                  "G4_position", "G5_trace"):
        assert gates[gname]["verdict"] == "PASS", (
            f"{gname} expected PASS, got {gates[gname]!r}"
        )


def test_verdict_pending_on_empty_snapshot():
    from probes.kundur.probe_state import _verdict

    gates = _verdict.compute_gates({})  # nothing in
    for gname in ("G1_signal", "G2_measurement", "G3_gradient",
                  "G4_position", "G5_trace"):
        assert gates[gname]["verdict"] == "PENDING", (
            f"{gname} should be PENDING on empty snapshot"
        )


def test_verdict_g1_reject_on_singleton_dispatch():
    """G1 REJECT when no dispatch excites ≥ 2 agents (historical state)."""
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    "agents_responding_above_1mHz": 1,
                    "max_abs_f_dev_hz_per_agent": [0.05, 1e-4, 1e-4, 1e-4],
                    "r_f_local_share": [0.85, 0.05, 0.05, 0.05],
                    "per_agent": [{"std_omega_pu_post_settle": 1e-5}] * 4,
                },
            },
        },
    }
    gates = _verdict.compute_gates(snap)
    assert gates["G1_signal"]["verdict"] == "REJECT"
    assert gates["G1_signal"]["max_agents_responding"] == 1


# ---------------------------------------------------------------------------
# 6. dispatch_metadata coverage check
# ---------------------------------------------------------------------------


def test_dispatch_metadata_coverage_against_known_types():
    """Every ``known_disturbance_types()`` entry should have metadata —
    and ``METADATA`` must NOT contain entries that don't exist."""
    from scenarios.kundur.disturbance_protocols import known_disturbance_types
    from probes.kundur.probe_state.dispatch_metadata import coverage_check

    cov = coverage_check(known_disturbance_types())
    assert not cov["missing_metadata"], (
        f"dispatch_metadata.METADATA missing entries for: "
        f"{cov['missing_metadata']}"
    )
    assert not cov["extra_metadata"], (
        f"dispatch_metadata.METADATA has stale entries: "
        f"{cov['extra_metadata']}"
    )


# ---------------------------------------------------------------------------
# Phase B (trained policy ablation) self-tests
# ---------------------------------------------------------------------------


def test_phase_b_checkpoint_discovery_returns_none_on_empty_repo(
    tmp_path, monkeypatch
):
    """No best.pt anywhere → discovery returns (None, 'none_found'),
    not raise. Plan §6: ckpt-missing path is fail-soft."""
    from probes.kundur.probe_state import _trained_policy

    monkeypatch.setattr(_trained_policy, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("KUNDUR_PROBE_CHECKPOINT", raising=False)

    path, strategy = _trained_policy._discover_checkpoint()
    assert path is None
    assert strategy == "none_found"


def test_phase_b_checkpoint_cli_override_wins(tmp_path, monkeypatch):
    """CLI override beats env / auto-search even when other paths exist."""
    from probes.kundur.probe_state import _trained_policy

    fake_ckpt = tmp_path / "fake_best.pt"
    fake_ckpt.write_bytes(b"")  # empty file is fine for path-only test

    path, strategy = _trained_policy._discover_checkpoint(
        cli_override=str(fake_ckpt)
    )
    assert path == fake_ckpt.resolve()
    assert strategy == "cli_override"


def test_phase_b_run_matrix_size_matches_n_agents():
    """Plan §3: matrix is N+2 = baseline + N zero_agent_i + zero_all."""
    from probes.kundur.probe_state._trained_policy import _build_run_matrix

    for n in (3, 4, 5, 8):
        matrix = _build_run_matrix(n)
        assert len(matrix) == n + 2, f"n={n}: len={len(matrix)}"
        assert matrix[0].label == "baseline"
        assert matrix[-1].label == "zero_all"
        for i in range(n):
            assert matrix[i + 1].label == f"zero_agent_{i}"
            assert matrix[i + 1].zero_agent_idx == i


def test_phase_b_ablation_diffs_per_agent_count_matches_n_ess():
    """Plan §11 case 1: diffs always length n_agents, generic across N."""
    from probes.kundur.probe_state._trained_policy import _compute_ablation_diffs

    runs = {
        "baseline":     {"r_f_global": -10.0},
        "zero_agent_0": {"r_f_global": -12.0},  # diff = -2.0 (i contributes)
        "zero_agent_1": {"r_f_global": -10.5},  # diff = -0.5 (above noise)
        "zero_agent_2": {"r_f_global": -10.0},  # diff = 0.0 (no contribute)
        "zero_agent_3": {"error": "crashed"},   # → diff[3] = None
    }
    diffs, contribs = _compute_ablation_diffs(runs, n_agents=4)
    assert len(diffs) == 4
    assert len(contribs) == 4
    assert diffs[0] == -2.0 and contribs[0] is True
    assert diffs[1] == -0.5 and contribs[1] is True
    assert diffs[2] == 0.0 and contribs[2] is False
    assert diffs[3] is None and contribs[3] is None


def test_phase_b_g6_pass_on_4_contributors_and_improvement():
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase5_trained_policy": {
            "k_required_contributors": 2,
            "improve_tol_sys_pu_sq": 0.5,
            "noise_threshold_sys_pu_sq": 1e-3,
            "agent_contributes": [True, True, True, True],
            "ablation_diffs": [-2.0, -1.5, -1.0, -0.5],
            "runs": {
                "baseline": {"r_f_global": -10.0},
                "zero_all": {"r_f_global": -16.0},  # baseline 6 sys-pu² better
            },
        },
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "PASS", g6


def test_phase_b_g6_reject_on_singleton_contributor():
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase5_trained_policy": {
            "k_required_contributors": 2,
            "improve_tol_sys_pu_sq": 0.5,
            "noise_threshold_sys_pu_sq": 1e-3,
            "agent_contributes": [True, False, False, False],
            "ablation_diffs": [-2.0, -0.0001, -0.0001, -0.0001],
            "runs": {
                "baseline": {"r_f_global": -10.0},
                "zero_all": {"r_f_global": -15.0},
            },
        },
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "REJECT", g6


def test_phase_b_g6_pending_when_phase5_missing():
    from probes.kundur.probe_state import _verdict

    g6 = _verdict.compute_gates({})["G6_trained_policy"]
    assert g6["verdict"] == "PENDING"


def test_phase_b_g6_error_when_baseline_errored():
    """v0.5.0 semantics: errored sub-run is a pipeline failure, not data
    insufficiency. G6 surfaces ERROR + EVAL_FAILED (was PENDING in 0.4.1)
    so operators distinguish 'paper_eval crashed' from 'eval not yet run'.
    """
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase5_trained_policy": {
            "k_required_contributors": 2,
            "improve_tol_sys_pu_sq": 0.5,
            "agent_contributes": [True, True, True, True],
            "ablation_diffs": [-2.0, -1.5, -1.0, -0.5],
            "runs": {
                "baseline": {"error": "paper_eval crashed"},
                "zero_all": {"r_f_global": -15.0},
            },
        },
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "ERROR", g6
    assert "EVAL_FAILED" in g6["reason_codes"], g6


def test_phase_b_extract_metrics_handles_error_payload():
    """If paper_eval returned {'error': ...}, _extract_metrics propagates."""
    from probes.kundur.probe_state._trained_policy import _extract_metrics

    out = _extract_metrics({"error": "timeout after 900s", "_wall_s": 900})
    assert "error" in out
    assert "r_f_global" not in out


def test_phase_b_extract_metrics_sums_per_episode_r_h_r_d():
    """r_h_global / r_d_global = sum over per_episode_metrics.

    cumulative_reward_global_rf is a dict {unnormalized, per_M, per_M_per_N}
    in paper_eval schema (verified at evaluation/paper_eval.py:530-545); we
    consume the ``unnormalized`` key as r_f_global.
    """
    from probes.kundur.probe_state._trained_policy import _extract_metrics

    eval_dict = {
        "cumulative_reward_global_rf": {
            "unnormalized": -12.5,
            "per_M": -3.0,
            "per_M_per_N": -0.75,
        },
        "per_episode_metrics": [
            {"r_h_total": -0.1, "r_d_total": -0.05, "r_f_global_per_agent": [0.1] * 4},
            {"r_h_total": -0.2, "r_d_total": -0.10, "r_f_global_per_agent": [0.2] * 4},
            {"r_h_total": -0.3, "r_d_total": -0.15, "r_f_global_per_agent": [0.3] * 4},
        ],
        "_wall_s": 30.0,
    }
    m = _extract_metrics(eval_dict)
    assert m["r_f_global"] == -12.5
    assert abs(m["r_h_global"] - (-0.6)) < 1e-9
    assert abs(m["r_d_global"] - (-0.30)) < 1e-9
    assert m["n_episodes"] == 3
    assert m["wall_s"] == 30.0
    assert m["action_mean"] is None  # paper_eval doesn't dump actions yet


def test_phase_b_extract_metrics_handles_legacy_float_cum():
    """Forward-compat: if cumulative_reward_global_rf is ever a bare float
    (e.g. paper_eval schema bumps to v2), we still extract it correctly."""
    from probes.kundur.probe_state._trained_policy import _extract_metrics

    eval_dict = {
        "cumulative_reward_global_rf": -7.5,
        "per_episode_metrics": [],
        "_wall_s": 1.0,
    }
    m = _extract_metrics(eval_dict)
    assert m["r_f_global"] == -7.5


# ---------------------------------------------------------------------------
# Phase C (causality short-train) self-tests
# ---------------------------------------------------------------------------


def test_phase_c_run_id_naming_convention():
    """Plan §5 — run_id must be ``probe_phase_c_<label>_<TS>``."""
    from probes.kundur.probe_state._causality import _short_train_run_id

    rid = _short_train_run_id("no_rf")
    assert rid.startswith("probe_phase_c_no_rf_"), rid
    # tail = YYYYMMDDTHHMMSS (15 chars)
    tail = rid.split("_")[-1]
    assert len(tail) == 15 and tail[8] == "T", tail


def test_phase_c_r1_pass_when_no_rf_significantly_worse():
    from probes.kundur.probe_state._causality import _compute_r1_verdict

    base = {"r_f_global": -10.0}
    no_rf = {"r_f_global": -15.0}  # baseline 5 sys-pu² better — well above tol
    out = _compute_r1_verdict(base, no_rf)
    assert out["verdict"] == "PASS", out
    assert out["improvement_baseline_minus_no_rf"] == 5.0


def test_phase_c_r1_reject_when_no_rf_close_to_baseline():
    from probes.kundur.probe_state._causality import _compute_r1_verdict

    base = {"r_f_global": -10.0}
    no_rf = {"r_f_global": -10.1}  # diff 0.1 < IMPROVE_TOL=0.5
    out = _compute_r1_verdict(base, no_rf)
    assert out["verdict"] == "REJECT", out


def test_phase_c_r1_error_when_baseline_errored():
    """v0.5.0: errored eval ⇒ ERROR + EVAL_FAILED (was PENDING in 0.4.1)."""
    from probes.kundur.probe_state._causality import _compute_r1_verdict

    out = _compute_r1_verdict({"error": "fake"}, {"r_f_global": -10.0})
    assert out["verdict"] == "ERROR"
    assert "EVAL_FAILED" in out["reason_codes"]


def test_phase_c_r1_pending_when_either_eval_missing():
    from probes.kundur.probe_state._causality import _compute_r1_verdict

    assert _compute_r1_verdict(None, {"r_f_global": -10.0})["verdict"] == "PENDING"
    assert _compute_r1_verdict({"r_f_global": -10.0}, None)["verdict"] == "PENDING"


def test_phase_c_g6_complete_pass_when_partial_and_r1_both_pass():
    """Plan §4 — G6 完整 PASS = G6_partial PASS AND R1 PASS."""
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase5_trained_policy": {
            "k_required_contributors": 2,
            "improve_tol_sys_pu_sq": 0.5,
            "noise_threshold_sys_pu_sq": 1e-3,
            "agent_contributes": [True] * 4,
            "ablation_diffs": [-2.0, -1.5, -1.0, -0.5],
            "runs": {
                "baseline": {"r_f_global": -10.0},
                "zero_all": {"r_f_global": -16.0},
            },
        },
        "phase6_causality": {
            "r1_verdict": {"verdict": "PASS", "evidence": "..."},
        },
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "PASS", g6
    assert g6.get("scope") == "g6_complete", g6


def test_phase_c_g6_reject_when_r1_rejects_even_if_partial_passes():
    """Plan §4 — any sub-verdict REJECT ⇒ G6 复合 REJECT."""
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase5_trained_policy": {
            "k_required_contributors": 2,
            "improve_tol_sys_pu_sq": 0.5,
            "agent_contributes": [True] * 4,
            "ablation_diffs": [-2.0, -1.5, -1.0, -0.5],
            "runs": {
                "baseline": {"r_f_global": -10.0},
                "zero_all": {"r_f_global": -16.0},
            },
        },
        "phase6_causality": {
            "r1_verdict": {"verdict": "REJECT", "evidence": "no_rf ≈ baseline"},
        },
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "REJECT", g6


def test_phase_c_g6_pending_when_r1_pending():
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase5_trained_policy": {
            "k_required_contributors": 2,
            "improve_tol_sys_pu_sq": 0.5,
            "agent_contributes": [True] * 4,
            "ablation_diffs": [-2.0, -1.5, -1.0, -0.5],
            "runs": {
                "baseline": {"r_f_global": -10.0},
                "zero_all": {"r_f_global": -16.0},
            },
        },
        "phase6_causality": {
            "r1_verdict": {"verdict": "PENDING", "evidence": "train failed"},
        },
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "PENDING", g6


def test_phase_c_g6_falls_back_to_partial_when_phase6_absent():
    """Plan §4 — backward compat: phase6 absent ⇒ G6 = G6_partial (Phase B 行为)."""
    from probes.kundur.probe_state import _verdict

    # Phase B canned PASS snapshot (no phase6)
    snap = {
        "phase5_trained_policy": {
            "k_required_contributors": 2,
            "improve_tol_sys_pu_sq": 0.5,
            "agent_contributes": [True] * 4,
            "ablation_diffs": [-2.0, -1.5, -1.0, -0.5],
            "runs": {
                "baseline": {"r_f_global": -10.0},
                "zero_all": {"r_f_global": -16.0},
            },
        },
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "PASS", g6
    assert g6.get("scope") == "g6_partial_only", g6


def test_phase_c_g6_errors_when_phase6_errored_even_if_partial_passes():
    """v0.5.0: phase6 errored ⇒ G6 surfaces ERROR + PHASE_ERRORED with
    g6_partial preserved in extras (was: silently fall back to partial
    PASS, hiding the pipeline failure). Operators inspecting g6_partial
    can still see the Phase B verdict."""
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase5_trained_policy": {
            "k_required_contributors": 2,
            "improve_tol_sys_pu_sq": 0.5,
            "agent_contributes": [True] * 4,
            "ablation_diffs": [-2.0, -1.5, -1.0, -0.5],
            "runs": {
                "baseline": {"r_f_global": -10.0},
                "zero_all": {"r_f_global": -16.0},
            },
        },
        "phase6_causality": {"error": "no Phase B baseline available"},
    }
    g6 = _verdict.compute_gates(snap)["G6_trained_policy"]
    assert g6["verdict"] == "ERROR", g6
    assert "PHASE_ERRORED" in g6["reason_codes"], g6
    assert g6.get("scope") == "g6_complete", g6
    # Phase B partial verdict still inspectable for evidence preservation.
    assert g6.get("g6_partial", {}).get("verdict") == "PASS", g6


def test_phase_c_resolve_baseline_eval_returns_phase_b_baseline():
    from probes.kundur.probe_state._causality import _resolve_baseline_eval

    class _StubProbe:
        snapshot = {
            "phase5_trained_policy": {
                "runs": {
                    "baseline": {
                        "r_f_global": -83.7,
                        "r_h_global": -0.04,
                        "r_d_global": -0.04,
                    },
                },
            },
        }

    out = _resolve_baseline_eval(_StubProbe())
    assert out is not None
    assert out["r_f_global"] == -83.7
    assert out["_source"] == "phase5"


def test_phase_c_resolve_baseline_eval_returns_none_when_phase5_missing():
    from probes.kundur.probe_state._causality import _resolve_baseline_eval

    class _StubProbe:
        snapshot: dict = {}

    assert _resolve_baseline_eval(_StubProbe()) is None


def test_phase_c_resolve_baseline_eval_returns_none_when_baseline_errored():
    from probes.kundur.probe_state._causality import _resolve_baseline_eval

    class _StubProbe:
        snapshot = {
            "phase5_trained_policy": {
                "runs": {"baseline": {"error": "paper_eval crashed"}},
            },
        }

    assert _resolve_baseline_eval(_StubProbe()) is None


def test_g4_dispatch_metadata_has_expected_min_df_hz_for_known_dispatches():
    """G4 (2026-05-01): every dispatch in known_disturbance_types() must have
    a non-None expected_min_df_hz OR an explicit historical_source explaining
    the gap. Catches drift when a new dispatch is added but its floor isn't."""
    from scenarios.kundur.disturbance_protocols import known_disturbance_types
    from probes.kundur.probe_state.dispatch_metadata import METADATA

    missing_floor: list[str] = []
    for d_type in known_disturbance_types():
        md = METADATA.get(d_type)
        if md is None:
            continue  # caught by test_dispatch_metadata_coverage
        if md.expected_min_df_hz is None and not md.historical_source:
            missing_floor.append(d_type)
    assert not missing_floor, (
        f"dispatches with no expected_min_df_hz AND no historical_source: "
        f"{missing_floor}"
    )


def test_g4_dispatch_metadata_g_dispatches_have_design_5_7_floors():
    """Cross-check 3 design §5.7 example floors against METADATA."""
    from probes.kundur.probe_state.dispatch_metadata import METADATA

    cases = [
        ("pm_step_proxy_g2", 0.05),
        ("pm_step_hybrid_sg_es", 0.30),
        ("loadstep_paper_trip_bus14", 0.005),
    ]
    for name, expected in cases:
        md = METADATA[name]
        assert md.expected_min_df_hz == expected, (
            f"{name}: expected_min_df_hz={md.expected_min_df_hz} != "
            f"design §5.7 example {expected}"
        )
        assert md.historical_source, f"{name}: historical_source empty"


def test_g3_resolve_alias_baseline_missing_raises_with_hint(tmp_path):
    """G3: 'baseline' alias raises FileNotFoundError with --promote-baseline hint."""
    from probes.kundur.probe_state._diff import resolve_alias

    try:
        resolve_alias("baseline", tmp_path)
    except FileNotFoundError as exc:
        assert "--promote-baseline" in str(exc), str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_g3_resolve_alias_latest_missing_raises(tmp_path):
    from probes.kundur.probe_state._diff import resolve_alias

    try:
        resolve_alias("latest", tmp_path)
    except FileNotFoundError as exc:
        assert "state_snapshot_latest.json" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_g3_resolve_alias_passes_through_real_paths(tmp_path):
    """Plain path strings (not 'baseline'/'latest') resolve verbatim."""
    from probes.kundur.probe_state._diff import resolve_alias

    p = tmp_path / "something.json"
    p.write_text("{}", encoding="utf-8")
    out = resolve_alias(str(p), tmp_path)
    assert out == p.resolve()


def test_g3_promote_baseline_copies_file(tmp_path):
    from probes.kundur.probe_state._diff import promote_baseline, resolve_alias

    src = tmp_path / "snap_v1.json"
    src.write_text('{"schema_version": 1, "implementation_version": "0.4.0"}',
                   encoding="utf-8")
    result = promote_baseline(src, tmp_path)
    dst = result["dst"]
    assert dst == tmp_path / "baseline.json"
    assert dst.exists()
    assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    assert result["backup"] is None  # first promotion: nothing to back up
    # Now baseline alias resolves to the copied file.
    assert resolve_alias("baseline", tmp_path) == dst


def test_g3_promote_baseline_overwrites_existing(tmp_path):
    """I7 review fix: existing baseline.json is renamed to .bak before overwrite."""
    from probes.kundur.probe_state._diff import promote_baseline

    # First promotion
    src1 = tmp_path / "old.json"
    src1.write_text('{"v": 1}', encoding="utf-8")
    promote_baseline(src1, tmp_path)
    assert (tmp_path / "baseline.json").exists()
    assert not (tmp_path / "baseline.json.bak").exists()  # nothing to back up first time

    # Second promotion: previous baseline preserved as .bak
    src2 = tmp_path / "new.json"
    src2.write_text('{"v": 2}', encoding="utf-8")
    result = promote_baseline(src2, tmp_path)
    assert result["dst"].read_text(encoding="utf-8") == '{"v": 2}'
    assert result["backup"] is not None
    assert result["backup"].name == "baseline.json.bak"
    assert result["backup"].read_text(encoding="utf-8") == '{"v": 1}'  # old preserved


def test_g3_promote_baseline_returns_verdict_summary(tmp_path):
    """I7 review fix: result includes one-line G1-G6 verdict summary."""
    from probes.kundur.probe_state._diff import promote_baseline

    src = tmp_path / "snap.json"
    src.write_text(
        json.dumps({
            "schema_version": 1,
            "falsification_gates": {
                "G1_signal": {"verdict": "PASS"},
                "G2_measurement": {"verdict": "PASS"},
                "G3_gradient": {"verdict": "REJECT"},
                "G4_position": {"verdict": "PASS"},
                "G5_trace": {"verdict": "PASS"},
                "G6_trained_policy": {"verdict": "PENDING"},
            },
        }),
        encoding="utf-8",
    )
    result = promote_baseline(src, tmp_path)
    summary = result["verdict_summary"]
    assert "G1=PASS" in summary
    assert "G3=REJECT" in summary
    assert "G6=PENDING" in summary


def test_g3_diff_snapshots_e2e_detects_field_change(tmp_path, capsys):
    """End-to-end diff: 2 fixture snapshots → expect numeric Δ output."""
    from probes.kundur.probe_state._diff import diff_snapshots

    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({
        "schema_version": 1,
        "implementation_version": "0.4.0",
        "phase3_open_loop": {"std_diff_max_min_pu": 1e-5},
    }), encoding="utf-8")
    b.write_text(json.dumps({
        "schema_version": 1,
        "implementation_version": "0.4.0",
        "phase3_open_loop": {"std_diff_max_min_pu": 5e-5},
    }), encoding="utf-8")
    rc = diff_snapshots(a, b)
    captured = capsys.readouterr().out
    assert rc == 1
    assert "phase3_open_loop.std_diff_max_min_pu" in captured
    assert "1e-05 -> 5e-05" in captured or "5e-05" in captured  # delta line


def test_g3_diff_snapshots_e2e_no_changes_returns_zero(tmp_path, capsys):
    from probes.kundur.probe_state._diff import diff_snapshots

    a = tmp_path / "a.json"
    a.write_text('{"schema_version": 1, "implementation_version": "0.4.0"}',
                 encoding="utf-8")
    rc = diff_snapshots(a, a)
    out = capsys.readouterr().out
    assert rc == 0
    assert "no field-level changes" in out


def test_i5_dispatch_metadata_hybrid_has_ceiling():
    """I5 review fix: F4 hybrid dispatch must have expected_max_df_hz set."""
    from probes.kundur.probe_state.dispatch_metadata import METADATA

    md = METADATA["pm_step_hybrid_sg_es"]
    assert md.expected_max_df_hz is not None, (
        "F4 hybrid lost ceiling — runaway divergence detection broken"
    )
    assert md.expected_max_df_hz > md.expected_min_df_hz, (
        "ceiling must exceed floor: "
        f"max={md.expected_max_df_hz} <= min={md.expected_min_df_hz}"
    )


def test_p1_resolve_baseline_returns_none_on_scenario_set_mismatch():
    """P1 review fix: baseline reused only if eval-config matches expected."""
    from probes.kundur.probe_state._causality import _resolve_baseline_eval

    class _StubProbe:
        snapshot = {
            "phase5_trained_policy": {
                "runs": {
                    "baseline": {
                        "r_f_global": -84.16,
                        "scenario_set": "test",   # full mode
                        "n_scenarios": 50,
                    },
                },
            },
        }

    # Phase C requires scenario_set='none' n=5; baseline has 'test' n=50
    out = _resolve_baseline_eval(
        _StubProbe(),
        expected_scenario_set="none",
        expected_n_scenarios=5,
    )
    assert out is None, "should reject mismatched eval-config"


def test_p1_resolve_baseline_returns_none_on_n_scenarios_mismatch():
    from probes.kundur.probe_state._causality import _resolve_baseline_eval

    class _StubProbe:
        snapshot = {
            "phase5_trained_policy": {
                "runs": {
                    "baseline": {
                        "r_f_global": -84.16,
                        "scenario_set": "none",
                        "n_scenarios": 2,         # different from expected
                    },
                },
            },
        }

    out = _resolve_baseline_eval(
        _StubProbe(),
        expected_scenario_set="none",
        expected_n_scenarios=5,
    )
    assert out is None


def test_p1_resolve_baseline_passes_when_config_matches():
    from probes.kundur.probe_state._causality import _resolve_baseline_eval

    class _StubProbe:
        snapshot = {
            "phase5_trained_policy": {
                "runs": {
                    "baseline": {
                        "r_f_global": -84.16,
                        "scenario_set": "none",
                        "n_scenarios": 5,
                    },
                },
            },
        }

    out = _resolve_baseline_eval(
        _StubProbe(),
        expected_scenario_set="none",
        expected_n_scenarios=5,
    )
    assert out is not None
    assert out["r_f_global"] == -84.16


def test_p2a_extract_metrics_errors_on_missing_cum_field():
    """P2a review fix: silent fallback to 0.0 would mask schema drift."""
    from probes.kundur.probe_state._trained_policy import _extract_metrics

    out = _extract_metrics({"per_episode_metrics": [], "_wall_s": 1.0})
    assert "error" in out
    assert "cumulative_reward_global_rf" in out["error"]


def test_p2a_extract_metrics_errors_on_dict_missing_unnormalized():
    """Cumulative dict shape with renamed/missing 'unnormalized' key
    must error rather than silently produce r_f_global=0.0."""
    from probes.kundur.probe_state._trained_policy import _extract_metrics

    eval_dict = {
        "cumulative_reward_global_rf": {
            "per_M": -2.5,           # renamed schema; no 'unnormalized'
            "per_M_per_N": -0.6,
        },
        "per_episode_metrics": [],
        "_wall_s": 1.0,
    }
    out = _extract_metrics(eval_dict)
    assert "error" in out
    assert "unnormalized" in out["error"]
    assert "schema drift" in out["error"]


def test_p2b_g4_uses_thresholds_singleton(monkeypatch):
    """P2b review fix: G4 must read floor from THRESHOLDS, not hardcode."""
    from probes.kundur.probe_state import _verdict, probe_config

    # Build a snapshot where 1 dispatch's max|Δf|_per_agent straddles the
    # default 1e-3 floor: 0.5e-3, 2e-3, 0.5e-3, 0.5e-3 → 1 responder.
    snap = {
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    "max_abs_f_dev_hz_per_agent": [5e-4, 2e-3, 5e-4, 5e-4],
                },
                "Y": {
                    "max_abs_f_dev_hz_per_agent": [3e-3, 5e-4, 5e-4, 5e-4],
                },
            },
        },
    }
    g4_default = _verdict._g4_position(snap)
    # Two distinct signatures: {1} and {0} → PASS at floor=1e-3
    assert g4_default["verdict"] == "PASS"

    # Now monkeypatch THRESHOLDS.g1_respond_hz higher (5e-3): both
    # dispatches now classify as 0 responders (signatures collapse to {})
    # which is 1 distinct signature → REJECT. If G4 still hardcoded 1e-3
    # this test would PASS instead, exposing the desync.
    new_thresholds = probe_config.ProbeThresholds(g1_respond_hz=5e-3)
    monkeypatch.setattr(probe_config, "THRESHOLDS", new_thresholds)
    g4_after = _verdict._g4_position(snap)
    assert g4_after["verdict"] == "REJECT", (
        f"G4 ignored THRESHOLDS bump; got {g4_after!r}"
    )


def test_i2_init_exports_version():
    """I2 review fix: __init__.py exports __version__ for importlib.metadata.

    Also asserts ≥ 0.4.1 floor — pre-0.4.1 verdict semantics on R1 / G4
    differ from current behaviour (see probe_config CHANGELOG); checks
    cross-version reading callers should require this floor.
    """
    import probes.kundur.probe_state as pkg
    assert hasattr(pkg, "__version__"), "__version__ missing from package"
    # Semver shape: 'X.Y.Z'
    parts = pkg.__version__.split(".")
    assert len(parts) == 3 and all(p.isdigit() for p in parts), pkg.__version__
    major, minor, patch = (int(p) for p in parts)
    assert (major, minor, patch) >= (0, 5, 0), (
        f"impl_version {pkg.__version__} below 0.5.0 floor — pre-0.5.0 "
        "lacks ERROR verdict + reason_codes contract"
    )


def test_phase_c_short_train_subprocess_uses_probe_phase_c_run_id_prefix(monkeypatch):
    """End-to-end naming-convention check (added 2026-05-01 from review).

    Mocks ``subprocess.run`` so no actual train fires. Asserts the
    constructed CLI arg list includes ``--run-id probe_phase_c_no_rf_<TS>``
    so production launchers (``kundur_simulink_*``) cannot be confused
    with probe runs in ``ls`` / ``find``.
    """
    from probes.kundur.probe_state import _causality

    captured: dict = {}

    class _FakeCompleted:
        returncode = 1  # pretend train failed (so we don't have to mock best.pt)
        stderr = "fake stderr — short-circuit"

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env")
        return _FakeCompleted()

    monkeypatch.setattr(_causality.subprocess, "run", _fake_run)

    spec = _causality._TrainSpec(
        config_label="no_rf",
        phi_f=0.0, phi_h=5e-4, phi_d=5e-4,
        episodes=10,
    )
    _causality._run_short_train(spec, timeout_s=60)

    cmd = captured.get("cmd") or []
    assert "--run-id" in cmd, f"--run-id missing from cmd: {cmd}"
    rid_idx = cmd.index("--run-id") + 1
    assert rid_idx < len(cmd), "no value follows --run-id"
    rid = cmd[rid_idx]
    assert rid.startswith("probe_phase_c_no_rf_"), (
        f"run_id {rid!r} not prefixed with 'probe_phase_c_no_rf_' — "
        "production-vs-probe naming separation broken"
    )

    # Also assert the env injects KUNDUR_PHI_F=0 (R1 ablation contract).
    env = captured.get("env") or {}
    assert env.get("KUNDUR_PHI_F") == "0.0", (
        f"KUNDUR_PHI_F not injected as 0.0 in subprocess env: "
        f"{env.get('KUNDUR_PHI_F')!r}"
    )


# ===========================================================================
# v0.5.0 — Evidence-Pack contract (ERROR + reason_codes)
# ===========================================================================
#
# Test matrix mapping (plan §5):
#   - test_v050_*_phase_errored                : ERROR + PHASE_ERRORED
#   - test_v050_*_phase_missing                : PENDING + MISSING_PHASE
#   - test_v050_*_field_missing                : PENDING + MISSING_FIELD
#   - test_v050_*_real_zero_yields_reject      : no silent fallback
#   - test_v050_reason_codes_*                 : contract enforcement
#   - test_v050_old_snapshot_diff_compat       : v0.4.1 fixture interop
#   - test_v050_train_failed / eval_failed     : Phase C ERROR codes
#   - test_v050_baseline_mismatch_pending      : 0.4.1 P1 path keeps PENDING + new code
# ---------------------------------------------------------------------------


_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "probe_state"


# ---- ERROR vs PENDING distinction (plan §2) -------------------------------


def test_v050_g2_error_when_phase3_errored():
    from probes.kundur.probe_state import _verdict

    snap = {"phase3_open_loop": {"error": "MATLAB engine died"}}
    g2 = _verdict.compute_gates(snap)["G2_measurement"]
    assert g2["verdict"] == "ERROR"
    assert g2["reason_codes"] == ["PHASE_ERRORED"]


def test_v050_g1_g3_g4_error_when_phase4_errored():
    from probes.kundur.probe_state import _verdict

    gates = _verdict.compute_gates(
        {"phase4_per_dispatch": {"error": "engine stuck"}}
    )
    for gname in ("G1_signal", "G3_gradient", "G4_position"):
        v = gates[gname]
        assert v["verdict"] == "ERROR", f"{gname}: {v}"
        assert v["reason_codes"] == ["PHASE_ERRORED"], f"{gname}: {v}"


def test_v050_phase_missing_yields_pending_not_error():
    """Empty snapshot ⇒ all gates PENDING + MISSING_PHASE (not ERROR).

    PENDING semantics: re-run the missing phase to resolve.
    ERROR semantics: pipeline broke; fix code/env first.
    """
    from probes.kundur.probe_state import _verdict

    gates = _verdict.compute_gates({})
    for gname in ("G1_signal", "G2_measurement", "G3_gradient",
                  "G4_position", "G5_trace"):
        v = gates[gname]
        assert v["verdict"] == "PENDING", f"{gname}: {v}"
        assert "MISSING_PHASE" in v["reason_codes"], f"{gname}: {v}"


# ---- No silent fallback for missing fields (plan §1 — verdict gates) ------


def test_v050_g1_pending_when_agents_responding_field_missing():
    """G1 must NOT silently treat missing 'agents_responding_above_1mHz'
    as zero (which would emit REJECT). v0.5.0 surfaces MISSING_FIELD.
    """
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    # No agents_responding_above_1mHz key — silent-fallback bait.
                    "max_abs_f_dev_hz_per_agent": [0.5, 0.4, 0.3, 0.2],
                    "r_f_local_share": [0.25, 0.25, 0.25, 0.25],
                },
            }
        }
    }
    g1 = _verdict.compute_gates(snap)["G1_signal"]
    assert g1["verdict"] == "PENDING", g1
    assert g1["reason_codes"] == ["MISSING_FIELD"], g1


def test_v050_g3_pending_when_share_field_missing():
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    "agents_responding_above_1mHz": 4,
                    "max_abs_f_dev_hz_per_agent": [0.5, 0.4, 0.3, 0.2],
                    # No r_f_local_share field.
                },
            }
        }
    }
    g3 = _verdict.compute_gates(snap)["G3_gradient"]
    assert g3["verdict"] == "PENDING", g3
    assert g3["reason_codes"] == ["MISSING_FIELD"], g3


def test_v050_g4_pending_when_per_agent_max_field_missing():
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    "agents_responding_above_1mHz": 4,
                    # No max_abs_f_dev_hz_per_agent — would silently
                    # become empty signature in 0.4.1.
                    "r_f_local_share": [0.25, 0.25, 0.25, 0.25],
                },
                "Y": {
                    "agents_responding_above_1mHz": 4,
                    "max_abs_f_dev_hz_per_agent": [0.5, 0.4, 0.3, 0.2],
                    "r_f_local_share": [0.25, 0.25, 0.25, 0.25],
                },
            }
        }
    }
    g4 = _verdict.compute_gates(snap)["G4_position"]
    assert g4["verdict"] == "PENDING", g4
    assert g4["reason_codes"] == ["MISSING_FIELD"], g4


def test_v050_g2_pending_when_phase3_required_field_missing():
    from probes.kundur.probe_state import _verdict

    snap = {"phase3_open_loop": {"n_steps": 50}}  # missing the 3 required fields
    g2 = _verdict.compute_gates(snap)["G2_measurement"]
    assert g2["verdict"] == "PENDING", g2
    assert g2["reason_codes"] == ["MISSING_FIELD"], g2


def test_v050_g3_empty_data_distinct_from_reject():
    """All dispatches present but with empty share lists ⇒ PENDING +
    EMPTY_DATA (recoverable by fixing data emission). Not REJECT
    (which means data was decisive)."""
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    "agents_responding_above_1mHz": 4,
                    "max_abs_f_dev_hz_per_agent": [0.5, 0.4, 0.3, 0.2],
                    "r_f_local_share": [],
                },
                "Y": {
                    "agents_responding_above_1mHz": 4,
                    "max_abs_f_dev_hz_per_agent": [0.5, 0.4, 0.3, 0.2],
                    "r_f_local_share": [],
                },
            }
        }
    }
    g3 = _verdict.compute_gates(snap)["G3_gradient"]
    assert g3["verdict"] == "PENDING", g3
    assert "EMPTY_DATA" in g3["reason_codes"], g3


def test_v050_g1_real_zero_yields_reject_not_pending():
    """Field present with real zero count ⇒ REJECT + THRESHOLD_NOT_MET
    (decisive negative evidence). Not PENDING (which means data
    insufficient)."""
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    "agents_responding_above_1mHz": 0,  # genuine zero
                    "max_abs_f_dev_hz_per_agent": [0.0, 0.0, 0.0, 0.0],
                    "r_f_local_share": [0.25, 0.25, 0.25, 0.25],
                },
            }
        }
    }
    g1 = _verdict.compute_gates(snap)["G1_signal"]
    assert g1["verdict"] == "REJECT", g1
    assert g1["reason_codes"] == ["THRESHOLD_NOT_MET"], g1


def test_v050_g4_insufficient_dispatches_yields_pending():
    """1 dispatch ⇒ PENDING + INSUFFICIENT_DISPATCHES (need ≥ 2 for
    distinct signatures; not enough data)."""
    from probes.kundur.probe_state import _verdict

    snap = {
        "phase4_per_dispatch": {
            "dispatches": {
                "X": {
                    "agents_responding_above_1mHz": 4,
                    "max_abs_f_dev_hz_per_agent": [0.5, 0.4, 0.3, 0.2],
                    "r_f_local_share": [0.4, 0.3, 0.2, 0.1],
                },
            }
        }
    }
    g4 = _verdict.compute_gates(snap)["G4_position"]
    assert g4["verdict"] == "PENDING", g4
    assert g4["reason_codes"] == ["INSUFFICIENT_DISPATCHES"], g4


# ---- reason_codes contract (plan §1, §11a silent-error-path-impact) -------


def test_v050_reason_codes_always_present_on_all_gates():
    """Every gate verdict — under any input — must carry a non-empty
    reason_codes list. Missing field is a contract violation."""
    from probes.kundur.probe_state import _verdict

    snapshots_to_probe = [
        {},                                                          # PENDING
        {"phase3_open_loop": {"error": "x"}},                        # ERROR
        {"phase4_per_dispatch": {"dispatches": {}}},                 # PENDING/EMPTY
        json.loads(
            (_FIXTURE_DIR / "snapshot_v0_4_1.json").read_text(encoding="utf-8")
        ),                                                           # PASS-heavy
    ]
    for snap in snapshots_to_probe:
        gates = _verdict.compute_gates(snap)
        for gname, gv in gates.items():
            assert "reason_codes" in gv, (
                f"{gname} missing reason_codes: {gv}"
            )
            assert isinstance(gv["reason_codes"], list), (
                f"{gname} reason_codes not a list: {gv}"
            )
            assert len(gv["reason_codes"]) > 0, (
                f"{gname} has empty reason_codes (contract violation): {gv}"
            )


def test_v050_reason_codes_drawn_from_frozen_vocabulary():
    from probes.kundur.probe_state import _verdict
    from probes.kundur.probe_state.probe_config import REASON_CODES

    fix = json.loads(
        (_FIXTURE_DIR / "snapshot_v0_4_1.json").read_text(encoding="utf-8")
    )
    gates = _verdict.compute_gates(fix)
    for gname, gv in gates.items():
        for code in gv["reason_codes"]:
            assert code in REASON_CODES, (
                f"{gname} emitted unknown reason_code {code!r}; "
                f"vocab = {sorted(REASON_CODES)}"
            )


def test_v050_verdict_constructor_rejects_empty_reason_codes():
    from probes.kundur.probe_state._verdict import _verdict as build_verdict, VERDICT_PASS

    with pytest.raises(ValueError, match="reason_codes must be non-empty"):
        build_verdict(VERDICT_PASS, "fake", reason_codes=[])


def test_v050_verdict_constructor_rejects_unknown_codes():
    from probes.kundur.probe_state._verdict import _verdict as build_verdict, VERDICT_PASS

    with pytest.raises(ValueError, match="unknown reason_codes"):
        build_verdict(VERDICT_PASS, "fake", reason_codes=["NOT_A_REAL_CODE"])


def test_v050_verdict_constructor_rejects_invalid_verdict_string():
    from probes.kundur.probe_state._verdict import _verdict as build_verdict

    with pytest.raises(ValueError, match="unknown verdict"):
        build_verdict("MAYBE", "fake", reason_codes=["EVIDENCE_OK"])


# ---- v0.4.1 → v0.5.0 backward-compat (plan §1) ----------------------------


def test_v050_old_snapshot_v041_is_loadable():
    """v0.4.1 fixture has no reason_codes; loading and re-deriving gates
    via compute_gates must succeed without crashing (the snapshot fields
    drive verdicts, not the embedded gate block)."""
    from probes.kundur.probe_state import _verdict

    fix = json.loads(
        (_FIXTURE_DIR / "snapshot_v0_4_1.json").read_text(encoding="utf-8")
    )
    # The embedded falsification_gates block lacks reason_codes — that's OK,
    # we don't read it; we re-derive from raw phase data.
    assert "reason_codes" not in fix["falsification_gates"]["G1_signal"]
    gates = _verdict.compute_gates(fix)
    # Re-derived gates DO carry reason_codes (new contract).
    for gname, gv in gates.items():
        assert "reason_codes" in gv, f"{gname}: {gv}"


def test_v050_diff_old_vs_new_does_not_crash(tmp_path):
    """--diff between a v0.4.1 fixture and a v0.5.0 fresh snapshot must
    not raise: _diff._walk handles missing reason_codes via set-difference
    (ADDED entries) automatically, no special migration code required.
    """
    from probes.kundur.probe_state import _verdict
    from probes.kundur.probe_state._diff import diff_snapshots

    # v0.4.1: fixture as-is.
    old_path = _FIXTURE_DIR / "snapshot_v0_4_1.json"
    fix = json.loads(old_path.read_text(encoding="utf-8"))

    # v0.5.0: re-derive gates with reason_codes; rewrite fixture into tmp.
    fix_new = dict(fix)
    fix_new["implementation_version"] = "0.5.0"
    fix_new["falsification_gates"] = _verdict.compute_gates(fix)
    new_path = tmp_path / "snap_v050.json"
    new_path.write_text(json.dumps(fix_new), encoding="utf-8")

    rc = diff_snapshots(old_path, new_path)
    # Diff finds at least the impl_version bump and the added reason_codes.
    assert rc == 1


# ---- Phase C ERROR codes (plan §1 — silent-fallback widening) -------------


def test_v050_phase_c_train_failed_emits_error():
    """Short-train subprocess failure ⇒ R1 ERROR + TRAIN_FAILED (was
    PENDING in 0.4.1). Operator must diagnose; re-running won't fix it."""
    from probes.kundur.probe_state import _causality

    class _StubProbe:
        snapshot = {
            "phase5_trained_policy": {
                "runs": {
                    "baseline": {
                        "r_f_global": -84.16,
                        "scenario_set": "none",
                        "n_scenarios": 5,
                    },
                },
            },
        }
        phase_c_mode = "smoke"
        phase_c_eval_n_scenarios = 5
        phase_c_train_timeout_s = 60

    # Force _run_short_train to emit a failure payload.
    def _fake_train(spec, timeout_s=None):
        return {
            "run_id": "probe_phase_c_no_rf_2026XXXXTYYYYY",
            "run_dir": None,
            "ckpt": None,
            "wall_s": 1.0,
            "error": "non-zero exit 1",
            "stderr_tail": "boom",
        }

    orig = _causality._run_short_train
    _causality._run_short_train = _fake_train
    try:
        rec = _causality.run_causality_short_train(_StubProbe())
    finally:
        _causality._run_short_train = orig

    r1 = rec["r1_verdict"]
    assert r1["verdict"] == "ERROR", rec
    assert r1["reason_codes"] == ["TRAIN_FAILED"], rec


def test_v050_phase_c_eval_failed_emits_error():
    """Eval subprocess crash ⇒ R1 ERROR + EVAL_FAILED."""
    from probes.kundur.probe_state import _causality

    class _StubProbe:
        snapshot = {
            "phase5_trained_policy": {
                "runs": {
                    "baseline": {
                        "r_f_global": -84.16,
                        "scenario_set": "none",
                        "n_scenarios": 5,
                    },
                },
            },
        }
        phase_c_mode = "smoke"
        phase_c_eval_n_scenarios = 5
        phase_c_train_timeout_s = 60

    # Train succeeds, eval crashes.
    def _fake_train(spec, timeout_s=None):
        return {
            "run_id": "probe_phase_c_no_rf_X",
            "run_dir": "/fake/dir",
            "ckpt": "/fake/best.pt",
            "wall_s": 1.0,
        }

    def _fake_eval_ckpt(ckpt_path, *, label, n_scenarios, timeout_s=900):
        raise RuntimeError("paper_eval boom")

    orig_train = _causality._run_short_train
    orig_eval = _causality._eval_ckpt
    _causality._run_short_train = _fake_train
    _causality._eval_ckpt = _fake_eval_ckpt
    try:
        rec = _causality.run_causality_short_train(_StubProbe())
    finally:
        _causality._run_short_train = orig_train
        _causality._eval_ckpt = orig_eval

    r1 = rec["r1_verdict"]
    assert r1["verdict"] == "ERROR", rec
    assert r1["reason_codes"] == ["EVAL_FAILED"], rec


def test_v050_phase_c_baseline_mismatch_pending_with_code():
    """0.4.1 P1 BASELINE_MISMATCH path is preserved as PENDING (data
    insufficiency — re-run Phase B with matching config). v0.5.0 just
    adds the reason_code so consumers can pattern-match without parsing
    evidence strings."""
    from probes.kundur.probe_state import _causality

    class _StubProbe:
        snapshot = {
            "phase5_trained_policy": {
                "runs": {
                    "baseline": {
                        "r_f_global": -84.16,
                        "scenario_set": "test",   # mismatch — Phase C wants 'none'
                        "n_scenarios": 50,
                    },
                },
            },
        }
        phase_c_mode = "smoke"
        phase_c_eval_n_scenarios = 5
        phase_c_train_timeout_s = 60

    rec = _causality.run_causality_short_train(_StubProbe())
    r1 = rec["r1_verdict"]
    assert r1["verdict"] == "PENDING", rec
    assert r1["reason_codes"] == ["BASELINE_MISMATCH"], rec


# ---- _report.py rendering (additive — does not touch verdict numbers) ----


def test_v050_report_renders_reason_codes_column(tmp_path):
    """Markdown report must include a 'Reason codes' column with the
    codes for each gate."""
    from probes.kundur.probe_state import _report

    snap = {
        "schema_version": 1,
        "implementation_version": "0.5.0",
        "timestamp": "2026-05-01T00:00:00",
        "git_head": "abc123",
        "config": {"dispatch_magnitude_sys_pu": 0.5, "sim_duration_s": 5.0},
        "errors": [],
        "phase1_topology": {},
        "phase2_nr_ic": {},
        "falsification_gates": {
            "G1_signal": {
                "verdict": "PASS",
                "evidence": "stub",
                "reason_codes": ["EVIDENCE_OK"],
            },
            "G2_measurement": {
                "verdict": "ERROR",
                "evidence": "phase3 errored",
                "reason_codes": ["PHASE_ERRORED"],
            },
        },
    }
    out = _report.write(snap, tmp_path)
    md = out["md"].read_text(encoding="utf-8")
    assert "Reason codes" in md, "header column missing"
    assert "`EVIDENCE_OK`" in md
    assert "`PHASE_ERRORED`" in md
    # ERROR glyph rendered:
    assert "🛑" in md or "ERROR" in md  # fall back to verdict string if glyph swallowed
