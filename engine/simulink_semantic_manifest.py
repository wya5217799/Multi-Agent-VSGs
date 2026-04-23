from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SemanticManifest:
    scenario_id: str
    model_name: str
    solver: dict[str, Any]
    initialization: dict[str, Any]
    measurement: dict[str, Any]
    units: list[dict[str, Any]]
    disturbances: list[dict[str, Any]]
