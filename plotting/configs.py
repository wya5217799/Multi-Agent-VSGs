"""
Typed configuration for Multi-Agent VSG evaluation.

Three-layer separation:
  ScenarioConfig — what physical system to simulate
  EvalConfig     — how to run evaluation
  IOConfig       — where to read/write files
"""
from dataclasses import dataclass, field, asdict
from typing import List
from enum import Enum
import importlib


class EnvType(Enum):
    KUNDUR_VSG = "AndesMultiVSGEnv"
    NEW_ENGLAND = "AndesNEEnv"


# EnvType → concrete class
ENV_CLASS_MAP = {
    EnvType.KUNDUR_VSG: ("env.andes.andes_vsg_env", "AndesMultiVSGEnv"),
    EnvType.NEW_ENGLAND: ("env.andes.andes_ne_env", "AndesNEEnv"),
}


def resolve_env_class(env_type: EnvType):
    """Resolve an environment class lazily so optional backends stay optional."""
    module_name, class_name = ENV_CLASS_MAP[env_type]
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


# ── Disturbance hierarchy ──

@dataclass
class DisturbanceBase:
    name: str
    time: float = 1.0

@dataclass
class LoadStep(DisturbanceBase):
    bus: str = ""
    delta_p: float = 0.0
    delta_q: float = 0.0

@dataclass
class BusFault(DisturbanceBase):
    bus: str = ""
    duration: float = 0.1


# ── Communication config ──

@dataclass
class CommConfig:
    failure_rate: float = 0.0
    delay_steps: int = 0
    topology: str = "full"


# ── Three-layer configs ──

@dataclass
class ScenarioConfig:
    """Physical system description only."""
    name: str
    env_type: EnvType
    n_agents: int
    disturbances: List[DisturbanceBase]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["env_type"] = self.env_type.value
        return d

@dataclass
class EvalConfig:
    """How to run evaluation."""
    deterministic: bool = True
    comm: CommConfig = field(default_factory=CommConfig)

    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class IOConfig:
    """Output paths, determined by evaluation workflow."""
    model_dir: str = ""
    training_log: str = ""
    output_dir: str = "results/figures_paper_style"
    fig_prefix: str = "fig"


# ── Pre-defined scenarios ──

SCENARIOS = {
    "kundur": ScenarioConfig(
        name="kundur",
        env_type=EnvType.KUNDUR_VSG,
        n_agents=4,
        disturbances=[
            LoadStep(name="LS1", bus="BUS6", delta_p=2.0),
            LoadStep(name="LS2", bus="BUS6", delta_p=-2.0),
        ],
    ),
    "new_england": ScenarioConfig(
        name="new_england",
        env_type=EnvType.NEW_ENGLAND,
        n_agents=8,
        disturbances=[
            LoadStep(name="LS1", bus="BUS20", delta_p=3.0),
        ],
    ),
}

IO_PRESETS = {
    "kundur": IOConfig(
        model_dir="results/andes_models_v3",
        training_log="results/andes_models_v3/training_log.json",
        fig_prefix="fig",
    ),
    "new_england": IOConfig(
        model_dir="results/andes_ne_models",
        training_log="results/andes_ne_models/training_log.json",
        fig_prefix="fig17",
    ),
}
