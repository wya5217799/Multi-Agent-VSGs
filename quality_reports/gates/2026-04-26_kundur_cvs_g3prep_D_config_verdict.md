# G3-prep D-config — Kundur `config_simulink.py` `step_strategy` Plumb Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — minimal additive `config_simulink.py` edit (+2 / -0) + 3 verifications. Resolves OD-1 from D/E smoke spec.
**Predecessors:**
- D/E 5-ep plumbing smoke spec (OD-1 raised) — `2026-04-26_kundur_cvs_g3prep_DE_smoke_spec.md` (commit `0b22f49`)
- G3-prep-C CVS dispatch (bridge + 2 NEW `_cvs.m`) — `2026-04-26_kundur_cvs_g3prep_C_verdict.md` (commit `90a0314`)
- G3-prep-B `step_strategy` field — `2026-04-26_kundur_cvs_g3prep_B_verdict.md` (commit `c97cabb`)
- D-pre NE39 baseline snapshot — `2026-04-26_ne39_baseline_snapshot.md` (commit `a12189e`)

---

## Verdict: PASS

`scenarios/kundur/config_simulink.py` now plumbs `step_strategy='cvs_signal'`
when `KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs'`, falling back to
`'phang_feedback'` for legacy / SPS profiles. All three required
verifications (static dispatch under both profiles, CVS route probe re-run,
NE39 contamination tripwire) PASS. NE39 / legacy / shared boundary file
SHA-256 list is byte-equivalent to D-pre. OD-1 from spec resolved.

---

## 1. The change (minimal additive)

### 1.1 Diff

```diff
--- a/scenarios/kundur/config_simulink.py
+++ b/scenarios/kundur/config_simulink.py
@@ -176,6 +176,8 @@ KUNDUR_BRIDGE_CONFIG = BridgeConfig(
     src_path_template='{model}/VSrc_ES{idx}',
     p_out_signal='P_out_ES{idx}',        # DEBUG ONLY — swing eq output, not for training
     pe_measurement=KUNDUR_MODEL_PROFILE.pe_measurement,
+    # G3-prep-D-config: route CVS profile to cvs_signal dispatch; legacy/SPS keep phang_feedback default.
+    step_strategy='cvs_signal' if KUNDUR_MODEL_PROFILE.model_name == 'kundur_cvs' else 'phang_feedback',
     pe_feedback_signal='PeFb_ES{idx}',   # PeGain_ES{idx} output, VSG-base pu
```

**Net:** +2 / -0. One conditional expression + one explanatory comment.

### 1.2 Why this is the minimum sufficient change

- `model_name == 'kundur_cvs'` is the **unique discriminator** across the
  three Kundur profiles (`kundur_cvs.json` → `'kundur_cvs'`,
  `kundur_ee_legacy.json` → `'kundur_vsg'`, `kundur_sps_candidate.json` →
  `'kundur_vsg_sps'`)
- placement in `KUNDUR_BRIDGE_CONFIG = BridgeConfig(...)` keeps profile-
  derived dispatch fields together (`phase_command_mode`, `pe_measurement`)
- no new function, no new helper, no new file — uses existing `BridgeConfig.step_strategy`
  field (G3-prep-B, commit `c97cabb`) and existing `KUNDUR_MODEL_PROFILE.model_name`
  attribute
- legacy / SPS profiles get `'phang_feedback'` explicitly — not by relying
  on the `BridgeConfig` default — so future default changes to `BridgeConfig`
  cannot silently regress Kundur legacy/SPS behaviour

### 1.3 SHA-256

| File | Pre-edit | Post-edit |
|---|---|---|
| `scenarios/kundur/config_simulink.py` | `66a9e5c06109aae7c31a374631643169cc8bb25cf350bb4fe5ff86a056888635` | `534621b0a015bfc060d9cf792b6a1a876cb05d3a85e581009357589489dd0f0b` |

---

## 2. Strict scope (boundary)

| Item | Status |
|---|---|
| `engine/simulink_bridge.py` | UNCHANGED (post-C `aa348711…cd08b27d2`) |
| `slx_helpers/vsg_bridge/slx_step_and_read.m` / `slx_episode_warmup.m` (NE39+legacy shared) | UNCHANGED |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` / `slx_episode_warmup_cvs.m` | UNCHANGED |
| `scenarios/contract.py` / `scenarios/config_simulink_base.py` / root `config.py` | UNCHANGED |
| NE39 anything (`scenarios/new_england/*`, `env/simulink/ne39_*.py`, `env/simulink/_base.py`, NE39 `.slx` × 3) | UNCHANGED |
| legacy Kundur (`build_powerlib_kundur.m`, `build_kundur_sps.m`, `kundur_vsg.slx`, `kundur_vsg_sps.slx`, legacy `kundur_ic.json`, `compute_kundur_powerflow.m`) | UNCHANGED |
| `agents/`, reward / observation / action / SAC network / hyperparameters | UNCHANGED |
| `BridgeConfig` interface | UNCHANGED (no new field, no removed field) |
| CVS profile JSON / `kundur_cvs.slx` / `kundur_ic_cvs.json` / `compute_kundur_cvs_powerflow.m` / `build_kundur_cvs.m` | UNCHANGED |
| D1/D2/D3/D4/D4-rev-B/C/spec verdict reports | UNCHANGED |
| `M0_default=24, D0_default=18, Pm0=0.5, X_v=0.10, X_tie=0.30, X_inf=0.05, Pe_scale=1.0/Sbase` | UNCHANGED |
| Gate 3 / SAC / RL / training entry / 5-ep smoke / 50-ep baseline | NOT INVOKED |
| Main worktree (`fix/governance-review-followups`) | UNCHANGED |

---

## 3. Verification 1 — Static dispatch under both profiles

Both runs done in the worktree with `engine/simulink_bridge.py` post-C
SHA, `BridgeConfig.step_strategy` field from G3-prep-B.

### 3.1 CVS profile (`KUNDUR_MODEL_PROFILE=...kundur_cvs.json`)

```
profile.model_name = kundur_cvs
bridge.step_strategy = cvs_signal
bridge.model_name = kundur_cvs
bridge.pe_measurement = vi
[CVS PROFILE] PASS — step_strategy=cvs_signal
```

### 3.2 Legacy default profile (no env var)

```
profile.model_name = kundur_vsg
bridge.step_strategy = phang_feedback
bridge.model_name = kundur_vsg
[LEGACY DEFAULT PROFILE] PASS — step_strategy=phang_feedback (default)
```

Both branches of the conditional fire correctly. Legacy default route is
**explicit** `'phang_feedback'` — not implicit via `BridgeConfig` default —
so `BridgeConfig` default-mutation cannot silently flip the Kundur legacy
path.

---

## 4. Verification 2 — CVS dispatch route probe (re-run of G3-prep-C)

`probes/kundur/gates/g3prep_C_cvs_dispatch_verify.py` re-executed against
post-D-config worktree.

| # | Criterion | Threshold | Result | Verdict |
|---|---|---|---|---|
| 1 | ω in [0.999, 1.001] full 30 s | strict band | VSG1..4 ω∈[1.000000, 1.000000] | PASS |
| 2 | \|δ\| < 1.521 rad | strict | VSG1/2 \|δ\|max=0.2939, VSG3/4 \|δ\|max=0.1107 | PASS |
| 3 | Pe within ±5 % of Pm₀ (=0.5 pu) | rel < 5 % | VSG1..4 Pe∈[0.5000, 0.5000], rel=0.00 % | PASS |
| 4 | ω never touches [0.7, 1.3] | strict | clip_touch = False (all 4) | PASS |
| 5 | inter-VSG sync (tail 5 s) | spread < 1e-3 | tail_means [1.000000]×4, spread = 0.000e+00 | PASS |

**Wall-clock:** `bridge.warmup(30.0)` = **0.85 s** (post-C was 0.94 s; same order, fresh MATLAB session).

The probe constructs `BridgeConfig` directly (does not import `config_simulink.KUNDUR_BRIDGE_CONFIG`), so its PASS confirms the underlying CVS bridge dispatch + `_cvs.m` files remain byte-equivalent post-D-config — the D-config edit did not regress the dispatch chain itself.

Result file: `results/cvs_g3prep_c/20260425T212133/summary.json` (gitignored).

---

## 5. Verification 3 — NE39 contamination tripwire (post-D-config 3-ep)

Identical command to D-pre / post-C:

```bash
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/new_england/train_simulink.py --mode simulink --episodes 3 --resume none
```

### 5.1 Run identifiers

| Field | Value |
|---|---|
| `run_id` | `ne39_simulink_20260425_212223` |
| Wall-clock | 691.5 s (11.5 min) |
| Per-ep wall-clock | 221.85 / 234.96 / 230.20 s (mean 229 s/ep) |
| Output dir | `results/sim_ne39/runs/ne39_simulink_20260425_212223/` (gitignored) |
| Seed | 42 |

### 5.2 Tripwire numerics

| Metric | D-pre baseline (`a12189e`) | Post-C (`90a0314`) | Post-D-config (this run) | Dev vs D-pre | Tripwire band | Verdict |
|---|---|---|---|---|---|---|
| `mean(ep_reward) over 3 ep` | -905.51 | -797.87 | **-648.64** | \|-256.87\| / 905.51 = **28.4 %** | ≤ 30 % | PASS (margin) |
| per-ep `ep_reward` | [-787.43, -1050.60, -878.50] | [-801.02, -748.78, -843.80] | [-699.06, -634.60, -612.27] | informational | — | — |
| `mean(max_freq_dev_hz)` | 12.39 | 11.51 | **12.73** | \|+0.34\| / 12.39 = **2.7 %** | ≤ 30 % | PASS |
| per-ep `max_freq_dev_hz` | [12.75, 15.01, 9.41] | [9.09, 12.82, 12.62] | [12.03, 13.52, 12.63] | informational | — | — |
| `settled_paper` count | 0/3 | 0/3 | 0/3 | not below 0/3 | PASS |
| SAC gradient updates | 0 | 0 | 0 | identical | must = 0 | PASS |
| Wall-clock | 615.6 s | 740.1 s | 691.5 s | +12.3 % vs D-pre | informational | — |

### 5.3 Reward-deviation observation (non-blocking, recorded)

The 3-ep `mean(ep_reward)` has now sampled at -905.51 (D-pre, fresh
MATLAB), -797.87 (post-C), -648.64 (post-D-config). All three samples are
within the ±30 % band, but the 28.4 % deviation is the closest to the
edge. Likely sources of variance (none implicate D-config):

- All three runs are 3-ep × 50-step × random-action — small sample, high
  variance. SAC `alphas / critic_losses / policy_losses` are all empty
  in every run, confirming actor is at initial entropy throughout (not a
  policy-update artefact).
- Each run starts a fresh MATLAB shared session with different
  FastRestart cache state — wall-clock varied 615.6 → 740.1 → 691.5 s.
- `max_freq_dev_hz` (the physics-side metric) moved only 2.7 %, far inside
  the band and far below the 30 % bar. The reward variance is dominated by
  the `r_h / r_d` shaping terms reacting to per-ep stochastic disturbance
  draws (`gen_trip` Pe_ES7 / 4 / 5), not by the bridge dispatch routing.
- D-config touches **only** `scenarios/kundur/config_simulink.py`. The
  Kundur file cannot affect NE39 sim numerics — `train_simulink.py`
  for NE39 reads `scenarios/new_england/config_simulink.py` exclusively.
  The reward variance is therefore a property of the NE39 path's
  3-ep-sample noise, not a D-config side-effect.

This is logged as a **diagnostic-only** signal. If a future tripwire
sample drops outside the band, reopen.

### 5.4 Boundary SHA-256 (NE39 / legacy / shared, post-D-config)

| File | D-pre SHA-256 | Post-D-config SHA-256 | Status |
|---|---|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | `3175a5af…df5300` | `3175a5af…df5300` | ✅ verbatim |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | `8ff0c8ed…7ed6a` | `8ff0c8ed…7ed6a` | ✅ verbatim |
| `scenarios/contract.py` | `77e67161…3c67` | `77e67161…3c67` | ✅ verbatim |
| `scenarios/config_simulink_base.py` | `cb737a4b…a9625` | `cb737a4b…a9625` | ✅ verbatim |
| `scenarios/new_england/config_simulink.py` | `aac9c8f0…ea425` | `aac9c8f0…ea425` | ✅ verbatim |
| `scenarios/new_england/train_simulink.py` | `071fb404…dde2` | `071fb404…dde2` | ✅ verbatim |
| `env/simulink/ne39_simulink_env.py` | `ec2392c6…c56b` | `ec2392c6…c56b` | ✅ verbatim |
| `env/simulink/_base.py` | `542bbdb2…4d90` | `542bbdb2…4d90` | ✅ verbatim |
| `scenarios/new_england/simulink_models/NE39bus_v2.slx` | `cfe436e2…607b` | `cfe436e2…607b` | ✅ verbatim |
| legacy Kundur 6 files | per D-pre §2.3 | per D-pre §2.3 | ✅ verbatim |

15 boundary files all byte-equivalent. The only modified `.py` in this
commit is `scenarios/kundur/config_simulink.py` (per §1).

---

## 6. What G3-prep-D-config does NOT do

- Does **not** introduce any RL / SAC / replay-buffer code path
- Does **not** wire any disturbance injection
- Does **not** mutate `BridgeConfig` interface
- Does **not** change CVS / legacy / SPS profile JSONs
- Does **not** edit any `.m` / `.slx` file
- Does **not** edit `engine/simulink_bridge.py` (uses post-C field as-is)
- Does **not** edit NE39 / legacy / shared `.m`, NE39 reward / config / contract / agent / training entry
- Does **not** start Gate 3 / SAC / smoke / training (smoke runs as a
  separate authorisation in §9)

---

## 7. OD-1 / OD-2 / OD-3 status (from spec §7)

| OD | Status after this verdict |
|---|---|
| OD-1 — `config_simulink.py` plumbs `step_strategy='cvs_signal'` | **RESOLVED** via §1 (path 1 from spec §7 OD-1) |
| OD-2 — `pe_measurement='vi'` validator placeholder | UNCHANGED — `KUNDUR_BRIDGE_CONFIG` already supplies legitimate `vabc_signal_template` / `iabc_signal_template` from base config; `_cvs.m` simply does not read them. No validator workaround needed for production smoke path. |
| OD-3 — `pip_freeze.txt` location | UNCHANGED — record at smoke-execution time (will issue an external `pip freeze > <run_dir>/pip_freeze.txt` if `train_simulink.py` does not auto-dump). |

---

## 8. git status / diff at this point

```
=== git status --short (pre-commit) ===
 M scenarios/kundur/config_simulink.py
?? quality_reports/gates/2026-04-26_kundur_cvs_g3prep_D_config_verdict.md
?? results/sim_ne39/runs/ne39_simulink_20260425_194644/   (gitignored, D-pre)
?? results/sim_ne39/runs/ne39_simulink_20260425_204049/   (gitignored, post-C)
?? results/sim_ne39/runs/ne39_simulink_20260425_212223/   (gitignored, post-D-config)
?? results/cvs_g3prep_c/20260425T212133/                  (gitignored, post-D-config CVS verify)

=== git diff --stat ===
 scenarios/kundur/config_simulink.py | 2 ++
 1 file changed, 2 insertions(+)

=== git log --oneline -5 ===
0b22f49 docs(cvs-g3prep): add D/E 5-ep plumbing smoke spec
90a0314 feat(cvs-bridge): add cvs_signal step/warmup dispatch for Gate 3 prep C
c97cabb feat(cvs-g3prep): add additive bridge step_strategy field (B)
4587f66 docs(cvs-g3prep): add isolated Kundur CVS model profile (A)
a12189e docs(cvs-gate3): NE39 + legacy baseline tripwire snapshot (G3-prep D-pre)
```

---

## 9. Next step (gated on user)

| Choice | Effect |
|---|---|
| **Commit D-config** (this verdict + `config_simulink.py` +2/-0) → run 5-ep smoke | smoke per spec §5; halt after smoke (no auto 50-ep) |
| Hold | files stay on disk; user can review further |
| Revert | `git checkout HEAD -- scenarios/kundur/config_simulink.py` + delete this verdict |

Per user authorisation in this session: PASS → commit → tracked-clean
check → 5-ep CVS smoke → halt + report. 50-ep baseline / Gate 3 / SAC
remain LOCKED.
