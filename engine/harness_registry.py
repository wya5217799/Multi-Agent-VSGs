from __future__ import annotations

from pathlib import Path

from engine.harness_models import ScenarioSpec

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

_REGISTRY = {
    "kundur": ScenarioSpec(
        scenario_id="kundur",
        model_name="kundur_vsg",
        model_dir=Path("scenarios/kundur/simulink_models"),
        train_entry=Path("scenarios/kundur/train_simulink.py"),
    ),
    "ne39": ScenarioSpec(
        scenario_id="ne39",
        model_name="NE39bus_v2",
        model_dir=Path("scenarios/new_england/simulink_models"),
        train_entry=Path("scenarios/new_england/train_simulink.py"),
    ),
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
