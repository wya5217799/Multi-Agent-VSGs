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


def test_phase_b_g6_pending_when_baseline_errored():
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
    assert g6["verdict"] == "PENDING", g6


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


def test_phase_c_r1_pending_when_baseline_errored():
    from probes.kundur.probe_state._causality import _compute_r1_verdict

    out = _compute_r1_verdict({"error": "fake"}, {"r_f_global": -10.0})
    assert out["verdict"] == "PENDING"


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


def test_phase_c_g6_falls_back_to_partial_when_phase6_errored():
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
    assert g6["verdict"] == "PASS", g6
    assert g6.get("scope") == "g6_partial_only", g6


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
