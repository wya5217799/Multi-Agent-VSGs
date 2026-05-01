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
        expected_min_df_hz=0.30,
        mag_unit="sys-pu (total budget)",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="F4_V3_RETRAIN_FINAL_VERDICT.md (mean 0.65 Hz)",
    ),
    # =====================================================================
    # LoadStep R-branch — name-valid only (compile-frozen at FastRestart)
    # =====================================================================
    "loadstep_paper_bus14": DispatchMetadata(
        "loadstep_paper_bus14", "load_step_r", "bus_14",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_drop",
        "Series RLC R load engage at bus 14. Compile-frozen — NOT effective.",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="NOTES.md '2026-04-29 Eval 协议偏差' (R-block frozen)",
    ),
    "loadstep_paper_bus15": DispatchMetadata(
        "loadstep_paper_bus15", "load_step_r", "bus_15",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_drop",
        "Series RLC R load engage at bus 15. Compile-frozen — NOT effective.",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="NOTES.md '2026-04-29 Eval 协议偏差'",
    ),
    "loadstep_paper_random_bus": DispatchMetadata(
        "loadstep_paper_random_bus", "load_step_r", "random",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_drop",
        "Random Series RLC R bus. NOT effective (compile-frozen).",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="NOTES.md '2026-04-29 Eval 协议偏差'",
    ),
    # =====================================================================
    # CCS injection at ESS terminal (Bus 14/15) — name-valid, ~0.01 Hz
    # =====================================================================
    "loadstep_paper_trip_bus14": DispatchMetadata(
        "loadstep_paper_trip_bus14", "ccs_inject_ess", "bus_14",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_rise",
        "CCS trip injection at bus 14 ESS terminal; ~0.01 Hz signal — NOT effective.",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="OPTION_E_ABORT_VERDICT (Phasor decay)",
    ),
    "loadstep_paper_trip_bus15": DispatchMetadata(
        "loadstep_paper_trip_bus15", "ccs_inject_ess", "bus_15",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_rise",
        "CCS trip injection at bus 15 ESS terminal; ~0.01 Hz signal — NOT effective.",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="OPTION_E_ABORT_VERDICT",
    ),
    "loadstep_paper_trip_random_bus": DispatchMetadata(
        "loadstep_paper_trip_random_bus", "ccs_inject_ess", "random",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_rise",
        "Random CCS trip injection. NOT effective.",
        expected_min_df_hz=0.005,
        mag_unit="sys-pu -> W via cfg.sbase_va",
        t_trigger_s=_DEFAULT_T_TRIG,
        historical_source="OPTION_E_ABORT_VERDICT",
    ),
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
