"""Typed workspace-variable schema — Python ↔ MATLAB contract for Kundur CVS.

PURPOSE
-------
Every base-workspace var that Python pushes via
``SimulinkBridge.apply_workspace_var`` is currently a raw string literal
scattered across ``env/simulink/kundur_simulink_env.py``. Renaming a var
on the MATLAB side (``build_kundur_cvs*.m``) requires manual hunting
across files; typos are silent (the assignin succeeds, the Constant
never reads it).

This schema names every var symbolically so:

  * call sites resolve the formatted name in one place,
  * profile mismatch (e.g. v2-only var written under v3) raises
    immediately rather than silently writing a dangling base-ws entry,
  * index-out-of-range raises before the MATLAB call,
  * the schema is the single document for the contract surface.

SCOPE  (additive, minimal — Candidate 3, 2026-04-29)
----------------------------------------------------
Covers ONLY the Kundur CVS apply_workspace_var write paths in
``KundurSimulinkEnv._reset_backend`` (v3 IC restoration) and
``_apply_disturbance_backend`` (Pm-step / Pmg-step / LoadStep dispatch).

Does NOT cover:

  * ``SimulinkBridge.warmup`` — uses ``kundur_cvs_ip`` struct, separate path.
  * ``BridgeConfig`` template fields — string templates remain.
  * NE39 / legacy SPS ``M0_val_ESi`` / ``D0_val_ESi`` family.
  * MATLAB-side consumer registration.

The schema is read-only; adding a new var is a one-line edit here.

NOTES
-----
LoadStep R-path vars (``LoadStep_amp_busXX``) are declared LIVE in v3 in
the sense that the MATLAB Constant references the workspace var, but the
v3 Series RLC R block compile-freezes its Resistance string at warmup,
making the writes weak under FastRestart (see
``scenarios/kundur/NOTES.md`` §"2026-04-29 Eval 协议偏差"). The schema
still surfaces these names so the symbol set is centrally documented;
"weak signal" is a physics-side concern not enforced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Profile identifiers (mirror KundurModelProfile.model_name)
# ---------------------------------------------------------------------------

PROFILE_CVS_V2 = "kundur_cvs"
PROFILE_CVS_V3 = "kundur_cvs_v3"
_PROFILES_CVS = frozenset({PROFILE_CVS_V2, PROFILE_CVS_V3})


class IndexFamily(Enum):
    """Index family of a workspace var template."""
    SCALAR = "scalar"
    PER_AGENT = "per_agent"  # i in [1, n_agents]
    PER_SG = "per_sg"        # g in [1, 3]
    PER_BUS = "per_bus"      # bus in {14, 15}


@dataclass(frozen=True)
class WorkspaceVarSpec:
    template: str
    family: IndexFamily
    profiles: frozenset
    description: str


_V3_BUSES = frozenset({14, 15})
_SG_INDICES = frozenset({1, 2, 3})


# ---------------------------------------------------------------------------
# Schema (Kundur CVS v2 + v3)
# ---------------------------------------------------------------------------

_SCHEMA: dict[str, WorkspaceVarSpec] = {
    # SAC control inputs (M, D per ESS) — listed for completeness; written
    # by bridge.step (NOT migrated by this changeset, but the schema covers
    # them so future bridge.step migration has a typed handle).
    "M_PER_AGENT": WorkspaceVarSpec(
        template="M_{i}",
        family=IndexFamily.PER_AGENT,
        profiles=_PROFILES_CVS,
        description="VSG inertia M for ESS i (set per step by bridge.step).",
    ),
    "D_PER_AGENT": WorkspaceVarSpec(
        template="D_{i}",
        family=IndexFamily.PER_AGENT,
        profiles=_PROFILES_CVS,
        description="VSG damping D for ESS i (set per step by bridge.step).",
    ),
    # ESS-side Pm-step proxy (Phase 4 Path C).
    "PM_STEP_T": WorkspaceVarSpec(
        template="Pm_step_t_{i}",
        family=IndexFamily.PER_AGENT,
        profiles=_PROFILES_CVS,
        description="ESS i Pm-step trigger time (s).",
    ),
    "PM_STEP_AMP": WorkspaceVarSpec(
        template="Pm_step_amp_{i}",
        family=IndexFamily.PER_AGENT,
        profiles=_PROFILES_CVS,
        description="ESS i Pm-step amplitude (sys-pu).",
    ),
    # SG-side Pm-step proxy (Z1 routing — v3 only).
    "PMG_STEP_T": WorkspaceVarSpec(
        template="PmgStep_t_{g}",
        family=IndexFamily.PER_SG,
        profiles=frozenset({PROFILE_CVS_V3}),
        description="SG g Pm-step trigger time (s).",
    ),
    "PMG_STEP_AMP": WorkspaceVarSpec(
        template="PmgStep_amp_{g}",
        family=IndexFamily.PER_SG,
        profiles=frozenset({PROFILE_CVS_V3}),
        description="SG g Pm-step amplitude (sys-pu).",
    ),
    # Paper LoadStep — bus-suffixed Series RLC R-block amplitude (Phase A).
    "LOAD_STEP_AMP": WorkspaceVarSpec(
        template="LoadStep_amp_bus{bus}",
        family=IndexFamily.PER_BUS,
        profiles=frozenset({PROFILE_CVS_V3}),
        description="Series RLC R-block load amplitude (W) at bus 14 or 15.",
    ),
    # Phase A++ Controlled Current Source trip injection.
    "LOAD_STEP_TRIP_AMP": WorkspaceVarSpec(
        template="LoadStep_trip_amp_bus{bus}",
        family=IndexFamily.PER_BUS,
        profiles=frozenset({PROFILE_CVS_V3}),
        description="CCS trip-injection amplitude (W) at bus 14 or 15.",
    ),
}


class WorkspaceVarError(ValueError):
    """Raised when a workspace var key, profile, or index is invalid."""


def resolve(
    key: str,
    *,
    profile: str,
    n_agents: int = 4,
    **idx: Any,
) -> str:
    """Resolve a symbolic schema key to its MATLAB workspace var name.

    Parameters
    ----------
    key      : schema entry name (e.g. ``"PM_STEP_AMP"``).
    profile  : ``KundurModelProfile.model_name`` (e.g. ``"kundur_cvs_v3"``).
    n_agents : ESS count for PER_AGENT bounds (default 4 for Kundur).
    idx      : index family kwargs — ``i``, ``g``, or ``bus`` depending on
               the entry's family.

    Raises
    ------
    WorkspaceVarError on unknown key, unsupported profile, or out-of-range idx.
    """
    spec = _SCHEMA.get(key)
    if spec is None:
        raise WorkspaceVarError(
            f"Unknown workspace var key: {key!r}. "
            f"Known keys: {sorted(_SCHEMA)}"
        )
    if profile not in spec.profiles:
        raise WorkspaceVarError(
            f"Workspace var {key!r} not declared for profile {profile!r}; "
            f"declared in {sorted(spec.profiles)}"
        )
    if spec.family is IndexFamily.SCALAR:
        if idx:
            raise WorkspaceVarError(
                f"{key}: SCALAR family takes no idx kwargs, got {sorted(idx)}"
            )
        return spec.template
    if spec.family is IndexFamily.PER_AGENT:
        i = idx.get("i")
        if not (isinstance(i, int) and 1 <= i <= n_agents):
            raise WorkspaceVarError(
                f"{key}: expected i in [1, {n_agents}], got i={i!r}"
            )
        return spec.template.format(i=i)
    if spec.family is IndexFamily.PER_SG:
        g = idx.get("g")
        if not (isinstance(g, int) and g in _SG_INDICES):
            raise WorkspaceVarError(
                f"{key}: expected g in {sorted(_SG_INDICES)}, got g={g!r}"
            )
        return spec.template.format(g=g)
    if spec.family is IndexFamily.PER_BUS:
        bus = idx.get("bus")
        if not (isinstance(bus, int) and bus in _V3_BUSES):
            raise WorkspaceVarError(
                f"{key}: expected bus in {sorted(_V3_BUSES)}, got bus={bus!r}"
            )
        return spec.template.format(bus=bus)
    raise WorkspaceVarError(f"unhandled family {spec.family!r} for key {key!r}")


def keys() -> tuple[str, ...]:
    """Return all schema entry keys (for tests / introspection)."""
    return tuple(_SCHEMA.keys())


def spec_for(key: str) -> WorkspaceVarSpec:
    """Return the WorkspaceVarSpec for ``key``, or raise."""
    spec = _SCHEMA.get(key)
    if spec is None:
        raise WorkspaceVarError(f"Unknown workspace var key: {key!r}")
    return spec


__all__ = [
    "PROFILE_CVS_V2",
    "PROFILE_CVS_V3",
    "IndexFamily",
    "WorkspaceVarSpec",
    "WorkspaceVarError",
    "resolve",
    "keys",
    "spec_for",
]
