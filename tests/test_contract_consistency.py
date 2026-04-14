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


# ── Simulink env ↔ scenario config drift detection (Phase 2) ──


def test_kundur_env_vsg_base_from_config():
    """Env VSG base params must come from config_simulink_base (not hardcoded)."""
    pytest.importorskip("gymnasium")
    from scenarios.config_simulink_base import (
        VSG_M0, VSG_D0, VSG_SN, DM_MIN, DM_MAX, DD_MIN, DD_MAX,
    )
    from env.simulink import kundur_simulink_env as mod

    assert mod.VSG_M0 is VSG_M0, "VSG_M0 must be imported, not redefined"
    assert mod.VSG_D0 is VSG_D0, "VSG_D0 must be imported, not redefined"
    assert mod.VSG_SN is VSG_SN, "VSG_SN must be imported, not redefined"
    assert mod.DM_MIN is DM_MIN, "DM_MIN must be imported, not redefined"
    assert mod.DM_MAX is DM_MAX, "DM_MAX must be imported, not redefined"
    assert mod.DD_MIN is DD_MIN, "DD_MIN must be imported, not redefined"
    assert mod.DD_MAX is DD_MAX, "DD_MAX must be imported, not redefined"


def test_kundur_env_scenario_params_from_config():
    """Env scenario-specific params must come from kundur config (not hardcoded).

    Note: ``is`` identity checks are reliable for floats and dicts but NOT for
    small integers (CPython interns [-5, 256]).  N_SUBSTEPS=5 and
    STEPS_PER_EPISODE=25 fall in that range, so ``is`` cannot distinguish
    import from redefinition.  We keep ``==`` for those as a value guard only.
    """
    pytest.importorskip("gymnasium")
    from scenarios.kundur.config_simulink import (
        PHI_F, PHI_H, PHI_D, COMM_ADJ, T_EPISODE, T_WARMUP,
        N_SUBSTEPS, STEPS_PER_EPISODE,
    )
    from env.simulink import kundur_simulink_env as mod

    # floats + dict: identity proves import (not redefinition)
    assert mod.PHI_F is PHI_F, "PHI_F must be imported, not redefined"
    assert mod.PHI_H is PHI_H, "PHI_H must be imported, not redefined"
    assert mod.PHI_D is PHI_D, "PHI_D must be imported, not redefined"
    assert mod.COMM_ADJ is COMM_ADJ, "COMM_ADJ must be imported, not redefined"
    assert mod.T_EPISODE is T_EPISODE, "T_EPISODE must be imported, not redefined"
    assert mod.T_WARMUP is T_WARMUP, "T_WARMUP must be imported, not redefined"
    # ints: value guard only (CPython small-int interning defeats identity)
    assert mod.N_SUBSTEPS == N_SUBSTEPS
    assert mod.STEPS_PER_EPISODE == STEPS_PER_EPISODE


def test_ne39_env_vsg_base_from_config():
    """Env VSG base params must come from config_simulink_base (not hardcoded)."""
    pytest.importorskip("gymnasium")
    from scenarios.config_simulink_base import (
        VSG_M0, VSG_D0, VSG_SN, DM_MIN, DM_MAX, DD_MIN, DD_MAX,
    )
    from env.simulink import ne39_simulink_env as mod

    assert mod.VSG_M0 is VSG_M0, "VSG_M0 must be imported, not redefined"
    assert mod.VSG_D0 is VSG_D0, "VSG_D0 must be imported, not redefined"
    assert mod.VSG_SN is VSG_SN, "VSG_SN must be imported, not redefined"
    assert mod.DM_MIN is DM_MIN, "DM_MIN must be imported, not redefined"
    assert mod.DM_MAX is DM_MAX, "DM_MAX must be imported, not redefined"
    assert mod.DD_MIN is DD_MIN, "DD_MIN must be imported, not redefined"
    assert mod.DD_MAX is DD_MAX, "DD_MAX must be imported, not redefined"


def test_ne39_env_scenario_params_from_config():
    """Env scenario-specific params must come from NE39 config (not hardcoded).

    See test_kundur_env_scenario_params_from_config docstring for ``is`` vs
    ``==`` rationale on integer constants.
    """
    pytest.importorskip("gymnasium")
    from scenarios.new_england.config_simulink import (
        PHI_F, PHI_H, PHI_D, COMM_ADJ, T_EPISODE, T_WARMUP,
        N_SUBSTEPS, STEPS_PER_EPISODE,
    )
    from env.simulink import ne39_simulink_env as mod

    # floats + dict: identity proves import
    assert mod.PHI_F is PHI_F, "PHI_F must be imported, not redefined"
    assert mod.PHI_H is PHI_H, "PHI_H must be imported, not redefined"
    assert mod.PHI_D is PHI_D, "PHI_D must be imported, not redefined"
    assert mod.COMM_ADJ is COMM_ADJ, "COMM_ADJ must be imported, not redefined"
    assert mod.T_EPISODE is T_EPISODE, "T_EPISODE must be imported, not redefined"
    assert mod.T_WARMUP is T_WARMUP, "T_WARMUP must be imported, not redefined"
    # ints: value guard only
    assert mod.N_SUBSTEPS == N_SUBSTEPS
    assert mod.STEPS_PER_EPISODE == STEPS_PER_EPISODE


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


# ── Harness reference t_episode ──


@pytest.mark.parametrize(
    "scenario_id,config_module",
    [
        ("kundur", "scenarios.kundur.config_simulink"),
        ("ne39", "scenarios.new_england.config_simulink"),
    ],
)
def test_reference_json_t_episode_matches_config(scenario_id: str, config_module: str):
    """t_episode in reference manifest must match config_simulink.T_EPISODE."""
    import importlib

    cfg = importlib.import_module(config_module)
    ref_path = _REF_PATHS[scenario_id]
    ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
    ref_items = {item["key"]: item["value"] for item in ref_data["reference_items"]}

    assert ref_items["t_episode"] == cfg.T_EPISODE, (
        f"{scenario_id}: harness_reference t_episode={ref_items['t_episode']} "
        f"!= config T_EPISODE={cfg.T_EPISODE}"
    )


def test_kundur_reference_disturbance_vars_match_bridge_config():
    """Disturbance variable names in Kundur reference must match BridgeConfig field defaults."""
    from scenarios.kundur.config_simulink import KUNDUR_BRIDGE_CONFIG, SCENARIO1_TIME

    ref_path = _REF_PATHS["kundur"]
    ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
    ref_items = {item["key"]: item["value"] for item in ref_data["reference_items"]}

    assert ref_items["disturbance_var1"] == KUNDUR_BRIDGE_CONFIG.tripload1_p_var, (
        f"disturbance_var1={ref_items['disturbance_var1']} != "
        f"bridge tripload1_p_var={KUNDUR_BRIDGE_CONFIG.tripload1_p_var}"
    )
    assert ref_items["disturbance_var2"] == KUNDUR_BRIDGE_CONFIG.tripload2_p_var, (
        f"disturbance_var2={ref_items['disturbance_var2']} != "
        f"bridge tripload2_p_var={KUNDUR_BRIDGE_CONFIG.tripload2_p_var}"
    )
    assert ref_items["disturbance_time"] == SCENARIO1_TIME, (
        f"disturbance_time={ref_items['disturbance_time']} != "
        f"config SCENARIO1_TIME={SCENARIO1_TIME}"
    )


def test_ne39_reference_disturbance_fields_match_config():
    """Disturbance fields in NE39 reference must match config_simulink constants."""
    from scenarios.new_england.config_simulink import (
        SCENARIO1_GEN_TRIP,
        SCENARIO1_TRIP_TIME,
        SCENARIO2_BUS,
        SCENARIO2_TIME,
    )

    ref_path = _REF_PATHS["ne39"]
    ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
    ref_items = {item["key"]: item["value"] for item in ref_data["reference_items"]}

    assert ref_items["scenario1_gen_trip"] == SCENARIO1_GEN_TRIP
    assert ref_items["scenario1_trip_time"] == SCENARIO1_TRIP_TIME
    assert ref_items["scenario2_bus"] == SCENARIO2_BUS
    assert ref_items["scenario2_time"] == SCENARIO2_TIME


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
