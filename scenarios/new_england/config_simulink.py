"""
Configuration for Modified NE 39-Bus Multi-Agent VSG System.

All parameters aligned with paper Section IV-G and reference implementation.
"""

import numpy as np

from scenarios.contract import NE39 as _CONTRACT
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

# ========== System (from contract) ==========
N_AGENTS = _CONTRACT.n_agents
SBASE = 100.0       # MVA
FN = _CONTRACT.fn    # Hz  (NE 39-bus is a 60 Hz system)
OMEGA_N = 2 * np.pi * FN  # rad/s

# ========== Simulation (NE39-specific) ==========
# T_EPISODE: NE39 uses 10s episodes — 8-gen system needs longer to observe dynamics
T_EPISODE = 10.0
STEPS_PER_EPISODE = int(T_EPISODE / DT)  # 50

# ========== VSG Parameters (NE39-specific) ==========
VSG_RA = 0.001       # p.u. armature resistance (NE39-specific; Kundur uses 0.003)
VSG_XD1 = 0.15       # p.u. transient reactance (NE39-specific; Kundur uses 0.30)

# ========== Wind Farm Parameters ==========
WIND_FARM_M = 0.1      # near-zero inertia
WIND_FARM_D = 0.0      # no damping
WIND_FARM_GOV_R = 999.0  # governor disabled

# ========== Bus Mapping ==========
WIND_BUSES = [30, 31, 32, 33, 34, 35, 36, 37]   # G1-G8 original buses
ESS_BUSES = list(range(40, 48))                    # New buses 40-47
ESS_PARENT_BUSES = WIND_BUSES                      # Connected to wind buses
SYNC_BUSES = [38, 39]                              # G9, G10

# Retained sync machine parameters
SYNC_H = [3.45, 50.0]   # G9, G10 inertia constants
SYNC_D = [0.0, 0.0]

# ========== Connecting Lines ==========
NEW_LINE_R = 0.001    # p.u.
NEW_LINE_X = 0.10     # p.u.
NEW_LINE_B = 0.0175   # p.u.
VSG_BUS_VN = 22.0     # kV

# ========== PV Interface ==========
VSG_P0 = 0.5          # p.u. initial active power
VSG_Q0 = 0.0          # p.u. initial reactive power
VSG_PMAX = 5.0
VSG_PMIN = 0.0
VSG_QMAX = 5.0
VSG_QMIN = -5.0
VSG_V0 = 1.0

# ========== PQ Load Mode ==========
PQ_P2P = 1.0   # constant power
PQ_P2Z = 0.0
PQ_Q2Q = 1.0
PQ_Q2Z = 0.0

# ========== Communication Topology (8-node ring) ==========
COMM_ADJ = {
    0: [1, 7], 1: [0, 2], 2: [1, 3], 3: [2, 4],
    4: [3, 5], 5: [4, 6], 6: [5, 7], 7: [6, 0],
}

# ========== Reward (NE39-specific) ==========
# PHI_F: 100 per paper Table I (φ_f=100, φ_h=1, φ_d=1 for all experiments).
PHI_F = 100.0

# ========== SAC Hyperparameters (NE39-specific overrides) ==========
# BATCH_SIZE: 8 agents × 50 steps = 400 transitions/episode.
# 256 gives stable gradient estimates across the 8-agent action space.
BATCH_SIZE = 256
BUFFER_SIZE = 100000
# WARMUP_STEPS: need ~5 full episodes of random data (~2000 steps) before
# SAC updates start, so all 8 agents have seen diverse initial conditions.
WARMUP_STEPS = 2000

# ========== Test Scenarios ==========
# Scenario 1: W2 trip
SCENARIO1_GEN_TRIP = "GENROU_2"
SCENARIO1_TRIP_TIME = 0.5  # s

# Scenario 2: Bus 3 short circuit (approximated as load step)
SCENARIO2_BUS = "PQ_4"
SCENARIO2_MAGNITUDE = 5.0  # p.u.
SCENARIO2_TIME = 0.2  # s

# ========== Calibration Reference (from paper Fig.17) ==========
CALIB_STEADY_STATE_FREQ_DEV = -0.15  # Hz
CALIB_MAX_TRANSIENT_FREQ_DEV = -0.4  # Hz
CALIB_OSCILLATION_PERIOD = 2.0       # s
CALIB_MAX_DEV_AGENT = 1              # ES2 (index 1, closest to tripped G2)

# ========== SimulinkBridge Configuration ==========
import os as _os
from engine.simulink_bridge import BridgeConfig

NE39_BRIDGE_CONFIG = BridgeConfig(
    model_name='NE39bus_v2',
    model_dir=_os.path.join(
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
    pe_measurement='vi',    # NE39: Pe from V×I (Vabc/Iabc ToWorkspace)
    pe0_default_vsg=VSG_P0,
    # Phase-angle feedback (NE39-specific — must match patch_ne39_faststart.m init_phAng)
    phase_command_mode='absolute_with_loadflow',
    init_phang=(-3.646, 0.0, 2.466, 4.423, 3.398, 5.698, 8.494, 2.181),
    phase_feedback_gain=0.3,  # limit ΔPe to ~30 MW/step; gain=1.0 causes oscillations
)
