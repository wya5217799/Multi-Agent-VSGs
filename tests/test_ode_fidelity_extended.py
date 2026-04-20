"""Promotion gates for Tasks 1–5 (engineering regression thresholds).

Each gate covers one dimension of the ODE upgrade and fails if a
future refactor violates the design-time threshold.
"""
import numpy as np
import pytest

from env.network_topology import build_laplacian
from env.ode.power_system import PowerSystem
from utils.ode_events import (
    DisturbanceEvent,
    EventSchedule,
    LineTripEvent,
)
from utils.ode_heterogeneity import generate_heterogeneous_params


_B = np.array([
    [0, 4, 0, 0],
    [4, 0, 4, 0],
    [0, 4, 0, 4],
    [0, 0, 4, 0],
], dtype=float)
_V = np.ones(4)
_L = build_laplacian(_B, _V)


def _peak_omega(ps, steps):
    peak = 0.0
    for _ in range(steps):
        r = ps.step()
        peak = max(peak, float(np.max(np.abs(r['omega']))))
    return peak


def test_heterogeneous_peak_freq_within_20pct_of_uniform():
    """±30 % spread in H should keep peak |ω| within 20 % of the uniform case."""
    H_uni = np.full(4, 24.0)
    D_uni = np.full(4, 18.0)
    H_het = generate_heterogeneous_params(H_uni, spread=0.30, seed=2023)
    D_het = generate_heterogeneous_params(D_uni, spread=0.30, seed=2024)

    du = np.array([2.4, 0.0, -2.4, 0.0])
    ps_uni = PowerSystem(_L, H_uni, D_uni, dt=0.1, fn=50.0)
    ps_uni.reset(delta_u=du)
    peak_uni = _peak_omega(ps_uni, 100)

    ps_het = PowerSystem(_L, H_het, D_het, dt=0.1, fn=50.0)
    ps_het.reset(delta_u=du)
    peak_het = _peak_omega(ps_het, 100)

    assert 0.80 * peak_uni <= peak_het <= 1.20 * peak_uni, (
        f"peak_uni={peak_uni:.3f}, peak_het={peak_het:.3f}"
    )


def test_nonlinear_large_signal_bounded():
    """Nonlinear network must stay finite and not exceed linear peak by more than 50% for 1.5 p.u. step.

    Uses 1.5 p.u. — the largest amplitude that keeps both modes synchronized
    (stability margin < 3 p.u. for B_tie=4).  At this amplitude sin(θ) ≈ θ
    within ~2 %, so the nonlinear peak should track the linear peak closely.
    """
    du = np.array([1.5, 0.0, -1.5, 0.0])
    ps_lin = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.1, fn=50.0,
                          B_matrix=_B, V_bus=_V, network_mode='linear')
    ps_lin.reset(delta_u=du)
    peak_lin = _peak_omega(ps_lin, 100)

    ps_non = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.1, fn=50.0,
                          B_matrix=_B, V_bus=_V, network_mode='nonlinear')
    ps_non.reset(delta_u=du)
    peak_non = _peak_omega(ps_non, 100)

    assert np.isfinite(peak_non), "nonlinear diverged"
    assert peak_non <= 1.5 * peak_lin, f"nonlinear overshoot: lin={peak_lin}, non={peak_non}"


def test_governor_steady_state_error_below_threshold():
    """Governor with R=0.05 reduces SS |Δω| vs no-governor for uniform -0.5 p.u. step."""
    delta_u = np.array([-0.5, -0.5, -0.5, -0.5])
    ps_off = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0)
    ps_off.reset(delta_u=delta_u)
    for _ in range(500):
        r_off = ps_off.step()
    ss_off = float(np.mean(np.abs(r_off['omega'])))

    ps = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.2, fn=50.0,
                     governor_enabled=True, governor_R=0.05, governor_tau_g=0.5)
    ps.reset(delta_u=delta_u)
    for _ in range(500):
        r = ps.step()
    ss = float(np.mean(np.abs(r['omega'])))
    assert ss < 0.6 * ss_off, f"Governor should cut SS |ω| by >40%: off={ss_off:.2f}, on={ss:.2f} rad/s"
    assert ss < 6.0, f"Governor SS |ω| physically too large: {ss:.2f} rad/s (expected ~4 rad/s)"


def test_multivsgenv_default_path_is_deterministic():
    """With all ODE flags off, two identical MultiVSGEnv runs must produce identical obs/reward/ps.state."""
    import config as cfg
    from env.ode.multi_vsg_env import MultiVSGEnv

    assert not getattr(cfg, 'ODE_HETEROGENEOUS', False), "Test requires all ODE flags off"
    assert not getattr(cfg, 'ODE_GOVERNOR_ENABLED', False), "Test requires all ODE flags off"
    assert getattr(cfg, 'ODE_NETWORK_MODE', 'linear') == 'linear', "Test requires all ODE flags off"

    du = np.array([2.0, 0.0, -2.0, 0.0])

    def run_env():
        env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
        env.reset(delta_u=du)
        rewards = []
        zero_actions = {i: np.zeros(2) for i in range(env.N)}
        for _ in range(5):
            obs, rew, _, _ = env.step(zero_actions)
            rewards.append(float(sum(rew.values())))
        obs_arr = np.concatenate([obs[i] for i in range(env.N)])
        return obs_arr, rewards, env.ps.state.copy()

    obs_a, rew_a, state_a = run_env()
    obs_b, rew_b, state_b = run_env()

    np.testing.assert_allclose(obs_a, obs_b, atol=1e-12, err_msg="obs not reproducible")
    np.testing.assert_allclose(rew_a, rew_b, atol=1e-12, err_msg="rewards not reproducible")
    np.testing.assert_allclose(state_a, state_b, atol=1e-12, err_msg="ps.state not reproducible")


def test_line_trip_modal_frequency_decreases():
    """Tripping the middle tie should lower the chain's λ_min and slow oscillation."""
    ps_pre = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.1, fn=50.0,
                         B_matrix=_B.copy(), V_bus=_V, network_mode='linear')
    ps_pre.reset(delta_u=np.array([1.0, 0.0, -1.0, 0.0]))
    for _ in range(100):
        ps_pre.step()
    eig_pre = sorted(np.linalg.eigvalsh(ps_pre.L).tolist())

    ps_post = PowerSystem(_L, np.full(4, 24.0), np.full(4, 18.0), dt=0.1, fn=50.0,
                          B_matrix=_B.copy(), V_bus=_V, network_mode='linear')
    ps_post.reset(event_schedule=EventSchedule(events=(
        DisturbanceEvent(t=0.0, delta_u=np.array([1.0, 0.0, -1.0, 0.0])),
        LineTripEvent(t=0.0, bus_i=1, bus_j=2),
    )))
    ps_post.step()  # apply trip
    eig_post = sorted(np.linalg.eigvalsh(ps_post.L).tolist())

    assert eig_post[1] < eig_pre[1], (
        f"λ_2 should decrease after trip: pre={eig_pre[1]:.3f}, post={eig_post[1]:.3f}"
    )
