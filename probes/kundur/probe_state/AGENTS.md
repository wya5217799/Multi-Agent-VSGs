# probe_state — AI Agent Guide

> **本文档 = AI agent 用**. 决策表 + 输出契约 + 硬性约束.
> 优化为 "read once → know what to run", 不需要 narrative inference.
>
> 同目录 sibling docs (边界严格不重叠):
> - `README.md` — design rationale / scope (designers; 不重复在此)
> - `USAGE.md` — operator workflow narrative (humans; 不重复在此)
>
> 本文不重复 sibling 内容: 不写 5-workflow 故事 (见 USAGE), 不解释
> 设计为什么这么做 (见 README).

---

## 1. Identity (read first)

```
package: probes.kundur.probe_state
role:    runtime ground-truth probe for Kundur CVS Simulink power model
output:  state_snapshot_<TS>.json + STATE_REPORT_<TS>.md +
         falsification gates G1..G6 verdicts
guards:  CLAUDE.md PAPER-ANCHOR HARD RULE (G1-G6 must all PASS before
         citing paper numbers / running PHI sweep / HPO)
read-only on: env/, engine/, evaluation/paper_eval.py, scenarios/kundur/
              (except --run-id flag in train_simulink.py)
write-allowed under: probes/kundur/probe_state/, tests/, results/harness/
                     kundur/probe_state/, results/sim_kundur/runs/probe_phase_c_*/,
                     quality_reports/
```

---

## 2. Pre-flight checks (run before any work)

```bash
PY="C:/Users/27443/miniconda3/envs/andes_env/python.exe"

# (1) Importable
$PY -c "from probes.kundur.probe_state import ModelStateProbe, __version__; print(__version__)"
# expect: "0.4.0" or higher

# (2) self-tests pass (no MATLAB)
$PY -m pytest tests/test_probe_internal.py -q
# expect: 33+ passed

# (3) latest snapshot exists (Type A invariants need it)
ls results/harness/kundur/probe_state/state_snapshot_latest.json
```

If any of (1)(2) fails → STOP. Probe package broken; do not run phases.

---

## 3. User-intent → command (decision table)

| User says (or means) | Command | wall |
|---|---|---|
| "verify model state / model unchanged" | `$PY -m probes.kundur.probe_state --phase 1,2,3,4 --sim-duration 3.0` | ~80 s |
| "build script changed, sanity check" | same as above | ~80 s |
| "IC JSON re-derived only" | `$PY -m probes.kundur.probe_state --phase 2 --no-mcp` | ~1 s |
| "is trained policy degenerate?" | `$PY -m probes.kundur.probe_state --phase 5 --phase-b-n-scenarios 5` | ~3-5 min |
| "is phi_f a causal driver?" smoke | `$PY -m probes.kundur.probe_state --phase 5,6 --phase-c-mode smoke` | ~5 min |
| "is phi_f a causal driver?" full (real signal) | `$PY -m probes.kundur.probe_state --phase 5,6 --phase-c-mode full --phase-b-n-scenarios 5 --phase-c-eval-n-scenarios 5` | ~50 min |
| "diff against last green baseline" | `$PY -m probes.kundur.probe_state --diff baseline latest` | < 1 s |
| "promote current as baseline" | `$PY -m probes.kundur.probe_state --promote-baseline <snapshot.json>` | < 1 s |
| "verify probe code itself" | `$PY -m pytest tests/test_state_invariants.py tests/test_probe_internal.py` | < 1 s |
| "what's the current verdict status" | `$PY -c "import json; d=json.load(open('results/harness/kundur/probe_state/state_snapshot_latest.json',encoding='utf-8')); g=d['falsification_gates']; print({k:v['verdict'] for k,v in g.items()})"` | < 1 s |

When user intent is ambiguous → ask 1 question; default to **Phase 1+2+3+4 sweep** (cheapest fact-gathering).

---

## 4. Snapshot contract (FACT layer — query these directly)

Path: `results/harness/kundur/probe_state/state_snapshot_latest.json`

```jsonc
{
  "schema_version": 1,                 // bump = data-format change
  "implementation_version": "0.4.0",   // bump = algorithm change
  "timestamp": "2026-05-01T...",
  "git_head": "<short sha>",
  "config": {
    "dispatch_magnitude_sys_pu": 0.5,  // probe-default; per-dispatch may override
    "sim_duration_s": 5.0,
  },
  "falsification_gates": {
    "G1_signal":         {"verdict": "PASS|REJECT|PENDING", "evidence": "<str>"},
    "G2_measurement":    {...},
    "G3_gradient":       {...},
    "G4_position":       {...},
    "G5_trace":          {...},
    "G6_trained_policy": {
      "verdict": "...",
      "scope":   "g6_partial_only" | "g6_complete",  // signals whether R1 layer present
      "g6_partial": {...},                            // Phase B sub-verdict (extras)
      "r1":         {...} | null,                     // Phase C sub-verdict (extras)
    },
  },
  "phase1_topology":     {...} | {"error": "..."},
  "phase2_nr_ic":        {...} | {"error": "..."},
  "phase3_open_loop":    {...} | {"error": "..."},
  "phase4_per_dispatch": {
    "dispatches": {
      "<dispatch_name>": {
        "max_abs_f_dev_hz_global": 0.121,
        "expected_min_df_hz":      0.30,    // historical floor
        "expected_max_df_hz":      1.0,     // historical ceiling (rare)
        "below_expected_floor":    true,    // ⚠️ diagnostic flag
        "above_expected_ceiling":  false,
        "floor_status":            "below_expected_floor",  // | "ok" | "above_expected_ceiling" | "expected_floor_unknown"
        "agents_responding_above_1mHz": 4,
        "metadata": {                       // 11 fields incl. historical_source
          "expected_min_df_hz": 0.30,
          "historical_source": "F4_V3_RETRAIN_FINAL_VERDICT.md (mean 0.65 Hz)",
          ...
        },
        ...
      },
      ...
    },
    ...
  },
  "phase5_trained_policy": {                // Phase B
    "runs": {
      "baseline":     {"r_f_global": -84.16, ...},
      "zero_agent_0": {...}, "zero_agent_1": {...}, ...,
      "zero_all":     {"r_f_global": -106.05, ...},
    },
    "ablation_diffs":     [-21.81, -43.76, -42.37, -24.73],
    "agent_contributes":  [true, true, true, true],
    "k_required_contributors": 2,
    ...
  },
  "phase6_causality": {                     // Phase C
    "mode": "smoke" | "full",
    "ablation_config": "no_rf",
    "no_rf_eval":   {"r_f_global": -91.06, ...} | null,
    "baseline_eval": {"r_f_global": -84.16, ...},
    "r1_verdict":   {"verdict": "PASS|REJECT|PENDING", "improvement_baseline_minus_no_rf": 6.90, ...},
    ...
  },
  "errors": [{"phase": "<name>", "error": "<msg>"}, ...],
}
```

`phase*.error` exists ⇒ that phase failed (fail-soft). Sub-verdicts unaffected.

---

## 5. Verdict semantics (state machine)

Each gate ∈ {`PASS`, `REJECT`, `PENDING`}. Routing rules:

```
Verdict       ⇒ AI next action
PASS          ⇒ green; consume the result
REJECT        ⇒ data is decisive but anomalous; show user the evidence
                 string and ASK before taking corrective action
PENDING       ⇒ data insufficient to decide; if user wanted that gate,
                 propose the missing phase command (decision table §3)
```

`G6.scope` field disambiguates Phase B vs Phase C composite:
- `"g6_partial_only"` ⇒ Phase 6 absent or errored; verdict = G6_partial
- `"g6_complete"`     ⇒ Phase 6 present; verdict = G6_partial AND R1

---

## 6. Hard constraints (NEVER violate)

```
NEVER edit:
  - env/                                (env code)
  - engine/                             (MATLAB session, bridge)
  - evaluation/paper_eval.py            (eval pipeline)
  - scenarios/kundur/*.py except train_simulink.py --run-id flag
  - results/sim_kundur/runs/kundur_simulink_*/  (production train artefacts)
  - results/harness/kundur/probe_state/baseline.json EXCEPT via
    --promote-baseline command

NEVER commit:
  - without an explicit user request ("commit" / "/commit" / "ship it")
  - to bypass git hooks (--no-verify forbidden unless explicitly authorised)
  - results/sim_kundur/runs/probe_phase_c_*/checkpoints/*.pt  (gitignored)
  - results/harness/kundur/probe_state/*.json                  (gitignored)

NEVER run Phase 6 full mode IF:
  - Production train is currently running (MATLAB engine exclusive)
  - G1-G5 not all fresh PASS in the latest paper-anchor-gate snapshot
    (CLAUDE.md PAPER-ANCHOR HARD RULE; Phase C plan §4)
  - Without explicit user authorisation (~10-50 min wall, MATLAB occupies)

NEVER fabricate verdict numbers; always cite snapshot path + timestamp.

NEVER bypass the THRESHOLDS singleton; do not set module-level
constants (e.g. G6_NOISE_THRESHOLD_SYS_PU_SQ = 5e-3) — edit
probe_config.ProbeThresholds and bump IMPLEMENTATION_VERSION instead.
```

---

## 7. Error / failure playbook

```
Symptom                                        ⇒ Action
─────────────────────────────────────────────────────────────────────────
"matlab.engine not available"                  ⇒ check andes_env path; pip install matlabengine
phase4 dispatches all error                    ⇒ MATLAB engine stuck or production train running;
                                                 retry once, then STOP and tell user
Phase 6 short-train: no best.pt produced       ⇒ smoke mode is plumbing-only; if full mode →
                                                 check results/.../training_log.json for NaN
G1 PENDING after --phase 5,6 alone             ⇒ expected: G1 needs phase4 data;
                                                 propose --phase 1,2,3,4 sweep
"--diff baseline latest" → FileNotFoundError   ⇒ run --promote-baseline once; default
                                                 baseline = the V1 full mode snapshot if available
Type A pytest FAIL                             ⇒ paper FACT broken (n_ess≠4 / phi_f≠100);
                                                 STOP; investigate build script changes
phase1 consistency_warnings present            ⇒ build naming convention drifted;
                                                 read the warning, update _discover.py if needed
implementation_version mismatch in --diff      ⇒ probe algorithm bumped; verdict numbers
                                                 across versions need CHANGELOG context
                                                 (probe_config.py docstring)
```

---

## 8. Cross-snapshot paper-anchor unlock

CLAUDE.md HARD RULE wants G1-G6 all PASS, but they may live in
**different snapshots**:

```
Required:
  - G1-G5 PASS in some "paper-anchor gate" snapshot < 7 day age
    (typically from --phase 1,2,3,4 run)
  - G6 PASS in a "Phase 5+6 full" snapshot < 7 day age
    (from --phase 5,6 --phase-c-mode full run)

Verification recipe:
  1. find paper-anchor snapshot:
       grep paper-anchor verdict in quality_reports/phase_C_R1_verdict_*.md
       (most recent verdict markdown is canonical)
  2. confirm both age stamps (json field "timestamp") within 7 days of NOW
  3. if either snapshot is stale → re-run; do not unlock anchor based
     on stale verdict
```

---

## 9. Configuration sources (single-source-of-truth chain)

```
runtime values             ← read from
─────────────────────────────────────────────────────────────────────────
n_ess / n_sg / n_wind      ← scenarios/kundur/kundur_ic_cvs_v3.json
                             (NOT contract.py; NOT hardcoded)
dispatch types (22)        ← scenarios.kundur.disturbance_protocols.
                             known_disturbance_types()
dispatch metadata          ← probes.kundur.probe_state.dispatch_metadata.
                             METADATA  (cross-validated via
                             coverage_check())
PHI_F / PHI_H / PHI_D      ← scenarios.kundur.config_simulink.PHI_*
                             (env-var override: KUNDUR_PHI_F=0)
Probe thresholds           ← probes.kundur.probe_state.probe_config.
                             THRESHOLDS  (dataclass instance)
Implementation version     ← same module ::IMPLEMENTATION_VERSION
                             (== package __version__)
Schema version             ← probes.kundur.probe_state.probe_state.
                             SCHEMA_VERSION  (= 1, do not bump w/o
                             migration)
Checkpoint discovery       ← probes.kundur.probe_state._trained_policy.
                             _discover_checkpoint()  (priority:
                             CLI override > KUNDUR_PROBE_CHECKPOINT
                             ENV > auto-search results/)
```

---

## 10. Common AI mis-reads (avoid)

```
Mis-read 1: G6 PENDING means "broken"
  Reality: PENDING = data insufficient (e.g. R1 train didn't converge).
  Phase B PASS evidence preserved in g6_partial extras field.

Mis-read 2: dispatch with high max|Δf| is good
  Reality: above_expected_ceiling can flag runaway divergence (damping
  collapse). Always check floor_status, not just the raw number.

Mis-read 3: --no-mcp means "skip everything risky"
  Reality: --no-mcp drops phases 1/3/4/5/6 (any MATLAB-touching phase);
  keeps phase 2 + verdict + report. Useful for quick file-IO sanity
  but does not validate the model.

Mis-read 4: best.pt under any results/ dir is acceptable
  Reality: _is_v3_compatible heuristic accepts paths containing
  "kundur_simulink" / "cvs_v3" / "kundur_cvs". A v2 archive could
  match. paper_eval will fail on obs_dim mismatch — surface that as
  the actionable error.

Mis-read 5: snapshot_latest.json is always the most recent run
  Reality: it's a copy alias. Manually overwriting it (e.g. by running
  --no-mcp after a full run) replaces the V1 full-mode results in the
  alias. Use timestamped paths when correctness matters; restore
  latest from a timestamped snap if needed.

Mis-read 6: pytest SKIP = test failed
  Reality: SKIP is by design when phase data absent (Type B fail-soft).
  Only Type A FAIL is actionable; Type B SKIP is normal until phase
  data is populated.
```

---

## 11. Self-update protocol

When you (AI) make changes to `probes/kundur/probe_state/`:

1. Run `tests/test_probe_internal.py` (must stay green; mock-only).
2. If verdict logic changed → bump
   `probe_config.IMPLEMENTATION_VERSION` minor; CHANGELOG note in
   the same module's docstring.
3. If snapshot field shape changed → bump `SCHEMA_VERSION` and
   document migration; `--diff` will [WARN] on cross-version reads.
4. Update `USAGE.md` if user-facing CLI / behaviour changed.
5. Update this `AGENTS.md` only if AI-decision rules changed.
6. ASK before commit; "1 commit" or "ship it" needed in user message.

---

## 12. Quick sanity (one-shot)

```bash
$PY -c "
import json
d = json.load(open('results/harness/kundur/probe_state/state_snapshot_latest.json', encoding='utf-8'))
g = d.get('falsification_gates', {})
print('schema:', d.get('schema_version'), '/ impl:', d.get('implementation_version'))
print('git_head:', d.get('git_head'))
for name in ('G1_signal','G2_measurement','G3_gradient','G4_position','G5_trace','G6_trained_policy'):
    v = g.get(name, {})
    print(f'  {name:24s} {v.get(\"verdict\",\"?\"):10s} {v.get(\"evidence\",\"\")[:80]}')
"
```

Use this to take a snapshot's pulse before deciding any action.

---

*end — design ref: docs/design/probe_state_design.md*
