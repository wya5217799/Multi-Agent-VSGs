# FACT: this module's METADATA dict is itself a CLAIM authored by a human.
# The single source of truth for "what dispatches exist" is
# scenarios.kundur.disturbance_protocols.known_disturbance_types(); the
# probe verifies coverage at runtime and WARNs on any dispatch missing
# metadata. Magnitudes / sim_s / expected_min_df_hz here are
# project-historical defaults derived from past verdicts, not paper FACT.
"""Per-dispatch metadata for Phase 4.

Plan §5 / F3 (design §5.7): cross-dispatch comparison has a systematic
bias because physical semantics differ. This module attaches per-dispatch
defaults so Phase 4 can give each dispatch its own appropriate
``magnitude_sys_pu`` / ``sim_duration_s``, AND auto-flag observed Phase 4
results that fall below the historically-known signal floor
(``expected_min_df_hz``, G4 reconciliation 2026-05-01).

Schema (design §5.7) — additive over the original 7 fields:

| field                     | meaning                                                  |
|---------------------------|----------------------------------------------------------|
| name                      | dispatch ID (key into ``known_disturbance_types()``)     |
| family                    | physics family — ess_pm_step / sg_pm_step / hybrid / ... |
| target_descriptor         | dispatch target (bus_7 / G1 / random_gen / ...)          |
| default_magnitude_sys_pu  | mag the probe uses at this dispatch                      |
| default_sim_duration_s    | sim seconds                                              |
| expected_behavior         | freq_drop / freq_rise / either                           |
| notes                     | (legacy alias of physics_note)                           |
| **expected_min_df_hz**    | known-good signal floor; Phase 4 ``max\\|Δf\\|`` < this  |
|                           | ⇒ ``below_expected_floor=True`` flag                     |
| **mag_unit**              | unit semantics of magnitude (sys-pu SG cap / total / W)  |
| **t_trigger_s**           | trigger time within sim window                           |
| **historical_source**     | where this floor came from (verdict / artifact)          |

``expected_min_df_hz = None`` is allowed for dispatches with no
historical floor; Phase 4 emits ``expected_floor_unknown=True`` then.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class DispatchMetadata:
    name: str
    family: str  # 'ess_pm_step' | 'sg_pm_step' | 'load_step_r' |
                 # 'ccs_inject_ess' | 'ccs_load_center' | 'hybrid' |
                 # 'pm_step_single'
    target_descriptor: str  # 'bus_7' | 'G1' | 'random_bus' | etc.
    default_magnitude_sys_pu: float
    default_sim_duration_s: float
    expected_behavior: str  # 'freq_drop' | 'freq_rise' | 'either'
    notes: str = ""
    # G4 fields (added 2026-05-01, design §5.7):
    expected_min_df_hz: float | None = None
    """Known-good signal floor (Hz). Phase 4 max|Δf| below this triggers
    ``below_expected_floor`` flag. None = no historical floor recorded;
    Phase 4 emits ``expected_floor_unknown`` instead."""
    expected_max_df_hz: float | None = None
    """Known-good signal ceiling (Hz) — runaway-divergence detection
    (I5 review fix 2026-05-01). Phase 4 max|Δf| above this triggers
    ``above_expected_ceiling`` flag. None = no ceiling recorded
    (default); use sparingly — only set when you have a tight historical
    upper bound (e.g. F4 hybrid mean is 0.65 Hz so 1.5 Hz on the same
    dispatch is anomalous; ceiling 1.0 Hz catches that)."""
    mag_unit: str = "sys-pu"
    """Magnitude semantics. Common values: ``sys-pu`` (default — sys-pu
    on SBASE), ``sys-pu (SG cap)`` (fraction of generator capacity),
    ``sys-pu (total budget)`` (split across multiple targets), ``W``
    (when amplitude is pushed in watts via cfg.sbase_va)."""
    t_trigger_s: float = 0.5
    """Trigger time inside the sim window (s). 0.5 default = post-warmup
    typical."""
    historical_source: str = ""
    """Verdict or artifact path the ``expected_min_df_hz`` came from."""
    expected_df_hz_per_sys_pu: float | None = None
    """Linear-scaled Δf floor per unit of applied magnitude (Hz / sys-pu).
    When set, takes precedence over ``expected_min_df_hz`` for floor checks:
    effective_floor = expected_df_hz_per_sys_pu * |applied_magnitude_sys_pu|.
    None = use static ``expected_min_df_hz`` field.
    Calibration: derived from historical verdict mean Δf ÷ mean magnitude.
    P1-2 recalibration (2026-05-04): pm_step_hybrid_sg_es at mag=1.55 sys-pu
    produced mean 0.65 Hz → 0.65/1.55 ≈ 0.42 Hz/sys-pu (retro §3.5, D2)."""


# Common defaults (project history: probe B mag=±0.5, F4 hybrid mag=+0.5,
# 5 s sim window with 0.5 s trigger). Override at probe construction with
# --dispatch-mag / --sim-duration to reproduce historical sweeps.
_DEFAULT_MAG = 0.5
_DEFAULT_SIM_S = 5.0
_DEFAULT_T_TRIG = 0.5


METADATA: dict[str, DispatchMetadata] = {
    # =====================================================================
    # ESS Pm-step proxies (single agent — Probe B-ESS family, 2026-04-30)
    # =====================================================================
    "pm_step_single_es1": DispatchMetadata(
        "pm_step_single_es1", "pm_step_single", "ES1",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS-side Pm step on agent 0 (Bus 12)",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (single-ESS Pm)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="cvs_v3_probe_b_ess (2026-04-30 Branch A PASS)",
    ),
    "pm_step_single_es2": DispatchMetadata(
        "pm_step_single_es2", "pm_step_single", "ES2",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS-side Pm step on agent 1 (Bus 16)",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (single-ESS Pm)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="cvs_v3_probe_b_ess",
    ),
    "pm_step_single_es3": DispatchMetadata(
        "pm_step_single_es3", "pm_step_single", "ES3",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS-side Pm step on agent 2 (Bus 14)",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (single-ESS Pm)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="cvs_v3_probe_b_ess",
    ),
    "pm_step_single_es4": DispatchMetadata(
        "pm_step_single_es4", "pm_step_single", "ES4",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS-side Pm step on agent 3 (Bus 15)",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (single-ESS Pm)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="cvs_v3_probe_b_ess",
    ),
    "pm_step_single_vsg": DispatchMetadata(
        "pm_step_single_vsg", "pm_step_single", "vsg_indices_param",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "Legacy ESS Pm-step proxy; requires vsg_indices argument.",
        expected_min_df_hz=None,  # legacy path, no fresh historical anchor
        mag_unit="sys-pu (single-ESS Pm)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="legacy pre-Probe B",
    ),
    # =====================================================================
    # ESS Pm-step at proxy bus (P0' v2 ESS-side anchor protocol)
    # =====================================================================
    "pm_step_proxy_bus7": DispatchMetadata(
        "pm_step_proxy_bus7", "ess_pm_step", "bus_7",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS Pm step targeting agent at electrical bus 7 (proxy).",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (ESS Pm)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="P0' v2 ESS-side anchor",
    ),
    "pm_step_proxy_bus9": DispatchMetadata(
        "pm_step_proxy_bus9", "ess_pm_step", "bus_9",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS Pm step targeting agent at electrical bus 9 (proxy).",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (ESS Pm)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="P0' v2 ESS-side anchor",
    ),
    "pm_step_proxy_random_bus": DispatchMetadata(
        "pm_step_proxy_random_bus", "ess_pm_step", "random_bus",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS Pm step at randomly chosen proxy bus (7 or 9).",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (ESS Pm)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="P0' v2 ESS-side anchor",
    ),
    # =====================================================================
    # SG Pm-step proxies (Z1, paper-form-correct; Probe B 1.33-of-4 hist)
    # =====================================================================
    "pm_step_proxy_g1": DispatchMetadata(
        "pm_step_proxy_g1", "sg_pm_step", "G1",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "SG-side Pm step at G1 (paper-form-correct).",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (SG cap)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="Z1 (2026-04-27); design §5.7 example",
    ),
    "pm_step_proxy_g2": DispatchMetadata(
        "pm_step_proxy_g2", "sg_pm_step", "G2",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "SG-side Pm step at G2.",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (SG cap)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="cvs_v3_probe_b/probe_b_pos_gen_b2.json (1.33-of-4)",
    ),
    "pm_step_proxy_g3": DispatchMetadata(
        "pm_step_proxy_g3", "sg_pm_step", "G3",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "SG-side Pm step at G3.",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (SG cap)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="Z1 (2026-04-27)",
    ),
    "pm_step_proxy_random_gen": DispatchMetadata(
        "pm_step_proxy_random_gen", "sg_pm_step", "random_gen",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "Random SG Pm step at G1/G2/G3.",
        expected_min_df_hz=0.05,
        mag_unit="sys-pu (SG cap)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="P1b pilot (per_M=-16.14 ≈ paper -15.20 at DIST_MAX=3.0)",
    ),
    # =====================================================================
    # Hybrid (Option F4 — multi-point dispatch, F4 v3 +18% RL improvement)
    # =====================================================================
    "pm_step_hybrid_sg_es": DispatchMetadata(
        "pm_step_hybrid_sg_es", "hybrid", "sg+ess_compensate",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "SG step + ESS compensate (Option F4 multi-point). Largest expected "
        "max|Δf| in current model.",
        # P1-2 (2026-05-04): static floor replaced by per-sys-pu linear scaling
        # (retro §3.5, D2 follow-up). Old static 0.30 Hz was calibrated at
        # mag=1.55 mean; probe runs at mag=0.5 → false-alarm at 0.18-0.21 Hz.
        # Derived: 0.65 Hz / 1.55 sys-pu = 0.42 Hz/sys-pu.
        # At probe mag=0.5: effective_floor = 0.42 * 0.5 = 0.21 Hz ≈ observed.
        expected_min_df_hz=None,  # nulled; per-sys-pu field takes precedence
        expected_max_df_hz=1.0,  # F4 v3 mean 0.65 Hz; 1.0 Hz catches runaway
        mag_unit="sys-pu (total budget)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="F4_V3_RETRAIN_FINAL_VERDICT.md (mean 0.65 Hz at mag≈1.55)",
        expected_df_hz_per_sys_pu=0.42,
    ),
    # =====================================================================
    # LoadStep paper-lumped ΔP via Pm_step (Phase 1.5 reroute 2026-05-04)
    # =====================================================================
    # CCS path (P0-1c) abandoned: 62× weaker than paper LS1 baseline.
    # Paper §1.4 Remark 1 (Kron reduction): LS1/LS2 lumped as Pm_step on
    # co-located ESS (ES3=bus14 for LS1, ES4=bus15 for LS2).
    # Magnitudes calibrated EMPIRICALLY (2026-05-04 sanity sweep):
    #   Quadratic fit reward ≈ K × amp² (overdamped system, ζ=2.81 per A2):
    #     K_LS1 = -0.69 / amp²  → target -1.61 → amp = 1.53 sys-pu
    #     K_LS2 = -0.99 / amp²  → target -0.80 → amp = 0.90 sys-pu
    #   Direct verify: amp=1.53 → -1.81 (LS1, +12% target), amp=-0.90 → -0.83 (LS2, +3%)
    #   Both within G1.5-B/C ±25% tolerance.
    # NOTE: paper "248 MW absolute" does NOT map to our Sbase=100 MVA system.
    #   At amp=2.48 sys-pu, ES3 system goes nonlinear/unstable (max|Δf|=19 Hz).
    #   Empirical 1.53/0.90 is paper-equivalent perturbation in our system.
    # ES3/ES4 max|Δf| at paper-equivalent: 0.39 Hz / 0.23 Hz — falls in
    #   A2 physics upper bound [0.30, 0.52] Hz. Two metrics agree.
    "loadstep_paper_bus14": DispatchMetadata(
        "loadstep_paper_bus14", "paper_lumped_pm_step", "ES3(bus14)",
        1.53, _DEFAULT_SIM_S, "freq_rise",
        "Phase 1.5 reroute (2026-05-04): paper LS1 via PM_STEP_AMP@ES3 "
        "(bus14 ESS). Positive Pm_step → freq UP (paper LS1 load reduction). "
        "Default magnitude 1.53 sys-pu (empirically calibrated to match "
        "paper §8.4 LS1 reward = -1.61 Hz²; at amp=2.48 system blows up). "
        "Verified 2026-05-04: amp=1.53 → paper_reward=-1.81 (+12% target). "
        "Acceptance gate G1.5-B: paper_reward in [-2.0, -1.2] (±25%). "
        "ES3 max|Δf| ≈ 0.39 Hz (within A2 [0.30, 0.52] Hz physics bound).",
        expected_min_df_hz=0.30,
        expected_max_df_hz=None,
        mag_unit="sys-pu (ES3 Pm_step, empirically calibrated)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="P1.5 reroute sanity sweep (2026-05-04); paper §8.4 LS1",
        expected_df_hz_per_sys_pu=None,
    ),
    "loadstep_paper_bus15": DispatchMetadata(
        "loadstep_paper_bus15", "paper_lumped_pm_step", "ES4(bus15)",
        0.90, _DEFAULT_SIM_S, "freq_drop",
        "Phase 1.5 reroute (2026-05-04): paper LS2 via PM_STEP_AMP@ES4 "
        "(bus15 ESS). Negative Pm_step → freq DOWN (paper LS2 load increase). "
        "Default magnitude 0.90 sys-pu (empirically calibrated to match "
        "paper §8.4 LS2 reward = -0.80 Hz²). "
        "Verified 2026-05-04: amp=-0.90 → paper_reward=-0.83 (+3% target). "
        "Acceptance gate G1.5-C: paper_reward in [-1.0, -0.6] (±25%). "
        "ES4 max|Δf| ≈ 0.23 Hz. Adapter applies negative sign internally.",
        expected_min_df_hz=0.15,
        expected_max_df_hz=None,
        mag_unit="sys-pu (ES4 Pm_step, sign negated by adapter)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="P1.5 reroute sanity sweep (2026-05-04); paper §8.4 LS2",
        expected_df_hz_per_sys_pu=None,
    ),
    "loadstep_paper_random_bus": DispatchMetadata(
        "loadstep_paper_random_bus", "paper_lumped_pm_step", "random(ES3|ES4)",
        1.53, _DEFAULT_SIM_S, "either",
        "Phase 1.5 reroute (2026-05-04): random 50/50 between paper LS1 "
        "(ES3/bus14, freq_rise, amp=1.53) and paper LS2 (ES4/bus15, "
        "freq_drop, amp=0.90 magnitude). Default 1.53 = LS1 scale; "
        "LS2 path uses 0.90 with sign negation. Expected behavior: 'either'.",
        expected_min_df_hz=0.15,
        expected_max_df_hz=None,
        mag_unit="sys-pu (ES3 amp=1.53 or ES4 amp=-0.90 by random pick)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="P1.5 reroute sanity sweep (2026-05-04)",
        expected_df_hz_per_sys_pu=None,
    ),
    # =====================================================================
    # Archived 2026-05-04 (B4 cleanup): loadstep_paper_trip_bus14,
    # loadstep_paper_trip_bus15, loadstep_paper_trip_random_bus
    # (family ccs_inject_ess) were superseded by Phase 1.5 paper-lumped
    # reroute (loadstep_paper_bus14/bus15/random_bus, family
    # paper_lumped_pm_step). The CCS path was measured at 62x weaker than
    # the paper anchor (route_audit.md). Entries removed from active
    # metadata; canonical names are loadstep_paper_bus14, _bus15,
    # _random_bus. Commit history preserves the old entries.
    # =====================================================================
    # CCS at paper Fig.3 load centers (Option E) — name-valid, dormant
    # =====================================================================
    "loadstep_paper_ccs_bus7": DispatchMetadata(
        "loadstep_paper_ccs_bus7", "ccs_load_center", "bus_7",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "CCS at paper load center bus 7. NOT effective in current build.",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="OPTION_E_ABORT_VERDICT (Bus 7/9 << 0.01 Hz)",
    ),
    "loadstep_paper_ccs_bus9": DispatchMetadata(
        "loadstep_paper_ccs_bus9", "ccs_load_center", "bus_9",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "CCS at paper load center bus 9. NOT effective in current build.",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="OPTION_E_ABORT_VERDICT",
    ),
    "loadstep_paper_ccs_random_load": DispatchMetadata(
        "loadstep_paper_ccs_random_load", "ccs_load_center", "random",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "Random CCS load center. NOT effective.",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="OPTION_E_ABORT_VERDICT",
    ),
}


def get_metadata(name: str) -> dict:
    """Return metadata as a plain dict; ``metadata_missing`` on cache miss.

    Always includes both legacy and G4 fields so consumers can rely on a
    stable shape regardless of when the dispatch was registered.
    """
    md = METADATA.get(name)
    if md is None:
        return {
            "name": name,
            "metadata_missing": True,
            "family": "unknown",
            "target_descriptor": "unknown",
            "default_magnitude_sys_pu": None,
            "default_sim_duration_s": None,
            "expected_behavior": "either",
            "notes": "metadata not registered — probe used defaults",
            "expected_min_df_hz": None,
            "expected_max_df_hz": None,
            "expected_df_hz_per_sys_pu": None,
            "mag_unit": "sys-pu",
            "t_trigger_s": None,
            "historical_source": "",
        }
    return {
        "name": md.name,
        "metadata_missing": False,
        "family": md.family,
        "target_descriptor": md.target_descriptor,
        "default_magnitude_sys_pu": md.default_magnitude_sys_pu,
        "default_sim_duration_s": md.default_sim_duration_s,
        "expected_behavior": md.expected_behavior,
        "notes": md.notes,
        "expected_min_df_hz": md.expected_min_df_hz,
        "expected_max_df_hz": md.expected_max_df_hz,
        "expected_df_hz_per_sys_pu": md.expected_df_hz_per_sys_pu,
        "mag_unit": md.mag_unit,
        "t_trigger_s": md.t_trigger_s,
        "historical_source": md.historical_source,
    }


def coverage_check(known_types: Iterable[str]) -> dict:
    """Compare ``METADATA`` keys against the dispatch single-source-of-truth.

    Returns ``{covered, missing_metadata, extra_metadata}``.
    Phase 1 surfaces this in the snapshot so a build-time dispatch addition
    that forgot to update this module is loud at probe time.
    """
    known_set = set(known_types)
    have_set = set(METADATA)
    return {
        "covered": sorted(known_set & have_set),
        "missing_metadata": sorted(known_set - have_set),
        "extra_metadata": sorted(have_set - known_set),
    }
