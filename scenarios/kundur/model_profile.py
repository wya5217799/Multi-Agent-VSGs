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


def parse_kundur_model_profile(payload: dict[str, Any]) -> KundurModelProfile:
    bad = _FORBIDDEN_KEYS.intersection(payload)
    if bad:
        raise ValueError(f"Profile may not declare topology keys: {sorted(bad)}")
    flags = payload["feature_flags"]
    return KundurModelProfile(
        scenario_id=payload["scenario_id"],
        profile_id=payload["profile_id"],
        model_name=payload["model_name"],
        solver_family=payload["solver_family"],
        pe_measurement=payload["pe_measurement"],
        phase_command_mode=payload["phase_command_mode"],
        warmup_mode=payload["warmup_mode"],
        feature_flags=KundurFeatureFlags(**flags),
    )


def load_kundur_model_profile(path: str | Path) -> KundurModelProfile:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_kundur_model_profile(payload)
