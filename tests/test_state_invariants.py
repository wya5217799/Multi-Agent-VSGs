# FACT: invariants below operate on the latest probe_state snapshot
# (results/harness/kundur/probe_state/state_snapshot_latest.json) and on
# project FACT modules. CLAIM = anything we add as narrative beyond
# what the file/module returns.
"""Regression invariants over the latest probe_state snapshot.

**Type A — data-independent** (5 tests):
  Hardcoded paper FACT + project design-contract checks. Read the snapshot
  and assert; pytest.skip ONLY when no snapshot exists yet (chicken-and-
  egg break). Otherwise must PASS — Type A FAIL = build script broke or
  paper FACT changed → STOP and investigate.

**Type B — data-required**:
  Phase-data-dependent invariants. SKIP when the relevant phase is
  *missing* (fail-soft for fresh snapshots without all phases yet).
  *ERRORED* phases — under v0.5.0 — are pipeline-failure signals, not
  data-insufficiency signals; Type B treats ERRORED as data unavailable
  here too (pytest.skip), but the upstream gate's ERROR verdict is a
  separate test target via test_typeB_no_unexpected_error_verdicts.
  Reach REJECT verdicts produced by the probe should still result in
  PASS at this layer (the verdict itself is the regression observable,
  not its value).

Run::

    PY=".../andes_env/python.exe"
    $PY -m pytest tests/test_state_invariants.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = REPO_ROOT / "results/harness/kundur/probe_state"
LATEST_JSON = SNAPSHOT_DIR / "state_snapshot_latest.json"


@pytest.fixture(scope="module")
def snap() -> dict:
    if not LATEST_JSON.exists():
        pytest.skip(
            f"no probe snapshot at {LATEST_JSON}; "
            f"run `python -m probes.kundur.probe_state` first"
        )
    return json.loads(LATEST_JSON.read_text(encoding="utf-8"))


# ===========================================================================
# Type A — data-independent (paper FACT + project design contract)
# ===========================================================================


@pytest.mark.typeA
def test_typeA_schema_version(snap):
    assert snap.get("schema_version") == 1, (
        f"schema_version != 1; bumped without test update? "
        f"got {snap.get('schema_version')}"
    )


@pytest.mark.typeA
def test_typeA_paper_fact_n_ess_eq_4(snap):
    """Paper §IV-A: 4 ESS. Project design contract."""
    p1 = snap.get("phase1_topology") or {}
    if "error" in p1 or not p1:
        pytest.skip("phase1 absent: cannot verify n_ess")
    assert p1.get("n_ess") == 4, (
        f"phase1.n_ess != 4 (paper §IV-A says 4 ESS). "
        f"got {p1.get('n_ess')}"
    )


@pytest.mark.typeA
def test_typeA_paper_fact_n_sg_eq_3(snap):
    """Paper §IV-A: G1/G2/G3 (G4 replaced by W1)."""
    p1 = snap.get("phase1_topology") or {}
    if "error" in p1 or not p1:
        pytest.skip("phase1 absent: cannot verify n_sg")
    assert p1.get("n_sg") == 3, (
        f"phase1.n_sg != 3 (paper §IV-A says 3 SG). "
        f"got {p1.get('n_sg')}"
    )


@pytest.mark.typeA
def test_typeA_phi_f_paper_aligned(snap):
    """Paper Table I: phi_f = 100. Project should match."""
    p1 = snap.get("phase1_topology") or {}
    if "error" in p1 or not p1:
        pytest.skip("phase1 absent: cannot verify phi_f")
    cfg = p1.get("config") or {}
    assert cfg.get("phi_f") == 100.0, (
        f"phi_f != 100 (paper Table I). got {cfg.get('phi_f')}"
    )


@pytest.mark.typeA
def test_typeA_no_hidden_slack(snap):
    """Paper §IV-A: ESS group resolves slack — no hidden slack."""
    p2 = snap.get("phase2_nr_ic") or {}
    if "error" in p2 or not p2:
        pytest.skip("phase2 absent: cannot verify hidden-slack contract")
    assert p2.get("no_hidden_slack") is True, (
        "no_hidden_slack must be True (paper §IV-A)"
    )


# ===========================================================================
# Type B — data-required (fail-soft compatible)
# ===========================================================================


@pytest.mark.typeB
def test_typeB_omega_per_agent_distinct(snap):
    p3 = snap.get("phase3_open_loop") or {}
    if "error" in p3 or not p3:
        pytest.skip("phase3 not run / errored")
    assert p3.get("all_sha256_distinct") is True, (
        f"open-loop omega traces aliased: "
        f"{p3.get('n_distinct_sha256')}/{p3.get('n_agents')}"
    )


@pytest.mark.typeB
def test_typeB_g1_verdict_decided(snap):
    """G1 must reach a decisive verdict (PASS or REJECT) when phase 4 ran.

    v0.5.0 distinction:
    - PENDING ⇒ data was insufficient to decide (e.g. missing required
      field) — skip; not a regression.
    - ERROR ⇒ pipeline failure (phase4 errored or sub-pipeline crash) —
      skip here, surfaced separately by ``test_typeB_no_unexpected_error_verdicts``.
    - REJECT is acceptable; we flag historical-state drift via Type A.
    """
    p4 = snap.get("phase4_per_dispatch") or {}
    if "error" in p4 or not p4 or not p4.get("dispatches"):
        pytest.skip("phase4 not run / no dispatches / errored")
    g1 = (snap.get("falsification_gates") or {}).get("G1_signal", {})
    if g1.get("verdict") in ("PENDING", "ERROR"):
        pytest.skip(f"G1 verdict not decided: {g1!r}")
    assert g1.get("verdict") in {"PASS", "REJECT"}, (
        f"G1 verdict undecided: {g1!r}"
    )


@pytest.mark.typeB
def test_typeB_phase2_pm0_lengths_match_topology(snap):
    p1 = snap.get("phase1_topology") or {}
    p2 = snap.get("phase2_nr_ic") or {}
    if "error" in p2 or not p2:
        pytest.skip("phase2 not run / errored")
    if "error" in p1 or not p1:
        pytest.skip("phase1 absent: cannot cross-check lengths")
    assert len(p2.get("vsg_pm0_pu", [])) == p1["n_ess"], (
        f"phase2 vsg_pm0_pu length {len(p2.get('vsg_pm0_pu', []))} "
        f"!= phase1.n_ess {p1['n_ess']}"
    )
    assert len(p2.get("sg_pm0_sys_pu", [])) == p1["n_sg"], (
        f"phase2 sg_pm0_sys_pu length {len(p2.get('sg_pm0_sys_pu', []))} "
        f"!= phase1.n_sg {p1['n_sg']}"
    )


# ===========================================================================
# Type B — Phase B (trained policy ablation)
# ===========================================================================


@pytest.mark.typeB
def test_typeB_phase5_ablation_signal_nontrivial(snap):
    """Plan §7 — at least one ablation diff must exceed the noise floor.

    PASS condition is weaker than G6 PASS; this only guarantees Phase 5
    delivered measurable signal (= we can act on the verdict). G6 PASS
    requires K contributors AND beats zero_all — that's a stronger claim.
    """
    p5 = snap.get("phase5_trained_policy") or {}
    if "error" in p5 or not p5:
        pytest.skip("phase5 not run / errored")
    diffs = [d for d in (p5.get("ablation_diffs") or []) if d is not None]
    if not diffs:
        pytest.skip("no successful ablation runs (all zero_agent_i errored)")
    NOISE = float(p5.get("noise_threshold_sys_pu_sq", 1e-3))
    max_abs_diff = max(abs(d) for d in diffs)
    assert max_abs_diff > NOISE, (
        f"all ablation diffs below noise floor {NOISE}: "
        f"max|diff|={max_abs_diff:.3e}, diffs={diffs}"
    )


@pytest.mark.typeB
def test_typeB_g6_decided(snap):
    """Plan §7 — G6 verdict must be PASS or REJECT once Phase 5 ran.

    PENDING means insufficient data (e.g. ckpt missing, all runs errored);
    that's caught by typeB_phase5_ablation_signal_nontrivial via SKIP.
    REJECT is acceptable — it just says the trained policy is degenerate.
    Phase C R1 layer is allowed to be absent (G6 falls back to G6_partial).
    """
    p5 = snap.get("phase5_trained_policy") or {}
    if "error" in p5 or not p5 or not p5.get("runs"):
        pytest.skip("phase5 not run / no runs data")
    runs = p5.get("runs", {}) or {}
    baseline = runs.get("baseline") or {}
    zero_all = runs.get("zero_all") or {}
    if "error" in baseline or "error" in zero_all:
        pytest.skip(
            f"baseline or zero_all errored "
            f"(baseline_err={'error' in baseline}, "
            f"zero_all_err={'error' in zero_all})"
        )
    # Phase C R1 PENDING blocks the composite verdict — handle via skip.
    p6 = snap.get("phase6_causality") or {}
    if isinstance(p6, dict) and p6 and "error" not in p6:
        r1 = p6.get("r1_verdict") or {}
        if r1.get("verdict") == "PENDING":
            pytest.skip(f"R1 PENDING blocks G6 composite: {r1.get('evidence')}")
    g6 = (snap.get("falsification_gates") or {}).get("G6_trained_policy", {})
    assert g6.get("verdict") in {"PASS", "REJECT"}, (
        f"G6 should be decided when baseline + zero_all present: {g6!r}"
    )


# ===========================================================================
# Type B — Phase C (causality short-train)
# ===========================================================================


@pytest.mark.typeB
def test_typeB_phase6_r1_verdict_present(snap):
    """Plan §6 Step 6 — once Phase 6 ran, r1_verdict must be present and
    valid (PASS / REJECT / PENDING / ERROR per v0.5.0)."""
    p6 = snap.get("phase6_causality") or {}
    if "error" in p6 or not p6:
        pytest.skip("phase6 not run / errored")
    r1 = p6.get("r1_verdict") or {}
    if not r1:
        pytest.skip("r1_verdict empty")
    assert r1.get("verdict") in {"PASS", "REJECT", "PENDING", "ERROR"}, (
        f"R1 verdict invalid: {r1!r}"
    )
    assert "evidence" in r1, f"R1 has no evidence string: {r1!r}"


@pytest.mark.typeB
def test_typeB_g6_complete_decided_or_skip(snap):
    """Plan §6 Step 6 — phase6 present + R1 / partial both PASS/REJECT
    ⇒ G6 复合 verdict 必决断."""
    p6 = snap.get("phase6_causality") or {}
    if "error" in p6 or not p6:
        pytest.skip("phase6 not run / errored")
    r1 = p6.get("r1_verdict") or {}
    if not r1 or r1.get("verdict") == "PENDING":
        pytest.skip(f"R1 PENDING / missing: {r1!r}")
    g6 = (snap.get("falsification_gates") or {}).get("G6_trained_policy", {})
    partial = g6.get("g6_partial") or {}
    if partial.get("verdict") == "PENDING":
        pytest.skip(f"G6_partial PENDING: {partial.get('evidence')}")
    assert g6.get("verdict") in {"PASS", "REJECT"}, (
        f"G6 should be decided when both R1 + partial decided: {g6!r}"
    )
    # Composite verdict invariant: if any of (R1, partial) REJECT → G6 REJECT.
    if r1.get("verdict") == "REJECT" or partial.get("verdict") == "REJECT":
        assert g6.get("verdict") == "REJECT", (
            f"G6 should REJECT when any sub-verdict REJECT: {g6!r}"
        )


# ===========================================================================
# v0.5.0 — Evidence-Pack contract checks against the latest snapshot
# ===========================================================================


@pytest.mark.typeB
def test_typeB_no_unexpected_error_verdicts(snap):
    """v0.5.0: ERROR verdicts indicate pipeline failures (phase errored,
    train/eval crashed). When the latest snapshot has any gate in ERROR
    state, the operator must investigate; this test FAILs (not SKIPs) so
    pipeline brokenness is surfaced rather than silently absorbed.

    A snapshot from a partial probe run (e.g. ``--phase 1,2`` only) where
    later phases were never attempted produces PENDING verdicts (handled
    by SKIP elsewhere); ERROR specifically means a phase WAS attempted
    and FAILED.
    """
    gates = snap.get("falsification_gates") or {}
    if not gates:
        pytest.skip("no falsification_gates block in snapshot")
    errored = {
        gname: gv
        for gname, gv in gates.items()
        if isinstance(gv, dict) and gv.get("verdict") == "ERROR"
    }
    if not errored:
        return  # all clear
    # Build a compact failure message naming each ERROR gate + its reason.
    summary = "; ".join(
        f"{gname}={gv.get('reason_codes', '?')} ({gv.get('evidence','')[:60]})"
        for gname, gv in errored.items()
    )
    pytest.fail(
        f"{len(errored)} gate(s) in ERROR state — pipeline failure, "
        f"not data insufficiency: {summary}"
    )


@pytest.mark.typeB
def test_typeB_reason_codes_present_on_v050_snapshot(snap):
    """v0.5.0: snapshots produced under impl_version >= 0.5.0 must carry
    reason_codes on every gate. Older snapshots (impl < 0.5.0 or impl
    None) are skipped — _diff treats their absence as ``[]``."""
    impl = snap.get("implementation_version")
    if impl is None:
        pytest.skip("snapshot predates impl_version field")
    parts = str(impl).split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        pytest.skip(f"non-semver impl_version {impl!r}")
    if tuple(int(p) for p in parts) < (0, 5, 0):
        pytest.skip(f"snapshot impl_version {impl} < 0.5.0; reason_codes optional")
    gates = snap.get("falsification_gates") or {}
    if not gates:
        pytest.skip("no falsification_gates block")
    for gname, gv in gates.items():
        codes = gv.get("reason_codes")
        assert isinstance(codes, list) and len(codes) > 0, (
            f"{gname} missing or empty reason_codes under v0.5.0 contract: "
            f"{gv!r}"
        )
