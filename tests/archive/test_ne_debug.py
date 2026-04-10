"""NE env TDS crash diagnostic - Phase 1: Root cause investigation"""
import sys, os, traceback
import numpy as np

sys.path.insert(0, os.getcwd())

from env.andes.andes_ne_env import AndesNEEnv

print("=" * 60)
print("TEST 1: Reset without disturbance")
print("=" * 60)

env = AndesNEEnv(random_disturbance=False)
env.seed(42)

try:
    obs = env.reset()
    ss = env.ss
    print(f"[OK] Reset succeeded, t={ss.dae.t:.2f}")
    print(f"  PFlow converged: {ss.PFlow.converged}")
    print(f"  TDS.busted: {ss.TDS.busted}")

    print("\nGENROU states:")
    for i in range(ss.GENROU.n):
        idx = ss.GENROU.idx.v[i]
        M = ss.GENROU.M.v[i]
        D = ss.GENROU.D.v[i]
        omega = ss.GENROU.omega.v[i]
        print(f"  {idx}: M={M:.3f}, D={D:.3f}, omega={omega:.6f}")

    print("\nGENCLS (VSG) states:")
    for i in range(ss.GENCLS.n):
        idx = ss.GENCLS.idx.v[i]
        M = ss.GENCLS.M.v[i]
        D = ss.GENCLS.D.v[i]
        omega = ss.GENCLS.omega.v[i]
        print(f"  {idx}: M={M:.3f}, D={D:.3f}, omega={omega:.6f}")

except Exception as e:
    print(f"[FAIL] Reset failed: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("TEST 2: 5 steps with zero action, no disturbance")
print("=" * 60)

actions = {i: np.array([0.0, 0.0]) for i in range(8)}
for step in range(5):
    try:
        obs, rewards, done, info = env.step(actions)
        r_avg = np.mean(list(rewards.values()))
        tds_f = info["tds_failed"]
        t_val = info["time"]
        print(f"  Step {step}: t={t_val:.2f}, r_avg={r_avg:.2f}, "
              f"tds_failed={tds_f}, busted={env.ss.TDS.busted}")
        if done:
            print("  -> Episode terminated!")
            break
    except Exception as e:
        print(f"  Step {step} EXCEPTION: {e}")
        traceback.print_exc()
        break

print("\n" + "=" * 60)
print("TEST 3: Reset with random disturbance + step")
print("=" * 60)

env2 = AndesNEEnv(random_disturbance=True)
env2.seed(42)
try:
    obs = env2.reset()
    print(f"[OK] Reset with disturbance, t={env2.ss.dae.t:.2f}, "
          f"busted={env2.ss.TDS.busted}")

    actions = {i: np.array([0.0, 0.0]) for i in range(8)}
    for step in range(5):
        obs, rewards, done, info = env2.step(actions)
        r_avg = np.mean(list(rewards.values()))
        tds_f = info["tds_failed"]
        t_val = info["time"]
        print(f"  Step {step}: t={t_val:.2f}, r_avg={r_avg:.2f}, "
              f"tds_failed={tds_f}, busted={env2.ss.TDS.busted}")
        if done:
            M_val = info["M_es"]
            D_val = info["D_es"]
            print(f"  -> Terminated! M={M_val}, D={D_val}")
            break
except Exception as e:
    print(f"[FAIL]: {e}")
    traceback.print_exc()

print("\n" + "=" * 60)
print("TEST 4: Multiple episodes with random actions (like training)")
print("=" * 60)

for ep in range(5):
    env_ep = AndesNEEnv(random_disturbance=True, comm_fail_prob=0.1)
    env_ep.seed(42 + ep)
    try:
        obs = env_ep.reset()
        steps_done = 0
        last_info = None
        for step in range(50):
            act = {i: np.random.uniform(-1, 1, size=2) for i in range(8)}
            obs, rewards, done, last_info = env_ep.step(act)
            steps_done += 1
            if last_info["tds_failed"]:
                M_val = last_info["M_es"]
                D_val = last_info["D_es"]
                print(f"  Ep {ep}: TDS FAILED at step {step}, t={last_info['time']:.2f}")
                print(f"    M={np.round(M_val, 1)}")
                print(f"    D={np.round(D_val, 1)}")
                break
            if done:
                break
        if not last_info["tds_failed"]:
            total_r = sum(rewards.values())
            print(f"  Ep {ep}: OK, {steps_done} steps, total_reward={total_r:.2f}")
    except Exception as e:
        print(f"  Ep {ep}: EXCEPTION: {e}")
        traceback.print_exc()

print("\nDone.")
