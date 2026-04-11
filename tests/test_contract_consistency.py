"""Drift detection: verify all consumers agree with scenarios.contract.

If any test here fails, it means a file defines a contract value
independently instead of importing from scenarios.contract.
Fix the failing consumer, not the contract (unless the contract is wrong).

Acceptance criteria (from architecture discussion 2026-04-11):
  1. Contract values have exactly one definition point (scenarios/contract.py)
  2. harness/reference/train/env all reference or derive from it
  3. Any value change triggers at least one automated check (this file)
  4. A memoryless Agent can locate and modify via code contracts alone
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ── Contract self-consistency ──


def test_contract_obs_dim_formula():
    """obs_dim must equal 3 + 2 * max_neighbors."""
    from scenarios.contract import KUNDUR, NE39

    assert KUNDUR.obs_dim == 3 + 2 * KUNDUR.max_neighbors
    assert NE39.obs_dim == 3 + 2 * NE39.max_neighbors


def test_contract_post_init_validation():
    """ScenarioContract rejects inconsistent values."""
    from scenarios.contract import ScenarioContract

    with pytest.raises(ValueError, match="obs_dim.*inconsistent"):
        ScenarioContract(
            scenario_id="kundur",
            model_name="test",
            model_dir=Path("."),
            train_entry=Path("."),
            n_agents=4,
            fn=50.0,
            dt=0.2,
            max_neighbors=2,
            obs_dim=99,  # wrong
            act_dim=2,
        )


def test_scenario_invariant_fields():
    """Fields that must be the same across all scenarios."""
    from scenarios.contract import KUNDUR, NE39

    assert KUNDUR.dt == NE39.dt, "DT must be scenario-invariant"
    assert KUNDUR.max_neighbors == NE39.max_neighbors
    assert KUNDUR.obs_dim == NE39.obs_dim
    assert KUNDUR.act_dim == NE39.act_dim


# ── Simulink scenario configs ──


def test_kundur_config_matches_contract():
    from scenarios.contract import KUNDUR
    from scenarios.kundur import config_simulink as cfg

    assert cfg.N_AGENTS == KUNDUR.n_agents
    assert cfg.DT == KUNDUR.dt
    assert cfg.OBS_DIM == KUNDUR.obs_dim
    assert cfg.ACT_DIM == KUNDUR.act_dim
    assert cfg.FN == KUNDUR.fn
    assert cfg.MAX_NEIGHBORS == KUNDUR.max_neighbors


def test_ne39_config_matches_contract():
    from scenarios.contract import NE39
    from scenarios.new_england import config_simulink as cfg

    assert cfg.N_AGENTS == NE39.n_agents
    assert cfg.DT == NE39.dt
    assert cfg.OBS_DIM == NE39.obs_dim
    assert cfg.ACT_DIM == NE39.act_dim
    assert cfg.FN == NE39.fn
    assert cfg.MAX_NEIGHBORS == NE39.max_neighbors


# ── Root config (ANDES Kundur) ──


def test_root_config_matches_contract():
    from scenarios.contract import KUNDUR

    import config as cfg

    assert cfg.N_AGENTS == KUNDUR.n_agents
    assert cfg.DT == KUNDUR.dt
    assert cfg.OBS_DIM == KUNDUR.obs_dim
    assert cfg.ACTION_DIM == KUNDUR.act_dim
    assert cfg.MAX_NEIGHBORS == KUNDUR.max_neighbors


# ── Harness registry ──


def test_registry_matches_contract():
    from scenarios.contract import CONTRACTS
    from engine.harness_registry import _REGISTRY

    assert set(_REGISTRY) == set(CONTRACTS), "Registry and contract must cover same scenarios"
    for sid, contract in CONTRACTS.items():
        spec = _REGISTRY[sid]
        assert spec.scenario_id == contract.scenario_id
        assert spec.model_name == contract.model_name
        assert spec.model_dir == contract.model_dir
        assert spec.train_entry == contract.train_entry


# ── ANDES environment classes ──


def test_andes_kundur_env_matches_contract():
    from scenarios.contract import KUNDUR

    try:
        from env.andes.andes_vsg_env import AndesMultiVSGEnv
    except ImportError:
        pytest.skip("andes not installed")
    assert AndesMultiVSGEnv.N_AGENTS == KUNDUR.n_agents


def test_andes_ne_env_matches_contract():
    from scenarios.contract import NE39

    try:
        from env.andes.andes_ne_env import AndesNEEnv
    except ImportError:
        pytest.skip("andes not installed")
    assert AndesNEEnv.N_AGENTS == NE39.n_agents
    assert AndesNEEnv.FN == NE39.fn


def test_andes_base_shared_values():
    from scenarios.contract import KUNDUR

    try:
        from env.andes.base_env import AndesBaseEnv
    except ImportError:
        pytest.skip("andes not installed")
    assert AndesBaseEnv.DT == KUNDUR.dt
    assert AndesBaseEnv.MAX_NEIGHBORS == KUNDUR.max_neighbors
    assert AndesBaseEnv.OBS_DIM == KUNDUR.obs_dim


# ── Simulink environment classes ──


def test_simulink_kundur_env_matches_contract():
    pytest.importorskip("gymnasium")
    from scenarios.contract import KUNDUR

    # Import module constants (not class — these are module-level)
    from env.simulink import kundur_simulink_env as mod

    assert mod.N_AGENTS == KUNDUR.n_agents
    assert mod.OBS_DIM == KUNDUR.obs_dim
    assert mod.ACT_DIM == KUNDUR.act_dim
    assert mod.DT == KUNDUR.dt
    assert mod.F_NOM == KUNDUR.fn
    assert mod.MAX_NEIGHBORS == KUNDUR.max_neighbors


def test_simulink_ne39_env_matches_contract():
    pytest.importorskip("gymnasium")
    from scenarios.contract import NE39

    from env.simulink import ne39_simulink_env as mod

    assert mod.N_ESS == NE39.n_agents
    assert mod.OBS_DIM == NE39.obs_dim
    assert mod.ACT_DIM == NE39.act_dim
    assert mod.DT == NE39.dt
    assert mod.F_NOM == NE39.fn
    assert mod.MAX_NEIGHBORS == NE39.max_neighbors


# ── Harness reference JSON ──


_REF_PATHS = {
    "kundur": _PROJECT_ROOT / "scenarios" / "kundur" / "harness_reference.json",
    "ne39": _PROJECT_ROOT / "scenarios" / "new_england" / "harness_reference.json",
}


@pytest.mark.parametrize("scenario_id", ["kundur", "ne39"])
def test_reference_json_matches_contract(scenario_id: str):
    """Reference manifest values must match contract — catches silent drift."""
    from scenarios.contract import get_contract

    contract = get_contract(scenario_id)
    ref_path = _REF_PATHS[scenario_id]
    ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
    ref_items = {item["key"]: item["value"] for item in ref_data["reference_items"]}

    assert ref_items["model_name"] == contract.model_name
    assert ref_items["n_agents"] == contract.n_agents
    assert ref_items["dt"] == contract.dt
    assert ref_items["obs_dim"] == contract.obs_dim
    assert ref_items.get("act_dim") == contract.act_dim
    assert ref_items.get("max_neighbors") == contract.max_neighbors


# ── BridgeConfig instantiations ──


def test_kundur_bridge_config_matches_contract():
    from scenarios.contract import KUNDUR
    from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG

    assert KUNDUR_BRIDGE_CONFIG.n_agents == KUNDUR.n_agents
    assert KUNDUR_BRIDGE_CONFIG.model_name == KUNDUR.model_name
    assert KUNDUR_BRIDGE_CONFIG.dt_control == KUNDUR.dt


def test_ne39_bridge_config_matches_contract():
    from scenarios.contract import NE39
    from scenarios.new_england.config_simulink import NE39_BRIDGE_CONFIG

    assert NE39_BRIDGE_CONFIG.n_agents == NE39.n_agents
    assert NE39_BRIDGE_CONFIG.model_name == NE39.model_name
    assert NE39_BRIDGE_CONFIG.dt_control == NE39.dt
