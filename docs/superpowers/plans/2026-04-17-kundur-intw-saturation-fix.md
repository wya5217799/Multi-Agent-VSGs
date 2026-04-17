# Kundur IntW Saturation Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the root cause of Kundur Simulink training failure: IntW integrator saturation at ±15 Hz that corrupts the replay buffer with physically distorted observations.

**Architecture:** Two Python-only changes — add omega saturation monitoring to the env info dict, and reduce DIST_MAX to a level where the Kundur two-area oscillation peak stays safely below the ±15 Hz IntW clip limit. No model rebuild required.

**Tech Stack:** Python, Gymnasium env, optimization_log.py

---

## Physics Derivation (justification for DIST_MAX=0.5)

- DIST_MAX = 0.5 pu (sys base, 100 MVA) = 50 MW
- On VSG base (200 MVA): 0.5 × 100/200 = 0.25 pu, split over 4 agents → 0.0625 pu/agent
- At D_LO = 1.5 (minimum damping): Δf_ss = (0.0625/1.5) × 50 Hz = 2.08 Hz
- Kundur two-area oscillation peak multiplier ~2.3×: peak ≈ 4.8 Hz → safe margin below 15 Hz
- Worst-case 3× multiplier: 6.25 Hz → still safe
- Comparison: current DIST_MAX=1.5 gives Δf_ss=6.25 Hz → peak≈14.4 Hz → saturates IntW

---

## Task 1: Add omega saturation monitoring

**Files:**
- Modify: `env/simulink/kundur_simulink_env.py:269-283`

- [ ] Add `OMEGA_SAT_DETECT_HZ = 13.5` constant near the top of the module (line ~75), just below TDS_FAIL_PENALTY

```python
OMEGA_SAT_DETECT_HZ: float = 13.5  # detect within 1.5 Hz of IntW clip (±15 Hz @ 50 Hz)
```

- [ ] In `step()` (after `_max_freq_dev` computation at line ~269), add saturation flag:

```python
_max_freq_dev = float(np.max(np.abs((self._omega - 1.0) * F_NOM)))
_omega_saturated = _max_freq_dev >= OMEGA_SAT_DETECT_HZ
info: Dict[str, Any] = {
    "sim_time": self._sim_time,
    "omega": self._omega.copy(),
    "M": self._M.copy(),
    "D": self._D.copy(),
    "P_es": self._P_es.copy(),
    "sim_ok": sim_ok,
    "freq_hz": self._omega * F_NOM,
    "max_freq_dev_hz": _max_freq_dev,
    "max_freq_deviation_hz": _max_freq_dev,
    "tds_failed": not sim_ok,
    "omega_saturated": _omega_saturated,      # NEW: IntW clip detected
    "hit_freq_clip": _omega_saturated,        # NEW: alias for monitor compat
    "reward_components": components,
}
```

- [ ] Run smoke: `python -c "from env.simulink.kundur_simulink_env import KundurStandaloneEnv; e=KundurStandaloneEnv(); obs,_=e.reset(); _,_,_,_,info=e.step(e.action_space.sample()); print(info.keys()); print('omega_saturated' in info)"`

---

## Task 2: Reduce DIST_MAX and DIST_MIN

**Files:**
- Modify: `scenarios/kundur/config_simulink.py:97-98`

- [ ] Replace the disturbance block comment + values:

```python
# Disturbance magnitude range (Kundur-specific override).
# Physics: at D_LO=1.5, DIST_MAX=0.5 → Δf_ss=2.1Hz → peak≈4.8Hz (2.3× two-area factor).
# Even worst-case 3× factor gives peak≈6.3Hz — well below IntW clip at 15Hz.
# Previous DIST_MAX=1.5 gave peak≈14.4Hz, saturating IntW on 507/510 episodes
# (run kundur_simulink_20260414_211958) and filling replay buffer with distorted physics.
DIST_MIN = 0.1   # 10 MW minimum disturbance
DIST_MAX = 0.5   # 50 MW maximum disturbance — verified safe below IntW clip
```

---

## Task 3: Update optimization log

**Files:**
- Run Python script (no file edit needed)

- [ ] Append outcome to opt_kd_20260417_03 once training result is known.
- [ ] Update status to applied immediately:

```python
from engine.optimization_log import load_log, _log_path
import json
from pathlib import Path
path = _log_path('kundur')
lines = path.read_text('utf-8').splitlines()
# Find opt_kd_20260417_03 and update status to applied
updated = []
for line in lines:
    r = json.loads(line)
    if r.get('opt_id') == 'opt_kd_20260417_03' and r.get('type') == 'optimization':
        r['status'] = 'applied'
    updated.append(json.dumps(r, ensure_ascii=False))
path.write_text('\n'.join(updated) + '\n', encoding='utf-8')
```

---

## Task 4: Run tests

- [ ] `python -m pytest tests/test_harness_tasks.py tests/test_mcp_simulink_tools.py -x -q --ignore-glob="*matlab*"` — verify no import regressions

---

## Task 5: Commit

- [ ] `git add env/simulink/kundur_simulink_env.py scenarios/kundur/config_simulink.py scenarios/contracts/optimization_log_kundur.jsonl`
- [ ] `git commit -m "fix(kundur): reduce DIST_MAX 1.5→0.5, add omega_saturated monitoring\n\nRoot cause (Kd.md, opt_kd_20260417_01/02): DIST_MAX=1.5 caused Kundur\ntwo-area oscillation peaks of ~14.4Hz, saturating IntW at ±15Hz on\n507/510 episodes and filling replay buffer with distorted physics.\n\nFix: DIST_MAX 1.5→0.5 (50MW max), physics derivation shows peak≤4.8Hz\nat D_LO=1.5 with 2.3x two-area oscillation factor. Added omega_saturated\nfield to info dict for monitoring saturation events going forward."`

---

## Task 6: Launch training

- [ ] Launch via `engine/training_launch.py` or `scripts/launch_training.ps1 kundur`
- [ ] Monitor first 50 episodes: `omega_saturated` rate should be <5%
- [ ] After 100+ episodes, call `append_outcome('kundur', 'opt_kd_20260417_03', ...)` with settled_rate and saturation_rate

---

## Success Criteria

| Metric | Before | Target |
|--------|--------|--------|
| omega_saturated rate | ~99% | <5% |
| settled_rate | 0/510 | >0 |
| max_freq_dev_hz median | ~14.5 Hz | <8 Hz |
| tds_failed rate | low | low |
