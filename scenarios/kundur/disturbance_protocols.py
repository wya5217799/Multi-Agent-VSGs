"""Disturbance dispatch protocols for Kundur CVS.

Replaces the 235-line ``_apply_disturbance_backend`` CVS branch with four
adapter classes, one per workspace-var family. Each adapter is a frozen
value object whose ``apply()`` method receives all dependencies
explicitly (bridge, magnitude, rng, t_now, cfg) and returns a
``DisturbanceTrace`` recording the exact (key, value) sequence written
to MATLAB.

Design references:
  - ``docs/superpowers/plans/2026-04-29-c1-disturbance-protocol-design.md``
  - ``quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md``

Schema layer:
  - ``scenarios/kundur/workspace_vars.py`` — typed workspace-var contract.
    All MATLAB names resolved through ``resolve(...)``; LoadStep
    families pass ``require_effective=True`` to surface the v3
    R-block compile-freeze contract.

Out of scope (deferred to C2 / future):
  - Bridge.warmup ``kundur_cvs_ip`` struct writes.
  - SPS legacy ``apply_disturbance_load`` path (kept as fall-through
    in env._apply_disturbance_backend).
  - NE39 / SPS ``M0_val_ESi`` family.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import numpy as np

from scenarios.kundur.workspace_vars import resolve as _ws_resolve

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trace value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DisturbanceTrace:
    """Record of one dispatch — for monitoring and tests, not control flow.

    ``written_keys`` and ``written_values`` are tuples of equal length;
    each pair (k, v) corresponds to one ``bridge.apply_workspace_var(k, v)``
    call, in the order issued.
    """

    family: str
    target_descriptor: str
    written_keys: tuple[str, ...] = field(default_factory=tuple)
    written_values: tuple[float, ...] = field(default_factory=tuple)
    magnitude_sys_pu: float = 0.0


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class DisturbanceProtocol(Protocol):
    """One disturbance family. Stateless — RNG and bridge per call."""

    def apply(
        self,
        bridge: Any,
        magnitude_sys_pu: float,
        rng: np.random.Generator,
        t_now: float,
        cfg: Any,
    ) -> DisturbanceTrace: ...


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_ws(profile: str, n_agents: int) -> Callable[..., str]:
    """Bind profile + n_agents for the duration of one dispatch."""

    def _ws(key: str, **kwargs: Any) -> str:
        return _ws_resolve(
            key, profile=profile, n_agents=n_agents, **kwargs
        )

    return _ws


def _silence_pm(
    bridge: Any,
    ws: Callable[..., str],
    t_now: float,
    n_agents: int,
) -> tuple[list[str], list[float]]:
    """Zero all ESS Pm-step. Writes (T:=t_now, AMP:=0.0) for each agent."""
    keys: list[str] = []
    values: list[float] = []
    for i in range(1, n_agents + 1):
        kt = ws("PM_STEP_T", i=i)
        ka = ws("PM_STEP_AMP", i=i)
        bridge.apply_workspace_var(kt, t_now)
        bridge.apply_workspace_var(ka, 0.0)
        keys.extend([kt, ka])
        values.extend([t_now, 0.0])
    return keys, values


def _silence_pmg(
    bridge: Any,
    ws: Callable[..., str],
    t_now: float,
) -> tuple[list[str], list[float]]:
    """Zero all SG Pmg-step. Writes (T:=t_now, AMP:=0.0) for g in 1..3."""
    keys: list[str] = []
    values: list[float] = []
    for g in range(1, 4):
        kt = ws("PMG_STEP_T", g=g)
        ka = ws("PMG_STEP_AMP", g=g)
        bridge.apply_workspace_var(kt, t_now)
        bridge.apply_workspace_var(ka, 0.0)
        keys.extend([kt, ka])
        values.extend([t_now, 0.0])
    return keys, values


# ---------------------------------------------------------------------------
# Family A — EssPmStepProxy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EssPmStepProxy:
    """ESS-side Pm-step proxy.

    Writes ``PM_STEP_AMP[target_indices]`` at sys-pu (divided across
    targets), zeros all other ``PM_STEP_AMP[i]`` and the entire
    ``PMG_STEP`` family.

    ``target_indices`` may be:
      - a tuple of 0-indexed VSG ids (explicit targets), e.g. ``(0,)``,
        ``(3,)``, ``(0, 1, 2, 3)`` for legacy ``pm_step_single_vsg``;
      - the sentinel string ``"random_bus"`` — at apply time a 50/50
        choice between ``(0,)`` (proxy bus 7) and ``(3,)`` (proxy bus 9).

    ``proxy_bus`` is decorative (used only in log messages); the
    workspace writes are determined entirely by ``target_indices``.
    """

    target_indices: tuple[int, ...] | str
    proxy_bus: int | None = None

    def apply(
        self,
        bridge: Any,
        magnitude_sys_pu: float,
        rng: np.random.Generator,
        t_now: float,
        cfg: Any,
    ) -> DisturbanceTrace:
        ws = _make_ws(cfg.model_name, cfg.n_agents)

        # Resolve random sentinel
        if isinstance(self.target_indices, str):
            if self.target_indices == "random_bus":
                if float(rng.random()) < 0.5:
                    targets: tuple[int, ...] = (0,)
                    proxy_bus: int | None = 7
                else:
                    targets = (3,)
                    proxy_bus = 9
            else:
                raise ValueError(
                    f"EssPmStepProxy: unknown sentinel "
                    f"{self.target_indices!r}"
                )
        else:
            targets = self.target_indices
            proxy_bus = self.proxy_bus

        n_tgt = max(len(targets), 1)
        amp_focused_pu = float(magnitude_sys_pu) / n_tgt
        amps_per_vsg = [0.0] * cfg.n_agents
        for idx in targets:
            if 0 <= idx < cfg.n_agents:
                amps_per_vsg[idx] = amp_focused_pu

        keys: list[str] = []
        values: list[float] = []

        # Per-agent Pm writes (target + zero-others), exact order matches
        # the legacy god method (PM first, PMG silence after).
        for i in range(1, cfg.n_agents + 1):
            kt = ws("PM_STEP_T", i=i)
            ka = ws("PM_STEP_AMP", i=i)
            v_t = t_now
            v_a = amps_per_vsg[i - 1]
            bridge.apply_workspace_var(kt, v_t)
            bridge.apply_workspace_var(ka, v_a)
            keys.extend([kt, ka])
            values.extend([v_t, v_a])

        # Silence SG Pmg
        kg, vg = _silence_pmg(bridge, ws, t_now)
        keys.extend(kg)
        values.extend(vg)

        sign = "increase" if magnitude_sys_pu > 0 else "decrease"
        proxy_tag = (
            f"proxy_bus{proxy_bus}"
            if proxy_bus is not None
            else "single_vsg"
        )
        target_descriptor = f"VSG{list(targets)}/{proxy_tag}"
        logger.info(
            "[EssPmStepProxy] %s targets %s: amp=%+.4f pu (mag=%+.3f), t=%.4fs",
            sign, target_descriptor, amp_focused_pu,
            float(magnitude_sys_pu), t_now,
        )

        return DisturbanceTrace(
            family="ess_pm_step",
            target_descriptor=target_descriptor,
            written_keys=tuple(keys),
            written_values=tuple(values),
            magnitude_sys_pu=float(magnitude_sys_pu),
        )


# ---------------------------------------------------------------------------
# Family B — SgPmgStepProxy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SgPmgStepProxy:
    """SG-side Pmg-step proxy.

    Writes ``PMG_STEP_AMP[target_g]`` at sys-pu (full magnitude, not
    divided), silences all other ``PMG_STEP_AMP[g]`` first (so the
    target-set write wins), then silences the entire ``PM_STEP`` family.

    Magnitude semantic: ``magnitude_sys_pu`` is pushed verbatim to the
    target G's ``PMG_STEP_AMP`` register (Pmg vars are already sys-pu in
    ``build_kundur_cvs_v3.m``).

    ``target_g`` may be:
      - 1, 2, or 3 (explicit SG index);
      - sentinel string ``"random_gen"`` — uniform random pick of 1/2/3
        via ``rng.integers(1, 4)``.
    """

    target_g: int | str

    def apply(
        self,
        bridge: Any,
        magnitude_sys_pu: float,
        rng: np.random.Generator,
        t_now: float,
        cfg: Any,
    ) -> DisturbanceTrace:
        ws = _make_ws(cfg.model_name, cfg.n_agents)

        if isinstance(self.target_g, str):
            if self.target_g == "random_gen":
                target_g = int(rng.integers(1, 4))
            else:
                raise ValueError(
                    f"SgPmgStepProxy: unknown sentinel "
                    f"{self.target_g!r}"
                )
        else:
            target_g = int(self.target_g)
            if target_g not in (1, 2, 3):
                raise ValueError(
                    f"SgPmgStepProxy: target_g must be 1/2/3, got {target_g}"
                )

        amp_focused_pu = float(magnitude_sys_pu)

        keys: list[str] = []
        values: list[float] = []

        # Silence all PMG first — order matters: silence-then-set so that
        # the target write is not overwritten by the silence loop.
        kg, vg = _silence_pmg(bridge, ws, t_now)
        keys.extend(kg)
        values.extend(vg)

        # Set the target G amp (overwrites the 0.0 written above).
        ka = ws("PMG_STEP_AMP", g=target_g)
        bridge.apply_workspace_var(ka, amp_focused_pu)
        keys.append(ka)
        values.append(amp_focused_pu)

        # Silence ESS PM
        kp, vp = _silence_pm(bridge, ws, t_now, cfg.n_agents)
        keys.extend(kp)
        values.extend(vp)

        sign = "increase" if magnitude_sys_pu > 0 else "decrease"
        target_descriptor = f"SG[{target_g}]/proxy_g{target_g}"
        logger.info(
            "[SgPmgStepProxy] %s targets %s: amp=%+.4f pu (mag=%+.3f), t=%.4fs",
            sign, target_descriptor, amp_focused_pu,
            float(magnitude_sys_pu), t_now,
        )

        return DisturbanceTrace(
            family="sg_pmg_step",
            target_descriptor=target_descriptor,
            written_keys=tuple(keys),
            written_values=tuple(values),
            magnitude_sys_pu=float(magnitude_sys_pu),
        )


# ---------------------------------------------------------------------------
# Family C — LoadStepRBranch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadStepRBranch:
    """Series RLC R-block load-step dispatch (paper LS1 / LS2).

    Two semantically distinct actions on the same family:
      - **trip** (R disengage): write ``LOAD_STEP_AMP[ls_bus] := 0.0``.
        ``magnitude_sys_pu`` is IGNORED — the trip always disengages
        the IC-loaded R block (paper line 993: "sudden load reduction
        of 248 MW at bus 14"). The IC restored in env._reset_backend
        determines the trip amplitude.
      - **engage** (R engage): write
        ``LOAD_STEP_AMP[ls_bus] := abs(magnitude_sys_pu) * cfg.sbase_va``.
        Paper line 994: "sudden load increase of 188 MW at bus 15".

    ``ls_bus`` action mapping (mirrors the legacy god method):
      - 14 → trip
      - 15 → engage
      - sentinel ``"random_bus"`` → 50/50 between (14, trip) and (15, engage)

    All writes use ``require_effective=True``: under v3 the R-block
    Resistance is compile-frozen, so the schema raises
    ``WorkspaceVarError`` to surface the contract violation at the call
    site rather than silently no-oping (see
    ``scenarios/kundur/NOTES.md`` §"2026-04-29 Eval 协议偏差").
    """

    ls_bus: int | str

    def apply(
        self,
        bridge: Any,
        magnitude_sys_pu: float,
        rng: np.random.Generator,
        t_now: float,
        cfg: Any,
    ) -> DisturbanceTrace:
        ws = _make_ws(cfg.model_name, cfg.n_agents)

        # Resolve random sentinel + action
        if isinstance(self.ls_bus, str):
            if self.ls_bus == "random_bus":
                if float(rng.random()) < 0.5:
                    ls_bus_int = 14
                    ls_action = "trip"
                else:
                    ls_bus_int = 15
                    ls_action = "engage"
            else:
                raise ValueError(
                    f"LoadStepRBranch: unknown sentinel {self.ls_bus!r}"
                )
        else:
            ls_bus_int = int(self.ls_bus)
            if ls_bus_int == 14:
                ls_action = "trip"
            elif ls_bus_int == 15:
                ls_action = "engage"
            else:
                raise ValueError(
                    f"LoadStepRBranch: ls_bus must be 14/15 or "
                    f"'random_bus', got {self.ls_bus!r}"
                )

        amp_w = abs(float(magnitude_sys_pu)) * cfg.sbase_va
        other_bus_int = 15 if ls_bus_int == 14 else 14

        keys: list[str] = []
        values: list[float] = []

        if ls_action == "trip":
            # LS1: R disengage. Write 0; magnitude IGNORED.
            k = ws("LOAD_STEP_AMP", bus=ls_bus_int, require_effective=True)
            bridge.apply_workspace_var(k, 0.0)
            keys.append(k); values.append(0.0)
            k = ws("LOAD_STEP_TRIP_AMP", bus=ls_bus_int,
                   require_effective=True)
            bridge.apply_workspace_var(k, 0.0)
            keys.append(k); values.append(0.0)
            k = ws("LOAD_STEP_TRIP_AMP", bus=other_bus_int,
                   require_effective=True)
            bridge.apply_workspace_var(k, 0.0)
            keys.append(k); values.append(0.0)
        else:  # engage
            # LS2: R engage at amp_w watts.
            k = ws("LOAD_STEP_AMP", bus=ls_bus_int, require_effective=True)
            bridge.apply_workspace_var(k, amp_w)
            keys.append(k); values.append(amp_w)
            k = ws("LOAD_STEP_TRIP_AMP", bus=ls_bus_int,
                   require_effective=True)
            bridge.apply_workspace_var(k, 0.0)
            keys.append(k); values.append(0.0)
            k = ws("LOAD_STEP_TRIP_AMP", bus=other_bus_int,
                   require_effective=True)
            bridge.apply_workspace_var(k, 0.0)
            keys.append(k); values.append(0.0)

        # Silence PM + PMG (LoadStep order: silence PM, then PMG)
        kp, vp = _silence_pm(bridge, ws, t_now, cfg.n_agents)
        keys.extend(kp)
        values.extend(vp)
        kg, vg = _silence_pmg(bridge, ws, t_now)
        keys.extend(kg)
        values.extend(vg)

        target_descriptor = f"bus{ls_bus_int}:{ls_action}"
        logger.info(
            "[LoadStepRBranch] %s at %s: amp=%.2f MW (mag=%+.3f sys-pu), t=%.4fs",
            ls_action, f"bus{ls_bus_int}", amp_w / 1e6,
            float(magnitude_sys_pu), t_now,
        )

        return DisturbanceTrace(
            family="load_step_r",
            target_descriptor=target_descriptor,
            written_keys=tuple(keys),
            written_values=tuple(values),
            magnitude_sys_pu=float(magnitude_sys_pu),
        )


# ---------------------------------------------------------------------------
# Family D — LoadStepCcsInjection
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadStepCcsInjection:
    """Phase A++ CCS trip-injection dispatch.

    Writes ``LOAD_STEP_TRIP_AMP[ls_bus] := abs(magnitude_sys_pu) * cfg.sbase_va``
    and zeros the other bus's CCS register. Does NOT touch the R-block
    side (``LOAD_STEP_AMP`` stays at IC).

    All writes use ``require_effective=True``: under v3 the CCS
    injection signal is name-valid but only ~0.01 Hz at Bus 14/15 ESS
    terminals (electrically distant from the load center).

    ``ls_bus`` may be:
      - 14 or 15 (explicit);
      - sentinel ``"random_bus"`` → 50/50 pick of 14 vs 15.
    """

    ls_bus: int | str

    def apply(
        self,
        bridge: Any,
        magnitude_sys_pu: float,
        rng: np.random.Generator,
        t_now: float,
        cfg: Any,
    ) -> DisturbanceTrace:
        ws = _make_ws(cfg.model_name, cfg.n_agents)

        if isinstance(self.ls_bus, str):
            if self.ls_bus == "random_bus":
                ls_bus_int = (
                    14 if float(rng.random()) < 0.5 else 15
                )
            else:
                raise ValueError(
                    f"LoadStepCcsInjection: unknown sentinel "
                    f"{self.ls_bus!r}"
                )
        else:
            ls_bus_int = int(self.ls_bus)
            if ls_bus_int not in (14, 15):
                raise ValueError(
                    f"LoadStepCcsInjection: ls_bus must be 14/15 or "
                    f"'random_bus', got {self.ls_bus!r}"
                )

        amp_w = abs(float(magnitude_sys_pu)) * cfg.sbase_va
        other_bus_int = 15 if ls_bus_int == 14 else 14

        keys: list[str] = []
        values: list[float] = []

        # CCS path: target gets amp_w, other bus zeroed. R-side untouched.
        k = ws("LOAD_STEP_TRIP_AMP", bus=ls_bus_int,
               require_effective=True)
        bridge.apply_workspace_var(k, amp_w)
        keys.append(k); values.append(amp_w)
        k = ws("LOAD_STEP_TRIP_AMP", bus=other_bus_int,
               require_effective=True)
        bridge.apply_workspace_var(k, 0.0)
        keys.append(k); values.append(0.0)

        # Silence PM + PMG
        kp, vp = _silence_pm(bridge, ws, t_now, cfg.n_agents)
        keys.extend(kp)
        values.extend(vp)
        kg, vg = _silence_pmg(bridge, ws, t_now)
        keys.extend(kg)
        values.extend(vg)

        target_descriptor = f"bus{ls_bus_int}:cc_inject"
        logger.info(
            "[LoadStepCcsInjection] cc_inject at %s: amp=%.2f MW "
            "(mag=%+.3f sys-pu), t=%.4fs",
            f"bus{ls_bus_int}", amp_w / 1e6,
            float(magnitude_sys_pu), t_now,
        )

        return DisturbanceTrace(
            family="load_step_ccs",
            target_descriptor=target_descriptor,
            written_keys=tuple(keys),
            written_values=tuple(values),
            magnitude_sys_pu=float(magnitude_sys_pu),
        )


# ---------------------------------------------------------------------------
# Resolver factory
# ---------------------------------------------------------------------------


_DISPATCH_TABLE: dict[str, Callable[[], DisturbanceProtocol]] = {
    "pm_step_proxy_bus7":
        lambda: EssPmStepProxy(target_indices=(0,), proxy_bus=7),
    "pm_step_proxy_bus9":
        lambda: EssPmStepProxy(target_indices=(3,), proxy_bus=9),
    "pm_step_proxy_random_bus":
        lambda: EssPmStepProxy(target_indices="random_bus"),
    "pm_step_proxy_g1":
        lambda: SgPmgStepProxy(target_g=1),
    "pm_step_proxy_g2":
        lambda: SgPmgStepProxy(target_g=2),
    "pm_step_proxy_g3":
        lambda: SgPmgStepProxy(target_g=3),
    "pm_step_proxy_random_gen":
        lambda: SgPmgStepProxy(target_g="random_gen"),
    "loadstep_paper_bus14":
        lambda: LoadStepRBranch(ls_bus=14),
    "loadstep_paper_bus15":
        lambda: LoadStepRBranch(ls_bus=15),
    "loadstep_paper_random_bus":
        lambda: LoadStepRBranch(ls_bus="random_bus"),
    "loadstep_paper_trip_bus14":
        lambda: LoadStepCcsInjection(ls_bus=14),
    "loadstep_paper_trip_bus15":
        lambda: LoadStepCcsInjection(ls_bus=15),
    "loadstep_paper_trip_random_bus":
        lambda: LoadStepCcsInjection(ls_bus="random_bus"),
}


def known_disturbance_types() -> tuple[str, ...]:
    """All disturbance_type strings the resolver accepts (excluding
    the special ``pm_step_single_vsg``, which requires ``vsg_indices``).
    """
    return tuple(_DISPATCH_TABLE) + ("pm_step_single_vsg",)


def resolve_disturbance(
    disturbance_type: str,
    *,
    vsg_indices: tuple[int, ...] | None = None,
) -> DisturbanceProtocol:
    """Return the adapter instance for a disturbance_type string.

    Parameters
    ----------
    disturbance_type : one of ``known_disturbance_types()``.
    vsg_indices      : required only for ``pm_step_single_vsg``.
                       If ``None``, defaults to ``(0,)``.

    Raises
    ------
    ValueError on unknown disturbance_type.
    """
    if disturbance_type == "pm_step_single_vsg":
        idx = (0,) if vsg_indices is None else tuple(vsg_indices)
        return EssPmStepProxy(target_indices=idx, proxy_bus=None)
    factory = _DISPATCH_TABLE.get(disturbance_type)
    if factory is None:
        raise ValueError(
            f"unknown disturbance_type {disturbance_type!r}; "
            f"valid: {sorted(known_disturbance_types())}"
        )
    return factory()


__all__ = [
    "DisturbanceTrace",
    "DisturbanceProtocol",
    "EssPmStepProxy",
    "SgPmgStepProxy",
    "LoadStepRBranch",
    "LoadStepCcsInjection",
    "known_disturbance_types",
    "resolve_disturbance",
]
