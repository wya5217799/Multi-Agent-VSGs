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

NAME-VALID  vs  PHYSICALLY-EFFECTIVE  (C3b/C3c, 2026-04-29)
-----------------------------------------------------------
A var name being "name-valid" in a profile (``profile in spec.profiles``)
means the MATLAB Constant block references that workspace name —
``apply_workspace_var`` will not produce a dangling base-ws entry, and
typos are caught.

A var name being "physically effective" in a profile
(``profile in spec.effective_in_profile``) is a STRONGER claim: writes
to that name produce a paper-grade physical disturbance under the
profile's solver / FastRestart contract.

Default ``resolve(...)`` enforces only name-validity (back-compat with
C3a). Pass ``require_effective=True`` to also reject name-valid but
not-effective combinations (e.g. v3 LoadStep R-block, v3 CCS trip
injection — see ``scenarios/kundur/NOTES.md`` §"2026-04-29 Eval 协议
偏差").

The schema is a CONTRACT layer, not a physical-channel verifier:
``effective_in_profile`` is a hand-curated snapshot of post-physics-fix
state. When the physics layer is repaired (e.g. R-block edited so the
Resistance is re-evaluated under FastRestart), the matching schema
entry must be hand-promoted into ``effective_in_profile``. There is no
auto-detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Profile identifiers (mirror KundurModelProfile.model_name)
# ---------------------------------------------------------------------------

PROFILE_CVS_V2 = "kundur_cvs"
PROFILE_CVS_V3 = "kundur_cvs_v3"
PROFILE_CVS_V3_DISCRETE = "kundur_cvs_v3_discrete"

# Family aliases — single source of truth for "what counts as CVS-pattern"
# and "what counts as v3-pattern". All other modules (config_simulink.py,
# kundur_simulink_env.py, _discover.py, ...) import these instead of
# repeating literal model-name tuples.
PROFILES_CVS_V3 = frozenset({PROFILE_CVS_V3, PROFILE_CVS_V3_DISCRETE})
PROFILES_CVS = frozenset(
    {PROFILE_CVS_V2}
) | PROFILES_CVS_V3
# Internal back-compat alias (legacy spec definitions reference _PROFILES_CVS).
_PROFILES_CVS = PROFILES_CVS


class IndexFamily(Enum):
    """Index family of a workspace var template."""
    SCALAR = "scalar"
    PER_AGENT = "per_agent"  # i in [1, n_agents]
    PER_SG = "per_sg"        # g in [1, 3]
    PER_BUS = "per_bus"      # bus in {14, 15}


# Sentinel: "effective_in_profile defaults to == profiles when not set".
# We cannot put ``profiles`` itself as a default (forward-ref to another
# field), so we use a unique sentinel object detected in ``__post_init__``.
_EFFECTIVE_DEFAULT: frozenset = frozenset({"__effective_default__"})


@dataclass(frozen=True)
class WorkspaceVarSpec:
    template: str
    family: IndexFamily
    profiles: frozenset
    description: str
    # C3b/C3c: profiles in which writes to this var produce a paper-grade
    # physical disturbance (subset of ``profiles``). When omitted, defaults
    # to ``profiles`` itself (back-compat: assume effective everywhere it is
    # name-valid, until proven otherwise by NOTES + manual demotion here).
    effective_in_profile: frozenset = _EFFECTIVE_DEFAULT
    # C3b/C3c: short reason string per (name-valid but not-effective) profile,
    # surfaced in the WorkspaceVarError message under require_effective=True.
    # Keys MUST be a subset of ``profiles - effective_in_profile``.
    inactive_reason: dict = field(default_factory=dict)
    # Option E (2026-04-30): PER_BUS specs can override the default valid bus
    # set (``_V3_ESS_BUSES = {14, 15}``). For CCS load-center disturbance the
    # valid buses are {7, 9}. None means "use family default".
    valid_buses: frozenset | None = None

    def __post_init__(self) -> None:
        # Resolve the default-sentinel to the concrete `profiles` set.
        if self.effective_in_profile is _EFFECTIVE_DEFAULT:
            object.__setattr__(self, "effective_in_profile", self.profiles)
        # Invariant 1: effective_in_profile must be a subset of profiles.
        if not self.effective_in_profile.issubset(self.profiles):
            extra = sorted(self.effective_in_profile - self.profiles)
            raise ValueError(
                f"WorkspaceVarSpec({self.template!r}): "
                f"effective_in_profile contains profile(s) {extra} not in "
                f"profiles {sorted(self.profiles)}"
            )
        # Invariant 2: inactive_reason keys must be in name-valid-but-not-
        # effective set (no orphan reasons, no reason for an effective profile).
        allowed_reason_keys = self.profiles - self.effective_in_profile
        bad = set(self.inactive_reason) - allowed_reason_keys
        if bad:
            raise ValueError(
                f"WorkspaceVarSpec({self.template!r}): "
                f"inactive_reason keys {sorted(bad)} are not in "
                f"profiles - effective_in_profile = "
                f"{sorted(allowed_reason_keys)}"
            )
        # Invariant 3: valid_buses only meaningful for PER_BUS family.
        if self.valid_buses is not None and self.family is not IndexFamily.PER_BUS:
            raise ValueError(
                f"WorkspaceVarSpec({self.template!r}): "
                f"valid_buses set on non-PER_BUS family {self.family!r}"
            )


_V3_ESS_BUSES = frozenset({14, 15})  # ESS terminal buses (default PER_BUS set)
_V3_LOAD_BUSES = frozenset({7, 9})   # Paper Fig.3 load centers (Option E)
_V3_BUSES = _V3_ESS_BUSES            # Back-compat alias for legacy callers
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
    # SG-side Pm-step proxy (Z1 routing — v3 family: Phasor + Discrete).
    # Both v3 variants assign PmgStep_t_<g> / PmgStep_amp_<g> in their build
    # scripts and route them through the SG source helper's Pm-step gate.
    "PMG_STEP_T": WorkspaceVarSpec(
        template="PmgStep_t_{g}",
        family=IndexFamily.PER_SG,
        profiles=PROFILES_CVS_V3,
        description="SG g Pm-step trigger time (s).",
    ),
    "PMG_STEP_AMP": WorkspaceVarSpec(
        template="PmgStep_amp_{g}",
        family=IndexFamily.PER_SG,
        profiles=PROFILES_CVS_V3,
        description="SG g Pm-step amplitude (sys-pu).",
    ),
    # Paper LoadStep — bus-suffixed load amplitude. Name-valid in both v3
    # variants but physically effective ONLY in v3 Discrete:
    #   v3 Phasor: drives a Series RLC R-block Resistance — compile-frozen
    #     at FastRestart, writes do not re-evaluate (Phase A defect).
    #   v3 Discrete (2026-05-03): drives a Three-Phase Series RLC Load's
    #     ActivePower behind a Three-Phase Breaker; reads at every sim
    #     chunk under FastRestart. Phase 0 SMIB Oracle measured 4.9 Hz
    #     |Δf| at 248 MW step. See quality_reports/plans/2026-05-03_phase0_
    #     smib_discrete_verdict.md.
    "LOAD_STEP_AMP": WorkspaceVarSpec(
        template="LoadStep_amp_bus{bus}",
        family=IndexFamily.PER_BUS,
        profiles=PROFILES_CVS_V3,
        description=(
            "Bus-attached load amplitude (W) at bus 14 or 15. "
            "v3 Phasor: Series RLC R-block (compile-frozen). "
            "v3 Discrete: Three-Phase Series RLC Load.ActivePower behind "
            "Three-Phase Breaker (working)."
        ),
        effective_in_profile=frozenset({PROFILE_CVS_V3_DISCRETE}),
        inactive_reason={
            PROFILE_CVS_V3: (
                "Series RLC R Resistance string compile-frozen at FastRestart; "
                "writes do not re-evaluate the R-block. "
                "See scenarios/kundur/NOTES.md §'2026-04-29 Eval 协议偏差'."
            ),
        },
    ),
    # Phase A++ Controlled Current Source trip injection.
    # Name-valid in v3 Phasor (CCS Constant block reads it) but NOT physically
    # effective: measured signal at Bus 14/15 ESS terminals is ~0.01 Hz
    # (electrically distant from load center), well below paper-grade.
    # Name-valid in v3 Discrete as a reserved slot: CCS blocks are currently
    # wrapped in `if false` (Phase 1.5 to restore). Writes land in a dangling
    # base-ws var with no consumer block reading it; no physical effect.
    # The LoadStepRBranch adapter writes 0.0 as a state-reset (preventing
    # episode contamination) using require_effective=False.
    "LOAD_STEP_TRIP_AMP": WorkspaceVarSpec(
        template="LoadStep_trip_amp_bus{bus}",
        family=IndexFamily.PER_BUS,
        profiles=frozenset({PROFILE_CVS_V3, PROFILE_CVS_V3_DISCRETE}),
        description="CCS trip-injection amplitude (W) at bus 14 or 15.",
        effective_in_profile=frozenset(),
        inactive_reason={
            PROFILE_CVS_V3: (
                "CCS injection path live but signal ~0.01 Hz on Bus 14/15 "
                "ESS terminals (electrically distant from load center). "
                "See scenarios/kundur/NOTES.md §'2026-04-29 Eval 协议偏差'."
            ),
            PROFILE_CVS_V3_DISCRETE: (
                "CCS blocks currently wrapped in `if false` in "
                "build_kundur_cvs_v3_discrete.m; Phase 1.5 to restore. "
                "Workspace var name is reserved (writes are no-op until "
                "CCS blocks are built). Use require_effective=False for "
                "state-reset writes (episode contamination prevention)."
            ),
        },
    ),
    # Three-Phase Breaker SwitchTimes trigger time for LoadStep R-branch.
    # The build script bakes LoadStep_t_<lb> = 5.0 into runtime_consts
    # (build_kundur_cvs_v3_discrete.m lines ~299, 868). Under v3 Discrete the
    # breaker fires exactly once per sim chunk at this time; the adapter must
    # write a value within the post-warmup window so the disturbance fires
    # AFTER warmup completes. Under v3 Phasor the R-block Resistance is
    # compile-frozen so the trigger time is irrelevant (name-valid only).
    "LOAD_STEP_T": WorkspaceVarSpec(
        template="LoadStep_t_bus{bus}",
        family=IndexFamily.PER_BUS,
        profiles=PROFILES_CVS_V3,
        description=(
            "Inactive in all profiles; documented for legacy reference only. "
            "Three-Phase Breaker SwitchTimes is compile-frozen in Discrete + "
            "FastRestart per F2; runtime LOAD_STEP_T writes are silent no-ops. "
            "Breaker timing is locked at build time via the build script. "
            "See plan 2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md."
        ),
        effective_in_profile=frozenset(),
        inactive_reason={
            PROFILE_CVS_V3: (
                "Three-Phase Breaker SwitchTimes compile-frozen in Discrete+FastRestart per F2; "
                "runtime LOAD_STEP_T writes are silent no-ops. Breaker timing locked at build time "
                "via build script. See plan 2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md."
            ),
            PROFILE_CVS_V3_DISCRETE: (
                "Three-Phase Breaker SwitchTimes compile-frozen in Discrete+FastRestart per F2; "
                "runtime LOAD_STEP_T writes are silent no-ops. Breaker timing locked at build time "
                "via build script. See plan 2026-05-04_loadstep_bus15_hybrid_dispatch_fix.md."
            ),
        },
    ),
    # Option E (2026-04-30): Controlled Current Source at Bus 7/9 load
    # centers (paper Fig.3 load buses, 967 MW + 1767 MW). Targets the true
    # paper-LoadStep electrical site rather than ESS terminals.
    # Convention: positive amp = current INJECTION GND→bus = generator-like
    # = freq UP (paper LoadStep trip). Negative amp = current bus→GND =
    # additional load = freq DOWN (paper LoadStep engage).
    # Starts name-valid only; promote to effective_in_profile after
    # Probe E sign-pair smoke validates the per-agent signal.
    # Option E (2026-04-30): CCS at Bus 7/9 load centers — Phase A++ pattern
    # ported to paper Fig.3 load centers. ABORT'd at Probe E sign-pair smoke:
    # max sign-pair diff was 0.0007 Hz at Bus 7 / 0.0013 Hz at Bus 9 (acceptance
    # threshold 0.05 Hz). Direct CCS sweep on the model showed even 1 GW
    # injection produces only ~0.008 Hz omega excursion at ESS terminals —
    # the Phasor solver attenuates CCS injection to two orders of magnitude
    # below paper-grade, regardless of bus location (Bus 14/15 ESS-terminal
    # CCS gives ~0.019 Hz at 1 GW; Bus 9 load-center CCS gives ~0.008 Hz).
    # See results/harness/kundur/cvs_v3_option_e_smoke/OPTION_E_ABORT_VERDICT.md.
    "CCS_LOAD_AMP": WorkspaceVarSpec(
        template="CCS_Load_amp_bus{bus}",
        family=IndexFamily.PER_BUS,
        profiles=frozenset({PROFILE_CVS_V3}),
        description=(
            "CCS load-center current source amp at Bus 7/9 (W, system "
            "base). Option E (2026-04-30): true network LoadStep at "
            "paper Fig.3 load centers (Bus 7 = 967 MW, Bus 9 = 1767 MW). "
            "Sign convention: +amp = current INJECTION GND→bus = freq UP "
            "(paper LoadStep trip); -amp = current draw bus→GND = freq "
            "DOWN (paper LoadStep engage). Name-valid (Constant block "
            "reads it, NR/IC unaffected at amp=0) but NOT physically "
            "effective: Phasor solver attenuates injection. See "
            "OPTION_E_ABORT_VERDICT.md."
        ),
        effective_in_profile=frozenset(),
        inactive_reason={
            PROFILE_CVS_V3: (
                "Option E ABORT'd 2026-04-30 at Probe E sign-pair smoke: "
                "max per-agent (|nadir_diff|+|peak_diff|) was 0.0007 Hz "
                "at Bus 7 / 0.0013 Hz at Bus 9 (threshold 0.05 Hz). "
                "Phasor solver attenuates CCS injection to ~0.008 Hz at "
                "ESS terminals even with 1 GW amp. See "
                "results/harness/kundur/cvs_v3_option_e_smoke/"
                "OPTION_E_ABORT_VERDICT.md."
            ),
        },
        valid_buses=_V3_LOAD_BUSES,
    ),
}


class WorkspaceVarError(ValueError):
    """Raised when a workspace var key, profile, or index is invalid."""


def resolve(
    key: str,
    *,
    profile: str,
    n_agents: int = 4,
    require_effective: bool = False,
    **idx: Any,
) -> str:
    """Resolve a symbolic schema key to its MATLAB workspace var name.

    Parameters
    ----------
    key                : schema entry name (e.g. ``"PM_STEP_AMP"``).
    profile            : ``KundurModelProfile.model_name``
                         (e.g. ``"kundur_cvs_v3"``).
    n_agents           : ESS count for PER_AGENT bounds (default 4 for Kundur).
    require_effective  : if True (default False), additionally reject
                         name-valid combinations whose physical channel is
                         not effective in this profile (e.g. v3 LoadStep R
                         compile-freeze, v3 CCS weak signal). Default keeps
                         C3a back-compat: name-validity only.
    idx                : index family kwargs — ``i``, ``g``, or ``bus``
                         depending on the entry's family.

    Raises
    ------
    WorkspaceVarError on
      * unknown key,
      * unsupported profile (name not declared),
      * (require_effective=True only) name-valid but physically not-effective
        profile,
      * out-of-range / missing / wrong-type idx.

    Validation order: unknown-key → unsupported-profile → not-effective →
    index-bounds. Effectiveness is checked BEFORE index bounds so a
    not-effective name fails fast even if the index would also be invalid.
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
    if require_effective and profile not in spec.effective_in_profile:
        reason = spec.inactive_reason.get(
            profile, "no reason recorded in schema"
        )
        raise WorkspaceVarError(
            f"Workspace var {key!r} is name-valid for profile {profile!r} "
            f"but its physical channel is not effective: {reason} "
            f"Pass require_effective=False if you intend to write the name "
            f"without expecting a physical disturbance "
            f"(IC seeding, smoke probes)."
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
        valid_buses = spec.valid_buses if spec.valid_buses is not None else _V3_ESS_BUSES
        if not (isinstance(bus, int) and bus in valid_buses):
            raise WorkspaceVarError(
                f"{key}: expected bus in {sorted(valid_buses)}, got bus={bus!r}"
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
    "PROFILE_CVS_V3_DISCRETE",
    "PROFILES_CVS",
    "PROFILES_CVS_V3",
    "IndexFamily",
    "WorkspaceVarSpec",
    "WorkspaceVarError",
    "resolve",
    "keys",
    "spec_for",
]
