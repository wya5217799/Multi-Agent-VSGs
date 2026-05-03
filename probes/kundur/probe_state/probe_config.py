# FACT: this module's THRESHOLDS dataclass is the single source of truth
# for probe verdict / runner constants. Anything in plans / README /
# docstrings mentioning a numeric threshold is CLAIM until verified
# against this file.
"""Centralised probe thresholds + implementation version.

Design ref: ``docs/design/probe_state_design.md`` §5.5 (F1 — externalised
thresholds) and §10.2 (F5 — implementation_version).

Why this exists:
- Phase A/B/C originally hardcoded thresholds at module level
  (``G6_NOISE_THRESHOLD_SYS_PU_SQ`` in ``_trained_policy.py``,
  ``IMPROVE_TOL_R1_SYS_PU_SQ`` in ``_causality.py``,
  ``RESPOND_THRESHOLD_HZ`` in ``_dynamics.py``, ``noise_floor`` literal
  in ``_verdict.py::_g5_trace``, etc.). Tweaking a verdict cutoff meant
  editing N source files and grep'ing for stragglers.
- F1 collects these into one ``frozen`` dataclass. Modules import
  ``THRESHOLDS`` and read attributes; modifying a value is a one-line
  change with no scattered hardcode.
- ``IMPLEMENTATION_VERSION`` (F5) tracks probe-algorithm changes that do
  NOT bump ``schema_version`` (data-format stays). Bump rules in
  ``probes/kundur/probe_state/README.md`` §"Versioning".

Adding a threshold:
1. Add a frozen field to ``ProbeThresholds`` with a sensible default.
2. Replace the module-level constant with ``THRESHOLDS.<field>``.
3. Bump ``IMPLEMENTATION_VERSION`` minor (default change) or major
   (semantic change of what a verdict means).
4. CHANGELOG note at the top of this file (rolling, last 5).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProbeThresholds:
    """Frozen container for every probe-runtime numeric constant."""

    # ---- G1 / G3 / G4 / G5 (Phase A) ----
    g1_respond_hz: float = 1e-3
    """G1: per-agent max|Δf| floor for "agent responding" classification.
    Phase 4 dispatch is "exciting" when ≥ 2 agents exceed this."""

    g3_share_diff_rel: float = 0.05
    """G3: per-agent r_f_local_share max-min must exceed this fraction
    of mean for the gradient to count as non-degenerate."""

    g4_position_hz: float = 0.10
    """G4: per-agent max|Δf| threshold for "responder signature" bucketing.
    Distinct from g1_respond_hz (1 mHz, used for the "responding at all"
    classification): under EMT-coupled v3 Discrete every agent always
    responds > 74 mHz, so bucket-by-1-mHz collapses every dispatch's
    signature to (0,1,2,3) and G4 REJECTs even when dispatches actually
    excite different mode shapes. 0.10 Hz separates "primary responder"
    from "secondary mode echo" at v3 Discrete scale (alpha probe 2026-05-03
    showed pm_step_proxy_bus7 max|Δf|=0.34 Hz primary, ~0.07-0.10 Hz on
    other agents). D1 follow-up 2026-05-03; not yet wired into _verdict
    (separate impl)."""

    g5_noise_floor_pu: float = 1e-7
    """G5: omega-std diff (max-min across agents) must exceed this to
    rule out collapse-to-single-trace."""

    # ---- G6 (Phase B partial) ----
    g6_k_required_contributors: int = 2
    """G6 partial: minimum agent count whose ablation diff exceeds NOISE
    for the trained policy to count as non-degenerate (paper §IV-A
    intent: ≥ 2 agents actively contributing). Same K=2 floor as G1."""

    g6_noise_threshold_sys_pu_sq: float = 1e-3
    """G6 partial: |ablation_diff[i]| above this = agent i contributes."""

    g6_improve_tol_sys_pu_sq: float = 0.5
    """G6 partial: baseline.r_f - zero_all.r_f above this = trained
    policy beats no-control baseline meaningfully (5% of |zero_all|
    when |zero_all| ≈ -100; sets the smallest "improvement" we care
    about)."""

    # ---- R1 (Phase C v1) ----
    r1_improve_tol_sys_pu_sq: float = 0.5
    """R1: baseline.r_f - no_rf.r_f above this (in absolute Δ) =
    φ_f penalty drives improvement (R1 PASS). Same scale as G6."""

    # ---- Subprocess ceilings ----
    paper_eval_timeout_s: int = 900
    """Phase B / C: per paper_eval subprocess wall ceiling."""

    train_timeout_s: int = 86400
    """Phase C: per short-train subprocess wall ceiling (24 hr).
    Calibrated 2026-05-01: actual full-mode wall ≈ 47 min, so the
    ceiling is 30× safety margin."""

    # ---- Phase C episode counts ----
    episodes_smoke: int = 10
    """Phase C smoke mode: too few for real R1 signal, plumbing only."""

    episodes_full: int = 200
    """Phase C full mode: matches design §6.2 / plan §6 Step 8 spec."""


# Singleton instance — modules import this directly.
THRESHOLDS = ProbeThresholds()


# ---------------------------------------------------------------------------
# reason_codes vocabulary (v0.5.0 frozen set)
# ---------------------------------------------------------------------------
#
# Every gate verdict dict carries ``reason_codes: list[str]`` whose members
# are drawn from this frozenset. Adding a code is a minor IMPLEMENTATION
# bump (verdict-semantics widening); renaming or removing a code is a
# schema bump (consumers may switch on the literal).
#
# Codes are paired with verdicts as follows:
#   PASS    → EVIDENCE_OK
#   REJECT  → THRESHOLD_NOT_MET
#   PENDING → MISSING_PHASE | MISSING_FIELD | EMPTY_DATA
#             | INSUFFICIENT_DISPATCHES | BASELINE_MISMATCH | SCHEMA_DRIFT
#   ERROR   → PHASE_ERRORED | TRAIN_FAILED | EVAL_FAILED
#
# A verdict dict MUST carry at least one reason_code; an empty list is a
# contract violation (asserted at write time by _verdict._verdict()).
REASON_CODES: frozenset[str] = frozenset({
    "EVIDENCE_OK",
    "THRESHOLD_NOT_MET",
    "MISSING_PHASE",
    "MISSING_FIELD",
    "EMPTY_DATA",
    "INSUFFICIENT_DISPATCHES",
    "BASELINE_MISMATCH",
    "SCHEMA_DRIFT",
    "PHASE_ERRORED",
    "TRAIN_FAILED",
    "EVAL_FAILED",
})


# ---------------------------------------------------------------------------
# Implementation version (F5)
# ---------------------------------------------------------------------------

IMPLEMENTATION_VERSION = "0.6.0"
"""Probe algorithm version — semver. See README §"Versioning" for bump rules.

CHANGELOG (rolling, last 5):
- 0.6.0 (2026-05-03) — P2 parallel mode (subprocess pool) + LoadStep adapter
  fix + Z route v3 Discrete profile + D3 RNG seed + g4_position_hz threshold
  field added.
  * additive: ``--workers N`` and ``--dispatch-subset SPEC`` CLI flags.
    Default ``--workers=1`` preserves serial behaviour bit-exact (M1).
    ``--workers >= 2`` triggers subprocess pool path (Module γ).
  * additive: ``--t-warmup-s`` and ``--fast-restart`` CLI overrides for
    probe context. ``T_WARMUP`` production default unchanged.
  * additive: snapshot ``phase4_per_dispatch.parallel_metadata`` key
    (n_workers / worker_subsets / worker_meta / dropped_dispatches) when
    --workers >= 2; serial mode snapshot is byte-exact unchanged
    (parallel_metadata key absent). schema_version stays at 1.
  * additive: ``ProbeThresholds.g4_position_hz`` (default 0.10 Hz) for v3
    Discrete responder-signature bucketing under EMT coupling. Not yet
    wired into _verdict (D1 follow-up 2026-05-03).
  * verdict-semantics: G4 may still REJECT under v3 Discrete at default
    1 mHz threshold; user/operator should switch to g4_position_hz once
    _verdict is updated.
  * E2E 2026-05-03 verdict: GATE-G15/WALL/LIC PASS @ N=4, 2.92× speedup
    (47.9 min serial → 16.4 min parallel). GATE-PHYS partial (12/15
    dispatches bit-exact 1e-9; 3 LoadStep/hybrid dispatches diverge —
    serial-mode latent state-contamination bug exposed by P2, separate
    follow-up).
  * docs/decisions/2026-05-03-probe-state-phase4-p2-parallelization.md
    records the 6 decisions; quality_reports/specs+plans land alongside.
- 0.5.0 (2026-05-01) — Evidence-Pack boundary: ERROR verdict + reason_codes.
  * verdict-semantics: phases that errored (snapshot[phaseN].error present)
    now route to ``verdict="ERROR"`` instead of being silently absorbed into
    PENDING by the ``_phase3()/_phase4()`` helpers. PENDING now strictly
    means "data insufficient" (re-run the missing phase); ERROR strictly
    means "pipeline broke" (re-run won't self-heal — fix code or env).
  * verdict-semantics: G1/G2/G4 missing-field paths (`get(..., 0)` /
    `or []` silent fallbacks) now emit PENDING + ``MISSING_FIELD`` reason
    codes instead of fabricating REJECT verdicts from zero values. G3
    EMPTY_DATA path likewise distinguished from REJECT.
  * additive: every gate verdict dict now carries ``reason_codes:
    list[str]`` drawn from the frozen ``REASON_CODES`` vocabulary. Empty
    lists are a contract violation (asserted at write time).
  * additive: ``VERDICT_ERROR = "ERROR"`` is a new value of the existing
    ``verdict`` string field; no field renamed/removed/repurposed, so
    ``schema_version`` stays at 1. Old snapshots remain readable; ``--diff``
    treats missing reason_codes as ``[]`` automatically via the field-
    agnostic walk in ``_diff.py`` (no _diff.py code change required).
  * Phase B/C reporting metrics (r_h_global, r_d_global, ablation_diffs)
    are intentionally NOT touched — they don't feed verdicts under the
    G6 contract (G6_partial uses only r_f_global). Out-of-scope per the
    boundary contract: no experiment/training/paper-alignment changes.
  * AGENTS.md §8 cross-snapshot paper-anchor unlock recipe DELETED —
    anchor unlock is owned by the consuming agent, not the probe.
  Snapshot-level effect: snapshots with phase*.error fields will now
  emit ERROR (was PENDING) for the affected gate; missing-field paths
  in fresh phase4 data will now emit PENDING (was REJECT or REJECT-like
  zero counts). Cross-version --diff WARNs on impl_version mismatch.
- 0.4.1 (2026-05-01) — verdict-semantics fixes from external code review:
  * P1: R1 now PENDING when Phase B baseline eval-config (scenario_set /
    n_scenarios) does not match Phase C no_rf eval. Pre-0.4.1 silently
    compared incommensurable r_f_global populations and could emit
    PASS or REJECT on non-comparable data.
  * P2a: ``_extract_metrics`` now returns an error payload when paper_eval
    JSON is missing ``cumulative_reward_global_rf`` or its dict shape
    lacks the ``unnormalized`` key. Pre-0.4.1 fell back to r_f_global=0.0,
    erroneously marking R1 REJECT (no_rf "looks better than baseline")
    instead of PENDING.
  * P2b: G4 responder floor now sourced from ``THRESHOLDS.g1_respond_hz``
    (was hardcoded 1e-3). G1 / G4 cannot desynchronise across threshold tunes.
  * P3: report template literal ``{ts}`` placeholder fixed (cosmetic).
  * Phase B baseline run now records ``scenario_set`` + ``n_scenarios``
    (additive schema, schema_version=1 unchanged); used by P1 guard.
  Snapshot-level effect: some snapshots that pre-0.4.1 emitted PASS / REJECT
  on Phase C R1 will emit PENDING under 0.4.1. Cross-version --diff
  WARNs on impl_version mismatch.
- 0.4.0 (2026-05-01) — F1 thresholds externalised; F5 impl_version added;
  F2 ``--diff`` CLI added. Phase A+B+C verdict logic unchanged (numeric
  values preserved); only sourcing layer changed.
- 0.3.0 (2026-05-01) — Phase C v1 added (G6 composite verdict + R1).
- 0.2.0 (2026-05-01) — Phase B added (G6 partial verdict + ablation).
- 0.1.0 (2026-04-30) — Phase A initial (G1-G5 verdict + 4 sim phases).
"""
