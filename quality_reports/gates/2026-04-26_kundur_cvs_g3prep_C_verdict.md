# G3-prep C — Kundur CVS Step / Warmup Dispatch Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — G3-prep-C only (two NEW `_cvs.m` files + minimal additive bridge dispatch; no NE39 / legacy / shared `.m` modification)
**Predecessors:**
- G3-prep-A (CVS profile JSON) — `2026-04-26_kundur_cvs_g3prep_A_verdict.md` (commit `4587f66`)
- G3-prep-B (additive `step_strategy` field) — `2026-04-26_kundur_cvs_g3prep_B_verdict.md` (commit `c97cabb`)
- D-pre snapshot — `2026-04-26_ne39_baseline_snapshot.md` (commit `a12189e`)
- Gate 3 entry plan §2 G3-prep-C — `2026-04-26_kundur_cvs_gate3_entry_plan.md`

---

## Verdict: PASS

Three artefacts land. The CVS dispatch through `SimulinkBridge` produces a
30 s zero-action result that meets all 5 D3 PASS criteria, and the NE39
contamination tripwire (read-only 3-ep run, identical command to D-pre)
stays well within the ±30 % band on every metric the snapshot pinned.

---

## Artefacts in this commit

| File | Operation | SHA-256 | Lines |
|---|---|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | NEW | `d3f732e31530900bed0a39fb35780ecdcbe687a7850e8ab451ddc126ed1824e0` | 119 |
| `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` | NEW | `87efaa740c92544836afa7b2b5e0cefa0b651f76a1bde5e3d637d080edb5dcfb` | 144 |
| `engine/simulink_bridge.py` | M (additive: +111 / -1) | `aa348711dd02dc6acb49d5f28b648a397b9121d2e0f3d608ab14841cd08b27d2` | (see §2 below) |
| `probes/kundur/gates/g3prep_C_cvs_dispatch_verify.py` | NEW | n/a (probe) | 248 |
| `quality_reports/gates/2026-04-26_kundur_cvs_g3prep_C_verdict.md` | NEW (this) | n/a | — |

---

## 1. CVS dispatch design (matching the user-authorised scope)

### 1.1 Two NEW MATLAB functions (same signature as their `phang_feedback` siblings)

`slx_step_and_read_cvs.m` accepts the **identical 9-arg signature** as
`slx_step_and_read.m` and returns the **identical state schema**
(`omega(N), Pe(N), rocof(N), delta(N), delta_deg(N)`). Differences:

- Ignores `Pe_prev` and `delta_prev_deg` (CVS .slx closes the swing-eq
  internally — no phAng feedback path)
- Writes `M_<i>` / `D_<i>` via `cfg.m_var_template` / `cfg.d_var_template`
  (the CVS-profile values landed in G3-prep-A: `M_{idx}` / `D_{idx}`)
- Reads `omega_ts_<i>` / `delta_ts_<i>` / `Pe_ts_<i>` Timeseries directly
  from `simOut` (does **not** call `slx_extract_state`, which is hard-wired
  to NE39/legacy `omega_ES_<i>` / `Vabc_ES_<i>` / `Iabc_ES_<i>` naming)

`slx_episode_warmup_cvs.m` accepts the **identical 6-arg signature** as
`slx_episode_warmup.m`. Differences:

- `init_params` schema is CVS-specific: `M0`, `D0`, `Pm0_pu`, `delta0_rad`,
  optional `Vmag_volts`, `Pm_step_t`, `Pm_step_amp`, `t_warmup`
- Does **not** push `phAng_ES_<i>` / `Pe_ES_<i>` / `wref_<i>` (those
  variables don't exist in `kundur_cvs.slx`)
- Does **not** push physical constants (`wn_const`, `Vbase_const`, etc.) —
  `build_kundur_cvs.m` already wrote them at build time and they survive
  episode resets
- Reads state by the same Timeseries path as the step function

### 1.2 Bridge dispatch (engine/simulink_bridge.py, +111 / -1 lines)

Two minimal additive insertion points:

1. `SimulinkBridge.step()` (one-line function-name route):
   ```python
   step_fn = ("slx_step_and_read_cvs" if self.cfg.step_strategy == "cvs_signal"
              else "slx_step_and_read")
   ```
   — replaces the previous literal `"slx_step_and_read"` first arg in
   `self.session.call(...)`. **Default behaviour for every existing caller
   is identical** because `step_strategy` defaults to `"phang_feedback"`
   (G3-prep-B).

2. `SimulinkBridge.warmup()` (top-of-method early return):
   ```python
   if self.cfg.step_strategy == "cvs_signal":
       self._warmup_cvs(duration)
       return
   ```
   — placed **before** the existing `pe_nominal_vsg_arr = ...` line, so
   the existing 5/6-arg path (`kundur_ip` struct + `slx_episode_warmup`)
   and 3-arg path (assignin `phAng_ES_<i>` / `Pe_ES_<i>` / `wref_<i>` +
   `slx_fastrestart_reset`) **execute byte-for-byte unchanged** for any
   caller with `step_strategy == "phang_feedback"`.

3. New helper `SimulinkBridge._warmup_cvs(duration)` (~80 lines): reads
   `kundur_ic_cvs.json` (D2/D3 NR IC), constructs `kundur_cvs_ip` struct,
   calls `slx_episode_warmup_cvs`, and seeds `_Pe_prev` / `_delta_prev_deg`
   so future `step()` calls see consistent feedback caches even though the
   CVS step ignores them.

`BridgeConfig` is **NOT modified in C** — no new fields. The existing
`m_var_template` / `d_var_template` (used by all paths) are sufficient.

---

## 2. What was NOT touched (boundary confirmation)

### 2.1 NE39 / legacy / shared MATLAB layer — SHA-256 verbatim

| File | SHA-256 | Status |
|---|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | `3175a5af…df5300` | UNCHANGED |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | `8ff0c8ed…7ed6a` | UNCHANGED |
| `scenarios/contract.py` | `77e67161…3c67` | UNCHANGED |
| `scenarios/config_simulink_base.py` | `cb737a4b…a9625` | UNCHANGED |
| `scenarios/new_england/config_simulink.py` | `aac9c8f0…ea425` | UNCHANGED |
| `scenarios/new_england/train_simulink.py` | `071fb404…dde2` | UNCHANGED |
| `env/simulink/ne39_simulink_env.py` | `ec2392c6…56b` | UNCHANGED |
| `env/simulink/_base.py` | `542bbdb2…4d90` | UNCHANGED |
| `scenarios/new_england/simulink_models/NE39bus_v2.slx` | `cfe436e2…607b` | UNCHANGED |

### 2.2 Boundary scope (per user authorisation list)

- ❌ `slx_step_and_read.m` / `slx_episode_warmup.m`: not edited
- ❌ NE39 anything: not edited (only **read-only** 3-ep tripwire run)
- ❌ legacy Kundur (`build_powerlib_kundur.m`, `build_kundur_sps.m`,
  `kundur_vsg.slx`, `kundur_vsg_sps.slx`, legacy `kundur_ic.json`,
  legacy `compute_kundur_powerflow.m`): not edited
- ❌ reward / agent / SAC / network / hyperparameters: not edited
- ❌ `scenarios/contract.py` / root `config.py`: not edited
- ❌ `scenarios/kundur/config_simulink.py`: not edited (CVS profile is
  picked up via existing `KUNDUR_MODEL_PROFILE` env-var path; the profile
  JSON shipped in A and the bridge config remains uniform)
- ❌ `BridgeConfig` interface (no new fields, no removed fields)
- ❌ `build_kundur_cvs.m`, `kundur_cvs.slx`, `compute_kundur_cvs_powerflow.m`,
  `kundur_ic_cvs.json` (model side): not edited (verification probe runs
  the build but does not mutate sources)
- ❌ Gate 3 / SAC / RL / smoke / training: not entered
- ❌ Probe-only workaround for `pe_measurement='vi'` validation (placeholder
  `vabc_signal="Vabc_unused_{idx}"` / `iabc_signal="Iabc_unused_{idx}"` in
  the verification probe) is contained to the probe; **not promoted to any
  production config or bridge code path**.

---

## 3. Verification 1 — CVS dispatch end-to-end (D3-style 30 s zero-action)

`probes/kundur/gates/g3prep_C_cvs_dispatch_verify.py` builds a CVS
`BridgeConfig`, calls `SimulinkBridge.warmup(duration=30.0)` (which
exercises the new `cvs_signal` early-return → `_warmup_cvs` →
`slx_episode_warmup_cvs.m` chain), then re-runs a 30 s sim to capture
Timeseries and applies the 5 D3 PASS criteria.

| # | Criterion | Threshold | Result | Verdict |
|---|---|---|---|---|
| 1 | ω in [0.999, 1.001] full 30 s | strict band | VSG1..4 ω∈[1.000000, 1.000000] | PASS |
| 2 | \|δ\| < π/2 - 0.05 (≈ 1.521 rad) | strict | VSG1/2 \|δ\|max=0.2939, VSG3/4 \|δ\|max=0.1107 | PASS |
| 3 | Pe within ±5 % of Pm₀ (=0.5 pu) | rel < 5 % | VSG1..4 Pe∈[0.5000, 0.5000], rel=0.00 % | PASS |
| 4 | ω never touches [0.7, 1.3] | strict | clip_touch = False (all 4) | PASS |
| 5 | inter-VSG sync (tail 5 s) | spread < 1e-3 | tail_means = [1.000000]×4, spread = 0.000e+00 | PASS |

**Wall-clock:** `bridge.warmup(30.0)` = **0.94 s**. The CVS dispatch is
materially faster than the NE39 path because powergui Phasor mode + ode23t
variable-step coalesces aggressively at the NR equilibrium. Numerics are
identical (to floating-point precision) to D3 (commit `307952e`) — proving
the new dispatch produces the same physical answer as a direct NR-IC
sim, while now flowing through `SimulinkBridge`'s public API.

---

## 4. Verification 2 — NE39 contamination tripwire (read-only 3-ep)

Same command as D-pre (`scenarios/new_england/train_simulink.py --mode
simulink --episodes 3 --resume none`), no NE39 file modified, run against
the post-C bridge.

| Metric | D-pre baseline (a12189e) | post-C (this run) | Deviation | Tripwire ±30 % | Verdict |
|---|---|---|---|---|---|
| `mean(ep_reward) over 3 ep` | -905.51 | -797.87 | \|107.64\| / 905.51 = **11.9 %** | ≤ 30 % | PASS |
| `mean(max_freq_dev_hz)` | 12.39 | 11.51 | \|0.88\| / 12.39 = **7.1 %** | ≤ 30 % | PASS |
| per-ep `max_freq_dev_hz` | [12.75, 15.01, 9.41] | [9.09, 12.82, 12.62] | within band envelope | informational | — |
| per-ep `ep_reward` | [-787.43, -1050.60, -878.50] | [-801.02, -748.78, -843.80] | within band envelope | informational | — |
| `settled_paper` count | 0/3 | 0/3 | 0 pp | not below 0/3 | PASS |
| SAC gradient updates | 0 (warmup) | 0 (warmup) | identical | identical | PASS |
| Wall-clock | 615.6 s (10.3 min) | 740.1 s (12.3 min) | +20 % | informational | — |

The reward / freq_dev mean values **moved inward** (smaller magnitude)
between D-pre and post-C — natural variance from re-running with a fresh
MATLAB session. **No metric breached the ±30 % tripwire.** SAC gradient
state remains untouched (3 ep × 50 step = 150 transitions « `WARMUP_STEPS
= 2000`, no updates fire — same behaviour as D-pre, confirming no SAC-side
regression).

The wall-clock difference (+20 %) is below the snapshot's "≤ 800 s sanity
cap"; it does not trigger the `wall_clock` informational threshold from
D-pre §5. Likely cause: pre-warmed FastRestart cache state between runs.

**Default `phang_feedback` path is bit-equivalent in semantics; bridge
dispatch additions did not contaminate NE39.**

---

## 5. NE39 contamination tripwire — boundary check

| File | D-pre SHA-256 | Post-C SHA-256 | Status |
|---|---|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | `3175a5af…df5300` | `3175a5af…df5300` | ✅ verbatim |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | `8ff0c8ed…7ed6a` | `8ff0c8ed…7ed6a` | ✅ verbatim |
| `scenarios/new_england/config_simulink.py` | `aac9c8f0…ea425` | `aac9c8f0…ea425` | ✅ verbatim |
| `scenarios/new_england/train_simulink.py` | `071fb404…dde2` | `071fb404…dde2` | ✅ verbatim |
| `env/simulink/ne39_simulink_env.py` | `ec2392c6…56b` | `ec2392c6…56b` | ✅ verbatim |
| `env/simulink/_base.py` | `542bbdb2…4d90` | `542bbdb2…4d90` | ✅ verbatim |
| `scenarios/new_england/simulink_models/NE39bus_v2.slx` | `cfe436e2…607b` | `cfe436e2…607b` | ✅ verbatim |
| `scenarios/contract.py` | `77e67161…3c67` | `77e67161…3c67` | ✅ verbatim |
| `scenarios/config_simulink_base.py` | `cb737a4b…a9625` | `cb737a4b…a9625` | ✅ verbatim |

Only `engine/simulink_bridge.py` SHA-256 changed (B + C dispatch, additive
only); the 9 NE39 / legacy / shared boundary files are byte-identical to
D-pre baseline.

---

## 6. What G3-prep-C does NOT do

- Does **not** introduce any RL / SAC / replay-buffer code path
- Does **not** wire any disturbance injection in the new `.m` or in the
  bridge — `Pm_step_t_<i>` / `Pm_step_amp_<i>` defaults remain as set by
  `build_kundur_cvs.m` (Pm_step_amp = 0 → no perturbation)
- Does **not** mutate `BridgeConfig` interface — no new fields, no
  validation relaxation; the placeholder `vabc_signal="Vabc_unused_{idx}"`
  / `iabc_signal="Iabc_unused_{idx}"` work-around is contained to the
  verification probe (per the user-confirmed scope)
- Does **not** change the CVS profile JSON committed in A
- Does **not** reorder / rename / delete any existing public method on
  `SimulinkBridge`
- Does **not** alter NE39 / legacy / shared `.m` files, NE39 reward / config /
  contract / agent / training entry
- Does **not** start Gate 3 / SAC / smoke / training

---

## 7. Open known limitations (logged for G3-prep-D / E)

1. **`pe_measurement='vi'` validation placeholder.** The verification probe
   uses `vabc_signal="Vabc_unused_{idx}"` and `iabc_signal="Iabc_unused_{idx}"`
   to satisfy `BridgeConfig.__post_init__`. This is acceptable because the
   CVS `.m` files **do not read these signals**, but a future cleanup
   (G3-prep-D or beyond, with explicit user authorisation) should add an
   explicit `cvs_signal` branch in the validator, or relocate the CVS path
   to `pe_measurement='pout'` with `p_out_signal='Pe_ts_{idx}'`. **NOT in
   C scope.**

2. **`scenarios/kundur/config_simulink.py` does not yet plumb
   `step_strategy='cvs_signal'`** when `KUNDUR_MODEL_PROFILE` points at
   `kundur_cvs.json`. C's verification probe constructs `BridgeConfig`
   directly. Adding the dispatch into `config_simulink.py` is a separate
   ≤ 5-line change but was kept out of C to honour the "do not modify
   `config_simulink.py`" boundary; it lands in a follow-up step (G3-prep-D
   smoke spec or similar).

3. **CVS warmup wall-clock: 0.94 s for 30 s of model time.** Excellent
   margin against the entry plan §3.3 budget (≤ 5 min/ep). Should remain
   true at smaller `dt_control` (0.2 s/step), since per-step cost will
   dominate the same powergui Phasor solver.

---

## 8. git status / diff at this point

```
=== git status --short ===
 M engine/simulink_bridge.py
?? probes/kundur/gates/g3prep_C_cvs_dispatch_verify.py
?? quality_reports/gates/2026-04-26_kundur_cvs_g3prep_C_verdict.md
?? results/sim_ne39/runs/ne39_simulink_20260425_194644/   (gitignored, D-pre)
?? results/sim_ne39/runs/ne39_simulink_20260425_204049/   (gitignored, post-C)
?? results/cvs_g3prep_c/20260425T203954/                  (gitignored, CVS verify)
?? slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m
?? slx_helpers/vsg_bridge/slx_step_and_read_cvs.m

=== git diff --stat ===
 engine/simulink_bridge.py | 112 ++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 111 insertions(+), 1 deletion(-)

=== git log --oneline -5 ===
c97cabb feat(cvs-g3prep): add additive bridge step_strategy field (B)
4587f66 docs(cvs-g3prep): add isolated Kundur CVS model profile (A)
a12189e docs(cvs-gate3): NE39 + legacy baseline tripwire snapshot (G3-prep D-pre)
1143258 docs(cvs-gate3): add locked entry plan for SAC/RL prep
74428d7 feat(cvs-d4-rev): pass Gate 2 with paper-baseline damping metrics
```

---

## 9. Reproduction

CVS dispatch verification (≤ 1 min wall-clock, needs MCP MATLAB shared session):

```bash
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  probes/kundur/gates/g3prep_C_cvs_dispatch_verify.py
```
Expected: `OVERALL: PASS` with 5 PASS lines.

NE39 contamination tripwire (≤ 13 min wall-clock; identical to D-pre):

```bash
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/new_england/train_simulink.py --mode simulink --episodes 3 --resume none
```
Expected: `mean(ep_reward)` within ±30 % of -905.51, `mean(max_freq_dev_hz)`
within ±30 % of 12.39 Hz.

---

## 10. Next step (gated on user)

| Choice | Effect |
|---|---|
| **Commit C** (this verdict + 2 NEW `.m` + bridge dispatch + verification probe) | locks the dispatch; G3-prep-D / E and Gate 3 still locked |
| Hold | files stay on disk; user can review further |
| Revert | `git restore engine/simulink_bridge.py` + delete new files |

Gate 3 / SAC / RL remain locked. G3-prep-D (smoke spec) and any further
entry-plan steps require new explicit authorisation.
