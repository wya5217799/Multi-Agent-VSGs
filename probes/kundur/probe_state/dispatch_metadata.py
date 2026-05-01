# FACT: this module's dictionary is itself a CLAIM authored by a human.
# The single source of truth for "what dispatches exist" is
# scenarios.kundur.disturbance_protocols.known_disturbance_types(); the
# probe verifies coverage at runtime and WARNs on any dispatch missing
# metadata. Magnitudes / sim_s here are project-historical defaults, not
# paper FACT.
"""Per-dispatch metadata for Phase 4.

Plan §5 / F3: cross-dispatch comparison has a systematic bias because
physical semantics differ (e.g. SG-side Pm step vs ESS-side Pm step).
This module attaches per-dispatch defaults so Phase 4 can give each
dispatch its own appropriate ``magnitude_sys_pu`` / ``sim_duration_s``.

Design:
- ``METADATA``: dict keyed by ``known_disturbance_types()`` strings.
- ``get_metadata(name)``: returns DispatchMetadata or a fallback record
  with ``metadata_missing=True`` (Phase 4 will fall back to probe-global
  defaults and surface a WARN).

Adding a new dispatch:
1. Add the entry in ``scenarios/kundur/disturbance_protocols.py``
   (single source of truth — that's what makes it "known").
2. Add a metadata row HERE. If you forget, ``coverage_check()`` flags it
   the next time the probe runs.
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


# Default metadata; magnitudes follow project history (probe B mag=±0.5,
# F4 hybrid mag=+0.5). Override at probe construction with --dispatch-mag /
# --sim-duration to reproduce historical sweeps.
_DEFAULT_MAG = 0.5
_DEFAULT_SIM_S = 5.0

METADATA: dict[str, DispatchMetadata] = {
    # ESS Pm-step proxies (single agent)
    "pm_step_single_es1": DispatchMetadata(
        "pm_step_single_es1", "pm_step_single", "ES1",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS-side Pm step on agent 0 (Bus 12)",
    ),
    "pm_step_single_es2": DispatchMetadata(
        "pm_step_single_es2", "pm_step_single", "ES2",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS-side Pm step on agent 1 (Bus 16)",
    ),
    "pm_step_single_es3": DispatchMetadata(
        "pm_step_single_es3", "pm_step_single", "ES3",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS-side Pm step on agent 2 (Bus 14)",
    ),
    "pm_step_single_es4": DispatchMetadata(
        "pm_step_single_es4", "pm_step_single", "ES4",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS-side Pm step on agent 3 (Bus 15)",
    ),
    "pm_step_single_vsg": DispatchMetadata(
        "pm_step_single_vsg", "pm_step_single", "vsg_indices_param",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "Legacy ESS Pm-step proxy; requires vsg_indices argument.",
    ),
    # ESS Pm-step at proxy bus
    "pm_step_proxy_bus7": DispatchMetadata(
        "pm_step_proxy_bus7", "ess_pm_step", "bus_7",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS Pm step targeting agent at electrical bus 7 (proxy).",
    ),
    "pm_step_proxy_bus9": DispatchMetadata(
        "pm_step_proxy_bus9", "ess_pm_step", "bus_9",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS Pm step targeting agent at electrical bus 9 (proxy).",
    ),
    "pm_step_proxy_random_bus": DispatchMetadata(
        "pm_step_proxy_random_bus", "ess_pm_step", "random_bus",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "ESS Pm step at randomly chosen proxy bus (7 or 9).",
    ),
    # SG Pm-step proxies (Z1)
    "pm_step_proxy_g1": DispatchMetadata(
        "pm_step_proxy_g1", "sg_pm_step", "G1",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "SG-side Pm step at G1 (paper-form-correct).",
    ),
    "pm_step_proxy_g2": DispatchMetadata(
        "pm_step_proxy_g2", "sg_pm_step", "G2",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "SG-side Pm step at G2.",
    ),
    "pm_step_proxy_g3": DispatchMetadata(
        "pm_step_proxy_g3", "sg_pm_step", "G3",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "SG-side Pm step at G3.",
    ),
    "pm_step_proxy_random_gen": DispatchMetadata(
        "pm_step_proxy_random_gen", "sg_pm_step", "random_gen",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "Random SG Pm step at G1/G2/G3.",
    ),
    # Hybrid (Option F4 — multi-point dispatch)
    "pm_step_hybrid_sg_es": DispatchMetadata(
        "pm_step_hybrid_sg_es", "hybrid", "sg+ess_compensate",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "SG step + ESS compensate (Option F4 multi-point). Largest expected "
        "max|Δf| in current model.",
    ),
    # LoadStep R-branch (name-valid only — compile-frozen at FastRestart)
    "loadstep_paper_bus14": DispatchMetadata(
        "loadstep_paper_bus14", "load_step_r", "bus_14",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_drop",
        "Series RLC R load engage at bus 14. Compile-frozen — NOT effective.",
    ),
    "loadstep_paper_bus15": DispatchMetadata(
        "loadstep_paper_bus15", "load_step_r", "bus_15",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_drop",
        "Series RLC R load engage at bus 15. Compile-frozen — NOT effective.",
    ),
    "loadstep_paper_random_bus": DispatchMetadata(
        "loadstep_paper_random_bus", "load_step_r", "random",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_drop",
        "Random Series RLC R bus. NOT effective (compile-frozen).",
    ),
    # CCS inject at ESS terminal (Bus 14 / 15) — name-valid, weak signal
    "loadstep_paper_trip_bus14": DispatchMetadata(
        "loadstep_paper_trip_bus14", "ccs_inject_ess", "bus_14",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_rise",
        "CCS trip injection at bus 14 ESS terminal; ~0.01 Hz signal — NOT effective.",
    ),
    "loadstep_paper_trip_bus15": DispatchMetadata(
        "loadstep_paper_trip_bus15", "ccs_inject_ess", "bus_15",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_rise",
        "CCS trip injection at bus 15 ESS terminal; ~0.01 Hz signal — NOT effective.",
    ),
    "loadstep_paper_trip_random_bus": DispatchMetadata(
        "loadstep_paper_trip_random_bus", "ccs_inject_ess", "random",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "freq_rise",
        "Random CCS trip injection. NOT effective.",
    ),
    # CCS at paper Fig.3 load centers (Option E) — name-valid, electrically
    # dormant (Bus 7/9 < 0.01 Hz response, see OPTION_E_ABORT_VERDICT.md).
    "loadstep_paper_ccs_bus7": DispatchMetadata(
        "loadstep_paper_ccs_bus7", "ccs_load_center", "bus_7",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "CCS at paper load center bus 7. NOT effective in current build.",
    ),
    "loadstep_paper_ccs_bus9": DispatchMetadata(
        "loadstep_paper_ccs_bus9", "ccs_load_center", "bus_9",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "CCS at paper load center bus 9. NOT effective in current build.",
    ),
    "loadstep_paper_ccs_random_load": DispatchMetadata(
        "loadstep_paper_ccs_random_load", "ccs_load_center", "random",
        _DEFAULT_MAG, _DEFAULT_SIM_S, "either",
        "Random CCS load center. NOT effective.",
    ),
}


def get_metadata(name: str) -> dict:
    """Return metadata as a plain dict; ``metadata_missing`` on cache miss.

    The fallback record carries ``default_magnitude_sys_pu`` / ``...sim_s``
    set to ``None`` so callers fall back to probe-global defaults.
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
