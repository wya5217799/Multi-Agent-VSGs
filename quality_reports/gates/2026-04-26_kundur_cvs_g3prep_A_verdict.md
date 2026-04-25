# G3-prep A — Kundur CVS Model Profile JSON Verdict

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** GATE — G3-prep-A only (model profile JSON, no `bridge.py` / `.m` / NE39 / RL)
**Predecessors:**
- Gate 3 entry plan §2 G3-prep-A — `2026-04-26_kundur_cvs_gate3_entry_plan.md`
- D-pre snapshot — `2026-04-26_ne39_baseline_snapshot.md` (commit `a12189e`)

---

## Verdict: PASS

`scenarios/kundur/model_profiles/kundur_cvs.json` is created, schema-conformant,
loadable by `parse_kundur_model_profile`, and dispatchable through the
existing `KUNDUR_MODEL_PROFILE` env-var path. Default behaviour
(no env var) is unchanged — `kundur_ee_legacy` remains the fallback.
No `bridge.py` / `.m` / NE39 / agent / reward / config touched.

---

## Single artefact added

| File | SHA-256 | Origin |
|---|---|---|
| `scenarios/kundur/model_profiles/kundur_cvs.json` | `ab89e82e62b102c0d1da9284367c22cbe00b8a10940147d4b24d8dd2a0eaf869` | NEW |

Content (verbatim, 13 lines):

```json
{
  "scenario_id": "kundur",
  "profile_id": "kundur_cvs",
  "model_name": "kundur_cvs",
  "solver_family": "sps_phasor",
  "pe_measurement": "vi",
  "phase_command_mode": "passthrough",
  "warmup_mode": "technical_reset_only",
  "feature_flags": {
    "allow_pref_ramp": false,
    "allow_simscape_solver_config": false,
    "allow_feedback_only_pe_chain": false
  }
}
```

---

## Field-by-field justification

| Field | Value | Rationale |
|---|---|---|
| `scenario_id` | `"kundur"` | const per `schema.json` |
| `profile_id` | `"kundur_cvs"` | matches the file stem; sibling-uniform with `kundur_ee_legacy` / `kundur_sps_candidate` |
| `model_name` | `"kundur_cvs"` | matches `build_kundur_cvs.m` save target → `kundur_cvs.slx` (committed at `74428d7`) |
| `solver_family` | `"sps_phasor"` | CVS path uses `powergui` Phasor mode (cvs_design.md H4); same enum value as `kundur_sps_candidate` |
| `pe_measurement` | `"vi"` | Pe = Re(V·conj(I))·Pe_scale (cvs_design.md D-CVS-4); same as NE39 + `kundur_sps_candidate` |
| `phase_command_mode` | `"passthrough"` | CVS RI2C signal is the swing-eq `cosD/sinD` output × Vmag; no external loadflow offset (no `init_phang` correction needed). NE39's `absolute_with_loadflow` is **not** the right mode for the CVS path |
| `warmup_mode` | `"technical_reset_only"` | reset_workspace + 0.5 s sim warmup; no physical P_ref ramp (cvs_design.md D-CVS-5: T_WARMUP=0.2-0.5 s, no ramp) |
| `feature_flags.allow_pref_ramp` | `false` | cvs_design.md §2 E5 forbids P_ref ramp; same as `kundur_sps_candidate` |
| `feature_flags.allow_simscape_solver_config` | `false` | CVS path uses `powergui`, NOT `nesl_internal/Solver Configuration`; same as `kundur_sps_candidate` |
| `feature_flags.allow_feedback_only_pe_chain` | `false` | Pe is measured via `vi`, not feedback-only chain |

---

## Sanity checks (read-only, no Simulink, no training)

All four checks pass.

### 1. Schema conformance

| Check | Result |
|---|---|
| All 8 required fields present | ✅ |
| No additional / forbidden top-level keys | ✅ |
| `scenario_id == "kundur"` const | ✅ |
| `solver_family ∈ {simscape_ee, sps_phasor}` | ✅ (`sps_phasor`) |
| `pe_measurement ∈ {feedback, vi}` | ✅ (`vi`) |
| `phase_command_mode ∈ {passthrough, absolute_with_loadflow}` | ✅ (`passthrough`) |
| `warmup_mode ∈ {physics_compensation, technical_reset_only}` | ✅ (`technical_reset_only`) |
| All 3 `feature_flags` required keys present | ✅ |
| No extra `feature_flags` keys | ✅ |

### 2. `parse_kundur_model_profile` accepts the new profile

```
=== kundur_cvs.json loaded OK ===
  scenario_id        = 'kundur'
  profile_id         = 'kundur_cvs'
  model_name         = 'kundur_cvs'
  solver_family      = 'sps_phasor'
  pe_measurement     = 'vi'
  phase_command_mode = 'passthrough'
  warmup_mode        = 'technical_reset_only'
  feature_flags      = KundurFeatureFlags(allow_pref_ramp=False,
                                           allow_simscape_solver_config=False,
                                           allow_feedback_only_pe_chain=False)
```

### 3. Regression: legacy + sps profiles still load

```
=== legacy/sps profiles still load OK ===
  kundur_ee_legacy   profile_id='kundur_ee_legacy'   model_name='kundur_vsg'
  kundur_sps_candidate profile_id='kundur_sps_candidate' model_name='kundur_vsg_sps'
```

### 4. Default dispatch unchanged; env-var dispatch routes to CVS

```
=== config_simulink dispatch (no env var = legacy default) ===
  default KUNDUR_MODEL_PROFILE.profile_id = 'kundur_ee_legacy'
  default KUNDUR_MODEL_PROFILE.model_name = 'kundur_vsg'

=== env-var dispatch to kundur_cvs profile ===
  KUNDUR_MODEL_PROFILE = '.../scenarios/kundur/model_profiles/kundur_cvs.json'
  selected profile_id = 'kundur_cvs'
  selected model_name = 'kundur_cvs'
  bridge.model_name         = 'kundur_cvs'
  bridge.pe_measurement     = 'vi'
  bridge.phase_command_mode = 'passthrough'
  bridge.pe_vi_scale        = 0.5
  bridge.init_phang         = ()
```

`bridge.init_phang = ()` because `phase_command_mode != 'absolute_with_loadflow'`
— matches the existing branch in `scenarios/kundur/config_simulink.py` L191.

`bridge.pe_vi_scale = 0.5` is the **bridge-side** Pe scaling for env
observation (existing convention in `config_simulink.py` L196: `0.5 if
pe_measurement=='vi' else 1.0`). It is distinct from the **build-side**
`Pe_scale = 1.0/Sbase` that closes the swing-equation loop inside
`kundur_cvs.slx` (D2 verdict). Both layers are read-only verified here;
neither is changed.

---

## Boundary confirmation

SHA-256 of every boundary file is verbatim against the D-pre snapshot §2 and
the pre-A working tree:

| File | SHA-256 | Status |
|---|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | `3175a5af…df5300` | UNCHANGED |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | `8ff0c8ed…7ed6a` | UNCHANGED |
| `engine/simulink_bridge.py` | `e4f7399d…a577` | UNCHANGED |
| `scenarios/contract.py` | `77e67161…3c67` | UNCHANGED |
| `scenarios/config_simulink_base.py` | `cb737a4b…a9625` | UNCHANGED |
| `scenarios/kundur/model_profile.py` | `c4bc0870…c5499` | UNCHANGED |
| `scenarios/kundur/model_profiles/schema.json` | `0abf8970…3e65e` | UNCHANGED |
| `scenarios/kundur/model_profiles/kundur_ee_legacy.json` | `b092d8c0…0852` | UNCHANGED |
| `scenarios/kundur/model_profiles/kundur_sps_candidate.json` | `d7342209…203a` | UNCHANGED |
| `scenarios/kundur/config_simulink.py` | `66a9e5c0…8635` | UNCHANGED |

NE39 / legacy / shared / agents / reward / RL / Gate 3 path: untouched.
Default `KUNDUR_MODEL_PROFILE` still resolves to `kundur_ee_legacy` for
any caller that does not opt in via env var.

---

## What G3-prep-A does NOT touch

- `engine/simulink_bridge.py` — no `step_strategy` field added (that is G3-prep-B)
- `slx_helpers/vsg_bridge/*` — no new `.m` files added (that is G3-prep-C)
- NE39 anything — no read or write
- legacy Kundur (`kundur_vsg.slx`, `kundur_vsg_sps.slx`, `kundur_ee_legacy.json`,
  `kundur_sps_candidate.json`, `compute_kundur_powerflow.m`, etc.) — unchanged
- `model_profile.py` parser — unchanged; the new profile validates on the
  *existing* parser without code modification
- Reward / agent / SAC / hidden layers / SAC hyperparameters — untouched
- `config.py`, `config_simulink_base.py`, `scenarios/contract.py` — untouched
- `scenarios/kundur/config_simulink.py` — untouched (it already supports
  arbitrary profile selection via `KUNDUR_MODEL_PROFILE` env var)
- Gate 3 / SAC / RL / smoke — not entered, not invoked, not authorised

---

## git status / diff at this point

```
=== git status --short ===
?? quality_reports/gates/2026-04-26_kundur_cvs_g3prep_A_verdict.md
?? results/sim_ne39/runs/ne39_simulink_20260425_194644/  (gitignored, from D-pre)
?? scenarios/kundur/model_profiles/kundur_cvs.json

=== git diff --stat ===
(empty — all tracked files unchanged)

=== git log --oneline -5 ===
a12189e docs(cvs-gate3): NE39 + legacy baseline tripwire snapshot (G3-prep D-pre)
1143258 docs(cvs-gate3): add locked entry plan for SAC/RL prep
74428d7 feat(cvs-d4-rev): pass Gate 2 with paper-baseline damping metrics
255ab32 feat(cvs-d4): Gate 2 disturbance sweep — FAIL + diagnostic chain (D4/D4.1/D4.2)
307952e feat(cvs-d3): Gate 1 — 30s zero-action stability PASS
```

Two untracked files staged for the user's commit decision:
- `scenarios/kundur/model_profiles/kundur_cvs.json` (the artefact)
- `quality_reports/gates/2026-04-26_kundur_cvs_g3prep_A_verdict.md` (this verdict)

---

## Reproduction

```bash
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" -c "
import sys, os
sys.path.insert(0, os.getcwd())
from scenarios.kundur.model_profile import load_kundur_model_profile
p = load_kundur_model_profile('scenarios/kundur/model_profiles/kundur_cvs.json')
print(p)
"
```

Expected: `KundurModelProfile(scenario_id='kundur', profile_id='kundur_cvs',
model_name='kundur_cvs', solver_family='sps_phasor', pe_measurement='vi',
phase_command_mode='passthrough', warmup_mode='technical_reset_only',
feature_flags=KundurFeatureFlags(False, False, False))`.

---

## Next step (gated on user)

| Choice | Effect |
|---|---|
| **Commit A only** (this verdict + new JSON) | locks the profile in branch; nothing else changes; G3-prep-B/C/E still locked |
| Hold (no commit) | files stay on disk only; user can modify field values before commit |
| Skip A and discard | `git restore` the JSON + delete the verdict markdown |

No further action without explicit user authorisation. Gate 3 / SAC / RL
remain locked. G3-prep-B (bridge `step_strategy` field) and G3-prep-C
(new `.m` files) are NOT begun.
