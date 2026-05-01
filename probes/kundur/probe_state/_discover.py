# FACT: this module's runtime output is the contract; comments explaining
# WHAT it does are CLAIM. WHY-comments stay only when the reason is non-
# obvious (e.g. discovery-strategy fallback chains).
"""Phase 1 — static topology discovery.

Two halves:
- ``_static_from_config``: pure-Python, reads scenario config + IC JSON +
  paper_eval omega-source map. Always runs.
- ``_dynamic_from_matlab``: requires MATLAB engine; queries the live model
  for powergui mode, ToWorkspace block list, solver config. Skipped (with
  ``matlab_unavailable: True`` flag) when engine cannot be obtained.

Discovery rules per plan §3:
- ``n_ess`` derives from `vsg_pm0_pu` length in IC JSON, NOT a hardcoded ``4``.
- Dispatch types come from ``disturbance_protocols.known_disturbance_types()``.
- Effective subset comes from ``workspace_vars.WorkspaceVarSpec.effective_in_profile``.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from probes.kundur.probe_state.probe_state import ModelStateProbe

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]


def run(probe: "ModelStateProbe") -> dict[str, Any]:
    """Phase 1 entry point — composes static + dynamic halves."""
    result: dict[str, Any] = {}
    result.update(_static_from_config())
    result["matlab"] = _dynamic_from_matlab(model_name=result["model_name"])
    # Cross-check: build-script naming convention ⇒ ToWorkspace block Names
    # ``W_omega_ES<digit>`` / ``W_omega_G<digit>`` should agree with IC.
    # Step 0 of plan: if convention drifted, surface the mismatch (build
    # script changed; rerun probe interpretation).
    matlab = result["matlab"]
    warns: list[str] = []
    if matlab.get("omega_tw_count_ess") is not None:
        if matlab["omega_tw_count_ess"] != result["n_ess"]:
            warns.append(
                f"IC n_ess={result['n_ess']} != model "
                f"W_omega_ES* count={matlab['omega_tw_count_ess']} "
                "(build naming drift?)"
            )
    if matlab.get("omega_tw_count_sg") is not None:
        if matlab["omega_tw_count_sg"] != result["n_sg"]:
            warns.append(
                f"IC n_sg={result['n_sg']} != model "
                f"W_omega_G* count={matlab['omega_tw_count_sg']} "
                "(build naming drift?)"
            )
    if warns:
        result["consistency_warnings"] = warns
    return result


# ---------------------------------------------------------------------------
# Static discovery (always runs)
# ---------------------------------------------------------------------------


def _static_from_config() -> dict[str, Any]:
    """Read scenario config / IC / dispatch table without MATLAB."""
    from scenarios.kundur.config_simulink import (
        DEFAULT_KUNDUR_MODEL_PROFILE,
        DIST_MAX,
        DIST_MIN,
        PHI_D,
        PHI_F,
        PHI_H,
        T_EPISODE,
        T_WARMUP,
    )
    from scenarios.kundur.disturbance_protocols import (
        _DISPATCH_TABLE,
        known_disturbance_types,
    )
    from scenarios.kundur.model_profile import load_kundur_model_profile
    from scenarios.kundur.workspace_vars import (
        PROFILE_CVS_V3,
        _SCHEMA,
    )
    from scenarios.config_simulink_base import (
        DD_MAX,
        DD_MIN,
        DM_MAX,
        DM_MIN,
        VSG_D0,
        VSG_M0,
        VSG_SN,
    )
    from evaluation.paper_eval import (
        KUNDUR_CVS_V3_COMM_ADJ,
        KUNDUR_CVS_V3_OMEGA_SOURCES,
    )

    selected_path = os.getenv(
        "KUNDUR_MODEL_PROFILE", str(DEFAULT_KUNDUR_MODEL_PROFILE)
    )
    profile = load_kundur_model_profile(selected_path)

    ic_json_path = REPO_ROOT / "scenarios/kundur" / "kundur_ic_cvs_v3.json"
    ic = json.loads(ic_json_path.read_text(encoding="utf-8"))

    n_ess = len(ic["vsg_pm0_pu"])
    n_sg = len(ic["sg_names"])
    n_wind = len(ic["wind_names"])

    # Effective dispatch subset under active profile.
    profile_name = profile.model_name
    effective_dispatch = sorted(
        d
        for d in _DISPATCH_TABLE
        if _is_dispatch_effective(d, profile_name)
    )
    name_valid_only = sorted(set(_DISPATCH_TABLE) - set(effective_dispatch))

    # Workspace var schema (effective subset per profile).
    ws_effective = {}
    ws_inactive = {}
    for key, spec in _SCHEMA.items():
        if profile_name not in spec.profiles:
            continue
        is_effective = profile_name in spec.effective_in_profile
        ws_effective[key] = is_effective
        if not is_effective and profile_name in spec.inactive_reason:
            ws_inactive[key] = spec.inactive_reason[profile_name]

    # ESS bus map from paper_eval (NOT hardcoded — sourced from canonical
    # build-script-derived metadata table).
    ess_bus_map = {
        src["sname"]: src["bus"] for src in KUNDUR_CVS_V3_OMEGA_SOURCES
    }
    omega_vars_expected = [src["ts_var"] for src in KUNDUR_CVS_V3_OMEGA_SOURCES]

    from probes.kundur.probe_state.dispatch_metadata import coverage_check
    md_coverage = coverage_check(known_disturbance_types())

    return {
        "model_name": profile_name,
        "model_profile_path": selected_path,
        "topology_variant": ic.get("topology_variant"),
        "n_ess": n_ess,
        "n_sg": n_sg,
        "n_wind": n_wind,
        "ess_names": [s["sname"] for s in KUNDUR_CVS_V3_OMEGA_SOURCES],
        "sg_names": list(ic["sg_names"]),
        "wind_names": list(ic["wind_names"]),
        "ess_bus_map": ess_bus_map,
        "omega_vars_expected": omega_vars_expected,
        "comm_adj": {str(k): list(v) for k, v in KUNDUR_CVS_V3_COMM_ADJ.items()},
        "dispatch_total": len(known_disturbance_types()),
        "dispatch_effective": effective_dispatch,
        "dispatch_name_valid_only": name_valid_only,
        "dispatch_metadata_coverage": md_coverage,
        "workspace_vars_effective": ws_effective,
        "workspace_vars_inactive_reason": ws_inactive,
        "config": {
            "phi_f": PHI_F,
            "phi_h": PHI_H,
            "phi_d": PHI_D,
            "dist_min_sys_pu": DIST_MIN,
            "dist_max_sys_pu": DIST_MAX,
            "vsg_m0": VSG_M0,
            "vsg_d0": VSG_D0,
            "vsg_sn": VSG_SN,
            "dm_min": DM_MIN,
            "dm_max": DM_MAX,
            "dd_min": DD_MIN,
            "dd_max": DD_MAX,
            "t_warmup": T_WARMUP,
            "t_episode": T_EPISODE,
        },
    }


def _is_dispatch_effective(disturbance_type: str, profile: str) -> bool:
    """Heuristic: a dispatch is 'effective' if at least one workspace var
    its adapter touches has the active profile in ``effective_in_profile``.

    Falls back to ``True`` for adapters that don't go through the
    workspace_vars schema (e.g. legacy in-block param writes).
    """
    from scenarios.kundur.disturbance_protocols import resolve_disturbance
    from scenarios.kundur.workspace_vars import _SCHEMA

    try:
        adapter = resolve_disturbance(disturbance_type)
    except (ValueError, TypeError) as exc:
        logger.debug("Cannot resolve %s: %s", disturbance_type, exc)
        return False

    # Adapter exposes workspace vars it writes via either ``ws_keys``
    # attribute (if present) or by looking at the ``__class__.__name__`` against
    # known mappings. Default heuristic: scan adapter's ``__dict__`` for any
    # template-shaped string and see if it matches a schema entry.
    ws_keys: set[str] = set()
    for attr in ("ws_keys", "_ws_keys"):
        keys = getattr(adapter, attr, None)
        if keys:
            ws_keys.update(keys)

    if not ws_keys:
        # Best-effort: classify by adapter class name.
        cname = adapter.__class__.__name__
        cmap = {
            "EssPmStepProxy": {"PM_STEP_T", "PM_STEP_AMP"},
            "SgPmgStepProxy": {"PMG_STEP_T", "PMG_STEP_AMP"},
            "LoadStepRBranch": {"LOAD_STEP_AMP"},
            "LoadStepCcsInjection": {"LOAD_STEP_TRIP_AMP"},
            "HybridSgEssMultiPoint": {"PM_STEP_T", "PM_STEP_AMP",
                                       "PMG_STEP_T", "PMG_STEP_AMP"},
        }
        ws_keys = cmap.get(cname, set())
        # LoadStepCcsLoadCenter family — match against name pattern.
        if cname == "LoadStepCcsLoadCenter":
            ws_keys = {
                k for k, spec in _SCHEMA.items()
                if "ccs" in spec.description.lower()
                and "load center" in spec.description.lower()
            }

    if not ws_keys:
        return True  # no schema link → assume effective (back-compat)

    return any(
        profile in _SCHEMA[k].effective_in_profile
        for k in ws_keys
        if k in _SCHEMA
    )


# ---------------------------------------------------------------------------
# Dynamic discovery (needs MATLAB)
# ---------------------------------------------------------------------------


def _dynamic_from_matlab(model_name: str) -> dict[str, Any]:
    try:
        from engine.matlab_session import MatlabSession
    except Exception as exc:  # noqa: BLE001
        return {"matlab_unavailable": True, "reason": f"import: {exc}"}

    try:
        session = MatlabSession.get()
        # Trigger lazy connect via a no-op call.
        session.call("zeros", 1.0, nargout=1)
    except Exception as exc:  # noqa: BLE001
        return {"matlab_unavailable": True, "reason": f"connect: {exc}"}

    try:
        # Add scenarios/kundur/simulink_models so load_system can find the .slx.
        slx_dir = REPO_ROOT / "scenarios/kundur/simulink_models"
        session.eval(f"addpath('{slx_dir.as_posix()}');", nargout=0)
        session.eval(f"load_system('{model_name}');", nargout=0)
    except Exception as exc:  # noqa: BLE001
        return {"matlab_unavailable": True, "reason": f"load_system: {exc}"}

    out: dict[str, Any] = {"matlab_unavailable": False}

    # 1. powergui block — try multiple discovery strategies.
    #    Fallback chain: BlockType match → Name pattern → MaskType pattern.
    #    Different MATLAB versions / Simscape Electrical generations register
    #    powergui under different block-type strings; Name 'powergui' is the
    #    most stable across versions.
    powergui_path = None
    for strategy_name, strategy_args in (
        ("BlockType=PowerGUI", ("BlockType", "PowerGUI")),
        ("BlockType=powergui", ("BlockType", "powergui")),
        ("Name=powergui", ("Name", "powergui")),
        ("Name=Powergui", ("Name", "Powergui")),
    ):
        try:
            cand = session.call(
                "find_system", model_name, *strategy_args, nargout=1
            )
            cand_list = _to_str_list(cand)
            if cand_list:
                powergui_path = cand_list[0]
                out["powergui_strategy"] = strategy_name
                break
        except Exception:  # noqa: BLE001
            continue

    if powergui_path is None:
        out["powergui_mode"] = "no_powergui_block_found"
    else:
        out["powergui_path"] = powergui_path
        # Mode parameter name varies; PhasorSimulation = legacy on/off,
        # SimulationMode = newer dropdown. Try both.
        for param_name in ("PhasorSimulation", "SimulationMode"):
            try:
                val = session.call(
                    "get_param", powergui_path, param_name, nargout=1
                )
                out["powergui_mode"] = str(val)
                out["powergui_mode_param"] = param_name
                break
            except Exception:  # noqa: BLE001
                continue
        else:
            out["powergui_mode"] = "unknown"

    # 2. ToWorkspace blocks classified by Name pattern (build_kundur_cvs_v3.m:
    # add_block 'W_omega_<sname>' where sname ∈ {ES1..N, G1..M}).
    # Plan §0: discovery convention = `W_omega_(ES|G|W)<digit>+`; build script
    # naming is THE source of truth here. Mismatch ⇒ build refactor signal,
    # consistency warning surfaced to caller.
    import re

    name_pat = re.compile(r"^W_omega_(ES|G|W)(\d+)$")
    try:
        tw_paths = session.call(
            "find_system",
            model_name,
            "BlockType", "ToWorkspace",
            nargout=1,
        )
        tw_paths = _to_str_list(tw_paths)
        classified: dict[str, list[dict[str, Any]]] = {
            "ES": [], "G": [], "W": [], "OTHER": [],
        }
        for p in tw_paths:
            block_name = p.split("/")[-1]
            try:
                var = session.call("get_param", p, "VariableName", nargout=1)
                var_s = str(var)
            except Exception:  # noqa: BLE001
                var_s = "<error>"
            rec = {"block": p, "block_name": block_name, "var_name": var_s}
            m = name_pat.match(block_name)
            if m:
                classified[m.group(1)].append(rec)
            elif block_name.startswith("W_omega_"):
                classified["OTHER"].append(rec)
            # Non-omega TW blocks ignored (only omega blocks are interesting
            # for n_ess/n_sg consistency check).
        out["omega_tw_blocks_by_class"] = classified
        out["omega_tw_count_ess"] = len(classified["ES"])
        out["omega_tw_count_sg"] = len(classified["G"])
        out["omega_tw_count_wind"] = len(classified["W"])
        # ``omega_tw_count`` legacy field kept for back-compat invariants:
        # equals ESS-only count (= what should match IC n_ess).
        out["omega_tw_count"] = len(classified["ES"])
    except Exception as exc:  # noqa: BLE001
        out["omega_query_error"] = str(exc)
        out["omega_tw_count"] = None
        out["omega_tw_count_ess"] = None
        out["omega_tw_count_sg"] = None
        out["omega_tw_count_wind"] = None

    # 3. Solver config — concise dump of model-level params that bear on
    # numerical stability (Phasor models are insensitive to most of these but
    # we still record them for reproducibility).
    solver_keys = ("Solver", "StartTime", "StopTime", "FixedStep",
                   "SimulationMode", "FastRestart")
    solver_cfg: dict[str, str] = {}
    for k in solver_keys:
        try:
            val = session.call("get_param", model_name, k, nargout=1)
            solver_cfg[k] = str(val)
        except Exception as exc:  # noqa: BLE001
            solver_cfg[k] = f"<error: {exc}>"
    out["solver"] = solver_cfg

    return out


def _to_str_list(matlab_value: Any) -> list[str]:
    """Coerce a MATLAB cell-array-of-strings or scalar string to ``list[str]``."""
    if matlab_value is None:
        return []
    if isinstance(matlab_value, str):
        return [matlab_value] if matlab_value else []
    try:
        return [str(x) for x in matlab_value]
    except TypeError:
        return [str(matlab_value)]
