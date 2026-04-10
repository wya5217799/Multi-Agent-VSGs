"""
Configuration for Modified Kundur Two-Area Multi-Agent VSG System.

Aligned with Yang et al., IEEE TPWRS 2023 and NE39 reference implementation.
Adapted for 4-agent, 50 Hz Kundur system.
"""

import numpy as np

from scenarios.config_simulink_base import (
    LR, GAMMA, TAU_SOFT, HIDDEN_SIZES,
    DEFAULT_EPISODES, MAX_EPISODES,
    CHECKPOINT_INTERVAL, EVAL_INTERVAL, CLEAR_BUFFER_PER_EPISODE,
    ADAPTIVE_KH, ADAPTIVE_KD,
    DT, N_SUBSTEPS, T_WARMUP,
    DM_MIN, DM_MAX, DD_MIN, DD_MAX,
    DIST_MIN, DIST_MAX,
    VSG_M0, VSG_D0, VSG_SN,
    NORM_P, NORM_FREQ, NORM_ROCOF,
    MAX_NEIGHBORS, COMM_FAIL_PROB,
    OBS_DIM, ACT_DIM,
    PHI_H, PHI_D, TDS_FAIL_PENALTY,
)

# ========== System ==========
N_AGENTS = 4
SBASE = 100.0        # MVA
FN = 50.0             # Hz
OMEGA_N = 2 * np.pi * FN  # rad/s

# ========== Simulation (Kundur-specific) ==========
# T_EPISODE: Kundur uses 5s episodes (vs NE39 10s) — faster 4-gen dynamics converge sooner
T_EPISODE = 5.0
STEPS_PER_EPISODE = int(T_EPISODE / DT)  # 25

# ========== VSG Parameters (Kundur-specific) ==========
VSG_RA = 0.003        # p.u. armature resistance (Kundur-specific; NE39 uses 0.001)
VSG_XD1 = 0.30        # p.u. transient reactance (Kundur-specific; NE39 uses 0.15)

# Derived physical limits
M_LO = VSG_M0 + DM_MIN   # 6.0
M_HI = VSG_M0 + DM_MAX   # 30.0
D_LO = VSG_D0 + DD_MIN   # 1.5
D_HI = VSG_D0 + DD_MAX   # 7.5

# ========== Communication Topology (4-node ring) ==========
COMM_ADJ = {0: [1, 3], 1: [0, 2], 2: [1, 3], 3: [2, 0]}

# ========== Reward (Kundur-specific) ==========
# PHI_F: Kundur 4-gen system has lower frequency sensitivity than 8-gen NE39.
# Paper Table I uses PHI_F=100 for this topology. NE39 uses PHI_F=200.
PHI_F = 100.0

# ========== Electrical Network ==========
# Full 16-bus Modified Kundur topology is in the Simulink model.
# B_MATRIX below is for the KundurStandaloneEnv (4-bus Kron-reduced ODE).
B_MATRIX = np.array([
    [0,  10,  0,  0],
    [10,  0,  2,  0],
    [0,   2,  0, 10],
    [0,   0, 10,  0],
], dtype=np.float64)

# Generator initial dispatch (p.u. on VSG base = 200 MVA)
# Calibrated from steady-state V*I measurement in 16-bus model.
# Each ESS outputs ~375 MW due to network power sharing.
VSG_P0 = 1.87           # avg ~375 MW each on VSG base

# Load (original Kundur values, for reference)
LOAD_BUS7_MW = 967.0
LOAD_BUS9_MW = 1767.0

# Bus voltage
V_BUS = np.array([1.03, 1.01, 1.01, 1.03])
VSG_BUS_VN = 20.0      # kV


# ========== Breaker Mapping for Simulink ==========
# Breaker_1: Bus14 (near ES3), initially closed with 248 MW load
#   Open breaker -> load reduction -> freq rises
# Breaker_2: Bus15 (near ES4), initially open with 188 MW load
#   Close breaker -> load increase -> freq drops
BREAKER_MAP = {
    'load_decrease': {'breaker': 'Breaker_1', 'action': 'open'},
    'load_increase': {'breaker': 'Breaker_2', 'action': 'close'},
}

# ========== Test Scenarios (Section IV-C, Yang et al.) ==========
# Load Step 1: Bus14 load trip (248 MW reduction) -> freq rises
SCENARIO1_BREAKER = 'Breaker_1'
SCENARIO1_TIME = 0.5

# Load Step 2: Bus15 load connection (188 MW increase) -> freq drops
SCENARIO2_BREAKER = 'Breaker_2'
SCENARIO2_TIME = 0.5

# ========== SAC Hyperparameters (Kundur-specific overrides) ==========
# BATCH_SIZE: Kundur fills buffer slower (4 agents × 25 steps/ep vs NE39 8×50).
# 256 gives good sample utilization at warmup completion.
BATCH_SIZE = 256
BUFFER_SIZE = 100000
# WARMUP_STEPS: 4-agent Kundur needs more warmup to fill buffer adequately.
WARMUP_STEPS = 2000

# ========== Simulink Model ==========
SIMULINK_MODEL = 'kundur_vsg'
SIMULINK_MODEL_DIR = None  # Auto-detect from project root
MINGW_PATH = r'D:\mingw64'

# ========== SimulinkBridge Configuration ==========
import os as _os
from engine.simulink_bridge import BridgeConfig

KUNDUR_BRIDGE_CONFIG = BridgeConfig(
    model_name='kundur_vsg',
    model_dir=SIMULINK_MODEL_DIR or _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)), 'simulink_models'
    ),
    n_agents=N_AGENTS,
    dt_control=DT,
    sbase_va=SBASE * 1e6,  # 100 MVA -> 100e6 VA
    m_path_template='{model}/VSG_ES{idx}/M0',
    d_path_template='{model}/VSG_ES{idx}/D0',
    omega_signal='omega_ES{idx}',
    vabc_signal='Vabc_ES{idx}',
    iabc_signal='Iabc_ES{idx}',
    pe_path_template='{model}/Pe_{idx}',
    src_path_template='{model}/VSrc_ES{idx}',
    # Dynamic Load disturbance: per-phase W stored in base workspace.
    # Bus14: TripLoad1_P = 248/3 MW per phase (nominal load on).
    # Bus15: TripLoad2_P = 0 W (nominal load off; set to 188/3 MW on disturbance).
    tripload1_p_default=248e6 / 3,   # ~82.67 MW per phase
    tripload2_p_default=0.0,          # Bus15 off at episode start
    # No breaker Step blocks in new model
    breaker_step_block_template='',
    breaker_count=0,
)
