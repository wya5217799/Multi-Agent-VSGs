"""Profile 2 Simulink episodes to answer two questions:
  1. How much time goes to warmup vs step vs Python RL?
  2. Does the FR fast path (skip recompile) correctly reset Simscape ICs?
     Episode-2 omega after warmup must match episode-1 (both ≈ 1.0 p.u.).

Run:  python scripts/profile_one_episode.py

Output: wall-clock breakdown + IC check printed to stdout + saved to
        results/sim_kundur/logs/profile_1ep.json
"""

import os
import sys
import time
import json
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from env.simulink.kundur_simulink_env import KundurSimulinkEnv

IC_TOLERANCE = 0.02   # max |omega - 1.0| allowed after warmup (p.u.)


def run_episode(env, label):
    """Run one episode and return timing + post-warmup omega."""
    t0 = time.perf_counter()
    obs, info = env.reset()
    reset_ms = (time.perf_counter() - t0) * 1000

    # omega immediately after warmup (before any disturbance or step)
    omega_after_warmup = env._omega.copy()

    t0 = time.perf_counter()
    env.apply_disturbance(bus_idx=0, magnitude=2.0)
    dist_ms = (time.perf_counter() - t0) * 1000

    step_times = []
    python_rl_times = []
    n_steps = int(env.T_EPISODE / env.DT)

    for i in range(n_steps):
        action = np.random.uniform(-1, 1, size=(env.N_AGENTS, 2)).astype(np.float32)

        t_step = time.perf_counter()
        obs, reward, terminated, truncated, info = env.step(action)
        step_times.append((time.perf_counter() - t_step) * 1000)

        t_rl = time.perf_counter()
        for _ in range(10):
            _ = np.random.randn(256, 128) @ np.random.randn(128, 128)
        python_rl_times.append((time.perf_counter() - t_rl) * 1000)

        if terminated:
            print(f"  [{label}] Episode terminated at step {i}")
            break

    step_arr = np.array(step_times)
    rl_arr   = np.array(python_rl_times)

    return {
        "label":               label,
        "reset_warmup_ms":     round(reset_ms, 1),
        "disturbance_ms":      round(dist_ms, 1),
        "omega_after_warmup":  [round(float(w), 6) for w in omega_after_warmup],
        "steps": {
            "count":    len(step_times),
            "total_ms": round(float(step_arr.sum()), 1),
            "mean_ms":  round(float(step_arr.mean()), 1),
            "min_ms":   round(float(step_arr.min()), 1),
            "max_ms":   round(float(step_arr.max()), 1),
            "p50_ms":   round(float(np.median(step_arr)), 1),
            "p90_ms":   round(float(np.percentile(step_arr, 90)), 1),
        },
        "python_rl_total_ms": round(float(rl_arr.sum()), 1),
    }


def check_ic(ep1, ep2):
    """Verify episode-2 omega after warmup ≈ episode-1 omega after warmup.

    If the FR fast path does not reset Simscape ICs, episode 2 will start
    from episode 1's final state (omega ≠ 1.0) and training will be corrupted.
    """
    w1 = np.array(ep1["omega_after_warmup"])
    w2 = np.array(ep2["omega_after_warmup"])
    dev1 = float(np.max(np.abs(w1 - 1.0)))
    dev2 = float(np.max(np.abs(w2 - 1.0)))
    diff = float(np.max(np.abs(w1 - w2)))

    ic_ok = (dev1 < IC_TOLERANCE) and (dev2 < IC_TOLERANCE)

    return {
        "ep1_max_dev_from_nominal": round(dev1, 6),
        "ep2_max_dev_from_nominal": round(dev2, 6),
        "ep1_vs_ep2_max_diff":      round(diff, 6),
        "ic_reset_ok":              ic_ok,
        "tolerance":                IC_TOLERANCE,
    }


def main():
    env = KundurSimulinkEnv(training=True)

    # one-time model load
    t0 = time.perf_counter()
    env.bridge.load_model()
    load_ms = (time.perf_counter() - t0) * 1000

    # run two episodes
    print("\nRunning episode 1 (full recompile — FR off→on)...")
    ep1 = run_episode(env, "ep1")

    print("Running episode 2 (fast path — skip recompile)...")
    ep2 = run_episode(env, "ep2")

    env.close()

    # IC check
    ic = check_ic(ep1, ep2)

    # per-episode steady-state cost (excluding one-time load_model)
    ep1_total = ep1["reset_warmup_ms"] + ep1["disturbance_ms"] + ep1["steps"]["total_ms"] + ep1["python_rl_total_ms"]
    ep2_total = ep2["reset_warmup_ms"] + ep2["disturbance_ms"] + ep2["steps"]["total_ms"] + ep2["python_rl_total_ms"]

    # print report
    print("\n" + "=" * 64)
    print("  PROFILE: 2 Kundur Simulink Episodes")
    print("=" * 64)
    print(f"  load_model (one-time):  {load_ms:>8.0f} ms")
    print()
    for ep in (ep1, ep2):
        label = ep["label"]
        total = ep["reset_warmup_ms"] + ep["disturbance_ms"] + ep["steps"]["total_ms"] + ep["python_rl_total_ms"]
        print(f"  [{label}] reset/warmup:  {ep['reset_warmup_ms']:>8.0f} ms")
        print(f"  [{label}] sim steps:     {ep['steps']['total_ms']:>8.0f} ms  (mean {ep['steps']['mean_ms']:.0f} ms/step)")
        print(f"  [{label}] total:         {total:>8.0f} ms")
        print()

    warmup_saving = ep1["reset_warmup_ms"] - ep2["reset_warmup_ms"]
    print(f"  FR fast-path warmup saving: {warmup_saving:+.0f} ms/episode")
    print()

    # IC check result
    print("  IC Reset Check (Issue #4 — Simscape initial conditions):")
    print(f"    ep1 omega after warmup: {ep1['omega_after_warmup']}")
    print(f"    ep2 omega after warmup: {ep2['omega_after_warmup']}")
    print(f"    ep1 max |omega-1|: {ic['ep1_max_dev_from_nominal']:.6f} p.u.  (tolerance {IC_TOLERANCE})")
    print(f"    ep2 max |omega-1|: {ic['ep2_max_dev_from_nominal']:.6f} p.u.  (tolerance {IC_TOLERANCE})")
    if ic["ic_reset_ok"]:
        print("    IC reset: PASS — fast path correctly resets Simscape ICs")
    else:
        print("    IC reset: FAIL — fast path did NOT reset Simscape ICs!")
        print("    ACTION: set _fr_compiled=False (disable fast path) or investigate")
    print("=" * 64)

    # save
    report = {
        "load_model_ms": round(load_ms, 1),
        "ep1": ep1,
        "ep2": ep2,
        "ic_check": ic,
        "warmup_saving_ms": round(warmup_saving, 1),
    }
    out_dir = os.path.join(os.path.dirname(__file__), '..', 'results', 'sim_kundur', 'logs')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'profile_1ep.json')
    with open(out_path, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\nSaved to {out_path}")

    # non-zero exit if IC check failed
    if not ic["ic_reset_ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
