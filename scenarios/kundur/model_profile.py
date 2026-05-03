from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_FORBIDDEN_KEYS = {"connections", "block_paths", "wires", "topology"}


@dataclass(frozen=True)
class KundurFeatureFlags:
    allow_pref_ramp: bool
    allow_simscape_solver_config: bool
    allow_feedback_only_pe_chain: bool


@dataclass(frozen=True)
class KundurModelProfile:
    scenario_id: str
    profile_id: str
    model_name: str
    solver_family: str
    pe_measurement: str
    phase_command_mode: str
    warmup_mode: str
    feature_flags: KundurFeatureFlags


_VALID_SOLVER_FAMILY = {"simscape_ee", "sps_phasor", "sps_discrete"}
_VALID_PE_MEASUREMENT = {"feedback", "vi"}


def parse_kundur_model_profile(payload: dict[str, Any]) -> KundurModelProfile:
    bad = _FORBIDDEN_KEYS.intersection(payload)
    if bad:
        raise ValueError(f"Profile may not declare topology keys: {sorted(bad)}")
    try:
        scenario_id = payload["scenario_id"]
        profile_id = payload["profile_id"]
        model_name = payload["model_name"]
        solver_family = payload["solver_family"]
        pe_measurement = payload["pe_measurement"]
        phase_command_mode = payload["phase_command_mode"]
        warmup_mode = payload["warmup_mode"]
        flags = payload["feature_flags"]
    except KeyError as exc:
        raise ValueError(
            f"Profile '{payload.get('profile_id', '<unknown>')}' is missing required field: {exc}"
        ) from exc
    if solver_family not in _VALID_SOLVER_FAMILY:
        raise ValueError(
            f"Profile '{profile_id}': solver_family must be one of {sorted(_VALID_SOLVER_FAMILY)}, got {solver_family!r}"
        )
    if pe_measurement not in _VALID_PE_MEASUREMENT:
        raise ValueError(
            f"Profile '{profile_id}': pe_measurement must be one of {sorted(_VALID_PE_MEASUREMENT)}, got {pe_measurement!r}"
        )
    return KundurModelProfile(
        scenario_id=scenario_id,
        profile_id=profile_id,
        model_name=model_name,
        solver_family=solver_family,
        pe_measurement=pe_measurement,
        phase_command_mode=phase_command_mode,
        warmup_mode=warmup_mode,
        feature_flags=KundurFeatureFlags(**flags),
    )


def load_kundur_model_profile(path: str | Path) -> KundurModelProfile:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_kundur_model_profile(payload)
