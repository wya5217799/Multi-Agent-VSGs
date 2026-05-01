"""ODE Boundary Gate G2 — Proposition 1 (paper Sec.II-B).

Plan: quality_reports/plans/2026-05-02_ode_paper_alignment.md (Stage 5 follow-up)
Critic verdict Q2 (gap acknowledged): paper-mechanism check missing from
original Stage 5 output.

Paper claim (kd_4agent_paper_facts.md §1.5):
    H_es,i = k_i * H_es,0,  D_es,i = k_i * D_es,0,  Δu_i = k_i * Δu_0
    →  Δω_i (t) identical across all i  (no differential mode, no oscillation)

Verification: under proportional H/D/Δu, the 4 ESS frequency trajectories
must collapse to the same curve. We check three conditions (each tightens):

  P1.a  Equal-k case (k_i = 1 for all i, baseline H_ES0/D_ES0/uniform Δu)
        → trivially identical (sanity check).
  P1.b  Non-trivial proportional (k = [0.5, 1.0, 1.5, 2.0])
        → trajectories should still collapse (this is the paper claim).
  P1.c  Mismatched (k_H = [1,1,1,1] but Δu = [1,0,0,0]) — counter-example
        → trajectories MUST diverge (sanity that the test discriminates).

PASS: P1.a + P1.b agree to relative L2 < 1% across all pairs; P1.c diverges.

Note: This is the boundary doc §18 G2 (Proposition 1 sanity), distinct
from the Stage 2 manifest probe (also coincidentally named G2). Filename
chosen as ``ode_gate_proposition1`` to disambiguate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from env.network_topology import build_laplacian  # noqa: E402
from env.ode.power_system import PowerSystem      # noqa: E402
import config as cfg                                # noqa: E402


def _run_proportional(k: np.ndarray, n_steps: int = 50) -> np.ndarray:
    """Build a PowerSystem with H/D/Δu all scaled by k, return omega trace.

    Returns shape (n_steps+1, N) — initial state + n_steps integration.
    """
    L = build_laplacian(cfg.B_MATRIX, cfg.V_BUS)
    H = cfg.H_ES0 * k
    D = cfg.D_ES0 * k
    delta_u = 1.0 * k   # Δu_0 = 1, scale by k_i
    ps = PowerSystem(L, H, D, dt=cfg.DT, fn=cfg.OMEGA_N / (2 * np.pi))
    ps.reset(delta_u=delta_u)
    omega_trace = np.zeros((n_steps + 1, cfg.N_AGENTS))
    omega_trace[0] = ps.state[cfg.N_AGENTS:2 * cfg.N_AGENTS]
    for t in range(n_steps):
        ps.step()
        omega_trace[t + 1] = ps.state[cfg.N_AGENTS:2 * cfg.N_AGENTS]
    return omega_trace


def _max_pairwise_relative_l2(trace: np.ndarray) -> float:
    """Largest pairwise relative L2 distance across the N agents."""
    N = trace.shape[1]
    worst = 0.0
    for i in range(N):
        for j in range(i + 1, N):
            d = np.linalg.norm(trace[:, i] - trace[:, j])
            ref = max(np.linalg.norm(trace[:, i]), np.linalg.norm(trace[:, j]), 1e-12)
            worst = max(worst, d / ref)
    return float(worst)


def gate_p1a_uniform() -> bool:
    print("\n=== G_P1.a · k_i = [1,1,1,1] → trajectories identical (sanity) ===")
    trace = _run_proportional(np.array([1.0, 1.0, 1.0, 1.0]))
    rel = _max_pairwise_relative_l2(trace)
    if rel > 1e-9:
        print(f"  FAIL  max_pairwise_rel_L2 = {rel:.3e}")
        return False
    print(f"  PASS  max_pairwise_rel_L2 = {rel:.3e}")
    return True


def gate_p1b_proportional() -> bool:
    """Paper Proposition 1 main claim."""
    print("\n=== G_P1.b · k_i = [0.5, 1.0, 1.5, 2.0] → Δω_i identical (paper Prop.1) ===")
    k = np.array([0.5, 1.0, 1.5, 2.0])
    trace = _run_proportional(k)
    rel = _max_pairwise_relative_l2(trace)
    # M-1 fix 2026-05-02: tighten threshold from 1e-6 → 1e-10 to actually
    # enforce the numerical-precision claim (observed value ~3.7e-14).
    # Loose 1e-6 would let a regression to ~1e-7 silently pass.
    if rel > 1e-10:
        print(f"  FAIL  max_pairwise_rel_L2 = {rel:.3e}  (Prop.1 violated, threshold 1e-10)")
        print(f"    final omega = {trace[-1].round(6)}")
        return False
    print(f"  PASS  max_pairwise_rel_L2 = {rel:.3e}; final omega = {trace[-1].round(6)}")
    return True


def gate_p1c_mismatch_diverges() -> bool:
    """Counter-example: H/D scaled but Δu NOT scaled → divergent trajectories."""
    print("\n=== G_P1.c · k_H scaled but Δu uniform → trajectories MUST differ ===")
    L = build_laplacian(cfg.B_MATRIX, cfg.V_BUS)
    k = np.array([0.5, 1.0, 1.5, 2.0])
    H = cfg.H_ES0 * k
    D = cfg.D_ES0 * k
    delta_u = np.array([1.0, 0.0, 0.0, 0.0])  # NOT proportional to k
    ps = PowerSystem(L, H, D, dt=cfg.DT, fn=cfg.OMEGA_N / (2 * np.pi))
    ps.reset(delta_u=delta_u)
    omega_trace = np.zeros((51, cfg.N_AGENTS))
    omega_trace[0] = ps.state[cfg.N_AGENTS:2 * cfg.N_AGENTS]
    for t in range(50):
        ps.step()
        omega_trace[t + 1] = ps.state[cfg.N_AGENTS:2 * cfg.N_AGENTS]
    rel = _max_pairwise_relative_l2(omega_trace)
    # We require divergence: max_pairwise_rel_L2 > 1% (strong difference)
    if rel < 1e-2:
        print(f"  FAIL  max_pairwise_rel_L2 = {rel:.3e}  (test undiscriminating)")
        return False
    print(f"  PASS  max_pairwise_rel_L2 = {rel:.3e}  (divergence detected as expected)")
    return True


def main() -> int:
    print("=" * 65)
    print("  ODE Boundary G2 · Proposition 1 (paper Sec.II-B mechanism)")
    print("  Closes critic Q2 gap from 2026-05-02 verdict")
    print("=" * 65)
    results = {
        "P1.a_uniform_sanity": gate_p1a_uniform(),
        "P1.b_proportional_collapse": gate_p1b_proportional(),
        "P1.c_mismatch_diverges": gate_p1c_mismatch_diverges(),
    }
    print("\n" + "=" * 65)
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL':6s}  G_{k}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
