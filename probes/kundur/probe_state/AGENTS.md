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

### Parallel Mode Decision Table (P2 — 2026-05-03)

When to use `--workers` (N ≥ 2):

| Decision point | Use serial (`--workers 1`, default) | Use parallel (`--workers N` ≥ 2) |
|---|---|---|
| **Wall time pressure** | Quick single-phase (Phase 2 only) or fresh-model sanity | Phase 4 dispatch sweep; want ≤ 1192s @ N=4 |
| **License availability** | Default setup; no explicit 4-engine testing | Pre-flight smoke: `python probes/kundur/spike/test_y4_license_smoke.py 4` PASS |
| **Phase scope** | Any phase 5/6 run | Phase 1-4 only (M5: phases 5/6 incompatible with parallel) |
| **Snapshot consumption** | Any downstream (`_diff`, `_report`) — no change | Same interface; merge produces identical schema |

**Output contract** (identical in both modes):
- Canonical merged snapshot: `results/harness/kundur/probe_state/state_snapshot_<TS>.json`
  + `state_snapshot_latest.json` alias.
- Per-worker auxiliary: `results/harness/kundur/probe_state/p2_worker_<n>/state_snapshot_*.json`
  (audit trail only; not consumed by downstream tools).
- Verdict interface via `falsification_gates` — no change (M5).

**Hard rules** (from spec §3 + engineering_philosophy.md §6):
- GATE-PHYS @ 1e-9: per-dispatch `max_abs_f_dev_hz_global` identical serial ↔ parallel.
- GATE-G15 verdict-for-verdict: G1-G5 verdicts PASS↔PASS across serial/parallel (no flips).
- Production path untouched: `grep workers scenarios/kundur/train_simulink.py` = 0.
- Phase 5/6: CLI rejects `--workers > 1 --phase 5` | `--workers > 1 --phase 6`
  (SystemExit with explicit message).

**Failure modes**:
- Worker exit_code=1: MATLAB engine failed (license or init error); check
  `p2_worker_<n>/probe.log`.
- Worker exit_code=2: sim crash on assigned dispatch; check per-worker log +
  dispatch name in `parallel_metadata.dropped_dispatches`.
- Worker exit_code=3: output write error; check disk space + permissions.
- Merge `dropped_dispatches` non-empty: workers crashed; investigate per-worker
  logs before re-running.

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

Each gate ∈ {`PASS`, `REJECT`, `PENDING`, `ERROR`}. Every gate verdict
dict also carries `reason_codes: list[str]` drawn from the frozen
vocabulary in `probe_config.REASON_CODES`. Routing rules:

```
Verdict   ⇒ AI next action
PASS      ⇒ green; consume the result
REJECT    ⇒ data is decisive but anomalous; show user the evidence string
              + reason_codes and ASK before taking corrective action
PENDING   ⇒ data insufficient to decide; re-running the missing phase
              would resolve. Propose the relevant command from §3.
              Reason codes: MISSING_PHASE / MISSING_FIELD / EMPTY_DATA /
              INSUFFICIENT_DISPATCHES / BASELINE_MISMATCH / SCHEMA_DRIFT.
ERROR     ⇒ pipeline failure (a phase threw / subprocess crashed). Re-
              running alone will NOT self-heal — diagnose the underlying
              code or environment first. Reason codes: PHASE_ERRORED /
              TRAIN_FAILED / EVAL_FAILED.
```

PENDING vs ERROR is the v0.5.0 contract distinction: PENDING is
recoverable by data, ERROR requires code/env investigation. Old (pre-
0.5.0) snapshots that lacked this distinction surfaced ERROR conditions
as PENDING; the cross-version `--diff` will WARN on impl_version
mismatch.

`G6.scope` field disambiguates Phase B vs Phase C composite:
- `"g6_partial_only"` ⇒ Phase 6 absent; verdict = G6_partial
- `"g6_complete"`     ⇒ Phase 6 present (or errored); verdict combines
                        G6_partial AND R1 (or surfaces phase6 ERROR with
                        partial preserved in the `g6_partial` extras).

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
gate verdict = ERROR (any)                     ⇒ inspect reason_codes:
                                                  - PHASE_ERRORED ⇒ read snapshot.<phase>.error;
                                                                     fix code/env; re-run
                                                  - TRAIN_FAILED  ⇒ check results/.../training_log.json
                                                                     for NaN / low convergence
                                                  - EVAL_FAILED   ⇒ check evaluation/paper_eval.py
                                                                     stderr; verify schema
                                                 NEVER treat ERROR as PENDING — re-running alone
                                                 will not self-heal.
gate verdict = PENDING (any)                   ⇒ inspect reason_codes:
                                                  - MISSING_PHASE         ⇒ propose phase command
                                                  - MISSING_FIELD         ⇒ phase data drift; check
                                                                            _dynamics.py / _trained_policy.py
                                                  - EMPTY_DATA            ⇒ same; data emission gap
                                                  - INSUFFICIENT_DISPATCHES ⇒ run more dispatches
                                                  - BASELINE_MISMATCH     ⇒ re-run Phase B with
                                                                            scenario_set='none' n=eval_n
                                                  - SCHEMA_DRIFT          ⇒ paper_eval JSON shape changed
phase4 dispatches all error                    ⇒ MATLAB engine stuck or production train running;
                                                 retry once, then STOP and tell user
Phase 6 short-train: no best.pt produced       ⇒ smoke mode is plumbing-only; if full mode →
                                                 check results/.../training_log.json for NaN
G1 PENDING after --phase 5,6 alone             ⇒ expected: G1 needs phase4 data;
                                                 reason_codes=['MISSING_PHASE'];
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

## 8. (removed in v0.5.0) Anchor-unlock judgments

Earlier versions of this guide carried a "cross-snapshot paper-anchor
unlock recipe" here. **Removed in v0.5.0.** The probe collects facts
(verdicts + reason_codes + evidence + timestamps); deciding whether
the project may cite paper numbers / run PHI sweep / unlock anchor is
the **calling agent's** judgment, not the probe's. The probe does not
encode freshness rules, multi-snapshot composition, or any "if all
PASS then green-light X" automation.

If you are deciding anchor unlock, read the latest snapshot's
`falsification_gates`, the per-gate `timestamp` (the snapshot's
top-level field; phases are not separately timestamped), and the
relevant `reason_codes` — then make the call yourself with the user.

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
Mis-read 1: G6 PENDING means "broken" / G6 ERROR means "wait for more data"
  Reality (v0.5.0): PENDING = data insufficient — re-running the
  relevant phase resolves it. ERROR = pipeline failure (phase threw,
  subprocess crashed) — re-running alone will NOT fix it; diagnose code
  or env first. Phase B PASS evidence is preserved in g6_partial extras
  even when phase6 is in ERROR. Read reason_codes to disambiguate
  (PHASE_ERRORED / TRAIN_FAILED / EVAL_FAILED ⇒ ERROR; MISSING_*  /
  EMPTY_DATA / INSUFFICIENT_DISPATCHES ⇒ PENDING).

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
7. Run the **commit-time self-audit** below (§11a) and paste the
   resulting block into the commit message body before committing.

---

## 11a. Commit-time self-audit (MANDATORY)

**Trigger**: any commit whose `git diff --name-only HEAD` touches one
or more of:

```
probes/kundur/probe_state/_verdict.py        (verdict logic)
probes/kundur/probe_state/_trained_policy.py (Phase B + metrics extraction)
probes/kundur/probe_state/_causality.py      (Phase C + R1 + baseline resolution)
probes/kundur/probe_state/_dynamics.py       (Phase 3+4 + reconcile)
probes/kundur/probe_state/_discover.py       (Phase 1 schema)
probes/kundur/probe_state/_nr_ic.py          (Phase 2 schema)
probes/kundur/probe_state/_report.py         (snapshot serialisation)
probes/kundur/probe_state/probe_state.py     (snapshot top-level shape)
probes/kundur/probe_state/probe_config.py    (thresholds / version)
probes/kundur/probe_state/dispatch_metadata.py (DispatchMetadata schema / floors)
```

(Touching only `__init__.py`, `__main__.py` CLI plumbing, `_diff.py`,
`README.md`, `USAGE.md`, `AGENTS.md`, or `tests/` does NOT trigger
the audit unless one of the above co-changes.)

### The 5 audit questions

For every triggering commit, write the answer block into the commit
message **body** (one line each, exact key names):

```
impl-version-impact:      yes | no
schema-version-impact:    yes | no
verdict-semantics-impact: yes | no
threshold-default-impact: yes | no
silent-error-path-impact: yes | no
```

Question definitions (use these exact rules; do not re-interpret):

1. **`impl-version-impact: yes`** if the commit changes any code path
   that produces verdict numbers, verdict strings, or evidence
   strings, OR changes a default value in
   `probe_config.ProbeThresholds`. A "bug fix" that changes what
   verdict the probe emits for the same input data IS an
   impl-version-impact (this is the 1a86de2 / 9825e85 case).

2. **`schema-version-impact: yes`** if the commit renames, removes,
   or repurposes a snapshot JSON field. **Additive** new fields
   inside the existing `schema_version=1` envelope are allowed and
   answer `no`; document them in the CHANGELOG anyway.

3. **`verdict-semantics-impact: yes`** if running the same input
   through pre-commit code vs post-commit code can produce a
   different `verdict` ∈ {PASS, REJECT, PENDING} for any G1..G6
   gate or R1 sub-verdict. Includes "widened PENDING coverage on
   previously-silent error paths".

4. **`threshold-default-impact: yes`** if any field on
   `ProbeThresholds` (or any per-dispatch `expected_min_df_hz` /
   `expected_max_df_hz`) gains a different default than before.
   Pure additive new fields with `default=None` answer `no`.

5. **`silent-error-path-impact: yes`** if the commit converts a
   silent fallback (`get(..., 0.0)`, `try: ... except: pass`,
   missing-key default) into either an error payload, a PENDING
   verdict, or a logger.warning that downstream consumers will see.
   This is the P2a-class fix.

### Action mapping

```
Any answer = yes ⇒ MUST also do (in the same commit):
  impl-version-impact      → bump probe_config.IMPLEMENTATION_VERSION
                             (patch for bug fix; minor for new behaviour;
                             major for incompatible algorithm change)
                             AND add a CHANGELOG entry
  schema-version-impact    → bump SCHEMA_VERSION AND document migration
                             AND add a CHANGELOG entry
  verdict-semantics-impact → impl-version-impact must also be yes
                             (verdict semantics is a strict subset of
                             impl semantics)
  threshold-default-impact → impl-version-impact must also be yes
                             AND name the field in the CHANGELOG entry
  silent-error-path-impact → impl-version-impact must also be yes
                             (this was the meta-mistake in 1a86de2;
                             do not repeat)

All answers = no ⇒ commit message body explicitly states
                   "internal cleanup, no verdict semantics change"
                   so the no-bump decision is auditable.
```

### Enforcement

- **Reviewer gate**: any external review SHOULD reject a commit on
  triggering files that lacks the audit block, regardless of
  perceived correctness.
- **Self-check before commit**: AI agents MUST run the audit
  mentally and paste the block; committing without the block on a
  triggering file is a process violation.
- **No pre-commit hook yet**: the audit is doc-enforced for now;
  upgrade to a hook if compliance drifts.

### Worked example (from real history)

Commit `1a86de2` was the meta-correction that this audit exists to
prevent. The triggering commit (`9825e85`, P1/P2/P3 batch) should
have carried:

```
impl-version-impact:      yes
schema-version-impact:    no
verdict-semantics-impact: yes
threshold-default-impact: no
silent-error-path-impact: yes

(P1: R1 mismatch path now emits PENDING instead of PASS/REJECT;
 P2a: schema-drift path now emits error instead of r_f_global=0.0.
 Both are silent-error-path widenings; both are
 verdict-semantics-impact; both require impl-version bump per
 README §"Versioning". Bumping IMPLEMENTATION_VERSION 0.4.0 -> 0.4.1
 + CHANGELOG entry in this commit.)
```

Had `9825e85` carried this block, `1a86de2` would not have been
needed — the audit would have forced the version bump in-line.

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
