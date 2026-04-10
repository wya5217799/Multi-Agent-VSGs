"""Phase 1 continued: Isolate what component breaks TDS"""
import sys, os
import numpy as np
import andes
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.getcwd())

# Test 1: Base IEEE 39-bus without any modifications
print("=" * 60)
print("TEST 1: Pure IEEE 39-bus (no modifications)")
print("=" * 60)

case_path = andes.get_case("ieee39/ieee39_full.xlsx")
ss1 = andes.load(case_path, default_config=True)
ss1.PFlow.run()
print(f"  PFlow converged: {ss1.PFlow.converged}")
ss1.TDS.config.tf = 0.5
ss1.TDS.config.criteria = 0
ss1.TDS.run()
print(f"  TDS busted: {ss1.TDS.busted}, t={ss1.dae.t:.4f}")

# Test 2: Add just 1 VSG bus + GENCLS
print("\n" + "=" * 60)
print("TEST 2: IEEE 39-bus + 1 VSG (Bus 40 + GENCLS)")
print("=" * 60)

ss2 = andes.load(case_path, default_config=True, setup=False)
ss2.add("Bus", {"idx": 40, "name": "BusVSG1", "Vn": 22.0, "v0": 1.0, "a0": 0.0})
ss2.add("Line", {"idx": "Line_VSG_1", "bus1": 30, "bus2": 40,
                  "Vn1": 22.0, "Vn2": 22.0, "r": 0.001, "x": 0.10, "b": 0.0175})
ss2.add("PV", {"idx": "SG_VSG_1", "name": "VSG1", "bus": 40,
               "Vn": 22.0, "Sn": 200.0, "p0": 0.5, "q0": 0.0,
               "pmax": 5.0, "pmin": 0.0, "qmax": 5.0, "qmin": -5.0, "v0": 1.0})
ss2.add("GENCLS", {"idx": "VSG_1", "bus": 40, "gen": "SG_VSG_1",
                    "Vn": 22.0, "Sn": 200.0, "M": 20.0, "D": 4.0,
                    "ra": 0.001, "xd1": 0.15})
ss2.setup()
ss2.PFlow.run()
print(f"  PFlow converged: {ss2.PFlow.converged}")
ss2.TDS.config.tf = 0.5
ss2.TDS.config.criteria = 0
ss2.TDS.run()
print(f"  TDS busted: {ss2.TDS.busted}, t={ss2.dae.t:.4f}")

# Test 3: Add all 8 VSG buses + GENCLS
print("\n" + "=" * 60)
print("TEST 3: IEEE 39-bus + 8 VSGs (full NE setup, no wind mod)")
print("=" * 60)

ss3 = andes.load(case_path, default_config=True, setup=False)
VSG_BUSES = [40, 41, 42, 43, 44, 45, 46, 47]
PARENT_BUSES = [30, 31, 32, 33, 34, 35, 36, 37]

for i in range(8):
    ss3.add("Bus", {"idx": VSG_BUSES[i], "name": f"BusVSG{i+1}",
                     "Vn": 22.0, "v0": 1.0, "a0": 0.0})
    ss3.add("Line", {"idx": f"Line_VSG_{i+1}", "bus1": PARENT_BUSES[i],
                      "bus2": VSG_BUSES[i], "Vn1": 22.0, "Vn2": 22.0,
                      "r": 0.001, "x": 0.10, "b": 0.0175})
    ss3.add("PV", {"idx": f"SG_VSG_{i+1}", "name": f"VSG{i+1}",
                    "bus": VSG_BUSES[i], "Vn": 22.0, "Sn": 200.0,
                    "p0": 0.5, "q0": 0.0,
                    "pmax": 5.0, "pmin": 0.0, "qmax": 5.0, "qmin": -5.0, "v0": 1.0})
    ss3.add("GENCLS", {"idx": f"VSG_{i+1}", "bus": VSG_BUSES[i],
                        "gen": f"SG_VSG_{i+1}", "Vn": 22.0, "Sn": 200.0,
                        "M": 20.0, "D": 4.0, "ra": 0.001, "xd1": 0.15})

ss3.setup()
ss3.PFlow.run()
print(f"  PFlow converged: {ss3.PFlow.converged}")

# Check GENCLS vf values
print("  GENCLS initial vf values:")
for i in range(ss3.GENCLS.n):
    idx = ss3.GENCLS.idx.v[i]
    vf = ss3.GENCLS.vf.v[i] if hasattr(ss3.GENCLS, 'vf') else 'N/A'
    omega = ss3.GENCLS.omega.v[i]
    print(f"    {idx}: omega={omega:.6f}")

ss3.TDS.config.tf = 0.5
ss3.TDS.config.criteria = 0
ss3.TDS.run()
print(f"  TDS busted: {ss3.TDS.busted}, t={ss3.dae.t:.4f}")

# Test 4: Try with higher x_line and smaller p0
print("\n" + "=" * 60)
print("TEST 4: 8 VSGs with x_line=0.5, p0=0.1")
print("=" * 60)

ss4 = andes.load(case_path, default_config=True, setup=False)
for i in range(8):
    ss4.add("Bus", {"idx": VSG_BUSES[i], "name": f"BusVSG{i+1}",
                     "Vn": 22.0, "v0": 1.0, "a0": 0.0})
    ss4.add("Line", {"idx": f"Line_VSG_{i+1}", "bus1": PARENT_BUSES[i],
                      "bus2": VSG_BUSES[i], "Vn1": 22.0, "Vn2": 22.0,
                      "r": 0.001, "x": 0.50, "b": 0.0})
    ss4.add("PV", {"idx": f"SG_VSG_{i+1}", "name": f"VSG{i+1}",
                    "bus": VSG_BUSES[i], "Vn": 22.0, "Sn": 200.0,
                    "p0": 0.1, "q0": 0.0,
                    "pmax": 5.0, "pmin": 0.0, "qmax": 5.0, "qmin": -5.0, "v0": 1.0})
    ss4.add("GENCLS", {"idx": f"VSG_{i+1}", "bus": VSG_BUSES[i],
                        "gen": f"SG_VSG_{i+1}", "Vn": 22.0, "Sn": 200.0,
                        "M": 20.0, "D": 4.0, "ra": 0.001, "xd1": 0.30})

ss4.setup()
ss4.PFlow.run()
print(f"  PFlow converged: {ss4.PFlow.converged}")
ss4.TDS.config.tf = 0.5
ss4.TDS.config.criteria = 0
ss4.TDS.run()
print(f"  TDS busted: {ss4.TDS.busted}, t={ss4.dae.t:.4f}")

# Test 5: Kundur ANDES env (known working?)
print("\n" + "=" * 60)
print("TEST 5: Kundur ANDES env (reference)")
print("=" * 60)
try:
    from env.andes.andes_vsg_env import AndesMultiVSGEnv
    env_k = AndesMultiVSGEnv(random_disturbance=False)
    env_k.seed(42)
    obs = env_k.reset()
    print(f"  Reset OK, t={env_k.ss.dae.t:.2f}, busted={env_k.ss.TDS.busted}")

    actions = {i: np.array([0.0, 0.0]) for i in range(4)}
    obs, rewards, done, info = env_k.step(actions)
    print(f"  Step 0: t={info['time']:.2f}, r_avg={np.mean(list(rewards.values())):.2f}, "
          f"tds_failed={info['tds_failed']}")
except Exception as e:
    print(f"  EXCEPTION: {e}")
    import traceback; traceback.print_exc()

print("\nDone.")
