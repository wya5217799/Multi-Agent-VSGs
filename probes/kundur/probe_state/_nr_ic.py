# FACT: this module reports values verbatim from
# scenarios/kundur/kundur_ic_cvs_v3.json. Anything stronger than "verbatim
# read + a single derived sum" is CLAIM and stays out.
"""Phase 2 — read NR/IC JSON, dump key fields.

No MATLAB required. The IC JSON is the build-time NR ground truth and
treated as read-only.

The plan asks for ``aggregate_residual_pu < 1e-6``. The IC schema does
NOT store a single scalar residual; the closest is
``physical_invariants_checked`` (list of named checks the build script
ran). We dump that list verbatim plus a derived
``global_balance_sum_sys_pu`` (sum of per-source MW totals — should
be close to 0 if the dispatch is balanced).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from probes.kundur.probe_state.probe_state import ModelStateProbe

REPO_ROOT = Path(__file__).resolve().parents[3]
IC_JSON = REPO_ROOT / "scenarios/kundur/kundur_ic_cvs_v3.json"


def run(probe: "ModelStateProbe") -> dict[str, Any]:
    if not IC_JSON.exists():
        raise FileNotFoundError(
            f"IC JSON not found at {IC_JSON} — Phase 2 cannot proceed"
        )

    ic = json.loads(IC_JSON.read_text(encoding="utf-8"))

    gb = ic.get("global_balance", {}) or {}
    p_load = float(gb.get("p_load_total_sys_pu", 0.0))
    p_gen = float(gb.get("p_gen_paper_sys_pu", 0.0))
    p_wind = float(gb.get("p_wind_paper_sys_pu", 0.0))
    p_ess = float(gb.get("p_ess_total_sys_pu", 0.0))
    p_loss = float(gb.get("p_loss_sys_pu", 0.0))
    # Convention from build_powerlib_kundur: p_load_total_sys_pu is signed
    # negative. Sum of all sources + losses + load should be ≈ 0.
    balance_residual = p_load + p_gen + p_wind + p_ess + p_loss

    return {
        "ic_path": str(IC_JSON.relative_to(REPO_ROOT)),
        "schema_version": ic.get("schema_version"),
        "topology_variant": ic.get("topology_variant"),
        "source_hash": ic.get("source_hash"),
        "decisions": ic.get("decisions"),
        "vsg_pm0_pu": list(ic.get("vsg_pm0_pu", [])),
        "sg_pm0_sys_pu": list(ic.get("sg_pm0_sys_pu", [])),
        "vsg_terminal_voltage_mag_pu": list(
            ic.get("vsg_terminal_voltage_mag_pu", [])
        ),
        "vsg_terminal_voltage_angle_rad": list(
            ic.get("vsg_terminal_voltage_angle_rad", [])
        ),
        "sg_terminal_voltage_mag_pu": list(
            ic.get("sg_terminal_voltage_mag_pu", [])
        ),
        "sg_terminal_voltage_angle_rad": list(
            ic.get("sg_terminal_voltage_angle_rad", [])
        ),
        "physical_invariants_checked": list(
            ic.get("physical_invariants_checked", [])
        ),
        "no_hidden_slack": bool(gb.get("no_hidden_slack", False)),
        "p_load_total_sys_pu": p_load,
        "p_gen_paper_sys_pu": p_gen,
        "p_wind_paper_sys_pu": p_wind,
        "p_ess_total_sys_pu": p_ess,
        "p_loss_sys_pu": p_loss,
        "global_balance_sum_sys_pu": balance_residual,
        "p_balance_per_bus_checked": (
            "p_balance_per_bus" in ic.get("physical_invariants_checked", [])
        ),
    }
