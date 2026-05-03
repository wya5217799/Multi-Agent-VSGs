# engine/_harness_profile_gate.py
"""Phase E gate: reject harness_* calls whose runtime profile is unsupported.

Background: ``harness_*`` tools were designed against the v2 / SPS / NE39
contract. Newer profiles (e.g. kundur_cvs_v3 with cvs_signal step strategy
and integer-suffix loggers) silently produce wrong results when fed through
the v2-shaped helper paths. This gate rejects those calls upfront with an
actionable error rather than letting them silently misroute.

Profile resolution:
  - kundur: dynamic — read scenarios.kundur.config_simulink.KUNDUR_MODEL_PROFILE.
    The runtime variant (kundur_cvs / kundur_cvs_v3 / ...) is env-var driven
    via ``KUNDUR_MODEL_PROFILE`` envvar.
  - ne39: static — NE39 has no dynamic profile loader. The contract base name
    'NE39bus_v2' from engine.harness_registry.resolve_scenario IS the runtime
    name.
  - other scenario_ids: gate returns None (let downstream handle).

The gate fails open: profile resolution errors return None instead of
raising, so a broken profile import doesn't make every harness call
crash — only declared-unsupported profiles get rejected.

See plan §3.E.1, §10 D2/D3.
"""
from __future__ import annotations

import logging
from typing import Any

from scenarios.kundur.workspace_vars import PROFILES_CVS_V3

logger = logging.getLogger(__name__)

# Map scenario_id -> set of runtime profile names that the harness_* tools
# do NOT support. Add new entries here if a new profile variant is rolled
# out that the harness path was not designed for.
_UNSUPPORTED_PROFILES: dict[str, set[str]] = {
    "kundur": set(PROFILES_CVS_V3),
    "ne39":   set(),  # extend if NE39 grows incompatible profiles
}


def _runtime_profile_name(scenario_id: str) -> str | None:
    """Resolve the runtime profile name for a scenario.

    Returns None if resolution fails for any reason (import error, missing
    attribute, unknown scenario_id). The caller treats None as "supported"
    so the gate fails open.
    """
    try:
        if scenario_id == "kundur":
            # Dynamic: read the env-driven profile loader's result.
            from scenarios.kundur.config_simulink import (
                KUNDUR_MODEL_PROFILE as _profile,
            )
            return _profile.model_name  # dataclass attribute, NOT a dict
        if scenario_id == "ne39":
            # Static: NE39 has no dynamic profile; the contract base is the
            # runtime model name.
            from engine.harness_registry import resolve_scenario
            return resolve_scenario("ne39").model_name
    except (ImportError, AttributeError, ValueError) as exc:
        logger.debug(
            "harness profile gate: failed to resolve profile for scenario_id=%r (%s); "
            "fail-open (returning None)", scenario_id, exc,
        )
        return None
    return None  # unknown scenario_id


def check_harness_profile(scenario_id: str) -> dict[str, Any] | None:
    """Return None if the harness path supports this scenario's runtime profile.

    Otherwise return a structured error dict suitable for direct return from
    the harness_* tool. The dict matches the existing harness contract
    (``ok``, ``error``, ``message``) so callers don't need special handling.
    """
    runtime_name = _runtime_profile_name(scenario_id)
    if runtime_name is None:
        return None  # fail-open: let downstream surface real issues
    if runtime_name in _UNSUPPORTED_PROFILES.get(scenario_id, set()):
        return {
            "ok": False,
            "error": "harness_profile_mismatch",
            "scenario_id": scenario_id,
            "profile_name": runtime_name,
            "message": (
                f"harness path does not support profile {runtime_name!r} for "
                f"scenario {scenario_id!r}. The harness tools assume the v2 / "
                f"NE39 contract (default step strategy, contract logger names). "
                f"See docs/knowledge/training_management.md and "
                f"scenarios/{scenario_id}/NOTES.md for the supported alternative "
                f"(typically: a scenario-specific probe under probes/{scenario_id}/)."
            ),
        }
    return None
