"""Debug layer 2: Why does TDS fail at step 9 (t~2.33)?"""
import sys, os
import numpy as np
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.getcwd())

from env.andes.andes_ne_env import AndesNEEnv

# Test 1: No disturbance at all
print("=" * 60)
print("TEST 1: No disturbance, zero actions - detailed per-step")
print("=" * 60)

env = AndesNEEnv(random_disturbance=False)
env.seed(42)
obs = env.reset()
print(f"Reset: t={env.ss.dae.t:.2f}, busted={env.ss.TDS.busted}")

# Check GENROU omega during steps
actions = {i: np.array([-0.5, -0.5]) for i in range(8)}  # maps to baseline M,D

for step in range(15):
    obs, rewards, done, info = env.step(actions)
    tds_f = info["tds_failed"]
    freq = info["freq_hz"]
    omega = info["omega"]
    M = info["M_es"]
    D = info["D_es"]

    # Also check GENROU omega (wind farms)
    genrou_omega = []
    for i in range(env.ss.GENROU.n):
        genrou_omega.append(env.ss.GENROU.omega.v[i])
    genrou_omega = np.array(genrou_omega)

    print(f"  Step {step:2d}: t={info['time']:.2f}, busted={env.ss.TDS.busted}, "
          f"tds_failed={tds_f}")
    print(f"    VSG freq: [{freq.min():.4f}, {freq.max():.4f}] Hz")
    print(f"    VSG M: [{M.min():.1f}, {M.max():.1f}], D: [{D.min():.1f}, {D.max():.1f}]")
    print(f"    GENROU omega: [{genrou_omega.min():.6f}, {genrou_omega.max():.6f}]")

    if tds_f or done:
        print(f"  -> {'TDS FAILED' if tds_f else 'Episode done'}")
        break

# Test 2: Same but without wind farm modification
print("\n" + "=" * 60)
print("TEST 2: No wind farm mod, no disturbance")
print("=" * 60)

class AndesNEEnv_NoWind(AndesNEEnv):
    def _build_system(self):
        import andes
        ss = andes.load(self.case_path, default_config=True, setup=False)

        for i in range(self.N_AGENTS):
            new_bus = self.VSG_BUSES[i]
            parent_bus = self.PARENT_BUSES[i]
            ss.add("Bus", {"idx": new_bus, "name": f"BusVSG{i+1}",
                           "Vn": self.VSG_BUS_VN, "v0": 1.0, "a0": 0.0})
            ss.add("Line", {"idx": f"Line_VSG_{i+1}", "bus1": parent_bus,
                            "bus2": new_bus, "Vn1": self.VSG_BUS_VN,
                            "Vn2": self.VSG_BUS_VN,
                            "r": self.NEW_LINE_R, "x": self.x_line, "b": self.NEW_LINE_B})

        self.vsg_idx = []
        for i in range(self.N_AGENTS):
            new_bus = self.VSG_BUSES[i]
            vsg_id = f"VSG_{i+1}"
            gen_id = f"SG_VSG_{i+1}"
            ss.add("PV", {"idx": gen_id, "name": f"VSG{i+1}", "bus": new_bus,
                          "Vn": self.VSG_BUS_VN, "Sn": self.VSG_SN,
                          "p0": 0.5, "q0": 0.0,
                          "pmax": 5.0, "pmin": 0.0, "qmax": 5.0, "qmin": -5.0, "v0": 1.0})
            ss.add("GENCLS", {"idx": vsg_id, "bus": new_bus, "gen": gen_id,
                              "Vn": self.VSG_BUS_VN, "Sn": self.VSG_SN,
                              "M": self.M0[i], "D": self.D0[i],
                              "ra": 0.001, "xd1": 0.15})
            self.vsg_idx.append(vsg_id)

        ss.setup()
        # NO WIND FARM MODIFICATION
        ss.TDS.config.criteria = 0
        return ss

env2 = AndesNEEnv_NoWind(random_disturbance=False)
env2.seed(42)
obs2 = env2.reset()
print(f"Reset: t={env2.ss.dae.t:.2f}, busted={env2.ss.TDS.busted}")

actions = {i: np.array([-0.5, -0.5]) for i in range(8)}
for step in range(15):
    obs2, rewards, done, info = env2.step(actions)
    if info["tds_failed"]:
        print(f"  Step {step}: TDS FAILED at t={info['time']:.2f}")
        break
    if step % 5 == 0:
        freq = info["freq_hz"]
        print(f"  Step {step}: t={info['time']:.2f}, freq=[{freq.min():.4f}, {freq.max():.4f}]")
    if done:
        print(f"  Episode done at step {step}")
        break

if not info["tds_failed"]:
    print(f"  All 15 steps OK! Final freq: {info['freq_hz']}")

# Test 3: With wind mod but higher M
print("\n" + "=" * 60)
print("TEST 3: Wind farm M=5.0 (not 0.1), no disturbance")
print("=" * 60)

class AndesNEEnv_HigherM(AndesNEEnv):
    WIND_FARM_M = 5.0
    WIND_FARM_D = 1.0

env3 = AndesNEEnv_HigherM(random_disturbance=False)
env3.seed(42)
obs3 = env3.reset()
print(f"Reset: t={env3.ss.dae.t:.2f}, busted={env3.ss.TDS.busted}")

actions = {i: np.array([-0.5, -0.5]) for i in range(8)}
for step in range(15):
    obs3, rewards, done, info = env3.step(actions)
    if info["tds_failed"]:
        print(f"  Step {step}: TDS FAILED at t={info['time']:.2f}")
        genrou_omega = [env3.ss.GENROU.omega.v[i] for i in range(env3.ss.GENROU.n)]
        print(f"    GENROU omega: {np.round(genrou_omega, 4)}")
        break
    if step % 5 == 0:
        freq = info["freq_hz"]
        print(f"  Step {step}: t={info['time']:.2f}, freq=[{freq.min():.4f}, {freq.max():.4f}]")
    if done:
        print(f"  Episode done at step {step}")
        break

if not info["tds_failed"]:
    print(f"  All 15 steps OK!")

print("\nDone.")
