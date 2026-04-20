"""Physics validation gates — verify ODE modal parameters match paper targets."""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def _compute_modal_params(H, D, B_tie, fn=50.0):
    """Compute ω_n, ζ for a uniform 4-node chain with given H, D, B_tie."""
    omega_s = 2.0 * np.pi * fn
    # Minimum eigenvalue of 4-node chain Laplacian: λ_min = 2*B*(1-cos(π/N))
    lam_min = 2.0 * B_tie * (1.0 - np.cos(np.pi / 4))
    omega_n = np.sqrt(omega_s * lam_min / (2.0 * H))  # rad/s
    zeta = D / (4.0 * H * omega_n)
    return omega_n / (2.0 * np.pi), zeta  # Hz, dimensionless


def _compute_df_peak(H, D, B_tie, disturbance_amplitude=2.4, fn=50.0):
    """Simulate 10 s and return peak |Δf| in Hz for [A,0,-A,0] disturbance."""
    from env.network_topology import build_laplacian
    from env.ode.power_system import PowerSystem

    B = np.array([
        [0,      B_tie, 0,      0],
        [B_tie,  0,     B_tie,  0],
        [0,      B_tie, 0,      B_tie],
        [0,      0,     B_tie,  0],
    ], dtype=float)
    L = build_laplacian(B, np.ones(4))
    H_arr = np.full(4, H)
    D_arr = np.full(4, D)
    ps = PowerSystem(L, H_arr, D_arr, dt=0.1, fn=fn)
    delta_u = np.array([disturbance_amplitude, 0.0, -disturbance_amplitude, 0.0])
    ps.reset(delta_u=delta_u)

    peak_df = 0.0
    for _ in range(100):  # 10 s with dt=0.1
        result = ps.step()
        df = float(np.max(np.abs(result['freq_hz'] - fn)))
        if df > peak_df:
            peak_df = df
    return peak_df


def test_omega_n_in_target_range():
    """ω_n must be in [0.55, 0.70] Hz (paper target ~0.6 Hz)."""
    import config as cfg
    H = float(cfg.H_ES0[0])
    D = float(cfg.D_ES0[0])
    B_tie = float(cfg.B_MATRIX[0, 1])
    omega_n_hz, _ = _compute_modal_params(H, D, B_tie)
    assert 0.55 <= omega_n_hz <= 0.70, (
        f"ω_n = {omega_n_hz:.4f} Hz outside [0.55, 0.70] Hz; "
        f"check H_ES0={H}, B_tie={B_tie}"
    )


def test_damping_ratio_in_target_range():
    """ζ must be in [0.03, 0.08] (paper target ~0.05, lightly damped)."""
    import config as cfg
    H = float(cfg.H_ES0[0])
    D = float(cfg.D_ES0[0])
    B_tie = float(cfg.B_MATRIX[0, 1])
    _, zeta = _compute_modal_params(H, D, B_tie)
    assert 0.03 <= zeta <= 0.08, (
        f"ζ = {zeta:.5f} outside [0.03, 0.08]; "
        f"check D_ES0={D}, H_ES0={H}"
    )


def test_df_peak_in_target_range():
    """Δf_peak for LS1=[2.4,0,-2.4,0] must be in [0.30, 0.55] Hz (paper ~0.4 Hz)."""
    import config as cfg
    H = float(cfg.H_ES0[0])
    D = float(cfg.D_ES0[0])
    B_tie = float(cfg.B_MATRIX[0, 1])
    df_peak = _compute_df_peak(H, D, B_tie)
    assert 0.30 <= df_peak <= 0.55, (
        f"Δf_peak = {df_peak:.4f} Hz outside [0.30, 0.55] Hz"
    )


def test_warmup_h_floor_prevents_blowup():
    """DH_MIN must allow H below 8.0 so the env floor clamp (Task 2) is non-vacuous."""
    import config as cfg
    H_floor = 8.0
    min_H = float(cfg.H_ES0[0]) + cfg.DH_MIN
    assert min_H < H_floor, (
        f"DH_MIN={cfg.DH_MIN} gives min_H={min_H:.1f} which is not < H_floor={H_floor}; "
        f"the env floor clamp would be vacuous"
    )
