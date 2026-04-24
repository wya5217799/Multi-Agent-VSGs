# ODE Parameter Recalibration (Option B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recalibrate the ODE model's H/D/B parameters so modal dynamics match the Yang 2023 paper: ω_n ≈ 0.62 Hz, ζ ≈ 0.048, Δf_peak ≈ 0.39 Hz — eliminating the training reward explosion caused by the current H=80 ≫ D=1 mismatch.

**Architecture:** Three files touch: `config.py` (values), `env/ode/multi_vsg_env.py` (H floor + obs normalization), `scenarios/kundur/evaluate_ode.py` (denormalization mirror). A new test file validates the modal gates before training is relaunched.

**Tech Stack:** Python 3, numpy, scipy.integrate.solve_ivp, pytest

---

## Physics Derivation (Reference)

For the 4-node chain Laplacian with B_tie=4:
- λ_min = 2 × B_tie × (1 - cos(π/4)) = 2 × 4 × 0.2929 = 2.343
- ω_n = sqrt(ω_s × λ_min / (2H)) = sqrt(314.16 × 2.343 / 48) = **3.916 rad/s = 0.623 Hz** ✓
- ζ  = D / (4H × ω_n) = 18 / (4 × 24 × 3.916) = **0.0479** ✓
- Δf_peak ≈ 0.385 Hz for balanced disturbance [2.4, 0, −2.4, 0] ✓

Warmup safe floor: H_min = H_ES0 / 3 = 8.0 prevents ω blowup if agent chooses a = −1.

---

## File Map

| File | Change |
|---|---|
| `config.py` | H_ES0, D_ES0, B_MATRIX, DH/DD ranges, comments |
| `env/ode/multi_vsg_env.py` | H floor 0.1→8.0; P_es/5, omega_dot/25 normalization |
| `scenarios/kundur/evaluate_ode.py` | Denormalization mirror: `* 10.0` → `* 25.0` |
| `tests/test_ode_physics_gates.py` | New — validate ω_n, ζ, Δf_peak with hard bounds |

---

### Task 1: Update config.py

**Files:**
- Modify: `config.py:31-85`

- [ ] **Step 1: Write the test first (physics gate)**

Create `tests/test_ode_physics_gates.py`:

```python
"""Physics validation gates — verify ODE modal parameters match paper targets."""
import numpy as np
import pytest
import sys, os
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
    import config as cfg

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
    """With a=-1 action (max negative ΔH), H_es must stay ≥ 8.0."""
    import config as cfg
    H_floor = 8.0
    min_H = float(cfg.H_ES0[0]) + cfg.DH_MIN
    # Floor clamp in multi_vsg_env.py guarantees H >= 8.0
    assert min_H < H_floor, "DH_MIN allows H below floor — floor clamp needed"
    clamped = max(min_H, H_floor)
    assert clamped >= H_floor
```

- [ ] **Step 2: Run test to verify it fails with current params**

```
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
python -m pytest tests/test_ode_physics_gates.py -v 2>&1 | head -40
```

Expected: FAIL — `test_omega_n_in_target_range` and `test_damping_ratio_in_target_range` report current values (ω_n≈0.88 Hz, ζ≈0.00046).

- [ ] **Step 3: Update config.py**

Replace lines 28–85 in `config.py` with:

```python
# ═══════════════════════════════════════════════════════
#  VSG 基础参数
#  H=24, D=18 → ω_n=0.623 Hz, ζ=0.048, Δf_peak≈0.385 Hz
#  与论文 Fig 4 频率偏差量级吻合 (target ~0.4 Hz)
# ═══════════════════════════════════════════════════════
H_ES0 = np.array([24.0, 24.0, 24.0, 24.0])
D_ES0 = np.array([18.0, 18.0, 18.0, 18.0])

# ═══════════════════════════════════════════════════════
#  动作空间 — 惯量/阻尼修正量范围 (Section IV-B)
#  DH: H_min = H_ES0 + DH_MIN = 24 - 16 = 8 (warmup 安全地板)
#  DH_MAX = 3 × H_ES0 = 72 (允许 H 最大 96)
#  DD: D_min = 18 - 14 = 4; D_max = 18 + 54 = 72
# ═══════════════════════════════════════════════════════
DH_MIN, DH_MAX = -16.0, 72.0     # ΔH 范围 → H ∈ [8, 96] s
DD_MIN, DD_MAX = -14.0, 54.0     # ΔD 范围 → D ∈ [4, 72]
```

Also replace the B_MATRIX block (lines 76–85):

```python
# ═══════════════════════════════════════════════════════
#  电气网络 — 4 母线两区域系统 (Kundur 修改版)
#  均匀链形拓扑 B_tie=4 → ω_n=0.623 Hz, ζ=0.048
#  λ_min = 2×4×(1-cos(π/4)) = 2.343
# ═══════════════════════════════════════════════════════
B_MATRIX = np.array([
    [0, 4,  0,  0],
    [4, 0,  4,  0],
    [0, 4,  0,  4],
    [0, 0,  4,  0],
], dtype=np.float64)
```

Also update the docstring comment at line 10 from:
```
  - B_tie=24 → ω_n≈0.88 Hz (通过区间振荡闸门 [0.8,1.5] Hz)
```
to:
```
  - H_ES0=24, D_ES0=18, B_tie=4 → ω_n=0.623 Hz, ζ=0.048, Δf_peak≈0.39 Hz
```

And line 8 from:
```
  - H_ES0: 5→80, D_ES0: 10→1 (Kundur 物理值: 900MVA/100MVA, ζ≈0.15)
```
to:
```
  - H_ES0=24, D_ES0=18: modal calibration for ω_n≈0.6 Hz, ζ≈0.05
```

- [ ] **Step 4: Run physics gate tests to verify they pass**

```
python -m pytest tests/test_ode_physics_gates.py -v
```

Expected output:
```
tests/test_ode_physics_gates.py::test_omega_n_in_target_range PASSED
tests/test_ode_physics_gates.py::test_damping_ratio_in_target_range PASSED
tests/test_ode_physics_gates.py::test_df_peak_in_target_range PASSED
tests/test_ode_physics_gates.py::test_warmup_h_floor_prevents_blowup PASSED
4 passed
```

- [ ] **Step 5: Commit**

```bash
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
git add config.py tests/test_ode_physics_gates.py
git commit -m "feat(ode): recalibrate H=24, D=18, B_tie=4 — ω_n=0.623Hz, ζ=0.048"
```

---

### Task 2: Update env/ode/multi_vsg_env.py — H floor and obs normalization

**Files:**
- Modify: `env/ode/multi_vsg_env.py:148,201,203,213-214,218-219`

- [ ] **Step 1: Update H floor (line 148)**

Change:
```python
        H_es = np.maximum(H_es, 0.1)
```
to:
```python
        H_es = np.maximum(H_es, 8.0)
```

- [ ] **Step 2: Update obs normalization (lines 201, 203)**

Change lines 201–203:
```python
            o[0] = state['P_es'][i] / 15.0       # P_es 范围 ~[-15, 15]
            o[1] = state['omega'][i] / 3.0        # omega 范围 ~[-3, 3]
            o[2] = state['omega_dot'][i] / 10.0   # omega_dot 范围 ~[-10, 10]
```
to:
```python
            o[0] = state['P_es'][i] / 5.0         # P_es 范围 ~[-5, 5] with B_tie=4
            o[1] = state['omega'][i] / 3.0        # omega 范围 ~[-3, 3]
            o[2] = state['omega_dot'][i] / 25.0   # omega_dot 范围 ~[-25, 25] with H=24
```

- [ ] **Step 3: Update delayed-observation normalization (lines 213–214, 218–219)**

The delayed path at lines 213–214:
```python
                        o[3 + k] = self._delayed_omega[(i, j)][0] / 3.0
                        o[3 + cfg.MAX_NEIGHBORS + k] = self._delayed_omega_dot[(i, j)][0] / 10.0
```
change `/10.0` to `/25.0`:
```python
                        o[3 + k] = self._delayed_omega[(i, j)][0] / 3.0
                        o[3 + cfg.MAX_NEIGHBORS + k] = self._delayed_omega_dot[(i, j)][0] / 25.0
```

The non-delayed path at lines 218–219:
```python
                        o[3 + k] = state['omega'][j] / 3.0
                        o[3 + cfg.MAX_NEIGHBORS + k] = state['omega_dot'][j] / 10.0
```
change `/10.0` to `/25.0`:
```python
                        o[3 + k] = state['omega'][j] / 3.0
                        o[3 + cfg.MAX_NEIGHBORS + k] = state['omega_dot'][j] / 25.0
```

- [ ] **Step 4: Run quick sanity check — step produces finite obs**

```python
# Run inline:
import sys; sys.path.insert(0, ".")
import numpy as np
from env.ode.multi_vsg_env import MultiVSGEnv
import config as cfg

env = MultiVSGEnv(random_disturbance=False)
obs = env.reset(delta_u=cfg.LOAD_STEP_1)
actions = {i: np.zeros(2) for i in range(4)}
obs2, rewards, done, info = env.step(actions)
for i in range(4):
    assert np.all(np.isfinite(obs2[i])), f"agent {i} obs has non-finite value"
    assert np.max(np.abs(obs2[i])) < 5.0, f"agent {i} obs out of [-5,5]: {obs2[i]}"
print("OK — all obs finite, max abs =", max(np.max(np.abs(obs2[i])) for i in range(4)))
```

Run as:
```
python -c "
import sys; sys.path.insert(0, '.')
import numpy as np
from env.ode.multi_vsg_env import MultiVSGEnv
import config as cfg
env = MultiVSGEnv(random_disturbance=False)
obs = env.reset(delta_u=cfg.LOAD_STEP_1)
actions = {i: np.zeros(2) for i in range(4)}
obs2, rewards, done, info = env.step(actions)
for i in range(4):
    assert np.all(np.isfinite(obs2[i]))
    assert np.max(np.abs(obs2[i])) < 5.0, obs2[i]
print('OK max_abs', max(float(np.max(np.abs(obs2[i]))) for i in range(4)))
"
```

Expected: `OK max_abs <value around 0.1–0.8>`

- [ ] **Step 5: Commit**

```bash
git add env/ode/multi_vsg_env.py
git commit -m "fix(ode): H floor 8.0, obs norm P_es/5 omega_dot/25 for recalibrated params"
```

---

### Task 3: Fix denormalization mirror in evaluate_ode.py

**Files:**
- Modify: `scenarios/kundur/evaluate_ode.py:60`

The `_adaptive_inertia_action` function denormalizes omega_dot from the observation:

```python
        omega_dot = o[2] * 10.0   # match /10.0 normalization in multi_vsg_env.py
```

This must mirror the new normalization constant.

- [ ] **Step 1: Update the denormalization**

Change line 60:
```python
        omega_dot = o[2] * 10.0   # match /10.0 normalization in multi_vsg_env.py
```
to:
```python
        omega_dot = o[2] * 25.0   # match /25.0 normalization in multi_vsg_env.py
```

- [ ] **Step 2: Verify no other denormalization sites use the old constant**

```
grep -n "/ 10\.0\|/10\.0\|\* 10\.0\|\*10\.0" scenarios/kundur/evaluate_ode.py
```

Expected: zero matches (the only occurrence was line 60, now updated).

Also check multi_vsg_env.py to confirm all four `/10.0` occurrences are gone:
```
grep -n "10\.0" env/ode/multi_vsg_env.py
```

Expected: no remaining `/10.0` in normalization context.

- [ ] **Step 3: Commit**

```bash
git add scenarios/kundur/evaluate_ode.py
git commit -m "fix(ode): update adaptive inertia denorm to *25.0 for new obs normalization"
```

---

### Task 4: Run reward baseline sanity check

Before launching 2000-episode training, verify the no-control reward for LS1 is now closer to the paper target (−1.61 per episode) rather than the old −0.59.

**Files:**
- Read only: `scenarios/kundur/evaluate_ode.py`

- [ ] **Step 1: Run single-episode no-control baseline**

```
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
python -u -c "
import sys; sys.path.insert(0, '.')
import numpy as np
from env.ode.multi_vsg_env import MultiVSGEnv
import config as cfg

env = MultiVSGEnv(random_disturbance=False, comm_fail_prob=0.0)
obs = env.reset(delta_u=cfg.LOAD_STEP_1)
total_r = 0.0
freq_log = []
for _ in range(cfg.STEPS_PER_EPISODE):
    actions = {i: np.zeros(2) for i in range(cfg.N_AGENTS)}
    obs, rewards, done, info = env.step(actions)
    freq_log.append(info['freq_hz'].copy())
    total_r += sum(rewards.values())

freq_arr = np.array(freq_log)
f_bar = freq_arr.mean(axis=1, keepdims=True)
freq_sync_r = -float(np.sum((freq_arr - f_bar)**2))
peak_df = float(np.max(np.abs(freq_arr - 50.0)))

print(f'Total reward:      {total_r:.4f}')
print(f'Freq sync reward:  {freq_sync_r:.4f}  (paper no-ctrl LS1 target: -1.61)')
print(f'Peak Δf:           {peak_df:.4f} Hz   (target 0.30-0.55 Hz)')
"
```

Expected:
- Freq sync reward in range [−2.5, −0.8] (vs old −0.59, paper −1.61)
- Peak Δf in range [0.30, 0.55] Hz (vs old 0.114 Hz)

If freq sync reward is worse than −0.59 AND peak Δf < 0.30 Hz: **stop**, the B_MATRIX change did not take effect — check import caching (`python -c "import importlib; print(importlib.__file__)"` and restart Python).

- [ ] **Step 2: Launch 2000-episode training**

```
cd "C:\Users\27443\Desktop\Multi-Agent  VSGs"
python -u scenarios/kundur/train_ode.py 2>&1 | tee results/train_ode_recalib.log
```

Monitor for first 5 episodes — abort if any episode shows:
- `|Freq peak| > 2.0 Hz` (dynamics unstable)
- `r_h%` > 50% of total reward (parameter penalty dominating)

Expected healthy Episode 1:
```
Ep   1 | Total R = -XXX.X | Freq peak = 0.3-0.5 Hz | r_h% < 30%
```

- [ ] **Step 3: Commit training log if run is healthy**

```bash
git add results/train_ode_recalib.log
git commit -m "chore(ode): attach training log — recalibrated params H=24 D=18 B_tie=4"
```

---

## Validation Checklist

Before declaring Task 4 done, verify all three gates:

| Gate | Target | Measurement |
|---|---|---|
| ω_n | [0.55, 0.70] Hz | `test_omega_n_in_target_range` passes |
| ζ | [0.03, 0.08] | `test_damping_ratio_in_target_range` passes |
| Δf_peak | [0.30, 0.55] Hz | `test_df_peak_in_target_range` passes |
| No-ctrl LS1 freq sync | < −0.8 (closer to −1.61) | Baseline sanity check |
| Episode 1 r_h% | < 50% | Training monitor ep 1-5 |

---

## Self-Review Notes

1. **Spec coverage**: All three recalibration goals (H, D, B) covered in Task 1. Obs normalization (H floor + P_es/omega_dot scaling) covered in Task 2. Denorm mirror covered in Task 3. Training launch covered in Task 4.

2. **Type consistency**: `H_ES0` is `np.array` throughout; floor uses `np.maximum`; no scalar/array confusion.

3. **No-placeholders check**: Every step has exact file:line and exact code. Training expected output is bounded, not vague.

4. **Risk**: The `_adaptive_inertia_action` denorm in Task 3 only affects evaluation, not training. Forgetting it would make the adaptive baseline look weaker than it is — harmless to training correctness but distorts paper figure comparisons.
