"""ODE Gate 2 — Scenario manifest reproducibility & legacy parity.

Plan: quality_reports/plans/2026-05-02_ode_paper_alignment.md (Stage 2)

Verifies:
  G2.a  Two regenerations of train/test manifests with identical seeds
        produce JSON files with identical bytes.
  G2.b  ODEScenario manifest content matches the legacy inline generators
        ``train_ode.generate_scenario_set`` / ``evaluate_ode.generate_test_scenarios``
        for byte-equal ``delta_u`` and identical ``comm_failed_links`` ordering.
  G2.c  ``env.reset(scenario=ODEScenario(...))`` produces an environment
        state numerically identical to ``env.reset(delta_u=..., forced_link_failures=...)``
        after stepping 50 zero-action steps.

PASS criteria: all three sub-gates print PASS.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from env.ode.multi_vsg_env import MultiVSGEnv  # noqa: E402
from env.ode.ode_scenario import (  # noqa: E402
    SEED_TRAIN_DEFAULT,
    SEED_TEST_DEFAULT,
    generate_scenarios,
    save_manifest,
    load_manifest,
    ODE_SCENARIO_SETS_DIR,
    N_TRAIN_PAPER,
    N_TEST_PAPER,
)
import config as cfg  # noqa: E402


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def gate_2a_byte_reproducibility(tmp_dir: Path) -> bool:
    print("\n=== G2.a · Manifest regeneration is byte-reproducible ===")
    p1 = tmp_dir / "train_v1.json"
    p2 = tmp_dir / "train_v2.json"
    s1 = generate_scenarios(N_TRAIN_PAPER, SEED_TRAIN_DEFAULT, "kd_train_100")
    s2 = generate_scenarios(N_TRAIN_PAPER, SEED_TRAIN_DEFAULT, "kd_train_100")
    save_manifest(s1, p1)
    save_manifest(s2, p2)
    h1, h2 = _file_sha256(p1), _file_sha256(p2)
    if h1 != h2:
        print(f"  FAIL  hash mismatch:\n    v1={h1}\n    v2={h2}")
        return False
    print(f"  PASS  sha256={h1[:16]}...  ({N_TRAIN_PAPER} scenarios)")
    return True


def _legacy_generator(n: int, seed: int) -> list[tuple[np.ndarray, list[tuple[int, int]] | None]]:
    """Reproduce inline logic of ``train_ode.py::generate_scenario_set``."""
    rng = np.random.default_rng(seed)
    out: list[tuple[np.ndarray, list[tuple[int, int]] | None]] = []
    for _ in range(n):
        n_disturbed = rng.integers(1, 3)
        buses = rng.choice(cfg.N_AGENTS, size=n_disturbed, replace=False)
        delta_u = np.zeros(cfg.N_AGENTS)
        for bus in buses:
            magnitude = rng.uniform(cfg.DISTURBANCE_MIN, cfg.DISTURBANCE_MAX)
            sign = rng.choice([-1, 1])
            delta_u[bus] = sign * magnitude
        failed_links = []
        for i, neighbors in cfg.COMM_ADJACENCY.items():
            for j in neighbors:
                if (j, i) not in failed_links and rng.random() < cfg.COMM_FAIL_PROB:
                    failed_links.append((i, j))
                    failed_links.append((j, i))
        out.append((delta_u, failed_links if failed_links else None))
    return out


def gate_2b_legacy_parity() -> bool:
    print("\n=== G2.b · ODEScenario equals legacy inline generator (delta_u, links) ===")
    legacy = _legacy_generator(N_TRAIN_PAPER, SEED_TRAIN_DEFAULT)
    new_set = generate_scenarios(N_TRAIN_PAPER, SEED_TRAIN_DEFAULT, "kd_train_100")

    if len(legacy) != len(new_set.scenarios):
        print(f"  FAIL  length mismatch: legacy={len(legacy)} new={len(new_set.scenarios)}")
        return False
    max_du_err = 0.0
    fl_mismatch = 0
    for k, ((du_l, fl_l), s_n) in enumerate(zip(legacy, new_set.scenarios)):
        du_n = np.asarray(s_n.delta_u)
        max_du_err = max(max_du_err, float(np.max(np.abs(du_l - du_n))))
        # Convert legacy None -> () for comparison
        legacy_links = tuple(tuple(p) for p in (fl_l or []))
        if legacy_links != s_n.comm_failed_links:
            fl_mismatch += 1
    if max_du_err > 1e-12:
        print(f"  FAIL  max delta_u abs err = {max_du_err:.3e}")
        return False
    if fl_mismatch != 0:
        print(f"  FAIL  {fl_mismatch} scenarios have differing comm_failed_links")
        return False
    print(f"  PASS  max_du_err={max_du_err:.3e}, fl_mismatch=0/{N_TRAIN_PAPER}")
    return True


def gate_2c_reset_equivalence() -> bool:
    print("\n=== G2.c · env.reset(scenario=) equals legacy reset path numerically ===")
    new_set = generate_scenarios(N_TRAIN_PAPER, SEED_TRAIN_DEFAULT, "kd_train_100")
    s = new_set.scenarios[0]
    du, fl = s.to_legacy_tuple()

    # Path A: legacy
    env_a = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    env_a.forced_link_failures = fl
    env_a.reset(delta_u=du)
    zero_action = {i: np.zeros(2, dtype=np.float32) for i in range(cfg.N_AGENTS)}
    for _ in range(50):
        env_a.step(zero_action)
    state_a = env_a.ps.state.copy()

    # Path B: new scenario= kwarg
    env_b = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
    env_b.reset(scenario=s)
    for _ in range(50):
        env_b.step(zero_action)
    state_b = env_b.ps.state.copy()

    abs_err = float(np.max(np.abs(state_a - state_b)))
    if abs_err > 1e-12:
        print(f"  FAIL  abs_err = {abs_err:.6e} > 1e-12")
        return False
    print(f"  PASS  abs_err = {abs_err:.3e}  (state_dim={state_a.shape[0]})")
    return True


def gate_2d_forced_failures_authoritative() -> bool:
    """M3 regression: forced failures must override env-level prob.

    With env constructed at comm_fail_prob=0.3 and a scenario specifying
    explicit failures, only the scenario-listed links may be 0. All other
    links must be 1 (scenario VO is authoritative; no extra random fails).
    """
    print("\n=== G2.d · forced failures override comm_fail_prob (M3 fix) ===")
    from env.ode.ode_scenario import ODEScenario
    forced = ((0, 1), (1, 0))
    s = ODEScenario(scenario_idx=0, delta_u=(0.0, 0.0, 0.0, 0.0),
                    comm_failed_links=forced, seed_base=0)
    # Run multiple seeds: with prob=0.3 a buggy implementation would leak
    # random failures on most attempts.
    for trial in range(10):
        env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.3)
        env.seed(trial)
        env.reset(scenario=s)
        for (i, ns) in cfg.COMM_ADJACENCY.items():
            for j in ns:
                expected = 0 if (i, j) in forced else 1
                actual = env.comm.eta[(i, j)]
                if actual != expected:
                    print(f"  FAIL  trial={trial} link ({i},{j}): expected={expected} got={actual}")
                    return False
    print(f"  PASS  10 trials × {len(cfg.COMM_ADJACENCY)*2} links: only forced links are 0")
    return True


def main() -> int:
    print("=" * 65)
    print("  ODE Gate 2 · Scenario manifest reproducibility + reset() parity")
    print("=" * 65)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        results = {
            "2a_byte_reproducibility": gate_2a_byte_reproducibility(tmp_dir),
            "2b_legacy_parity": gate_2b_legacy_parity(),
            "2c_reset_equivalence": gate_2c_reset_equivalence(),
            "2d_forced_authoritative": gate_2d_forced_failures_authoritative(),
        }

    print("\n" + "=" * 65)
    print("  Summary")
    print("=" * 65)
    for k, v in results.items():
        print(f"  {'PASS' if v else 'FAIL':6s}  G{k}")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
