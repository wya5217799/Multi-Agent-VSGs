"""
Configuration for Modified Kundur Two-Area Multi-Agent VSG System.

Aligned with Yang et al., IEEE TPWRS 2023 and NE39 reference implementation.
Adapted for 4-agent, 50 Hz Kundur system.
"""

import numpy as np

from scenarios.contract import KUNDUR as _CONTRACT
from scenarios.kundur.kundur_ic import load_kundur_ic
from scenarios.config_simulink_base import (
    LR, GAMMA, TAU_SOFT, HIDDEN_SIZES,
    DEFAULT_EPISODES, MAX_EPISODES,
    CHECKPOINT_INTERVAL, EVAL_INTERVAL, CLEAR_BUFFER_PER_EPISODE,
    ADAPTIVE_KH, ADAPTIVE_KD,
    DT, N_SUBSTEPS, T_WARMUP,
    DM_MIN, DM_MAX, DD_MIN, DD_MAX,
    VSG_M0, VSG_D0, VSG_SN,
    NORM_ROCOF,
    MAX_NEIGHBORS, COMM_FAIL_PROB,
    OBS_DIM, ACT_DIM,
    PHI_H, PHI_D, TDS_FAIL_PENALTY,
)

import os as _os
from pathlib import Path
from scenarios.kundur.model_profile import load_kundur_model_profile

DEFAULT_KUNDUR_MODEL_PROFILE = (
    Path(__file__).resolve().parent / "model_profiles" / "kundur_ee_legacy.json"
)


def load_runtime_kundur_profile():
    path = _os.getenv("KUNDUR_MODEL_PROFILE", str(DEFAULT_KUNDUR_MODEL_PROFILE))
    return load_kundur_model_profile(path)


KUNDUR_MODEL_PROFILE = load_runtime_kundur_profile()

# ========== Kundur-specific warmup override ==========
# ConvGen and VSG P_ref ramps start at 0 (X0=0 in build_powerlib_kundur.m),
# so T_WARMUP must cover the full T_ramp=2s plus settling time (~1s).
# Base value 0.5s is too short — delta crashes before the ramp completes.
T_WARMUP = 3.0  # overrides config_simulink_base.T_WARMUP = 0.5

# ========== System (from contract) ==========
N_AGENTS = _CONTRACT.n_agents
SBASE = 100.0        # MVA
FN = _CONTRACT.fn     # Hz
OMEGA_N = 2 * np.pi * FN  # rad/s

# ========== Simulation (Kundur-specific) ==========
# T_EPISODE: 10s (50 steps), matching Yang et al. TPWRS 2023 Sec.IV-A (M=50, DT=0.2s).
T_EPISODE = 10.0
STEPS_PER_EPISODE = int(T_EPISODE / DT)  # 50

# DEFAULT_EPISODES: Paper Section IV trains for 2000 episodes.
DEFAULT_EPISODES = 2000

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
# PHI_F: Paper Table I uses PHI_F=100 for all experiments (φ_f=100, φ_h=1, φ_d=1).
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

# Generator initial dispatch — loaded from canonical source (kundur_ic.json)
_ic = load_kundur_ic()
VSG_P0_VSG_BASE: np.ndarray = np.asarray(_ic.vsg_p0_vsg_base_pu, dtype=np.float64)  # shape (4,)
VSG_P0_SBASE: np.ndarray = _ic.to_sbase_pu(vsg_sn_mva=VSG_SN, sbase_mva=SBASE)

# Load (original Kundur values, for reference)
LOAD_BUS7_MW = 967.0
LOAD_BUS9_MW = 1767.0

# Bus voltage
V_BUS = np.array([1.03, 1.01, 1.01, 1.03])
VSG_BUS_VN = 20.0      # kV

# Kundur steady-state P_e is about 3.74 p.u. on system base, so the shared
# normalization of 2.0 drives observations well outside the critic's nominal
# input scale.
NORM_P = 4.0

# Frequency observation normalization (Kundur-specific override).
# Base NORM_FREQ=3.0 gives obs ≈ 31 at 15 Hz (0.30 pu × 314 rad/s / 3.0)
# — well outside the critic network's nominal input range.
# At 8.0, the same deviation gives obs ≈ 11.8, which keeps critic inputs
# in a learnable range without gradient saturation.
NORM_FREQ = 8.0

# Disturbance magnitude range (Kundur-specific override).
# Physics (opt_kd_20260417_03): at D_LO=1.5 (min damping), DIST_MAX=0.5 →
#   Δf_ss = (0.5×100/200/4)/1.5 × 50Hz = 2.08 Hz
#   peak ≈ 2.08 × 2.3 (Kundur two-area oscillation factor) = 4.8 Hz
#   Even worst-case 3× factor: 6.25 Hz — safe margin below IntW clip (±15 Hz).
# Previous DIST_MAX=1.5 gave peak≈14.4 Hz, saturating IntW on 507/510 episodes
# (run kundur_simulink_20260414_211958), filling replay buffer with distorted physics.
DIST_MIN = 0.1   # 10 MW minimum disturbance
DIST_MAX = 0.5   # 50 MW maximum disturbance — verified safe below IntW clip


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
TRIPLOAD2_P_MAX_W = 188e6 / 3.0  # per-phase cap for the Bus15 disturbance bank

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
from engine.simulink_bridge import BridgeConfig

KUNDUR_BRIDGE_CONFIG = BridgeConfig(
    model_name=KUNDUR_MODEL_PROFILE.model_name,
    phase_command_mode=KUNDUR_MODEL_PROFILE.phase_command_mode,
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
    p_out_signal='P_out_ES{idx}',        # DEBUG ONLY — swing eq output, not for training
    pe_measurement=KUNDUR_MODEL_PROFILE.pe_measurement,
    # G3-prep-D-config: route CVS profile to cvs_signal dispatch; legacy/SPS keep phang_feedback default.
    step_strategy='cvs_signal' if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs' else 'phang_feedback',
    pe_feedback_signal='PeFb_ES{idx}',   # PeGain_ES{idx} output, VSG-base pu
    # Dynamic Load disturbance: per-phase W stored in base workspace.
    # Bus14: TripLoad1_P = 248/3 MW per phase (nominal load on).
    # Bus15: TripLoad2_P = 0 W (nominal load off; set to 188/3 MW on disturbance).
    tripload1_p_default=248e6 / 3,       # ~82.67 MW per phase
    tripload2_p_default=0.0,             # Bus15 off at episode start
    pe0_default_vsg=tuple(VSG_P0_VSG_BASE.tolist()),  # per-agent VSG-base pu
    delta0_deg=tuple(_ic.vsg_delta0_deg),             # rotor angle ICs [deg]; seeds 6-arg warmup
    # absolute_with_loadflow mode: init_phang offsets the post-warmup phAng update.
    # For Kundur SPS the phAng is the rotor angle directly (no bus-angle offset),
    # so init_phang = (0, ...) → formula reduces to ph = delta_clipped.
    # passthrough mode does not use init_phang; keep it empty for that path.
    init_phang=tuple(0.0 for _ in range(N_AGENTS))
    if KUNDUR_MODEL_PROFILE.phase_command_mode == 'absolute_with_loadflow'
    else (),
    # SPS Phasor Three-Phase V-I Measurement outputs peak phasors (not RMS).
    # real(V_peak × I_peak*) = 2 × average power → scale by 0.5 to recover watts.
    pe_vi_scale=0.5 if KUNDUR_MODEL_PROFILE.pe_measurement == 'vi' else 1.0,
    # No breaker Step blocks in new model
    breaker_step_block_template='',
    breaker_count=0,
)
