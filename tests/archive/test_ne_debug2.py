"""Phase 3: Test hypothesis - what WIND_FARM_M value allows TDS to converge?"""
import sys, os
import numpy as np

sys.path.insert(0, os.getcwd())

from env.andes.andes_ne_env import AndesNEEnv

# Test 1: What if we DON'T modify GENROU at all (keep original M/D)?
print("=" * 60)
print("TEST A: Skip GENROU modification (original M/D values)")
print("=" * 60)

class AndesNEEnv_NoWindMod(AndesNEEnv):
    """Same as AndesNEEnv but don't modify GENROU to wind farm params."""
    def _build_system(self):
        import andes
        ss = andes.load(self.case_path, default_config=True, setup=False)

        if self._gen_trip is not None:
            ss.add("Toggler", {
                "idx": "Trip_Gen", "model": "GENROU",
                "dev": self._gen_trip, "t": 0.5,
            })

        for i in range(self.N_AGENTS):
            new_bus = self.VSG_BUSES[i]
            parent_bus = self.PARENT_BUSES[i]
            ss.add("Bus", {
                "idx": new_bus, "name": f"BusVSG{i+1}",
                "Vn": self.VSG_BUS_VN, "v0": 1.0, "a0": 0.0,
            })
            ss.add("Line", {
                "idx": f"Line_VSG_{i+1}",
                "bus1": parent_bus, "bus2": new_bus,
                "Vn1": self.VSG_BUS_VN, "Vn2": self.VSG_BUS_VN,
                "r": self.NEW_LINE_R, "x": self.x_line, "b": self.NEW_LINE_B,
            })

        self.vsg_idx = []
        for i in range(self.N_AGENTS):
            new_bus = self.VSG_BUSES[i]
            vsg_id = f"VSG_{i+1}"
            gen_id = f"SG_VSG_{i+1}"
            ss.add("PV", {
                "idx": gen_id, "name": f"VSG{i+1}", "bus": new_bus,
                "Vn": self.VSG_BUS_VN, "Sn": self.VSG_SN,
                "p0": 0.5, "q0": 0.0,
                "pmax": 5.0, "pmin": 0.0, "qmax": 5.0, "qmin": -5.0, "v0": 1.0,
            })
            ss.add("GENCLS", {
                "idx": vsg_id, "bus": new_bus, "gen": gen_id,
                "Vn": self.VSG_BUS_VN, "Sn": self.VSG_SN,
                "M": self.M0[i], "D": self.D0[i],
                "ra": 0.001, "xd1": 0.15,
            })
            self.vsg_idx.append(vsg_id)

        ss.setup()
        # NO wind farm modifications!
        ss.TDS.config.criteria = 0
        return ss

env_a = AndesNEEnv_NoWindMod(random_disturbance=True)
env_a.seed(42)
try:
    obs = env_a.reset()
    print(f"[OK] Reset succeeded, t={env_a.ss.dae.t:.2f}, busted={env_a.ss.TDS.busted}")

    # Check original GENROU M values
    ss = env_a.ss
    print("\nOriginal GENROU M values:")
    for i in range(ss.GENROU.n):
        idx = ss.GENROU.idx.v[i]
        M = ss.GENROU.M.v[i]
        print(f"  {idx}: M={M:.3f}")

    # Run 5 steps
    actions = {i: np.array([0.0, 0.0]) for i in range(8)}
    for step in range(5):
        obs, rewards, done, info = env_a.step(actions)
        r_avg = np.mean(list(rewards.values()))
        print(f"  Step {step}: t={info['time']:.2f}, r_avg={r_avg:.2f}, "
              f"tds_failed={info['tds_failed']}")
        if done:
            break
except Exception as e:
    print(f"[FAIL]: {e}")
    import traceback; traceback.print_exc()

# Test 2: Try different WIND_FARM_M values
print("\n" + "=" * 60)
print("TEST B: Sweep WIND_FARM_M values")
print("=" * 60)

for test_M in [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0]:
    class TempEnv(AndesNEEnv):
        WIND_FARM_M = test_M

    env_b = TempEnv(random_disturbance=True)
    env_b.seed(42)
    try:
        obs = env_b.reset()
        busted = env_b.ss.TDS.busted

        if busted:
            print(f"  M={test_M:5.1f}: BUSTED at reset (t={env_b.ss.dae.t:.2f})")
        else:
            # Try a few steps
            actions = {i: np.array([0.0, 0.0]) for i in range(8)}
            ok_steps = 0
            for step in range(5):
                obs, rewards, done, info = env_b.step(actions)
                if info["tds_failed"]:
                    print(f"  M={test_M:5.1f}: TDS failed at step {step}")
                    break
                ok_steps += 1
                if done:
                    break
            if ok_steps == 5:
                r_avg = np.mean(list(rewards.values()))
                print(f"  M={test_M:5.1f}: OK, 5 steps passed, r_avg={r_avg:.2f}")
    except Exception as e:
        print(f"  M={test_M:5.1f}: EXCEPTION: {e}")

# Test 3: What about also adding D > 0 for wind farms?
print("\n" + "=" * 60)
print("TEST C: M=2.0 + varying D for wind farms")
print("=" * 60)

for test_D in [0.0, 1.0, 2.0, 5.0]:
    class TempEnv2(AndesNEEnv):
        WIND_FARM_M = 2.0
        WIND_FARM_D = test_D

    env_c = TempEnv2(random_disturbance=True)
    env_c.seed(42)
    try:
        obs = env_c.reset()
        busted = env_c.ss.TDS.busted

        if busted:
            print(f"  M=2.0, D={test_D:.1f}: BUSTED")
        else:
            actions = {i: np.array([0.0, 0.0]) for i in range(8)}
            ok_steps = 0
            for step in range(10):
                obs, rewards, done, info = env_c.step(actions)
                if info["tds_failed"]:
                    print(f"  M=2.0, D={test_D:.1f}: TDS failed step {step}")
                    break
                ok_steps += 1
                if done:
                    break
            if ok_steps >= 10:
                freq = info["freq_hz"]
                print(f"  M=2.0, D={test_D:.1f}: OK, 10 steps, "
                      f"freq_range=[{freq.min():.4f}, {freq.max():.4f}] Hz")
    except Exception as e:
        print(f"  M=2.0, D={test_D:.1f}: EXCEPTION: {e}")

print("\nDone.")
