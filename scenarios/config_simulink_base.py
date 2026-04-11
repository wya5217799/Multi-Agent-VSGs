"""scenarios/config_simulink_base.py — Shared Simulink SAC hyperparameters.

Scenario-specific configs (kundur/config_simulink.py, new_england/config_simulink.py)
should import * from here and override only what differs.

DO NOT add system-specific parameters here (N_AGENTS, FN, T_EPISODE, PHI_F, BATCH_SIZE).
Those belong in the scenario config with a comment explaining WHY they differ.
"""

# Pick KUNDUR arbitrarily; test_scenario_invariant_fields guarantees
# DT, MAX_NEIGHBORS, OBS_DIM, ACT_DIM are identical across all contracts.
from scenarios.contract import KUNDUR as _CONTRACT

# ========== SAC Hyperparameters (scenario-invariant) ==========
LR = 3e-4
GAMMA = 0.99
TAU_SOFT = 0.005
HIDDEN_SIZES = (128, 128, 128, 128)

# ========== Training Control ==========
DEFAULT_EPISODES = 500
MAX_EPISODES = 2000
CHECKPOINT_INTERVAL = 100
EVAL_INTERVAL = 50
CLEAR_BUFFER_PER_EPISODE = False

# ========== Adaptive Baseline (Fu et al. 2022) ==========
ADAPTIVE_KH = 0.1
ADAPTIVE_KD = 2.0

# ========== Simulation Timing ==========
DT = _CONTRACT.dt    # control step (s) — from contract
N_SUBSTEPS = 5       # parameter interpolation substeps
T_WARMUP = 0.5       # warmup before disturbance (s)

# ========== Action Space (both scenarios use same M/D range) ==========
DM_MIN, DM_MAX = -6.0, 18.0    # M range: [M0+DM_MIN, M0+DM_MAX]
DD_MIN, DD_MAX = -1.5, 4.5     # D range: [D0+DD_MIN, D0+DD_MAX]

# ========== Disturbance Magnitude ==========
DIST_MIN = 1.0    # p.u.
DIST_MAX = 3.0

# ========== VSG Base Parameters ==========
VSG_M0 = 12.0    # M = 2H (s), H0 = 6.0 s
VSG_D0 = 3.0     # p.u.
VSG_SN = 200.0   # MVA per unit

# ========== Observation Normalization ==========
NORM_P = 2.0
NORM_FREQ = 3.0
NORM_ROCOF = 5.0

# ========== Communication ==========
MAX_NEIGHBORS = _CONTRACT.max_neighbors
COMM_FAIL_PROB = 0.1

# ========== Observation / Action Dimensions (from contract) ==========
OBS_DIM = _CONTRACT.obs_dim   # [P_norm, freq_dev, rocof, nb1_freq, nb2_freq, nb1_rocof, nb2_rocof]
ACT_DIM = _CONTRACT.act_dim   # [delta_M, delta_D]

# ========== Reward (PHI_H, PHI_D are scenario-invariant; PHI_F is not) ==========
PHI_H = 1.0    # inertia control cost
PHI_D = 1.0    # damping control cost
TDS_FAIL_PENALTY = -50.0
