# G3-prep B — Bridge `step_strategy` Additive Field Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — G3-prep-B only (additive `BridgeConfig.step_strategy` field; no dispatch wiring; no `.m` file change)
**Predecessors:**
- G3-prep-A (CVS profile JSON) — `2026-04-26_kundur_cvs_g3prep_A_verdict.md` (commit `4587f66`)
- D-pre snapshot — `2026-04-26_ne39_baseline_snapshot.md` (commit `a12189e`)
- Gate 3 entry plan §2 G3-prep-B — `2026-04-26_kundur_cvs_gate3_entry_plan.md`

---

## Verdict: PASS

A single new optional field `step_strategy: str = "phang_feedback"` is added
to `engine.simulink_bridge.BridgeConfig`, validated against an enum
`STEP_STRATEGY_MODES = ("phang_feedback", "cvs_signal")`. NE39 and legacy
Kundur paths see no behavioural change (default value reproduces pre-B
behaviour). `SimulinkBridge.step()` does **not** yet read the field —
dispatch wiring is reserved for G3-prep-C. No reward / agent / SAC / `.m` /
NE39 / legacy / shared layer touched.

---

## Single artefact modified

| File | Lines added | Lines removed | Note |
|---|---|---|---|
| `engine/simulink_bridge.py` | +25 | -0 | additive only |

Three insertion points (no existing line moved or deleted):

### 1. New module-level enum (lines 53-65, 13 lines after `PE_MEASUREMENT_MODES`)

```python
# step_strategy: how a single RL control step drives the .slx model.
#   "phang_feedback" — current default for all in-tree callers (NE39 +
#                      legacy Kundur). step() writes M_i / D_i workspace
#                      values, calls slx_step_and_read.m, optionally
#                      injects phAng feedback (NE39 only).
#   "cvs_signal"     — reserved for the Kundur CVS path (G3-prep-C). The
#                      CVS model has no phAng feedback; the swing-eq is
#                      already closed inside the .slx via cosD/sinD/RI2C.
#                      This value is currently ACCEPTED at construction
#                      time and stored on the config but NOT yet dispatched
#                      by step() — actual dispatch is added in G3-prep-C.
STEP_STRATEGY_MODES = ("phang_feedback", "cvs_signal")
```

### 2. New optional field in `BridgeConfig` (5 lines at end of dataclass body)

```python
# G3-prep-B (additive): how a single step drives the .slx.
#   Default "phang_feedback" reproduces the pre-B behaviour for every
#   existing caller (NE39, legacy Kundur). "cvs_signal" is reserved
#   for the Kundur CVS profile; dispatch wiring lands in G3-prep-C.
step_strategy: str = "phang_feedback"
```

### 3. New `__post_init__` validation block (7 lines after the `pe_measurement` block)

```python
# G3-prep-B: validate step_strategy enum
if self.step_strategy not in STEP_STRATEGY_MODES:
    errors.append(
        f"step_strategy={self.step_strategy!r} not in "
        f"{STEP_STRATEGY_MODES}"
    )
```

---

## Sanity checks (read-only, no Simulink, no training)

All four checks pass.

### 1. NE39 BridgeConfig still constructs OK with default

```
=== NE39 BRIDGE_CONFIG (default step_strategy) ===
  model_name      = 'NE39bus_v2'
  step_strategy   = 'phang_feedback'
  phase_command_mode = 'absolute_with_loadflow'
```

### 2. Legacy Kundur BridgeConfig still constructs OK with default

```
=== Kundur legacy BRIDGE_CONFIG (default step_strategy) ===
  model_name      = 'kundur_vsg'
  step_strategy   = 'phang_feedback'
```

Default value of `step_strategy` is `"phang_feedback"` for every existing
in-tree caller — no caller is mutated by this commit.

### 3. `step_strategy="cvs_signal"` is accepted

```
=== STEP_STRATEGY_MODES = ('phang_feedback', 'cvs_signal') ===
  cvs_signal accepted: step_strategy='cvs_signal'
```

A direct `BridgeConfig(..., step_strategy='cvs_signal')` constructs without
error and stores the value on the frozen dataclass.

### 4. Invalid `step_strategy` is rejected at construction time

```
  invalid step_strategy rejected: "BridgeConfig('x') validation failed:"
```

`step_strategy='nonsense'` raises `ValueError` from `__post_init__`.

### 5. `SimulinkBridge.step()` does NOT yet read `step_strategy`

```
=== step() does not yet read step_strategy: True ===
  (G3-prep-B is additive only; dispatch lands in G3-prep-C)
```

`inspect.getsource(SimulinkBridge.step)` does not contain the substring
`step_strategy`. Therefore even if a caller sets `step_strategy='cvs_signal'`
on `BridgeConfig`, the runtime behaviour of `step()` is identical to pre-B.
This is intentional: G3-prep-B is the field declaration only;
G3-prep-C will wire the dispatch.

---

## Boundary confirmation

| File | SHA-256 | Status |
|---|---|---|
| `engine/simulink_bridge.py` | `725ddad9b32396837fca36223b4cb9e54d664da16fdc07ddd5d90c6c5ab7b895` | CHANGED (was `e4f7399d…a577`; +25 lines, additive) |
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | `3175a5af…df5300` | UNCHANGED (NE39 共享层) |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | `8ff0c8ed…7ed6a` | UNCHANGED (NE39 共享层) |
| `scenarios/contract.py` | `77e67161…3c67` | UNCHANGED |
| `scenarios/config_simulink_base.py` | `cb737a4b…a9625` | UNCHANGED |
| `scenarios/kundur/config_simulink.py` | `66a9e5c0…8635` | UNCHANGED |
| `scenarios/new_england/config_simulink.py` | `aac9c8f0…ea425` | UNCHANGED |
| `env/simulink/_base.py` | `542bbdb2…4d90` | UNCHANGED |
| `env/simulink/ne39_simulink_env.py` | `ec2392c6…56b` | UNCHANGED |
| `env/simulink/kundur_simulink_env.py` | `da43d445…5d76` | UNCHANGED |
| `scenarios/kundur/model_profile.py` | `c4bc0870…c5499` | UNCHANGED |
| `scenarios/kundur/model_profiles/*.json` | (per A verdict) | UNCHANGED |

NE39 / legacy Kundur / agents / reward / config / SAC / RL / `.m` shared
layer: all untouched. Default behaviour of every existing call site is
preserved bit-for-bit.

---

## What G3-prep-B does NOT do

- Does **not** add any new `.m` file — that is G3-prep-C
  (`slx_step_and_read_cvs.m`, `slx_episode_warmup_cvs.m`)
- Does **not** wire any dispatch in `SimulinkBridge.step()` — that is G3-prep-C
- Does **not** modify NE39, legacy Kundur, `slx_helpers/vsg_bridge/*`
- Does **not** modify reward / agent / SAC / hidden layers / hyperparameters
- Does **not** modify `model_profile.py` parser (the new field lives only
  on `BridgeConfig`, not on `KundurModelProfile`)
- Does **not** modify `scenarios/kundur/config_simulink.py` — the existing
  CVS profile (committed in A) is loaded at runtime via `KUNDUR_MODEL_PROFILE`
  env var; setting `step_strategy='cvs_signal'` for that profile is left
  to G3-prep-C, where the `.m` files exist to satisfy the dispatch
- Does **not** start Gate 3 / SAC / smoke / training
- Does **not** run any sim, no MATLAB engine call

---

## NE39 contamination tripwire (from D-pre)

D-pre §5 set the post-prep tripwire at "all NE39 boundary-file SHA-256 must
remain verbatim". After G3-prep-B:

| File | D-pre baseline (a12189e) | Post-B HEAD | Status |
|---|---|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | `3175a5af…df5300` | `3175a5af…df5300` | ✅ verbatim |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | `8ff0c8ed…7ed6a` | `8ff0c8ed…7ed6a` | ✅ verbatim |
| `scenarios/contract.py` | `77e67161…3c67` | `77e67161…3c67` | ✅ verbatim |
| `scenarios/config_simulink_base.py` | `cb737a4b…a9625` | `cb737a4b…a9625` | ✅ verbatim |
| `scenarios/new_england/config_simulink.py` | `aac9c8f0…ea425` | `aac9c8f0…ea425` | ✅ verbatim |
| `env/simulink/ne39_simulink_env.py` | `ec2392c6…56b` | `ec2392c6…56b` | ✅ verbatim |
| `env/simulink/_base.py` | `542bbdb2…4d90` | `542bbdb2…4d90` | ✅ verbatim |
| NE39 `.slx` files (all 3) | per D-pre §2.2 | identical | ✅ verbatim |

Only `engine/simulink_bridge.py` SHA-256 has changed, and the change is
+25 additive lines whose default-path execution is bit-equivalent to pre-B
(per sanity check 5).

The full NE39 3-ep contamination short run is **not** rerun here per the
G3-prep-B mandate ("no smoke / no training"). The D-pre baseline is the
pre-prep reference; if a future caller needs hard runtime verification,
rerunning the D-pre command after C lands and comparing against the §5
tripwire bands is the prescribed protocol (entry plan §2 G3-prep-B
verification clause).

---

## git status / diff at this point

```
=== git status --short ===
 M engine/simulink_bridge.py
?? quality_reports/gates/2026-04-26_kundur_cvs_g3prep_B_verdict.md
?? results/sim_ne39/runs/ne39_simulink_20260425_194644/  (gitignored, from D-pre)

=== git diff --stat ===
 engine/simulink_bridge.py | 25 +++++++++++++++++++++++++
 1 file changed, 25 insertions(+)

=== git log --oneline -5 ===
4587f66 docs(cvs-g3prep): add isolated Kundur CVS model profile (A)
a12189e docs(cvs-gate3): NE39 + legacy baseline tripwire snapshot (G3-prep D-pre)
1143258 docs(cvs-gate3): add locked entry plan for SAC/RL prep
74428d7 feat(cvs-d4-rev): pass Gate 2 with paper-baseline damping metrics
255ab32 feat(cvs-d4): Gate 2 disturbance sweep — FAIL + diagnostic chain (D4/D4.1/D4.2)
```

Two untracked items + one modified tracked file are staged for the user's
commit decision.

---

## Reproduction

```bash
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" -c "
import sys, os
sys.path.insert(0, os.getcwd())
from engine.simulink_bridge import BridgeConfig, STEP_STRATEGY_MODES
print('STEP_STRATEGY_MODES =', STEP_STRATEGY_MODES)
# Default
cfg = BridgeConfig(model_name='x', model_dir='/tmp', n_agents=4, dt_control=0.2,
                   sbase_va=1e8,
                   m_path_template='{model}/M_{idx}', d_path_template='{model}/D_{idx}',
                   omega_signal='omega_{idx}', vabc_signal='Vabc_{idx}', iabc_signal='Iabc_{idx}',
                   pe_measurement='vi')
print('default step_strategy =', cfg.step_strategy)
"
```

Expected: `STEP_STRATEGY_MODES = ('phang_feedback', 'cvs_signal')`,
`default step_strategy = phang_feedback`.

---

## Next step (gated on user)

| Choice | Effect |
|---|---|
| **Commit B only** (this verdict + bridge.py field) | locks the additive field; G3-prep-C / D / E / Gate 3 still locked |
| Hold (no commit) | files stay on disk only |
| Revert | `git restore engine/simulink_bridge.py` + delete the verdict markdown |

No further action without explicit user authorisation. Gate 3 / SAC / RL
remain locked. G3-prep-C (new `.m` files), G3-prep-E (smoke spec) are NOT
begun.
