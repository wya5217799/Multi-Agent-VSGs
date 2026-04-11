"""Single source of truth for scenario-level domain constants.

Every value that describes "what a scenario IS" lives here.
All other modules (configs, environments, harness, tests) must
import from or validate against this module.

Design rule: if a value appears in harness_reference.json with
check_mode="must_match", it MUST originate from here.

Change a value HERE and it propagates everywhere.
No other file should hardcode these values independently.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class ScenarioContract:
    """Immutable domain truth for one training scenario.

    Contains ONLY scenario-level constants that must be consistent
    across all layers (config, env, harness, tests).

    Does NOT contain:
    - SAC hyperparameters (LR, GAMMA, BATCH_SIZE)
    - Reward weights (PHI_F, PHI_H, PHI_D)
    - Backend-specific electrical parameters (B_MATRIX, VSG_RA)
    - Communication topology (COMM_ADJ)

    Those belong in scenario configs or environment classes.
    """

    scenario_id: Literal["kundur", "ne39"]
    model_name: str       # Simulink .slx stem (e.g. "kundur_vsg")
    model_dir: Path       # relative to project root
    train_entry: Path     # relative to project root
    n_agents: int         # number of RL agents (= number of VSGs)
    fn: float             # nominal grid frequency (Hz)
    dt: float             # RL control timestep (s)
    max_neighbors: int    # communication ring degree
    obs_dim: int          # per-agent observation dimension
    act_dim: int          # per-agent action dimension (delta_M, delta_D)

    def __post_init__(self) -> None:
        expected_obs = 3 + 2 * self.max_neighbors
        if self.obs_dim != expected_obs:
            raise ValueError(
                f"obs_dim={self.obs_dim} inconsistent with "
                f"max_neighbors={self.max_neighbors} (expected {expected_obs})"
            )
        if self.n_agents < 1:
            raise ValueError(f"n_agents must be positive, got {self.n_agents}")
        if self.dt <= 0:
            raise ValueError(f"dt must be positive, got {self.dt}")
        if self.fn <= 0:
            raise ValueError(f"fn must be positive, got {self.fn}")


# ── Kundur Two-Area System (4 VSG, 50 Hz) ──

KUNDUR = ScenarioContract(
    scenario_id="kundur",
    model_name="kundur_vsg",
    model_dir=Path("scenarios/kundur/simulink_models"),
    train_entry=Path("scenarios/kundur/train_simulink.py"),
    n_agents=4,
    fn=50.0,
    dt=0.2,
    max_neighbors=2,
    obs_dim=7,
    act_dim=2,
)

# ── New England 39-Bus System (8 VSG, 60 Hz) ──

NE39 = ScenarioContract(
    scenario_id="ne39",
    model_name="NE39bus_v2",
    model_dir=Path("scenarios/new_england/simulink_models"),
    train_entry=Path("scenarios/new_england/train_simulink.py"),
    n_agents=8,
    fn=60.0,
    dt=0.2,
    max_neighbors=2,
    obs_dim=7,
    act_dim=2,
)

# ── Lookup ──

CONTRACTS: dict[str, ScenarioContract] = {
    "kundur": KUNDUR,
    "ne39": NE39,
}


def get_contract(scenario_id: str) -> ScenarioContract:
    """Retrieve a scenario contract by ID.

    Raises ValueError for unknown scenario IDs.
    """
    try:
        return CONTRACTS[scenario_id]
    except KeyError:
        raise ValueError(
            f"Unknown scenario_id: {scenario_id!r}. "
            f"Expected one of: {sorted(CONTRACTS)}"
        )
