"""Phase 1 deep dive: Can ANDES even run IEEE 39-bus TDS?"""
import sys, os
import numpy as np
import andes
import warnings
warnings.filterwarnings("ignore")

# Test 1: Pure IEEE 39-bus, default config
print("=" * 60)
print("TEST 1: IEEE 39-bus, default_config=True, criteria=0")
print("=" * 60)

case_path = andes.get_case("ieee39/ieee39_full.xlsx")
ss = andes.load(case_path, default_config=True)
ss.PFlow.run()
print(f"  PFlow converged: {ss.PFlow.converged}")
print(f"  TDS.busted before run: {ss.TDS.busted}")
ss.TDS.config.criteria = 0
ss.TDS.config.tf = 0.5
ss.TDS.run()
print(f"  TDS.busted after run: {ss.TDS.busted}")
print(f"  dae.t = {ss.dae.t:.6f}")
# Check if t actually reached 0.5
print(f"  t reached tf? {abs(ss.dae.t - 0.5) < 1e-4}")

# Test 2: Without default_config
print("\n" + "=" * 60)
print("TEST 2: IEEE 39-bus, no default_config")
print("=" * 60)

ss2 = andes.load(case_path)
ss2.PFlow.run()
print(f"  PFlow converged: {ss2.PFlow.converged}")
ss2.TDS.config.criteria = 0
ss2.TDS.config.tf = 0.5
ss2.TDS.run()
print(f"  TDS.busted: {ss2.TDS.busted}")
print(f"  dae.t = {ss2.dae.t:.6f}")

# Test 3: Check what criteria=0 does - try criteria=1 too
print("\n" + "=" * 60)
print("TEST 3: IEEE 39-bus, criteria=1 (default)")
print("=" * 60)

ss3 = andes.load(case_path, default_config=True)
ss3.PFlow.run()
# DON'T set criteria=0
ss3.TDS.config.tf = 0.5
ss3.TDS.run()
print(f"  TDS.busted: {ss3.TDS.busted}")
print(f"  dae.t = {ss3.dae.t:.6f}")

# Test 4: Run to 1.0s instead of 0.5s
print("\n" + "=" * 60)
print("TEST 4: IEEE 39-bus, tf=1.0")
print("=" * 60)

ss4 = andes.load(case_path, default_config=True)
ss4.PFlow.run()
ss4.TDS.config.criteria = 0
ss4.TDS.config.tf = 1.0
ss4.TDS.run()
print(f"  TDS.busted: {ss4.TDS.busted}")
print(f"  dae.t = {ss4.dae.t:.6f}")

# Test 5: Check TDS exit code
print("\n" + "=" * 60)
print("TEST 5: TDS exit_code and internals")
print("=" * 60)

ss5 = andes.load(case_path, default_config=True)
ss5.PFlow.run()
ss5.TDS.config.criteria = 0
ss5.TDS.config.tf = 0.5
ss5.TDS.run()
print(f"  TDS.busted: {ss5.TDS.busted}")
print(f"  TDS.converged: {ss5.TDS.converged}")
if hasattr(ss5.TDS, 'exit_code'):
    print(f"  TDS.exit_code: {ss5.TDS.exit_code}")
print(f"  dae.t = {ss5.dae.t:.6f}")

# Check all GENROU omega values
print(f"  GENROU omega range: [{ss5.GENROU.omega.v.min():.6f}, {ss5.GENROU.omega.v.max():.6f}]")

# Test 6: What if we clear busted and run segmented?
print("\n" + "=" * 60)
print("TEST 6: Clear busted flag and run segmented TDS")
print("=" * 60)

ss6 = andes.load(case_path, default_config=True)
ss6.PFlow.run()
ss6.TDS.config.criteria = 0
ss6.TDS.config.tf = 0.5
ss6.TDS.run()
print(f"  After initial run: busted={ss6.TDS.busted}, t={ss6.dae.t:.6f}")

# Clear busted
ss6.TDS.busted = False
print(f"  After clearing busted: busted={ss6.TDS.busted}")

# Try to continue
ss6.TDS.config.tf = 0.7
ss6.TDS.run()
print(f"  After segmented run: busted={ss6.TDS.busted}, t={ss6.dae.t:.6f}")
print(f"  GENROU omega: {ss6.GENROU.omega.v}")

print("\nDone.")
