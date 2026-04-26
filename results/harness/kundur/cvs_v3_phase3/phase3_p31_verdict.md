# Phase 3.1 Verdict — Add v3 Model Profile JSON

> **Status: PASS — `kundur_cvs_v3.json` created, loader-validated, asset-existence-confirmed, identity-audit-clean.**
> **Date:** 2026-04-26
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase3_plan.md) §P3.1

---

## 1. Deliverable

[`scenarios/kundur/model_profiles/kundur_cvs_v3.json`](../../../../scenarios/kundur/model_profiles/kundur_cvs_v3.json) (NEW, 13 lines):

```jsonc
{
  "scenario_id":         "kundur",
  "profile_id":          "kundur_cvs_v3",
  "model_name":          "kundur_cvs_v3",
  "solver_family":       "sps_phasor",
  "pe_measurement":      "vi",
  "phase_command_mode":  "passthrough",
  "warmup_mode":         "technical_reset_only",
  "feature_flags": {
    "allow_pref_ramp":              false,
    "allow_simscape_solver_config": false,
    "allow_feedback_only_pe_chain": false
  }
}
```

Schema mirrors v2 [`kundur_cvs.json`](../../../../scenarios/kundur/model_profiles/kundur_cvs.json) exactly. Differs only in `profile_id` and `model_name` (both `kundur_cvs_v3`).

---

## 2. Validation results

### 2.1 Loader parse

`scenarios.kundur.model_profile.load_kundur_model_profile(<path>)` returns:

| Field | Value |
|---|---|
| profile_id | `kundur_cvs_v3` |
| model_name | `kundur_cvs_v3` |
| scenario_id | `kundur` |
| solver_family | `sps_phasor` (valid enum) |
| pe_measurement | `vi` (valid enum) |
| phase_command_mode | `passthrough` |
| warmup_mode | `technical_reset_only` |
| feature_flags | all three `False` |

✅ All required fields present; both enums valid; FrozenFlags dataclass populated.

### 2.2 Asset existence (5/5 ✅)

| Key | Path | exists | size (bytes) |
|---|---|---|---|
| slx       | `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` | ✅ | 481 262 |
| runtime   | `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat` | ✅ | 2 212 |
| build     | `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` | ✅ | 37 950 |
| ic_json   | `scenarios/kundur/kundur_ic_cvs_v3.json` | ✅ | 5 472 |
| nr_script | `scenarios/kundur/matlab_scripts/compute_kundur_cvs_v3_powerflow.m` | ✅ | 23 814 |

The bridge / config layer resolves the `.slx` from `model_name` + `model_dir`; `.mat` is loaded via the existing build sidecar mechanism. Profile JSON itself does not embed asset paths (those live in `config_simulink.py` dispatch + `build_kundur_cvs_v3.m`), so identity routing is sufficient for asset wiring.

### 2.3 Identity audit (no v2 / NE39 / SPS / legacy collision)

`profile.model_name = 'kundur_cvs_v3'` — confirmed NOT in forbidden set `{kundur_cvs, kundur_vsg, kundur_sps_candidate, kundur_ee_legacy}`. ✅

JSON content scan for forbidden tags `{kundur_vsg, ne39, new_england, legacy, sps_candidate}`: none found. ✅

`profile_id` matches `model_name` (both `kundur_cvs_v3`); same convention as v2 profile.

**ALL_PASS = 1.**

---

## 3. Boundary respected (this turn)

| Item | Status |
|---|---|
| `scenarios/kundur/model_profiles/kundur_cvs_v3.json` | **NEW (only file written)** |
| Other model_profiles (`kundur_cvs.json`, `kundur_ee_legacy.json`, `kundur_sps_candidate.json`, `schema.json`) | **untouched** |
| `compute_kundur_cvs_v3_powerflow.m` / `kundur_ic_cvs_v3.json` | **untouched** since Phase 1 commit `a40adc5` |
| `build_kundur_cvs_v3.m` / `kundur_cvs_v3.slx` / `_runtime.mat` | **untouched** since P3.0b/c commit `cbc5dda` |
| `engine/simulink_bridge.py` | **untouched** |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | **untouched** |
| `env/simulink/kundur_simulink_env.py` | **untouched** |
| `scenarios/kundur/config_simulink.py` | **untouched** (dispatch ladder edit deferred to P3.2) |
| `scenarios/kundur/train_simulink.py` | **untouched** |
| `scenarios/contract.py`, `scenarios/config_simulink_base.py`, `agents/`, `utils/` | **untouched** |
| Topology / IC / NR / dispatch / V_spec / line per-km params / disturbance physics / reward / SAC / training | **untouched** |
| v2 / NE39 | **untouched** |

No build, no MATLAB call, no smoke. Validation used only Python loader + filesystem `Path.is_file()` + JSON tag scan.

---

## 4. Files emitted

```
scenarios/kundur/model_profiles/kundur_cvs_v3.json     (NEW — only file written)
results/harness/kundur/cvs_v3_phase3/phase3_p31_verdict.md  (this file)
```

---

## 5. Halt — request user GO for P3.2

P3.1 done in scope. The new profile is loadable and identity-clean but **NOT yet wired** — `config_simulink.py` still has `if model_name == 'kundur_cvs'` branch only; loading `kundur_cvs_v3.json` via env var would currently fall through to the `else` branch (v2-base IC, wrong Pm0 / delta0).

P3.2 will extend the dispatch ladder + BridgeConfig ternaries. Awaiting GO.
