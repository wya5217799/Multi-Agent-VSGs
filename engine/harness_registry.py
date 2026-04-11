from __future__ import annotations

from pathlib import Path

from engine.harness_models import ScenarioSpec
from scenarios.contract import CONTRACTS

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Derived from scenarios.contract — single source of truth.
# ScenarioSpec is the harness's view; contract values are authoritative.
_REGISTRY = {
    sid: ScenarioSpec(
        scenario_id=c.scenario_id,
        model_name=c.model_name,
        model_dir=c.model_dir,
        train_entry=c.train_entry,
    )
    for sid, c in CONTRACTS.items()
}


def resolve_scenario(scenario_id: str) -> ScenarioSpec:
    try:
        spec = _REGISTRY[scenario_id]
    except KeyError as exc:
        hint = (
            "Unsupported scenario_id. Expected one of: kundur, ne39. "
            "For the New England model, use scenario_id='ne39'; "
            "model_name='NE39bus_v2' is resolved by the registry."
        )
        raise ValueError(hint) from exc

    model_file = _PROJECT_ROOT / spec.model_dir / f"{spec.model_name}.slx"
    train_entry = _PROJECT_ROOT / spec.train_entry
    if not model_file.exists():
        raise ValueError(f"Resolved model file does not exist: {model_file}")
    if not train_entry.exists():
        raise ValueError(f"Resolved train entry does not exist: {train_entry}")
    return spec
