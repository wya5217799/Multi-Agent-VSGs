"""Legacy CVS disturbance dispatch — byte-level oracle for P2 regression.

Verbatim copy of ``KundurSimulinkEnv._apply_disturbance_backend`` CVS branch
(lines 814-1048 at HEAD = P0 commit ``0af9813``). Used by
``tests/test_disturbance_protocols.py`` to verify that the new adapter
classes in ``scenarios/kundur/disturbance_protocols.py`` produce
byte-identical workspace-var write sequences.

Spec contract (Y1, MAY-tier): this file is removed once C4 (P4) is
complete and the new path has been exercised on the full smoke matrix.
DO NOT edit unless the upstream god method changes — drift here
defeats the byte-level regression.

Out of scope: SPS legacy fall-through (env lines 1050-1069). The
oracle raises ValueError on non-CVS profiles; callers must filter.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from scenarios.kundur.workspace_vars import resolve as _ws_resolve

logger = logging.getLogger(__name__)


def legacy_apply_disturbance_cvs(
    *,
    bridge: Any,
    disturbance_type: str,
    magnitude: float,
    rng: np.random.Generator,
    t_now: float,
    cfg: Any,
    vsg_indices: tuple[int, ...] = (0,),
) -> None:
    """Apply a Kundur CVS disturbance via the legacy god-method dispatch.

    Parameters mirror the new ``DisturbanceProtocol.apply`` signature so
    tests can run both paths against the same fake bridge under matching
    inputs.

    The function calls ``bridge.apply_workspace_var(name, value)`` for
    every variable the god method would write, in the same order, with
    the same name (resolved via the typed ``workspace_vars.resolve``
    schema) and the same value.
    """
    if cfg.model_name not in ("kundur_cvs", "kundur_cvs_v3"):
        raise ValueError(
            f"legacy oracle only handles CVS profiles, got "
            f"{cfg.model_name!r}"
        )

    profile = cfg.model_name
    n_agents = cfg.n_agents

    def _ws(key: str, **kwargs: Any) -> str:
        return _ws_resolve(
            key, profile=profile, n_agents=n_agents, **kwargs
        )

    dtype = disturbance_type

    # ------------------------------------------------------------------
    # Phase A LoadStep dispatch (env lines 836-954)
    # ------------------------------------------------------------------
    ls_bus_label: str | None = None
    ls_action: str | None = None
    if dtype == "loadstep_paper_bus14":
        ls_bus_label, ls_action = "bus14", "trip"
    elif dtype == "loadstep_paper_bus15":
        ls_bus_label, ls_action = "bus15", "engage"
    elif dtype == "loadstep_paper_random_bus":
        if float(rng.random()) < 0.5:
            ls_bus_label, ls_action = "bus14", "trip"
        else:
            ls_bus_label, ls_action = "bus15", "engage"
    elif dtype == "loadstep_paper_trip_bus14":
        ls_bus_label, ls_action = "bus14", "cc_inject"
    elif dtype == "loadstep_paper_trip_bus15":
        ls_bus_label, ls_action = "bus15", "cc_inject"
    elif dtype == "loadstep_paper_trip_random_bus":
        ls_bus_label = (
            "bus14" if float(rng.random()) < 0.5 else "bus15"
        )
        ls_action = "cc_inject"

    if ls_bus_label is not None and ls_action is not None:
        amp_w = abs(float(magnitude)) * cfg.sbase_va
        other_label = "bus15" if ls_bus_label == "bus14" else "bus14"
        ls_bus_int = int(ls_bus_label[3:])
        other_bus_int = int(other_label[3:])

        if ls_action == "trip":
            bridge.apply_workspace_var(
                _ws("LOAD_STEP_AMP", bus=ls_bus_int,
                    require_effective=True), 0.0
            )
            bridge.apply_workspace_var(
                _ws("LOAD_STEP_TRIP_AMP", bus=ls_bus_int,
                    require_effective=True), 0.0
            )
            bridge.apply_workspace_var(
                _ws("LOAD_STEP_TRIP_AMP", bus=other_bus_int,
                    require_effective=True), 0.0
            )
        elif ls_action == "engage":
            bridge.apply_workspace_var(
                _ws("LOAD_STEP_AMP", bus=ls_bus_int,
                    require_effective=True), amp_w
            )
            bridge.apply_workspace_var(
                _ws("LOAD_STEP_TRIP_AMP", bus=ls_bus_int,
                    require_effective=True), 0.0
            )
            bridge.apply_workspace_var(
                _ws("LOAD_STEP_TRIP_AMP", bus=other_bus_int,
                    require_effective=True), 0.0
            )
        else:  # cc_inject
            bridge.apply_workspace_var(
                _ws("LOAD_STEP_TRIP_AMP", bus=ls_bus_int,
                    require_effective=True), amp_w
            )
            bridge.apply_workspace_var(
                _ws("LOAD_STEP_TRIP_AMP", bus=other_bus_int,
                    require_effective=True), 0.0
            )

        # Zero Pm-step proxies so dispatch types don't compound.
        for i in range(1, n_agents + 1):
            bridge.apply_workspace_var(_ws("PM_STEP_T",   i=i), t_now)
            bridge.apply_workspace_var(_ws("PM_STEP_AMP", i=i), 0.0)
        for g in range(1, 4):
            bridge.apply_workspace_var(_ws("PMG_STEP_T",   g=g), t_now)
            bridge.apply_workspace_var(_ws("PMG_STEP_AMP", g=g), 0.0)
        return

    # ------------------------------------------------------------------
    # Z1 SG-side dispatch (env lines 956-1000)
    # ------------------------------------------------------------------
    sg_target_idx: int | None = None
    if dtype == "pm_step_proxy_g1":
        sg_target_idx = 1
    elif dtype == "pm_step_proxy_g2":
        sg_target_idx = 2
    elif dtype == "pm_step_proxy_g3":
        sg_target_idx = 3
    elif dtype == "pm_step_proxy_random_gen":
        sg_target_idx = int(rng.integers(1, 4))

    if sg_target_idx is not None:
        amp_focused_pu = float(magnitude)
        for g in range(1, 4):
            bridge.apply_workspace_var(_ws("PMG_STEP_T",   g=g), t_now)
            bridge.apply_workspace_var(_ws("PMG_STEP_AMP", g=g), 0.0)
        bridge.apply_workspace_var(
            _ws("PMG_STEP_AMP", g=sg_target_idx), amp_focused_pu
        )
        for i in range(1, n_agents + 1):
            bridge.apply_workspace_var(_ws("PM_STEP_T",   i=i), t_now)
            bridge.apply_workspace_var(_ws("PM_STEP_AMP", i=i), 0.0)
        return

    # ------------------------------------------------------------------
    # ESS-side Pm-step proxy (env lines 1002-1048)
    # ------------------------------------------------------------------
    if dtype == "pm_step_proxy_bus7":
        target_indices: tuple[int, ...] = (0,)
    elif dtype == "pm_step_proxy_bus9":
        target_indices = (3,)
    elif dtype == "pm_step_proxy_random_bus":
        if float(rng.random()) < 0.5:
            target_indices = (0,)
        else:
            target_indices = (3,)
    else:  # pm_step_single_vsg (legacy default)
        target_indices = tuple(vsg_indices)

    n_tgt = max(len(target_indices), 1)
    amp_focused_pu = float(magnitude) / n_tgt
    amps_per_vsg = [0.0] * n_agents
    for idx in target_indices:
        if 0 <= idx < n_agents:
            amps_per_vsg[idx] = amp_focused_pu

    for i in range(1, n_agents + 1):
        bridge.apply_workspace_var(_ws("PM_STEP_T",   i=i), t_now)
        bridge.apply_workspace_var(
            _ws("PM_STEP_AMP", i=i), amps_per_vsg[i - 1]
        )
    for g in range(1, 4):
        bridge.apply_workspace_var(_ws("PMG_STEP_T",   g=g), t_now)
        bridge.apply_workspace_var(_ws("PMG_STEP_AMP", g=g), 0.0)
    return


__all__ = ["legacy_apply_disturbance_cvs"]
