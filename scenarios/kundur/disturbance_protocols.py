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


_ESS_PM_STEP_SENTINELS = frozenset({"random_bus"})
_SG_PMG_STEP_SENTINELS = frozenset({"random_gen"})
_LOAD_STEP_SENTINELS = frozenset({"random_bus"})

# 2026-04-30 Option F4 (HybridSgEssMultiPoint): topology coupling map
# from Probe B G1/G2/G3 sign-pair empirical measurement.  G index (1-based)
# -> 0-indexed ES set that responds non-trivially to that G's Pm step.
# Source: results/harness/kundur/cvs_v3_probe_b/probe_b_pos_gen_b{1,2,3}.json
# Used only by HybridSgEssMultiPoint to compute the compensate-ES set.
_F4_SG_TO_EXCITED_ES: dict[int, frozenset[int]] = {
    1: frozenset({0}),         # G1 -> ES1 (0.062 Hz at mag=0.5)
    2: frozenset({0}),         # G2 -> ES1 (0.097 Hz at mag=0.5)
    3: frozenset({2, 3}),      # G3 -> ES3 + ES4 (0.021 + 0.017 Hz at mag=0.5)
}


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

    def __post_init__(self) -> None:
        if isinstance(self.target_indices, str):
            if self.target_indices not in _ESS_PM_STEP_SENTINELS:
                raise ValueError(
                    f"EssPmStepProxy: target_indices string must be one "
                    f"of {sorted(_ESS_PM_STEP_SENTINELS)}, got "
                    f"{self.target_indices!r}"
                )
        elif not (
            isinstance(self.target_indices, tuple)
            and all(isinstance(i, int) for i in self.target_indices)
        ):
            raise ValueError(
                f"EssPmStepProxy: target_indices must be a tuple of "
                f"int or a sentinel string, got "
                f"{type(self.target_indices).__name__}={self.target_indices!r}"
            )

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
        logger.debug(
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

    def __post_init__(self) -> None:
        if isinstance(self.target_g, str):
            if self.target_g not in _SG_PMG_STEP_SENTINELS:
                raise ValueError(
                    f"SgPmgStepProxy: target_g string must be one of "
                    f"{sorted(_SG_PMG_STEP_SENTINELS)}, got "
                    f"{self.target_g!r}"
                )
        elif not (isinstance(self.target_g, int) and self.target_g in (1, 2, 3)):
            raise ValueError(
                f"SgPmgStepProxy: target_g must be 1/2/3 or a sentinel "
                f"string, got {type(self.target_g).__name__}="
                f"{self.target_g!r}"
            )

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
        logger.debug(
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

    def __post_init__(self) -> None:
        if isinstance(self.ls_bus, str):
            if self.ls_bus not in _LOAD_STEP_SENTINELS:
                raise ValueError(
                    f"LoadStepRBranch: ls_bus string must be one of "
                    f"{sorted(_LOAD_STEP_SENTINELS)}, got {self.ls_bus!r}"
                )
        elif not (isinstance(self.ls_bus, int) and self.ls_bus in (14, 15)):
            raise ValueError(
                f"LoadStepRBranch: ls_bus must be 14/15 or a sentinel "
                f"string, got {type(self.ls_bus).__name__}={self.ls_bus!r}"
            )

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
        logger.debug(
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

    def __post_init__(self) -> None:
        if isinstance(self.ls_bus, str):
            if self.ls_bus not in _LOAD_STEP_SENTINELS:
                raise ValueError(
                    f"LoadStepCcsInjection: ls_bus string must be one of "
                    f"{sorted(_LOAD_STEP_SENTINELS)}, got {self.ls_bus!r}"
                )
        elif not (isinstance(self.ls_bus, int) and self.ls_bus in (14, 15)):
            raise ValueError(
                f"LoadStepCcsInjection: ls_bus must be 14/15 or a sentinel "
                f"string, got {type(self.ls_bus).__name__}={self.ls_bus!r}"
            )

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
        logger.debug(
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
    # 2026-04-30 Probe B-ESS (Option F prerequisite): direct ESS Pm-step
    # injection at a single ES{i}. Bypasses network-mode-shape coupling so
    # we can verify whether ES2 swing-eq Pm channel responds at all (D-T6
    # ES2-dead-agent finding from Probe B G1/G2/G3 shows ES2 is silent
    # under any SG-side disturbance — but is that because ES2's swing-eq
    # is broken, or because ES2 is electrically isolated from G1/G2/G3?).
    # ES{i} index is 1-based (ES1 = target_indices=(0,), ES4 = (3,)).
    "pm_step_single_es1":
        lambda: EssPmStepProxy(target_indices=(0,), proxy_bus=None),
    "pm_step_single_es2":
        lambda: EssPmStepProxy(target_indices=(1,), proxy_bus=None),
    "pm_step_single_es3":
        lambda: EssPmStepProxy(target_indices=(2,), proxy_bus=None),
    "pm_step_single_es4":
        lambda: EssPmStepProxy(target_indices=(3,), proxy_bus=None),
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
    # 2026-04-30 Option F4: hybrid SG + ESS-compensate. sg_share=0.7,
    # target_g="random_gen". See HybridSgEssMultiPoint docstring + Option F
    # design doc (docs/superpowers/plans/2026-04-30-option-f-design.md).
    "pm_step_hybrid_sg_es":
        lambda: HybridSgEssMultiPoint(),
}


# ---------------------------------------------------------------------------
# Family E — HybridSgEssMultiPoint (Option F4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HybridSgEssMultiPoint:
    """Option F4 dispatch: SG-side primary + ESS-direct compensate.

    Per call:
      1. Pick a random SG target g ∈ {1,2,3} (or honor explicit ``target_g``).
      2. Write ``PMG_STEP_AMP[g] = magnitude * sg_share`` (default 70%).
      3. Look up which ES are excited by that g via _F4_SG_TO_EXCITED_ES.
         Compensate set = all 4 agents minus the excited set.
      4. Distribute remaining ``magnitude * (1 - sg_share)`` equally across
         the compensate set, written to ``PM_STEP_AMP[i]`` for i in
         compensate set; same sign as ``magnitude``.
      5. Silence all other PM/PMG entries.

    Empirical guarantee (per 2026-04-30 Probe B + Probe B-ESS):
      - For g=1 or g=2: ES1 sees ~70%-magnitude SG-mediated kick; ES2/ES3/ES4
        each see ~10%-magnitude direct kick.
      - For g=3: ES3+ES4 see ~70%-magnitude SG-mediated kick (split between
        them); ES1+ES2 each see ~15%-magnitude direct kick.
      - **All 4 ES respond above 1e-3 Hz threshold in every scenario.**
      - **ES2 always receives non-zero r_f gradient** (D-T6 broken).

    Reward landscape: SG-side network propagation preserves mode-shape
    differential (r_f_i ≠ 0 across agents), unlike F1's in-phase split
    which collapses the differential. ES-side compensate adds direct
    learning signal for the otherwise-silent agents.

    Magnitude semantic: ``magnitude_sys_pu`` is the *total* disturbance
    budget; sum of |PMG_STEP_AMP[g]| + Σ |PM_STEP_AMP[i]| over compensate
    set equals ``|magnitude_sys_pu|``.
    """

    sg_share: float = 0.7
    target_g: int | str = "random_gen"
    # 2026-04-30 post-50sc-eval finding: with compensate_sign_flip=False,
    # 4 agents respond IN-PHASE (SG pushes excited ES one way, compensate
    # pushes silent ES same way) → r_f = -(Δω_i - mean)² differential
    # collapses (F1-style collapse, weakened). per_M = -0.09 vs paper
    # -15.20 (168x weak). With sign-flip: SG pushes excited ES one way,
    # compensate pushes silent ES OPPOSITE way → 4 agents split mode-shape
    # → r_f differential preserved.
    compensate_sign_flip: bool = True

    def __post_init__(self) -> None:
        if not (0.0 < self.sg_share < 1.0):
            raise ValueError(
                f"HybridSgEssMultiPoint: sg_share must be in (0,1), "
                f"got {self.sg_share}"
            )
        if isinstance(self.target_g, str):
            if self.target_g not in _SG_PMG_STEP_SENTINELS:
                raise ValueError(
                    f"HybridSgEssMultiPoint: target_g string must be one of "
                    f"{sorted(_SG_PMG_STEP_SENTINELS)}, got {self.target_g!r}"
                )
        elif not (isinstance(self.target_g, int) and self.target_g in (1, 2, 3)):
            raise ValueError(
                f"HybridSgEssMultiPoint: target_g must be 1/2/3 or sentinel, "
                f"got {self.target_g!r}"
            )

    def apply(
        self,
        bridge: Any,
        magnitude_sys_pu: float,
        rng: np.random.Generator,
        t_now: float,
        cfg: Any,
    ) -> DisturbanceTrace:
        ws = _make_ws(cfg.model_name, cfg.n_agents)

        # Resolve G target
        if isinstance(self.target_g, str):
            target_g = int(rng.integers(1, 4))  # uniform 1, 2, 3
        else:
            target_g = int(self.target_g)

        excited = _F4_SG_TO_EXCITED_ES.get(target_g, frozenset())
        compensate = tuple(sorted(set(range(cfg.n_agents)) - excited))

        sg_amp = float(magnitude_sys_pu) * self.sg_share
        # compensate_sign_flip: opposite sign vs SG pushes 4-agent into
        # split mode-shape, preserves r_f differential
        sign_factor = -1.0 if self.compensate_sign_flip else +1.0
        compensate_total = float(magnitude_sys_pu) * (1.0 - self.sg_share) * sign_factor
        n_comp = max(len(compensate), 1)
        compensate_amp_per_es = compensate_total / n_comp

        keys: list[str] = []
        values: list[float] = []

        # 1. Silence everything first (ESS PM + SG PMG)
        kp, vp = _silence_pm(bridge, ws, t_now, cfg.n_agents)
        keys.extend(kp); values.extend(vp)
        kg, vg = _silence_pmg(bridge, ws, t_now)
        keys.extend(kg); values.extend(vg)

        # 2. Set SG target Pmg amp (overwrites silence)
        ksg = ws("PMG_STEP_AMP", g=target_g)
        bridge.apply_workspace_var(ksg, sg_amp)
        keys.append(ksg); values.append(sg_amp)

        # 3. Set ES compensate amps (overwrites silence for each)
        comp_amps_per_vsg = [0.0] * cfg.n_agents
        for es_idx in compensate:
            comp_amps_per_vsg[es_idx] = compensate_amp_per_es
            ka = ws("PM_STEP_AMP", i=es_idx + 1)  # 1-indexed in schema
            bridge.apply_workspace_var(ka, compensate_amp_per_es)
            keys.append(ka); values.append(compensate_amp_per_es)

        sign = "increase" if magnitude_sys_pu > 0 else "decrease"
        target_descriptor = (
            f"hybrid_g{target_g}+es{list(compensate)}/"
            f"sg_share={self.sg_share:.2f}"
        )
        logger.debug(
            "[HybridSgEssMultiPoint] %s targets %s: sg_amp=%+.4f, "
            "es_amp_each=%+.4f (mag=%+.3f), t=%.4fs",
            sign, target_descriptor, sg_amp, compensate_amp_per_es,
            float(magnitude_sys_pu), t_now,
        )

        return DisturbanceTrace(
            family="hybrid_sg_ess",
            target_descriptor=target_descriptor,
            written_keys=tuple(keys),
            written_values=tuple(values),
            magnitude_sys_pu=float(magnitude_sys_pu),
        )


# ---------------------------------------------------------------------------
# Resolver factory
# ---------------------------------------------------------------------------


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
