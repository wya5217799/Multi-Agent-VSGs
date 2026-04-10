# SOURCE OF TRUTH — this file and the harness_reference.json it resolves are authoritative.
# CLAUDE.md is navigation-only. When CLAUDE.md conflicts with harness state, harness wins.
# Any agent action must read harness state here before proceeding.

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Mapping

from engine.harness_registry import resolve_scenario

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REFERENCE_PATHS = {
    "kundur": Path("scenarios/kundur/harness_reference.json"),
    "ne39": Path("scenarios/new_england/harness_reference.json"),
}
_CONFIG_MODULES = {
    "kundur": "scenarios.kundur.config_simulink",
    "ne39": "scenarios.new_england.config_simulink",
}
_MISSING = object()


def reference_path_for_scenario(scenario_id: str) -> Path:
    try:
        return _PROJECT_ROOT / _REFERENCE_PATHS[scenario_id]
    except KeyError as exc:
        raise ValueError("Unsupported scenario_id. Expected one of: kundur, ne39") from exc


def load_scenario_reference(scenario_id: str) -> dict[str, Any]:
    path = reference_path_for_scenario(scenario_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("scenario_id") != scenario_id:
        raise ValueError(f"Reference manifest scenario_id mismatch for {path}")
    if not isinstance(payload.get("reference_items"), list):
        raise ValueError(f"Reference manifest is missing reference_items: {path}")
    return payload


def summarize_reference_manifest(reference_manifest: Mapping[str, Any]) -> dict[str, list[str]]:
    summary = {
        "must_match_keys": [],
        "warn_if_missing_keys": [],
        "informational_keys": [],
    }
    for item in reference_manifest.get("reference_items", []):
        mode = item.get("check_mode")
        key = item.get("key")
        if not isinstance(key, str):
            continue
        if mode == "must_match":
            summary["must_match_keys"].append(key)
        elif mode == "warn_if_missing":
            summary["warn_if_missing_keys"].append(key)
        else:
            summary["informational_keys"].append(key)
    return summary


def _normalize_json_like(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, tuple):
        return [_normalize_json_like(item) for item in value]
    if isinstance(value, list):
        return [_normalize_json_like(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _normalize_json_like(item) for key, item in value.items()}
    return value


def _load_config_module(scenario_id: str):
    return importlib.import_module(_CONFIG_MODULES[scenario_id])


def build_reference_context(
    scenario_id: str,
    spec=None,
    load_result: Mapping[str, Any] | None = None,
    *,
    use_config_import: bool = False,
) -> dict[str, Any]:
    """Build actual values to compare against the reference manifest.

    Two validation modes — choose explicitly:

    **Mode A — spec_consistency_check** (``use_config_import=False``, default):
        Reads expected values from the reference JSON itself, then checks
        that the harness spec and the JSON are internally consistent.
        Does NOT import Python config modules (no numpy / simulink_bridge
        load cost, ~48 s saved on first MCP call).
        Use this for fast, routine harness runs.

    **Mode B — live_config_check** (``use_config_import=True``):
        Dynamically imports the scenario config module (e.g.
        ``scenarios.kundur.config_simulink``) and reads live Python values.
        Slower and heavier, but catches drift between the reference JSON
        and the actual Python config.
        Use this when updating the reference manifest or suspecting config
        drift.
    """
    spec = spec or resolve_scenario(scenario_id)

    # Fast path: build context from spec + reference JSON only (no import).
    context: dict[str, Any] = {
        "model_name": spec.model_name,
        "training_entry": spec.train_entry.as_posix(),
    }

    if load_result and "model_name" in load_result:
        context["loaded_model_name"] = load_result["model_name"]

    if not use_config_import:
        # Read expected values from reference JSON as "actual" — validates
        # that spec and reference are consistent without importing config.
        ref_path = reference_path_for_scenario(scenario_id)
        ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
        for item in ref_data.get("reference_items", []):
            key = item.get("key")
            if key and key not in context:
                context[key] = item.get("value")
        return _normalize_json_like(context)

    # Slow path: import config module for live validation.
    config = _load_config_module(scenario_id)
    context.update({
        "n_agents": getattr(config, "N_AGENTS", None),
        "dt": getattr(config, "DT", None),
        "t_episode": getattr(config, "T_EPISODE", None),
        "obs_dim": getattr(config, "OBS_DIM", None),
        "act_dim": getattr(config, "ACT_DIM", None),
        "max_neighbors": getattr(config, "MAX_NEIGHBORS", None),
        "comm_adj": getattr(config, "COMM_ADJ", None),
    })

    if scenario_id == "kundur":
        context.update(
            {
                "scenario1_breaker": getattr(config, "SCENARIO1_BREAKER", None),
                "scenario1_time": getattr(config, "SCENARIO1_TIME", None),
                "scenario2_breaker": getattr(config, "SCENARIO2_BREAKER", None),
                "scenario2_time": getattr(config, "SCENARIO2_TIME", None),
            }
        )
    elif scenario_id == "ne39":
        context.update(
            {
                "scenario1_gen_trip": getattr(config, "SCENARIO1_GEN_TRIP", None),
                "scenario1_trip_time": getattr(config, "SCENARIO1_TRIP_TIME", None),
                "scenario2_bus": getattr(config, "SCENARIO2_BUS", None),
                "scenario2_time": getattr(config, "SCENARIO2_TIME", None),
            }
        )

    return _normalize_json_like(context)


def validate_reference_items(
    *,
    reference_items: list[Mapping[str, Any]],
    actual_values: Mapping[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    mismatch_keys: list[str] = []
    missing_keys: list[str] = []

    normalized_actual = _normalize_json_like(dict(actual_values))
    for item in reference_items:
        key = str(item["key"])
        check_mode = str(item.get("check_mode", "informational"))
        expected = _normalize_json_like(item.get("value"))
        actual = normalized_actual.get(key, _MISSING)

        if check_mode == "informational":
            status = "informational"
        elif actual is _MISSING or actual is None:
            status = "missing"
            missing_keys.append(key)
        elif actual == expected:
            status = "match"
        else:
            status = "mismatch"
            mismatch_keys.append(key)

        checks.append(
            {
                "key": key,
                "check_mode": check_mode,
                "status": status,
                "expected": expected,
                "actual": None if actual is _MISSING else actual,
                "source": item.get("source", ""),
                "confidence": item.get("confidence", ""),
                "notes": item.get("notes", ""),
            }
        )

    return {
        "checks": checks,
        "mismatch_keys": mismatch_keys,
        "missing_keys": missing_keys,
        "has_warnings": bool(mismatch_keys or missing_keys),
    }

