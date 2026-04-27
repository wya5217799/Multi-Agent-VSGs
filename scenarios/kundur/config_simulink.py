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
    Path(__file__).resolve().parent / "model_profiles" / "kundur_cvs.json"
)


def load_runtime_kundur_profile():
    path = _os.getenv("KUNDUR_MODEL_PROFILE", str(DEFAULT_KUNDUR_MODEL_PROFILE))
    return load_kundur_model_profile(path)


KUNDUR_MODEL_PROFILE = load_runtime_kundur_profile()

# ========== Kundur-specific warmup override ==========
# ConvGen and VSG P_ref ramps start at 0 (X0=0 in build_powerlib_kundur.m),
# so T_WARMUP must cover the full T_ramp=2s plus settling time (~1s).
# Base value 0.5s is too short — delta crashes before the ramp completes.
#
# P3.3b (2026-04-26) — SMOKE-STAGE ONLY DECISION (NOT permanent for
# 2000-ep training): raised 3.0 -> 10.0 to absorb the v3 Phasor inductor-
# IC kick observed in Phase 2 zero-action probe (P2.1 fix-A2). At t=10 s
# residual |omega - 1| < 0.5 mHz across all 7 sources (ω/Pe both within
# 0.5 % of NR steady; full settling at t=30 s but the residual is below
# typical RL signal magnitude after t=10 s). v2 path (kundur_cvs) was
# previously running on T_WARMUP=3.0 and works fine at that value, but
# raising the shared override is acceptable: v2 also benefits from extra
# settle margin and the wall-clock cost is uniform per episode.
#
# Phase 4 / Phase 5 may revisit and either:
#   - keep 10 s if 50-ep r_f signal under PHI_F=100 is clean,
#   - raise to 20-30 s if residual contaminates reward shaping,
#   - or pursue an inductor-IC pre-loading fix (build edit; out of scope
#     for the current Phase 3 allow-list).
T_WARMUP = 10.0  # smoke-stage; was 3.0 (v2 baseline), bumped per P3.3b

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
# R2 (2026-04-27): allow per-run env-var override to widen the PHI sweep without
# editing this file between candidates. Default 100.0 = paper-faithful.
PHI_F = float(_os.getenv("KUNDUR_PHI_F", "100.0"))

# Kundur-only PHI_H/PHI_D override (2026-04-26 reward-scale gate after asym
# 50ep observation kundur_simulink_20260426_144431 showed r_f% ≈ 0.0005% with
# Q7 H/D dimension issue making r_h ~ -300 / r_d ~ -70 dominate. With M0=24
# D0=4.5 the |ΔH_avg|² and |ΔD_avg|² magnitudes are ~10^4 and ~10^2 larger
# than what φ_h=φ_d=1 paper baseline assumes (paper does not specify H/D
# dimensions — see docs/paper/yang2023-fact-base.md §2.1 Q7). Scaling
# φ_h=φ_d=0.001 brings r_h/r_d into the same order as r_f, restoring the
# paper's intended reward weighting (r_f leading by PHI_F factor). NE39 is
# untouched: this override is local to this module.
# Plan B1 (2026-04-26): PHI_H=PHI_D=0.001 produced r_f% mean 0.47% on the
# 50ep PHI-gate run kundur_simulink_20260426_150848 — well below the 1% floor.
# Math: r_f abs_mean ≈ 1.7e-3, r_h ≈ 0.293, r_d ≈ 0.080 → r_f / total ≈ 0.45%.
# Drop another decade to bring r_f% into the 3%-8% target band:
#   r_h ≈ 0.029, r_d ≈ 0.008 → predicted r_f% ≈ 1.7e-3/(1.7e-3+0.029+0.008) ≈ 4.4%.
# P4.2 (2026-04-27): allow per-run override via env vars without editing this
# file between sweep candidates. Plan §Gap 2 sweep candidates:
#   phi_b1            -> KUNDUR_PHI_H=1e-4  KUNDUR_PHI_D=1e-4   (defaults)
#   phi_asym_a        -> KUNDUR_PHI_H=1e-3  KUNDUR_PHI_D=1e-4
#   phi_paper_scaled  -> KUNDUR_PHI_H=1e-2  KUNDUR_PHI_D=1e-2
#   phi_asym_b        -> KUNDUR_PHI_H=1e-2  KUNDUR_PHI_D=1e-3   (only if needed)
#   phi_paper         -> KUNDUR_PHI_H=1.0   KUNDUR_PHI_D=1.0    (only if needed)
PHI_H = float(_os.getenv("KUNDUR_PHI_H", "0.0001"))
PHI_D = float(_os.getenv("KUNDUR_PHI_D", "0.0001"))

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

# Promotion 2026-04-26 — CVS profile uses self-contained 4-VSG topology
# (kundur_ic_cvs.json, no INF). Its Pm0 = 0.2 system-pu/VSG (4*0.2 = 0.8 = total
# load) is incompatible with the legacy kundur_ic.json (Pm0_sys = 0.05 paper
# baseline absorbed by INF). v3 (kundur_ic_cvs_v3.json) ships NR-derived
# ESS Pm0 ≈ -0.369 sys-pu/source (group absorbs +185 MW surplus). The
# helper below dispatches per profile so the bridge's pe0_default_vsg /
# delta0_deg always match the active profile's IC contract — no risk of
# pairing a v2 IC with a v3 model name (or vice versa).


def _load_profile_ic(profile):
    """Resolve (Pm0_sys_pu, delta0_rad) for a Kundur model profile.

    Single source of truth for the profile -> IC JSON mapping. Used both
    at module-import time (for the default ``KUNDUR_MODEL_PROFILE``) and
    at runtime by ``make_bridge_config`` when ``KundurSimulinkEnv`` is
    constructed with a ``model_profile_path`` that differs from the
    import-time env-var.
    """
    import json as _json
    scenario_dir = Path(__file__).resolve().parent
    if profile.model_name == 'kundur_cvs':
        with (scenario_dir / 'kundur_ic_cvs.json').open(encoding='utf-8') as _f:
            raw = _json.load(_f)
        return (
            np.asarray(raw['vsg_pm0_pu'], dtype=np.float64),
            np.asarray(raw['vsg_internal_emf_angle_rad'], dtype=np.float64),
        )
    if profile.model_name == 'kundur_cvs_v3':
        # P3.2 (2026-04-26): v3 paper-faithful 16-bus CVS path. Identity
        # contract enforced by build_kundur_cvs_v3.m: refuses to load a
        # non-v3 IC. Mirror that contract here.
        with (scenario_dir / 'kundur_ic_cvs_v3.json').open(encoding='utf-8') as _f:
            raw = _json.load(_f)
        if raw.get('schema_version') != 3:
            raise ValueError(
                f"kundur_ic_cvs_v3.json: expected schema_version=3, got "
                f"{raw.get('schema_version')!r}"
            )
        if raw.get('topology_variant') != 'v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged':
            raise ValueError(
                "kundur_ic_cvs_v3.json: topology_variant must be "
                "'v3_paper_kundur_15bus_w2_at_bus8_ls1_preengaged' "
                "(Task 1: W2 → Bus 8; Task 2: Bus 14 LS1 248 MW pre-engaged)"
            )
        return (
            np.asarray(raw['vsg_pm0_pu'], dtype=np.float64),
            np.asarray(raw['vsg_internal_emf_angle_rad'], dtype=np.float64),
        )
    # Legacy/SPS: powerlib kundur_ic.json (VSG-base) -> sys-pu via to_sbase_pu.
    return (
        VSG_P0_SBASE,
        np.asarray(_ic.vsg_delta0_deg, dtype=np.float64) * np.pi / 180.0,
    )


VSG_PE0_DEFAULT_SYS, VSG_DELTA0_RAD = _load_profile_ic(KUNDUR_MODEL_PROFILE)

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

# ========== Disturbance Type (Phase 4 Gap 1 — Path C Pm-step proxy) ==========
# Plan: quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md
# Audit: results/harness/kundur/cvs_v3_phase4/phase4_p40_audit_verdict.md
#
# Paper Sec.IV-C names disturbances "load step 1 / 2" at Bus 7 / Bus 9. v3
# build_kundur_cvs_v3.m creates G_perturb_*/LoadStep_t_*/LoadStep_amp_*
# workspace vars but the LoadStep R-only branches at lines 316-336 hardcode
# Resistance='1e9' as a string literal — workspace path is provably DEAD
# (Phase 4.0 audit §R2-Blocker1). Path (A) build-edit is forbidden under §0
# allow-list. Path (C) Pm-step proxy uses existing apply_workspace_var on
# Pm_step_t_<i>/Pm_step_amp_<i> with target ESS chosen by electrical
# proximity to the paper bus (P2.3-L1 measurements):
#   pm_step_proxy_bus7        -> ES1 (idx 0)  electrically nearest to Bus 7
#   pm_step_proxy_bus9        -> ES4 (idx 3)  electrically nearest to Bus 9
#   pm_step_proxy_random_bus  -> per-disturbance 50/50 pick (bus7 or bus9)
#   pm_step_single_vsg        -> legacy default: honors class attr
#                                DISTURBANCE_VSG_INDICES (fallback (0,))
#
# Phase 4 default keeps `pm_step_single_vsg` to preserve existing training
# behavior for any legacy path that imports the env without specifying
# disturbance_type. P4.2 PHI sweep launches will set
# `KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus` via env var.
KUNDUR_DISTURBANCE_TYPES_VALID = (
    "pm_step_single_vsg",
    "pm_step_proxy_bus7",
    "pm_step_proxy_bus9",
    "pm_step_proxy_random_bus",
    # Z1 (2026-04-27): SG-side Pm-step proxy. Routes the disturbance into the
    # synchronous-generator sources (G1/G2/G3) via PmgStep_amp_<g> workspace
    # vars. Paper-form-correct topology: disturbance enters at a non-ESS source
    # and propagates through the network to the ESS, where H/D adjustments now
    # have system-level leverage (vs ESS-side proxy which lacks leverage —
    # see phase5_r2_phi_sweep_verdict.md §2 root cause analysis).
    "pm_step_proxy_g1",
    "pm_step_proxy_g2",
    "pm_step_proxy_g3",
    "pm_step_proxy_random_gen",
    # Phase A (2026-04-27): real LoadStep wiring at v3 Bus 14 / Bus 15 via
    # workspace-tunable Series RLC R (Resistance = Vbase^2/max(amp,1e-3)).
    # amp pushed in W; magnitude (sys-pu) -> W via cfg.sbase_va. Step-on
    # semantics: amp 0 -> X engages X-watt load -> freq drops. Paper LoadStep
    # 1 trip-direction (Bus 14 freq rises) deferred — needs NR re-derivation
    # or controlled current source.
    "loadstep_paper_bus14",
    "loadstep_paper_bus15",
    "loadstep_paper_random_bus",
    # Phase A++ (2026-04-27): trip-direction LoadStep via Controlled Current
    # Source. amp pushed in W; magnitude (sys-pu, expected positive) -> W via
    # cfg.sbase_va. Trip semantics: amp 0 -> X injects X-watt at bus -> freq
    # rises (paper LoadStep 1 direction). NR/IC unchanged at amp=0.
    "loadstep_paper_trip_bus14",
    "loadstep_paper_trip_bus15",
    "loadstep_paper_trip_random_bus",
)
KUNDUR_DISTURBANCE_TYPE = _os.getenv(
    "KUNDUR_DISTURBANCE_TYPE", "pm_step_single_vsg"
)
if KUNDUR_DISTURBANCE_TYPE not in KUNDUR_DISTURBANCE_TYPES_VALID:
    raise ValueError(
        f"KUNDUR_DISTURBANCE_TYPE={KUNDUR_DISTURBANCE_TYPE!r} not in "
        f"{KUNDUR_DISTURBANCE_TYPES_VALID}"
    )


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
# G5 (2026-04-27, paper-explicit closure): paper Table I specifies replay
# buffer = 10000. Project previously used 100000 (10× larger) "Kundur fills
# buffer slower" override, but P4.2-overnight evidence (ep 50→670 plateau)
# suggests buffer was over-large and stale experience pulled policy toward
# inertia. Reverting to paper-faithful 10000.
BUFFER_SIZE = 10000
# WARMUP_STEPS: 4-agent Kundur needs more warmup to fill buffer adequately.
WARMUP_STEPS = 2000

# ========== Simulink Model ==========
SIMULINK_MODEL = 'kundur_vsg'
SIMULINK_MODEL_DIR = None  # Auto-detect from project root
MINGW_PATH = r'D:\mingw64'

# ========== SimulinkBridge Configuration ==========
from engine.simulink_bridge import BridgeConfig


def make_bridge_config(profile, *, model_dir=None) -> BridgeConfig:
    """Build a BridgeConfig from a Kundur model profile.

    Single factory used both at module-import (for the default
    ``KUNDUR_BRIDGE_CONFIG``) and at runtime by ``KundurSimulinkEnv``
    when the active profile differs from the import-time env-var.
    Loads the profile-matching IC JSON via ``_load_profile_ic`` and
    dispatches all CVS-vs-legacy template / strategy branches
    consistently — so callers cannot accidentally pair a v2 IC with
    a v3 model name (or vice versa) by passing a non-default
    ``model_profile_path`` to the env constructor.

    P3.2 (2026-04-26): v2 (kundur_cvs) and v3 (kundur_cvs_v3) share
    the CVS bridge contract verbatim — Timeseries logger naming
    ``omega_ts_{idx}``, ``cvs_signal`` step strategy, ``M_{idx}`` /
    ``D_{idx}`` workspace var names, M0=24/D0=4.5 defaults. Only the
    IC dispatched into ``pe0_default_vsg`` / ``delta0_deg`` differs.
    Legacy/SPS profiles keep the phang_feedback path with its own
    template set (M0_val_ES{idx} / D0_val_ES{idx}, M0=12/D0=3).
    """
    pe0_sys, delta0_rad = _load_profile_ic(profile)
    is_cvs = profile.model_name in ('kundur_cvs', 'kundur_cvs_v3')
    resolved_dir = model_dir or _os.path.join(
        _os.path.dirname(_os.path.abspath(__file__)), 'simulink_models'
    )
    return BridgeConfig(
        model_name=profile.model_name,
        phase_command_mode=profile.phase_command_mode,
        model_dir=resolved_dir,
        n_agents=N_AGENTS,
        dt_control=DT,
        sbase_va=SBASE * 1e6,  # 100 MVA -> 100e6 VA
        m_path_template='{model}/VSG_ES{idx}/M0',
        d_path_template='{model}/VSG_ES{idx}/D0',
        omega_signal='omega_ts_{idx}' if is_cvs else 'omega_ES{idx}',
        vabc_signal='Vabc_ES{idx}',
        iabc_signal='Iabc_ES{idx}',
        pe_path_template='{model}/Pe_{idx}',
        src_path_template='{model}/VSrc_ES{idx}',
        p_out_signal='P_out_ES{idx}',
        pe_measurement=profile.pe_measurement,
        step_strategy='cvs_signal' if is_cvs else 'phang_feedback',
        m_var_template='M_{idx}' if is_cvs else 'M0_val_ES{idx}',
        d_var_template='D_{idx}' if is_cvs else 'D0_val_ES{idx}',
        m0_default=24.0 if is_cvs else 12.0,
        # Promotion 2026-04-26: CVS d0 lowered 18.0 -> 4.5 to escape
        # over-damping. With DD_MIN/DD_MAX = [-1.5, +4.5] this gives
        # D_runtime ∈ [3.0, 9.0], the H-sensitive band where dry-run
        # probes confirmed RL learnability.
        d0_default=4.5 if is_cvs else 3.0,
        pe_feedback_signal='PeFb_ES{idx}',
        # Dynamic Load disturbance: per-phase W stored in base workspace.
        # Bus14: TripLoad1_P = 248/3 MW per phase (nominal load on).
        # Bus15: TripLoad2_P = 0 W (set to 188/3 MW on disturbance).
        tripload1_p_default=248e6 / 3,
        tripload2_p_default=0.0,
        # CVS profiles use sys-pu Pm0 (kundur_ic_cvs*.json); legacy/SPS
        # profiles use powerlib kundur_ic.json reduced to sys-pu by
        # _load_profile_ic via to_sbase_pu.
        pe0_default_vsg=tuple(pe0_sys.tolist()),
        delta0_deg=tuple((delta0_rad * 180.0 / np.pi).tolist()),
        # absolute_with_loadflow mode: init_phang offsets the
        # post-warmup phAng update. For Kundur SPS phAng is the rotor
        # angle directly (no bus-angle offset), so init_phang = (0,...)
        # reduces to ph = delta_clipped. passthrough mode does not use
        # init_phang; keep empty for that path.
        init_phang=tuple(0.0 for _ in range(N_AGENTS))
        if profile.phase_command_mode == 'absolute_with_loadflow'
        else (),
        # SPS Phasor Three-Phase V-I Measurement outputs peak phasors
        # (not RMS). real(V_peak × I_peak*) = 2 × average power -> scale
        # by 0.5 to recover watts.
        pe_vi_scale=0.5 if profile.pe_measurement == 'vi' else 1.0,
        breaker_step_block_template='',
        breaker_count=0,
    )


# Module-level default — built from the import-time KUNDUR_MODEL_PROFILE
# (env-var or DEFAULT_KUNDUR_MODEL_PROFILE). Kept for backwards compat
# with callers that import KUNDUR_BRIDGE_CONFIG directly. Runtime callers
# (KundurSimulinkEnv) should use make_bridge_config(self._runtime_profile)
# so the BridgeConfig matches the active profile end-to-end.
KUNDUR_BRIDGE_CONFIG = make_bridge_config(
    KUNDUR_MODEL_PROFILE, model_dir=SIMULINK_MODEL_DIR
)
