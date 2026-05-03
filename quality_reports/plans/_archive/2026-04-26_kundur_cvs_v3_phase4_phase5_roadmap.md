# Kundur CVS v3 — Phase 4 & Phase 5 Optimization Roadmap (DRAFT)

> **Status:** PLAN ONLY — no code changes, no training, no model edits.
> **Date:** 2026-04-26
> **Predecessor:** Phase 3 cleared at commit `a5bc173` (P3.4 5-ep smoke PASS).
> **Reference docs:**
> - [`docs/paper/yang2023-fact-base.md`](../../docs/paper/yang2023-fact-base.md)
> - [`docs/paper/v3_paper_alignment_audit.md`](../../docs/paper/v3_paper_alignment_audit.md)
> - [`quality_reports/plans/2026-04-26_kundur_cvs_v3_plan.md`](2026-04-26_kundur_cvs_v3_plan.md)
> - [`quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md`](2026-04-26_cvs_v3_topology_spec.md)
> - [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_plan.md`](2026-04-26_kundur_cvs_v3_phase4_plan.md) (skeleton; this doc supersedes its mid/late content)

---

## 0. Scope and hard non-goals

**Scope of this roadmap:** Phase 4 (RL gate, ≤ 50 ep per run) → Phase 5 (paper-replication gate, up to 2000 ep per locked config). Both phases are pre-launch staging.

**Hard non-goals across both phases (locked unless an explicit user-authorized gate-revision):**

- Do NOT touch `scenarios/new_england/` or `env/simulink/ne39_simulink_env.py`.
- Do NOT touch `env/andes/`, `env/ode/`, or any legacy ANDES / ODE path.
- Do NOT touch v2 (`kundur_cvs.slx`, `kundur_ic_cvs.json`, `build_kundur_cvs.m`, `compute_kundur_cvs_powerflow.m`, `model_profiles/kundur_cvs.json`, `kundur_cvs_runtime.mat`).
- Do NOT touch legacy SPS path (`kundur_vsg.slx`, `build_powerlib_kundur.m`, `model_profiles/kundur_sps_candidate.json`).
- Do NOT touch v3 NR / IC / build / `.slx` / `_runtime.mat` (locked at fix-A2 / R-h1 commits `cbc5dda` + `a5bc173`).
- Do NOT touch `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py` SAC base hyper.
- Do NOT touch the shared bridge (`engine/simulink_bridge.py`) or shared CVS helpers (`slx_helpers/vsg_bridge/slx_step_and_read_cvs.m`, `slx_episode_warmup_cvs.m`).
- Do NOT launch 2000-episode training in Phase 4. Phase 5 launches it only after explicit user GO based on Phase 4 verdicts.
- Do NOT touch the currently-running NE39 500-ep training session.

Any deviation = STOP and request user authorization.

---

## 1. Gap-by-gap analysis (the 6 gaps the user named)

For each gap: **target → modification surface → risk → validation → pass criteria → priority → schedule**.

### Gap 1 — Disturbance form: switch single-VSG Pm-step → bus-localised LoadStep7 / LoadStep9 (D5)

**Why this matters for paper alignment:**
Paper Sec.IV-C names the canonical scenarios "load step 1 / 2" and reports −1.61 / −0.80 (no-control) and −0.68 / −0.52 (DDIC) per-episode rewards. To benchmark against those numbers, v3 must apply load-step disturbances at **Bus 7 / Bus 9** (the actual paper buses), not on a VSG terminal. Phase 2.3-L1 already proved LoadStep7/9 produce a measurable transient (Bus 7: 110 mHz @ 500 MW; Bus 9: 21 mHz @ 967 MW; both linear-scaling and source-localised).

**Target:** route training-time disturbances through the existing `LoadStep7` / `LoadStep9` blocks (built into v3 .slx, currently disabled with `Resistance = 1e9` placeholder).

**Modification surface (REVISED 2026-04-27 per critic round-2: LoadStep workspace path is provably DEAD; switch default to Pm-step proxy):**

**Codebase reality check (verified by reading sources):**
- `build_kundur_cvs_v3.m:200-205` does `assignin('base', 'G_perturb_<k>_S', 0.0)` etc. — workspace vars are **created** ✓
- `build_kundur_cvs_v3.m:316-336` sets `LoadStep7/9 BranchType='R', Resistance='1e9'` — **HARDCODED**, no workspace expression
- **No Constant block, no Gain block, no gating cluster references `G_perturb_*`, `LoadStep_t_*`, or `LoadStep_amp_*`** anywhere in the build
- The workspace vars float unused. The "existing workspace-variable mechanism" assumed in the round-1 revision **does not exist in code**

**Three execution paths — pre-committed default + two upgrade options:**

| Path | What | Allow-list? | Paper-faithful? | Gap 1 default? |
|---|---|---|---|---|
| **(C-default) Pm-step proxy** | route LoadStep-equivalent disturbance through Pm-step on the ESS electrically nearest to Bus 7 / Bus 9 (ES1 for Bus 7; ES4 for Bus 9 per P2.3-L1). Use existing `bridge.apply_workspace_var(...)` on `Pm_step_t_<i>` / `Pm_step_amp_<i>` | ✅ env + config edit only | ⚠️ paper-form-divergent (paper applies load step at the load bus, not VSG terminal) but P2.3-L1 already showed ES1/ES4 are the nearest swing-eq sources whose ω deviation responds to a LoadStep at Bus 7/9 | **YES — default for P4.1** |
| (A-upgrade) build-side LoadStep wiring | rebuild `kundur_cvs_v3.slx` so `LoadStep7/9 Resistance` references a workspace expression (`'1/G_perturb_1_S'` or similar); add a gating cluster that toggles via `LoadStep_t_<k>` / `LoadStep_amp_<k>` | ❌ build edit (requires explicit scope-expansion authorization, breaking the §0 lock on `build_kundur_cvs_v3.m`) | ✅ paper-faithful | optional — Phase 5 if (C) is insufficient |
| (B-upgrade) helper / bridge edit | add a `set_param` primitive in shared helper or bridge to flip `Resistance` mid-episode | ❌ helper / bridge edit (forbidden) | ✅ if it works | NOT pursued |

**Concrete changes for Gap 1 default path (C):**
- `env/simulink/kundur_simulink_env.py::_apply_disturbance_backend` — extend the existing `kundur_cvs_v3` branch (line 699) to accept a `disturbance_type` arg. New disturbance types:
  - `pm_step_single_vsg` (current B1 default; preserve for backward compat)
  - `pm_step_proxy_bus7` (NEW, paper-form-via-proxy: target = ES1 Pm-step; magnitude scaled to match a Bus-7 LoadStep of equivalent ΔP)
  - `pm_step_proxy_bus9` (NEW, target = ES4 Pm-step)
  - `pm_step_proxy_random_bus` (NEW, randomly picks Bus 7 / Bus 9 each episode)
- `scenarios/kundur/config_simulink.py` — add `KUNDUR_DISTURBANCE_TYPE` constant (NEW; verified does not exist by `grep -n 'disturbance_type\|KUNDUR_DISTURBANCE' scenarios/kundur/`). Default for Phase 4 = `pm_step_proxy_random_bus`.
- `engine/simulink_bridge.py` — **untouched** ✓
- `build_kundur_cvs_v3.m` — **untouched** ✓
- `kundur_cvs_v3.slx` / `_runtime.mat` — **untouched** ✓

**Path (A) trigger condition:** if Phase 4.2 PHI sweep cannot produce a r_f signal on the proxy because ES1/ES4 Pm-step is electrically too distant from the disturbance target (P2.3-L1 showed Bus 7 → ES1 transient at 22 mHz/100 MW, which is sufficient — but if PHI sweep evidence shows the proxy's r_f is < 1 % even at saturation), Phase 5 may revisit Path (A) under explicit user authorization.

**Risks:**
- R-G1-1: `set_param` mid-sim under FastRestart may not propagate to the running solver until next compile. **Mitigation:** P2.3 confirmed `set_param` between sims works; inside a single sim, paper expectation is that the step happens at episode start (t=0) anyway. So per-episode topology change is sufficient — we set R **before** the warmup sim, not mid-sim within it.
- R-G1-2: Bus 9 stiff-network behavior (P2.3-L1 showed 10× lower df_peak than Bus 7) will require the agent to sense smaller frequency excursions when Bus 9 is the disturbance target. **Mitigation:** sample Bus 7 / Bus 9 disturbances 50/50 in training so the agent sees both regimes; gate-pass requires the agent to learn under both.
- R-G1-3: Paper magnitude for "load step 1 / 2" may not be 100 MW step but a specific MW value not given in fact-base. **Mitigation:** initially sweep ΔP ∈ {100, 200, 500} MW for Bus 7 and {200, 500, 967} MW for Bus 9 (Bus 9 needs higher because of stiffness); pick the magnitude that recovers paper's −1.61 / −0.80 baseline reward range.

**Validation method (probe-only, no training):**
- New probe `probes/kundur/v3_dryrun/probe_loadstep_disturbance_routing.py` that constructs `KundurSimulinkEnv` with v3 profile, calls `apply_disturbance(disturbance_type='load_step_random_bus')`, runs 1 episode, asserts: (a) per-step `info['max_freq_dev_hz'] > 0`, (b) per-step `r_f` non-zero across at least 80 % of post-disturbance steps, (c) no `tds_failed`, (d) `set_param` reaches MATLAB (verifiable by reading back R).

**Pass criteria for switching the default:** the new probe PASS + a 50-ep gate run (Phase 4.1) under the new default produces `r_f%` ∈ [3, 30 %] (Phase 4 gate criterion 3).

**Priority: P0 — paper-replication MUST.** Without this, Phase 5 paper-baseline comparison is not directly comparable to paper Table 1.

**Schedule:** Phase 4.1 — first gate run after the routing probe passes.

---

### Gap 2 — Reward weights: PHI_H / PHI_D sweep (D4)

**Why this matters:**
v3 currently runs `PHI_H = PHI_D = 1e-4` (B1 baseline locked at `de5a11c`) — 4 orders of magnitude below paper's `1.0`. The override is correct in principle (paper's H dimensionality differs from v3's; Q7 unresolved), but `1e-4` was tuned for a pre-fix-A2 v3 with different physics. After fix-A2 + R-h1 the operating point is different — the same weights may now over- or under-suppress action penalties. P2.5c found H is the primary action lever and D is secondary, so symmetric `(1e-4, 1e-4)` is also questionable.

**Target:** find `(PHI_H, PHI_D)` such that `r_f%` ≈ 5 % over the last 25 episodes (paper §IV-B implication; range [3, 30 %] gates pass).

**Modification surface:**
- `scenarios/kundur/config_simulink.py:93-94` (the two `PHI_H` / `PHI_D` lines).
- Optionally a new override mechanism (env var) so Phase 4 sweep can run without per-run config edits — or use distinct config snapshots per sweep candidate. Probe-orchestrator-decided.

**Risks:**
- R-G2-1: too-low PHI_H/PHI_D → agent free-rides on H/D actions, large `Δ` values that violate paper "stay near baseline" intent. **Mitigation:** include `mean(|ΔM|)` and `mean(|ΔD|)` in gate metrics; bounds [|ΔM_avg| < 3 (= half of action range), |ΔD_avg| < 3].
- R-G2-2: too-high PHI_H/PHI_D → r_f drowned, learning signal vanishes (currently observed at paper 1.0). **Mitigation:** `r_f%` floor 3 % gate.
- R-G2-3: asymmetric (PHI_H > PHI_D) might be warranted per P2.5c, but if D-axis is so weak that D becomes a free action even at PHI_D=1e-3, agent might exploit. **Mitigation:** monitor D action distribution per ep; flag if D collapses to a single value.

**Validation method:** sequential 50-ep runs per candidate, each writing `<phi_tag>_50ep_summary.json` with the metrics in §3.

**Sweep candidates (proposed; initial 3, expand only if all 3 fail):**

| Run tag | PHI_H | PHI_D | Rationale |
|---|---|---|---|
| `phi_b1` | 1e-4 | 1e-4 | regression check vs current Kundur v3 baseline; confirms r_f signal exists post-fix-A2 |
| `phi_asym_a` | 1e-3 | 1e-4 | P2.5c-recommended asymmetric (H lever 10× weighted) |
| `phi_paper_scaled` | 1e-2 | 1e-2 | symmetric, factor-100 above B1 — closer to paper 1.0 in spirit; confirms whether the issue is symmetry or absolute magnitude |
| `phi_asym_b` | 1e-2 | 1e-3 | (only if `phi_asym_a` r_f% too low) — same H:D ratio, larger absolute |
| `phi_paper` | 1.0 | 1.0 | (only if everything else passes — sanity check that paper's literal weights still kill learning on v3) |

**Stopping rule (REVISED 2026-04-27 round-2):** the first run whose r_f% over the last 25 ep is **inside the Phase 4 gate criterion 3 band [3 %, 30 %]** AND all other 50-ep gate criteria green is the v3 default for Phase 5. Within the band, prefer the candidate closest to the **5 % target midpoint**.

**Sweep runs under the Gap 1 default disturbance type** = `pm_step_proxy_random_bus` (Path C). Do NOT switch disturbance type mid-sweep.

**All-fail exit rule (NEW):**
- If 5 candidates fail to land r_f% in [3 %, 30 %], **halt Phase 4** and produce a `phase4_exit_diagnostic.md` documenting:
  1. The r_f% measured per candidate (table)
  2. Whether r_f% trends low (saturation by H/D penalty) or high (insufficient H/D constraint)
  3. Whether action distribution shows boundary pinning (criterion 5)
  4. A short hypothesis on Q7 / Q2 mapping
- The exit diagnostic ends with a **user decision request**: (a) try a path-A scope expansion (LoadStep build edit + DIST raise per § 3.3) and re-sweep, (b) revisit Q7 (paper-side ambiguity, may require offline analysis or co-author contact), (c) accept Phase 4 as NO-GO and skip directly to Phase 5.5+ extension experiments. **No automated retries; no silent fallback.**

**Pass criteria:** see Phase 4 gate criteria in §3.

**Priority: P0 — paper-replication MUST.**

**Schedule:** Phase 4.2 — runs sequentially after Gap 1 routing probe.

---

### Gap 3 — Train/test scenario set: build fixed scenario list (paper §IV-A: 100 train + 50 test)

**Why this matters:**
Paper claims fixed 100-train / 50-test scenarios. v3 currently resamples disturbance per ep on-line (`np.random.uniform(DIST_MIN, DIST_MAX)`). Without a fixed test set, "DDIC at −8.04 vs adaptive at −12.93" is not reproducible — every run would draw a different test set.

**Target:** produce two JSON manifest files describing 100 / 50 deterministic scenarios; train / eval pipelines load them by index. Q1 in fact base ("fixed or per-ep resampled?") remains paper-side OPEN — **default to fixed** because that's what the cumulative-reward comparison metric requires.

**Modification surface:**
- New file `scenarios/kundur/scenario_sets/v3_paper_train_100.json` — 100 entries, each `{seed, bus, magnitude_sys_pu, comm_failed_links, …}`.
- New file `scenarios/kundur/scenario_sets/v3_paper_test_50.json` — 50 entries.
- New module `scenarios/kundur/scenario_loader.py` with a deterministic generator (reads paper-fact-base ranges + a seed; writes the JSONs) and a runtime accessor (per-ep index → scenario dict).
- `env/simulink/kundur_simulink_env.py::reset` — accept optional `options={'scenario_idx': k}` and apply the indexed scenario instead of the random one. Keep the random path as the default fallback for non-paper-replication runs.
- `scenarios/kundur/train_simulink.py` — add `--scenario-set <train|test|none>` flag and `--scenario-index <k>` for eval-set deterministic replay.

**Risks:**
- R-G3-1: deterministic seed generation may drift across NumPy / random versions. **Mitigation:** materialize the JSONs once and ship them; never re-run the generator without an explicit `--regenerate` flag.
- R-G3-2: `scenarios` JSON schema must cover Bus 7 / Bus 9 LoadStep amplitudes AND Pm-step amplitudes if Phase 4 sweeps both. **Mitigation:** schema includes `disturbance_type` field; loader dispatches.
- R-G3-3: paper Q1 is OPEN — we may be over-specifying. **Mitigation:** Phase 4 documents this as a known assumption; Phase 5 baseline can re-run on an alternative "per-ep resampled" config to bracket the answer.

**Validation method:**
- Schema validator probe: load both JSONs, assert 100 / 50 entries, all fields present, magnitudes inside paper-feasible ranges.
- 5-ep smoke that uses indices `[0..4]` from the train set: same gate criteria as P3.4 5-ep smoke.

**Pass criteria:** smoke passes; one full Phase 4 50-ep run (under best PHI from Gap 2) using `--scenario-set train` produces a reward distribution shape similar to the random-resample run (within factor of 2 mean).

**Priority: P1 — paper-replication MUST for Phase 5 numerical comparison; P2 for Phase 4.**

**Schedule:** Phase 4.3 — after Gap 1 + Gap 2 stabilize a default config.

---

### Gap 4 — Paper-style evaluation: case studies + decomposition + freq metrics

**Why this matters:**
Paper Fig. 4-7 show frequency response curves under specific disturbances; Sec.IV-C reports r_f-only cumulative reward (NOT total reward) on test set, comparing DDIC vs adaptive vs no-control. v3 has none of this evaluation tooling.

**Target:** produce a per-checkpoint evaluation that emits:
1. **Case study (load step 1 / 2):** per-ep frequency trajectories for all 4 ESS, on identical paper-style disturbances, plotted side-by-side for {no-control, DDIC v3 trained, optionally adaptive baseline}.
2. **Reward decomposition:** per-ep `r_f, r_h, r_d` totals + `r_f%`.
3. **Frequency metrics per ep:** ROCOF (max |dω/dt| · fn), nadir (min ω), peak (max ω), settling time (first t such that |ω−1| < 0.01 % for 1 s), peak-to-peak.
4. **Test-set cumulative reward:** matches paper §IV-C global formula `−ΣΣ(Δf−f̄)²` (ω in Hz) over 50 test scenarios.

**Modification surface:**
- New module `plotting/paper_replication.py` — figure generators (paper Fig.4-7 style).
- New module `evaluation/paper_eval.py` — test-set runner and metric computer.
- `scenarios/kundur/train_simulink.py` — add `--eval-paper-style` flag that, after training, runs the test-set evaluation and emits a metrics JSON + figures.

**Risks:**
- R-G4-1: paper's exact disturbance magnitudes for Fig.4-7 are not in the fact base — they are visual estimates. **Mitigation:** sweep a small grid (e.g. 50/100/200 MW Bus 7 step) and pick the one whose no-control trajectory matches paper Fig.4 visually.
- R-G4-2: paper's "adaptive baseline" implementation is not provided (paper cites [25]). **Mitigation:** start with no-control baseline only; defer adaptive baseline to a later iteration. Documented in Phase 5 plan.
- R-G4-3: settling time computation depends on the freq-deviation tolerance (paper does not specify). **Mitigation:** use 0.01 % (= 5 mHz on 50 Hz) as the v3 settling threshold; document.

**Validation method:**
- Run on a known-good v2 checkpoint as a sanity probe: confirm the test-set evaluator emits a number, decomposition makes sense, plots render.
- Run on a fresh v3 random-action baseline (no policy, just zero-action): confirm the r_f-only cumulative reward is in `[-30, -8]` ballpark (paper's no-control −15.2).

**Pass criteria:** evaluator runs end-to-end on a v3 checkpoint; metric ranges sensible; figures render without zero-data axes.

**Priority: P1 — paper-replication MUST.**

**Schedule:** Phase 5.1 — after Phase 4 produces a viable trained checkpoint.

---

### Gap 5 — Wind trip: keep deferred (S3 / D-minor)

**Why this matters:**
P2.4 surfaced that `WindAmp_w → 0` near-grounds the wind-farm bus through the 1 µH `L_wind` internal impedance. That's a probe-mechanism limitation, not a model bug — for full-trip semantics we'd need either a Type-3/4 wind dynamic model OR a topology disconnect (FastRestart-incompatible).

**Decision: DEFER to Phase 5.5 / extension experiments, NOT Phase 4.**

**Why defer:**
- Paper's wind-trip experiment is in Sec.IV-G (NE39, not Kundur). Kundur main results in Sec.IV-C use load steps, not wind trip.
- The ~10 % partial trips (`WindAmp_w ∈ [0.5, 1.0]`) ARE physically meaningful and Phase 2.4 confirmed W1 partial trips behave linearly.
- Hard wind-trip requires a build-side topology change (forbidden in current allow-list), so it pulls in a scope-expansion decision that should not block Phase 4 / Phase 5.

**If Phase 5 paper-baseline mismatch traces to wind dynamics:** open a separate work item to either (a) implement Type-3 wind via Simscape (heavy), or (b) introduce a switchable disconnect block (light, but FastRestart-incompatible — would require shifting smoke-stage to non-FR mode).

**Priority: P3 — extension only.**

**Schedule:** out of Phase 4 scope. Reconsider in Phase 5.5 or beyond.

---

### Gap 6 — H/D scaling and reward averaging: ablation tests for Q7 / Q2

**Why this matters:**
- `M = 2H` (Q7 mapping) and `global mean(ΔH)` for r_h (Q2 protocol) are both project inferences, not paper facts.
- If paper used `H` directly (no factor 2) OR `neighbor mean` for r_h, v3 r_h numerical values differ by O(1) factors.
- A Phase 5 paper-baseline comparison that doesn't match might be due to Q7 / Q2 mismatch, not actual algorithm difference.

**Target:** **bracket the answer empirically** by running ablations.

**Modification surface (probe-only, no model edit):**
- `evaluation/paper_eval.py::ablation_q7` — re-run a single trained checkpoint's test-set evaluation under two conventions:
  1. Convention A: `H = M` (paper-strict, no factor 2). Re-scale ΔH range and r_h penalty accordingly.
  2. Convention B: `H = M/2` (current project working hypothesis).
  Compare cumulative reward.
- `evaluation/paper_eval.py::ablation_q2` — re-run reward computation under:
  1. Protocol A: r_h = `−(global mean ΔH)²` (current).
  2. Protocol B: r_h = `−(neighbor mean ΔH for agent i)²` (per-agent).
  Compare per-agent reward distributions.

**Risks:**
- R-G6-1: ablation fully invalidates v3 numerical results if Q7 mapping was wrong. **Mitigation:** the ablation is **observation-only** (re-evaluating an existing checkpoint with re-interpretation), not re-training. Cheap. If results diverge dramatically from paper, Phase 5 plan opens a re-train under the better convention.
- R-G6-2: paper's ΔH range [-100, 300] under v3 H units would be physically nonsensical (would imply M = -100 to +300 + M0 = 24, going negative). This is what motivates the project Q7 working hypothesis. **Mitigation:** the ablation is for *reward computation*, not action range; action range stays at v3's calibrated `[DM_MIN, DM_MAX]`.

**Validation method:** the ablation runner emits a comparison table; Phase 5 verdict cites it.

**Pass criteria:** ablation runs end-to-end and produces interpretable side-by-side numbers. No "right answer" required from the ablation itself; it serves as bracket evidence for the Phase 5 verdict.

**Priority: P2 — paper-replication SHOULD (not strict MUST). Extension if Phase 5 baseline already matches paper.**

**Schedule:** Phase 5.2 — after Gap 4 evaluator exists.

---

## 2. Phase 4 detailed sub-plan (current cadence, gates ≤ 50 ep)

```
P4.0  read-only audit  +  Gap 1 audit gate                          →  halt, request GO
        - existing: env/config/bridge insertion-point audit
        - NEW (per critic Gap 1 §4.1): determine whether build_kundur_cvs_v3.m
          actually wires LoadStep workspace vars into the block 'Resistance'
          parameter, or whether it stops at workspace-var creation (block R
          stays hardcoded '1e9'). The answer dispatches Gap 1 to (a) workspace-
          var path (no .slx rebuild), (b) build-edit path (scope expansion),
          or (c) Pm-step-proxy path (paper-form divergent, allow-list-clean).
        ↓
P4.1  Gap 1 — LoadStep disturbance routing  (PURE disturbance probe;  →  halt with disturbance-only verdict
        NOT a 50-ep gate run; fixes I2)
        - probe_loadstep_disturbance_routing.py (1-ep smoke under v3
          random-action workload, asserts info['max_freq_dev_hz']>0,
          per-step r_f non-zero on ≥80 % of post-disturbance steps,
          no tds_failed, set_param / workspace-var change verifiable)
        - NO 50-ep training run here. The 50-ep "first PHI" run moves to P4.2.
        ↓
P4.2  Gap 2 — PHI sweep on LoadStep disturbance                       →  halt with per-run verdicts
        - sequential 50-ep runs under the validated Gap 1 disturbance form:
          phi_b1 → phi_asym_a → phi_paper_scaled (→ phi_asym_b → phi_paper if needed)
        - stopping rule (per I1 fix): first run with r_f% in the Phase 4 gate
          criterion 3 band [3 %, 30 %] AND all gates green = v3 default
        - WARMUP_STEPS contract for Phase 4 (per G2 fix): see § 3.1 below
        ↓
P4.3  Gap 3 — Fixed scenario sets  (lightweight, no new SAC training)
        - generate v3_paper_train_100.json + v3_paper_test_50.json
        - schema validator probe + 5-ep smoke using indices 0..4 under the
          v3-default PHI from P4.2
        - 1 50-ep gate run under v3-default PHI + scenario-set=train
        ↓
P4.4  Phase 4 aggregate verdict + handoff contract emit (per M1)     →  halt with GO/NO-GO for Phase 5
        - lock the (PHI_H, PHI_D, disturbance type, scenario set, T_WARMUP,
          WARMUP_STEPS) tuple as v3-paper-replication-config
        - emit handoff contract artifact: see §3.2 below
        - measure mean s/ep wall on the chosen config across last 3 runs
        - project Phase 5 wall budget at the measured rate, NOT a default
          14 hr or 19 hr (per S2 fix)
```

### Phase 4 50-ep gate criteria (per run, applies P4.2 / P4.3)

| # | Criterion | Numeric gate |
|---|---|---|
| 1 | Completion | 50/50 episodes complete; no `tds_failed`, no Simscape constraint, no Python exception |
| 2 | Numerical health | zero NaN/Inf in (omega, Pe, action, reward) across 2500 step records |
| 3 | r_f% scale (TRAIN-LOCAL) | `mean(|r_f|) / mean(|total_reward|)` over last 25 ep ∈ **[3 %, 30 %]** (target 5 %). **Note (per critic H1): this gate uses LOCAL r_f from training. The paper Sec.IV-C cumulative reward uses GLOBAL r_f. Phase 4 cannot directly gate paper-global r_f% because the global evaluator (Gap 4) only lands in Phase 5.1. P4.4 verdict must explicitly note that Phase 4 train-local r_f% pass is necessary but NOT sufficient evidence for Phase 5 global-r_f% PASS.** |
| 4 | Frequency reach (REVISED 2026-04-27 per critic round-2) | Coupled to `DIST_MIN/DIST_MAX` and to disturbance type. **Under the Gap 1 default = `pm_step_proxy_random_bus` with current `DIST_MIN/DIST_MAX = [0.1, 0.5] sys-pu` (10–50 MW)**: per-ep `max_freq_dev_hz` ∈ **[0.05, 1.5] Hz** on ≥ 80 % of episodes — viable per P2.2 (per-source Pm-step at +0.2 sys-pu = 20 MW gave 63–94 mHz). Bus-7-proxy (= ES1 Pm-step) is comparable to Bus-7 direct; Bus-9-proxy (= ES4 Pm-step) is also comparable per P2.2 (ES4 self-response 64 mHz at +0.2). **If Phase 5 ever switches to Path (A) build-edited true LoadStep**, criterion 4 floor must drop or `DIST_MIN/DIST_MAX` must rise — see § 3.3 for the explicit DIST × disturbance-type interaction table. Phase 4 must report Bus-7-proxy and Bus-9-proxy sub-rates separately. |
| 5 | Action-space health | `mean(M)` ∈ [M_LO + 0.5, M_HI − 0.5] AND `mean(D)` ∈ [D_LO + 0.5, D_HI − 0.5] (no boundary pinning) |
| 6 | Wall-time budget | total wall < 60 min for 50 ep (= 1.2 min/ep cap). Phase 5 wall projection (§ Phase 5 below) uses each run's measured per-ep rate, NOT a fixed default. |
| 7 | SAC sanity | actor/critic/alpha losses finite throughout; no `requires_grad=False` issues; WARMUP_STEPS contract (§ 3.1) honored |
| 8 | Learning trend (REVISED per critic G2) | **Informational only at 50 ep / WARMUP_STEPS=2000 default.** With default WARMUP_STEPS=2000 the SAC barely learns inside the 50-ep window (buffer fills 2500 steps, warmup cap = 2000), so a "first 25 vs last 25" comparison measures noise, not learning. Two ways forward: (a) lower `WARMUP_STEPS` to 500 in Phase 4 only — see § 3.1 — and require last-25 > first-25 by ≥ 1 % of |mean reward|; (b) keep WARMUP_STEPS=2000 and mark criterion 8 informational, requiring only that loss curves are finite (already in criterion 7). Default Phase 4 path: option (a). |

A run is **PASS** if all 8 green (criterion 8 under option (a)); **CONDITIONAL** if 1, 2, 4 pass + ≥ 1 of 3/5/6/8 marginal; **FAIL** if 1 or 2 fails.

### 3.1 WARMUP_STEPS contract for Phase 4 (REVISED 2026-04-27 per critic round-2 math fix)

`scenarios/kundur/config_simulink.py` ships `WARMUP_STEPS=2000` (Kundur override; v2 reasoning at L186-188). The unit is **transitions in the replay buffer**, not RL episodes.

**Buffer fill rate (verified by reading `train_simulink.py` + `agents/sac.py`):** 4 agents × 50 steps/ep = **200 transitions per episode**.

**Round-1 plan said "WARMUP_STEPS=2000 = 40 ep warmup". WRONG.** The correct math:
- WARMUP_STEPS = 2000 transitions ÷ 200 transitions/ep = **10 ep** (not 40)
- WARMUP_STEPS = 500 transitions ÷ 200 transitions/ep = **2.5 ep** (not 10)

**Implication for Phase 4 50-ep gate:**
- Default 2000 → SAC updates begin at ep 11. Last 25 ep (ep 26-50) get full SAC. **Criterion 8 is observable.** Round-1 panic was based on wrong arithmetic.
- 500 override gives SAC updates almost immediately (ep 3+). For Phase 4 we may use it to maximize learning signal in the limited 50-ep window, but it's **not required** for criterion 8 observability.

**Phase 4 decision (REVISED):** keep `WARMUP_STEPS=2000` as the Phase 4 default. Criterion 8 (last 25 vs first 25 ep mean reward) is meaningful at this setting. Optionally lower to 500 for one of the PHI sweep candidates if early-learning measurement is wanted. Mark this knob as a sweep variable, not a hardcoded override.

**Phase 5 default:** keep 2000 unless P4.4 measurement evidence prompts otherwise. Paper Table I says replay 10000 / batch 256 / M 50 — no explicit warmup specified. Project's 2000 is reasonable.

### 3.3 DIST × disturbance-type interaction table (NEW per critic round-2)

The frequency-reach gate (criterion 4 floor 50 mHz) depends on BOTH disturbance magnitude AND disturbance form. From P2.2 / P2.3-L1 measurements:

| Disturbance type | ΔP magnitude (sys-pu / MW) | df_peak observed | passes 50 mHz floor? |
|---|---|---|---|
| Pm-step on ES1 | 0.20 / 20 | 69 mHz (P2.2) | ✅ |
| Pm-step on ES4 | 0.20 / 20 | 64 mHz (P2.2) | ✅ |
| Pm-step on G1/G2/G3 | 0.20 / 20 | 85–94 mHz (P2.2) | ✅ |
| LoadStep at Bus 7 | 1.00 / 100 | 22 mHz (P2.3-L1, extrapolated) | ❌ |
| LoadStep at Bus 7 | 5.00 / 500 | 110 mHz (P2.3-L1) | ✅ |
| LoadStep at Bus 7 | 9.67 / 967 | 210 mHz (P2.3-L1) | ✅ |
| LoadStep at Bus 9 | 9.67 / 967 | 21 mHz (P2.3-L1) | ❌ (Bus 9 stiff) |

**Implications:**
- `pm_step_*` disturbance types are gate-compatible with current `DIST_MIN/DIST_MAX = [0.1, 0.5]` sys-pu (10–50 MW, mapped to per-VSG ±0.4 sys-pu = 40 MW per ES). Phase 4 default **stays here**.
- True LoadStep at Bus 7 needs ΔP ≥ 200 MW (= 2.0 sys-pu) for floor pass. True LoadStep at Bus 9 cannot pass paper-feasible ΔP.
- If Phase 5 path-A activates (build-edit LoadStep wiring), **Phase 5 plan must raise `DIST_MIN/DIST_MAX` to [2.0, 9.0] sys-pu for Bus 7** AND **lower criterion 4 floor to 10 mHz for Bus 9 episodes** OR **drop Bus 9 from the disturbance distribution and bias to Bus 7 only**.

**This interaction is a sub-step of Phase 5 path-A scope expansion**, NOT Phase 4 work.

### 3.4 Phase 5 cumulative-reward bands — selected after P5.1 normalization choice (REVISED per critic round-2)

The Phase 5 criteria 2 / 3 bands previously hardcoded as `[-12, -5]` / `[-25, -10]` were calibrated against paper's UNNORMALIZED `-8.04` / `-15.2`. If Q8 bracketing at P5.1 selects the per-M variant (paper target ≈ −0.16) or per-M-per-N variant (≈ −0.04), those bands are off by orders of magnitude.

**REVISED:** the Phase 5 criterion 2 / 3 bands are **derived at P5.1 from the chosen normalization variant** as `paper_target ± 50 %`. Concretely:

| Normalization variant | Paper DDIC target | criterion 2 band | Paper no-control target | criterion 3 band |
|---|---|---|---|---|
| unnormalized | −8.04 | [−12.06, −4.02] | −15.20 | [−22.80, −7.60] |
| ÷ M (= ÷50) | −0.1608 | [−0.241, −0.080] | −0.304 | [−0.456, −0.152] |
| ÷ M·N (= ÷200) | −0.0402 | [−0.060, −0.020] | −0.076 | [−0.114, −0.038] |

**P5.4 verdict computes the headline band from the P5.1-locked variant.** Hardcoded `[-12, -5]` / `[-25, -10]` removed from criterion 2 / 3 below.

### 3.5 events.jsonl per-step component logging is NEW work (per critic round-2 verification)

Codebase reality check: `utils/artifact_writer.py` does emit `events.jsonl`, but **per-episode aggregates only**. Per-step `r_f` / `r_h` / `r_d` component logging during training does NOT exist. P5.3 scope expansion: implement per-step component emission. Surface: `env/simulink/_base.py::_compute_reward` returns `components` dict already (`_base.py:247-249`); `train_simulink.py` step loop must forward this to `ArtifactWriter.log_event` with a `step_components` event type. ~30 lines of new code, safely confined to `train_simulink.py` and ArtifactWriter — no SAC / env / bridge edit.

### 3.6 Checkpoint interval verification (per critic round-2 verification)

Plan handoff schema (§3.2) said "save_every_n_episodes_phase5: 100" but `scenarios/config_simulink_base.py:23` sets `CHECKPOINT_INTERVAL=50`. **Phase 5 launcher must pass `--save-interval 100` explicitly**, OR the handoff schema field is updated to `50`. Default decision: keep 100 in schema, require `--save-interval 100` in P5.3 launch command. P5.0 entry audit must verify the launcher CLI honors the override.

### 3.2 Phase 4 → Phase 5 handoff contract (NEW per critic M1)

P4.4 verdict MUST emit a single artifact `results/harness/kundur/cvs_v3_phase4/v3_paper_replication_config.json` with the following schema:

```jsonc
{
  "schema_version": 1,
  "phase4_commit_sha": "<commit hash at P4.4>",
  "config": {
    "PHI_H": <float>,
    "PHI_D": <float>,
    "PHI_F": 100.0,
    "T_WARMUP_s": <float>,
    "WARMUP_STEPS": <int>,
    "BATCH_SIZE": <int>,
    "BUFFER_SIZE": <int>,
    "DEFAULT_EPISODES": 2000,
    "disturbance_type": "load_step_random_bus" | "pm_step_single_vsg" | "mixed",
    "disturbance_amplitude_range_sys_pu": [<min>, <max>],
    "disturbance_bus_distribution": {"bus7": <prob>, "bus9": <prob>}
  },
  "scenarios": {
    "train_set_path": "scenarios/kundur/scenario_sets/v3_paper_train_100.json",
    "train_set_sha256": "<hex>",
    "test_set_path":  "scenarios/kundur/scenario_sets/v3_paper_test_50.json",
    "test_set_sha256":  "<hex>"
  },
  "kpis": {
    "best_run_dir": "<path>",
    "best_run_50ep_train_local_r_f_pct": <float>,
    "best_run_50ep_max_freq_dev_p80_hz": <float>,
    "measured_mean_s_per_ep": <float>,
    "phase5_2000ep_wall_projection_hr": <float>
  },
  "checkpoint_format": {
    "actor_state_dict_keys_sha256": "<hex>",
    "critic_state_dict_keys_sha256": "<hex>",
    "save_every_n_episodes_phase5": 100
  }
}
```

This artifact is the **sole input** to Phase 5.0 entry audit. Phase 5 launcher refuses to start if this file is missing or schema_version mismatches.

---

## 3. Phase 5 detailed sub-plan (paper replication, includes 2000-ep training)

```
P5.0  Phase 5 entry audit (load v3_paper_replication_config.json,        →  halt, request GO
       verify checkpoint format + train_simulink.py --resume support)
        - REQUIRED: confirm train_simulink.py supports --resume <path>
          AND that the checkpoint format saves every 100 ep (per M2/handoff).
          If not, that's an explicit prerequisite work item before P5.3.
        ↓
P5.1  Gap 4 — paper-style evaluator (no training)                        →  halt with eval-tooling verdict
        - plotting/paper_replication.py
        - evaluation/paper_eval.py (output schema § 5.1.1 below per critic M4)
        - validate on a v3 random-action baseline + a v3 Phase-4 checkpoint
        - bracket test-set formula Q8 ambiguity (per critic H2): emit BOTH
          unnormalized cumulative reward AND 1/M-normalized AND 1/(M·N)-
          normalized variants in the metrics JSON. The verdict picks one
          for the headline number after comparing all three magnitudes
          to paper's −8.04 / −15.2.
        ↓
P5.2  Gap 6 — Q7/Q2 ablation (cheap, on existing checkpoint)             →  halt with ablation report
        - run paper_eval.py twice on the SAME P4.2-best checkpoint:
            once with H = M/2 (project default), once with H = M (paper-strict)
            once with global mean ΔH (project default), once with neighbor mean
        - emit a 2x2 table; verdict reports which combination fits paper
          numerics best, but DOES NOT trigger a re-train automatically
        ↓
P5.2.5 (OPTIONAL per critic M5) Q1 bracket experiment                    →  halt with bracket report
        - using the same Gap-3 fixed scenario set, run a parallel small
          training (300 ep, NOT 2000) under "per-ep resampled" disturbances
          and compare convergence trend vs the fixed-set training so far
        - low-priority; only if Phase 5 schedule allows
        ↓
P5.3  v3 paper-replication 2000-ep training (the main run)               →  halt with training verdict
        - lock config from P4.4 v3_paper_replication_config.json
        - SINGLE run; checkpoint every 100 ep so a mid-train crash at ep 1500
          can resume from ep 1500 (not from ep 0). Verified at P5.0.
        - estimated wall: PROJECTED FROM Phase 4 measured s/ep × 2000.
          See § 5.3.1 below for the realistic projection method.
        - per-step r_f / r_h / r_d component logging into events.jsonl
          (per critic M3) — required so post-hoc reward-shape diagnosis is
          possible without re-running.
        ↓
P5.4  Test-set evaluation on 50 fixed scenarios + paper Fig.4-7 plots    →  halt with paper-baseline verdict
        - emit cumulative-reward number under all 3 normalization variants
          from P5.1 (per H2 fix)
        - emit frequency response figures
        ↓
P5.5  (OPTIONAL) Adaptive baseline (paper [25])                          →  halt
        Only if P5.4 numerics match paper within 50 % (P5 criterion 2 band),
        advance to comparison.
        ↓
P5.6  Phase 5 aggregate verdict                                          →  done
```

### 5.1.1 `evaluation/paper_eval.py` output schema (NEW per critic M4)

The evaluator's `metrics.json` MUST have:

```jsonc
{
  "schema_version": 1,
  "checkpoint_path": "<path>",
  "test_scenarios_set_sha256": "<hex>",
  "n_scenarios": 50,
  "cumulative_reward_global_rf": {
    "unnormalized":     <float>,    // raw -ΣΣ(Δf − f̄)²
    "per_M":            <float>,    // ÷ 50 (per-step average)
    "per_M_per_N":      <float>,    // ÷ (50·4) (per-step per-agent)
    "paper_target_unnormalized":  -8.04,
    "paper_no_control_unnormalized": -15.2
  },
  "per_episode_metrics": [
    {
      "scenario_idx": <int>,
      "max_freq_dev_hz": <float>,
      "rocof_max_hz_per_s": <float>,
      "nadir_hz": <float>,
      "peak_hz": <float>,
      "settling_time_s": <float>,
      "r_f_local_total": <float>,
      "r_h_total": <float>,
      "r_d_total": <float>,
      "total_reward": <float>
    }
  ],
  "figures": [
    "fig4_load_step_1_freq.png",
    "fig5_load_step_2_freq.png",
    "fig6_pe_split.png",
    "fig7_h_d_trajectories.png"
  ]
}
```

### 5.3.1 Phase 5 wall-time projection method (REVISED per critic S2)

Per-ep wall time on the **chosen P4.2 config** is the only valid projection input. P3.4 random-action smoke ran ~14 s/ep; SAC update with default `update_repeat=10` adds about 25 s per 50-step ep (0.5 s × 50). True per-ep cost ≈ **39 s/ep** (sim 14 s + SAC update 25 s) at full ramp. Earlier ep are faster during warmup ramp.

| Source | Per-ep cost |
|---|---|
| P3.4 random-action MCP smoke | 14 s/ep (50 steps, no SAC) |
| Estimated SAC update overhead | + 25 s/ep at update_repeat=10 |
| **Estimated per-ep cost at full ramp** | **~39 s/ep** |
| Average across 2000 ep (warmup ramp) | ~35 s/ep |

| Run length | Realistic wall |
|---|---|
| Phase 4 50-ep run | 50 × 35 ≈ **30 min** (was claimed ~21 min — too low) |
| Phase 4 sweep (5 runs) | ~2.5 hr (close to original ~2 hr claim) |
| **Phase 5.3 2000-ep main run** | **2000 × 35 ≈ ~19.4 hr** (was claimed ~14 hr — UNDERESTIMATED 40 %) |

**P4.4 measured s/ep replaces this estimate.** If P4.2 winners run at e.g. 42 s/ep (suspiciously high), Phase 5.3 projects at 2000 × 42 = 23.3 hr and the §3 Phase 5 criterion 6 ceiling (30 hr) still has margin. If P4.2 winners run at 50+ s/ep, criterion 6 is at risk and we re-evaluate before launching.

### Phase 5 paper-baseline gate criteria

| # | Criterion | Numeric gate |
|---|---|---|
| 1 | Training completes 2000 ep | yes / no (no NaN/Inf, no MATLAB engine crash, no Simscape constraint). Mid-train crash + successful resume from latest checkpoint counts as PASS for this criterion (per critic M2 / handoff §3.2). |
| 2 | Test-set cumulative reward (50 scenarios, global r_f formula) | within **paper_DDIC_target ± 50 %** under the **P5.1-locked normalization variant** (band derived from § 3.4 table; e.g. [−12.06, −4.02] for unnormalized, [−0.241, −0.080] for ÷M, [−0.060, −0.020] for ÷M·N). |
| 3 | No-control baseline cumulative reward on same test set, same normalization | within **paper_no_control_target ± 50 %** under the same locked normalization (e.g. [−22.80, −7.60] unnormalized). Bands 2 and 3 overlap (DDIC-best should still beat no-control by ≥ 20 % per criterion 4). |
| 4 | DDIC vs no-control improvement ratio | **DDIC reward > no-control reward** by **≥ 20 %** (paper: −8.04 vs −15.2 = 47 % better; v3 must show > 20 % improvement). This is the actual gate when criterion 2 / 3 land in their overlap band. |
| 5 | Frequency response figures (Fig.4-7 style) | nadir, peak, ROCOF in paper-quoted ranges (sub-1 Hz nadir, < 1 Hz/s ROCOF for normal load steps) |
| 6 | Wall-time | full Phase 5 round-trip < 30 hr for the main run (projection in §5.3.1; realistic ~19-23 hr) |

A Phase 5 PASS = all 6 green. CONDITIONAL = 1, 2, 4 pass; flag 3 or 5 for follow-up. FAIL on 1 or 2 = root-cause, no Phase 5 advance.

---

## 4. Priority + classification cross-cut table

| Gap | Class | Priority | Phase | Files-of-interest (read-only audit reveals) | Wall budget |
|---|---|---|---|---|---|
| **Gap 1** LoadStep routing | paper-replication MUST (D5) | **P0** | Phase 4.0 / 4.1 | `env/simulink/kundur_simulink_env.py`, `scenarios/kundur/config_simulink.py` (env predicate + new `KUNDUR_DISTURBANCE_TYPE` knob); **engine/simulink_bridge.py read-only** (use existing `apply_workspace_var`); LoadStep workspace gating wiring TBD at P4.0 audit (per critic S1) | probe 30 min + (no 50-ep run in P4.1 — moved to P4.2 per I2 fix) |
| **Gap 2** PHI sweep | paper-replication MUST (D4) | **P0** | Phase 4.2 | `scenarios/kundur/config_simulink.py:93-94` only; optional new env-var override mechanism for sweep automation | 3-5 × ~30 min runs (per S2 corrected timing) ≈ 1.5-2.5 hr total |
| **Gap 3** Fixed scenario sets | paper-replication MUST (D5 / Q1) | **P1** | Phase 4.3 | new `scenarios/kundur/scenario_sets/`, `scenarios/kundur/scenario_loader.py` (NEW), `env/simulink/kundur_simulink_env.py::reset`, `scenarios/kundur/train_simulink.py` CLI | 1 day (mostly artifacts + smoke) |
| **Gap 4** Paper-style evaluator | paper-replication MUST (Sec.IV-C) | **P1** | Phase 5.1 | new `evaluation/paper_eval.py` (output schema § 5.1.1), `plotting/paper_replication.py` | 1 day |
| **Gap 5** Wind trip semantics | extension only | **P3** | DEFER (Phase 5.5+) | TBD if reactivated | not in current budget |
| **Gap 6** Q7/Q2 ablation | paper-replication SHOULD | **P2** | Phase 5.2 | extends Gap 4 evaluator | half day |

**P0 = MUST do before Phase 5 launch. P1 = MUST do before Phase 5 verdict. P2 = SHOULD do for Phase 5 verdict robustness. P3 = extension only.**

---

## 5. What's a paper-replication MUST vs an extension

### Paper-replication MUST (cannot ship Phase 5 verdict without these)
1. Gap 1 — LoadStep at Bus 7/9 disturbance form (matches paper Sec.IV-C scenarios)
2. Gap 2 — PHI tuned to v3 such that r_f% is meaningful
3. Gap 3 — Fixed 50-scenario test set (paper §IV-A; required for the cumulative-reward number to be reproducible)
4. Gap 4 — Test-set evaluator with global r_f formula + Fig.4-7 plots (paper §IV-C)

### Paper-replication SHOULD (improves verdict robustness)
5. Gap 6 — Q7 / Q2 ablation (brackets paper-side ambiguity)
6. Independent learner check (already MATCH; no work needed)

### Extension only (NOT paper Kundur Sec.IV-A-C)
7. Gap 5 — Wind trip (paper has it for NE39 not Kundur main)
8. Comm-delay test (paper §IV-E; v3 already supports the knob; only an evaluation pass needed)
9. Comm-fail rate sweep (paper §IV-D)
10. NE39 v3-equivalent build (out of scope; do not start)
11. 2000-ep on-line resampling (alternative to fixed scenario sets — bracket only)

---

## 6. Boundary check (re-iterated; always-on)

- v2, NE39, ANDES, ODE, legacy SPS all **untouched**.
- v3 model files (`build_kundur_cvs_v3.m`, `kundur_cvs_v3.slx`, `_runtime.mat`, NR script, IC) **locked** since `cbc5dda` / `a5bc173`. **Do not regenerate IC, do not rebuild .slx.**
- Shared bridge / shared CVS helpers **untouched** (any edits go through their own R-h-class authorization).
- SAC architecture, `scenarios/contract.py`, `scenarios/config_simulink_base.py` **untouched**.
- 2000-ep launch only after explicit user GO based on Phase 4 verdict.
- NE39 500-ep training: do not interrupt; v3 Phase 4 / 5 runs use distinct MATLAB engines.

---

## 6.5 Buffer / fixed-scenario interaction note (NEW per critic M6)

`BUFFER_SIZE = 100000` Kundur override at 50 steps/ep = **2000 episodes** of capacity. With a 100-scenario fixed train set and 2000 training episodes, each scenario repeats ~20 times and **all of them stay in the buffer** (capacity > training length × steps/ep). Catastrophic forgetting risk is low. Random sampling from the buffer for SAC updates is sufficient — no prioritized replay or scenario-balanced sampling is needed.

If Phase 5 changes to a smaller buffer (paper Table I says 10000 = 200 ep), some early scenarios would age out and be sampled less. That is the paper-original setting; v3 currently uses 100000 for v2 reasons. Phase 5 plan should explicitly re-evaluate whether to revert to paper 10000 or keep 100000 — **decision deferred to P5.0 audit**.

---

## 7. Recommended roadmap (concrete sequencing)

| Step | What | Why this ordering | Halt for GO? |
|---|---|---|---|
| 1 | **Phase 4.0 audit** — read-only: `kundur_simulink_env.py`, `simulink_bridge.py` (no edit), `config_simulink.py`, AND confirm whether `build_kundur_cvs_v3.m` actually wires LoadStep workspace vars into the block `Resistance` parameter (per critic Gap 1 §4.1 dispatch) | minimizes blind edits + dispatches Gap 1 to the right modification path | yes |
| 2 | **Phase 4.1 Gap 1** — LoadStep disturbance routing via existing `apply_workspace_var` (NO bridge edit per critic S1) + 1-ep probe **only** (no 50-ep gate at this step per critic I2) | establishes the paper-form disturbance baseline as a clean unit, separately from PHI tuning | yes |
| 3 | **Phase 4.2 Gap 2** — PHI sweep (3-5 runs sequentially, ~30 min each, ~2.5 hr total per S2 corrected timing); **WARMUP_STEPS=2000 default per § 3.1** (round-2 math fix: 2000=10 ep is observable for criterion 8); optionally one sweep candidate at WARMUP=500 if early-learning measurement is wanted | identifies v3-default reward weights | yes after each run |
| 4 | **Phase 4.3 Gap 3** — fixed scenario sets + smoke + 1 50-ep run on train set | locks the train/test contract | yes |
| 5 | **Phase 4.4 aggregate** — produce Phase 4 verdict, emit `v3_paper_replication_config.json` per § 3.2 (handoff contract; per critic M1) | gate to Phase 5 | yes |
| 6 | **Phase 5.0 entry audit** — verify `train_simulink.py --resume` works, checkpoint format saves every 100 ep (per critic M2); decide buffer-size revisit (per § 6.5) | prevents 14+ hr restart on mid-train crash | yes |
| 7 | **Phase 5.1 Gap 4** — build paper-style evaluator with output schema § 5.1.1; bracket Q8 normalization (per critic H2); validate on Phase 4 checkpoints | required for the Phase 5 main-run verdict | yes |
| 8 | **Phase 5.2 Gap 6** — Q7/Q2 ablation on a Phase 4 checkpoint (re-evaluation only, no re-train) | brackets paper-side ambiguity ahead of the main 2000-ep run | yes |
| 9 | **Phase 5.2.5 (OPTIONAL)** — Q1 fixed-vs-resampled bracket experiment, 300 ep parallel run (per critic M5) | optional bracket on a paper-side ambiguity | yes |
| 10 | **Phase 5.3 main run** — 2000-ep v3 paper-replication training (single run, checkpoint every 100 ep, per-step `r_f` / `r_h` / `r_d` component logging into events.jsonl per critic M3) | the actual paper replication | yes — this is the explicit 2000-ep authorization gate |
| 11 | **Phase 5.4 paper-baseline verdict** — test-set 50 scenarios + figures + cumulative-reward comparison vs paper (under all 3 normalization variants per H2) | the actual paper-replication outcome | yes |
| 12 | **Phase 5.5+ optional extensions** — adaptive baseline, comm-delay test, wind-trip, Q7/Q2 re-train | follow-up only if needed | yes |

Each step halts with a verdict; user GO needed before next step. No automation across steps. NE39 untouched throughout.

---

## 8. Files emitted in this draft

```
quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md   (this file)
```

Only the plan markdown is emitted. **No code, no model, no training, no probe runs.**

---

## 9. Decision points for user

1. Approve this roadmap (Gap classification, Priority assignment, sequencing)?
2. Approve the Phase 4 50-ep gate criteria (§3 table). **Note: round-2 math fix in § 3.1 — `WARMUP_STEPS=2000` default IS observable for criterion 8 (2000 transitions ÷ 200 trans/ep = 10 ep warmup, leaving 40 ep of measurable learning). Round-1's "lower to 500" was based on wrong arithmetic and is now optional, not default.**
3. Approve the **Phase 4 → Phase 5 handoff contract** (§3.2 `v3_paper_replication_config.json` schema; per critic M1)?
4. Approve the **Phase 5 → train_simulink resume contract** (§P5.0; per critic M2 — checkpoint every 100 ep, `--resume` verification before P5.3)?
5. Approve the **Phase 5 paper-baseline gate criteria** (§ Phase 5 table) with the H2 fix (3 normalization variants emitted, headline picked at P5.1)?
6. Approve the **wind-trip DEFER** decision (Gap 5 → P3, not P0/P1)?
7. Concurrency: NE39 500-ep is still running. v3 Phase 4 may launch in parallel (separate engines). OK?
8. Ready to start **Phase 4.0 audit** now, or stage for a later session?

---

## 10. Critic-review revision changelog (2026-04-26)

The roadmap was revised after a `critic` agent review (9-section structured critique). All items applied:

| Critic ID | Issue | Fix in this doc |
|---|---|---|
| **S1** | Gap 1 modification surface proposed `engine/simulink_bridge.py` edit, contradicting §0 hard non-goals | Gap 1 modification table revised; reroute via existing `bridge.apply_workspace_var(...)`. Bridge stays read-only. |
| **S2** | Wall-time arithmetic dropped sim time → Phase 4 ~21 min and Phase 5 ~14 hr were too low | New § 5.3.1 with explicit per-ep cost decomposition (sim 14 s + SAC 25 s = 39 s/ep at full ramp, ~35 s/ep avg). Phase 5 main run revised to **~19.4 hr** (max 23 hr at 42 s/ep). Phase 5 criterion 6 ceiling 30 hr unchanged. Phase 4 sweep wall ≈ 2.5 hr. |
| **I1** | PHI sweep stopping rule [3, 8 %] vs gate criterion 3 [3, 30 %] inconsistent | Sweep stopping rule rewritten to reference gate band [3, 30 %], target midpoint 5 %. |
| **I2** | P4.1 conflated LoadStep validation with first 50-ep PHI gate run | Phase 4 sub-plan: P4.1 is now **probe-only** (1-ep). 50-ep training begins at P4.2 with PHI sweep. |
| **I3** | wall-time disagreement across two project documents (alignment audit vs roadmap) | Acknowledged; § 5.3.1 is now the authoritative projection method. Audit doc will be reconciled in a separate pass if needed. |
| **H1** | Phase 4 r_f% gate uses LOCAL r_f, paper Sec.IV-C uses GLOBAL | Criterion 3 carries an explicit caveat: "necessary but not sufficient for Phase 5 global-r_f% PASS"; Phase 5.1 evaluator emits the global formula. |
| **H2** | Phase 5 cumulative-reward bands ignore Q8 normalization ambiguity (1/M, 1/N, neither) | Phase 5.1 evaluator emits **all 3 variants** (unnormalized / per-M / per-M-per-N); criterion 2 picks the variant at P5.1 verdict. |
| **H3** | Gap 1 risk R-G1-3 references paper -1.61 / -0.80 numbers but those need Gap 4 evaluator | (Acknowledged; R-G1-3 mitigation deferred to Phase 5 once Gap 4 exists; Phase 4 magnitude tuning instead uses df_peak in [0.05, 1.5] Hz on Bus 7/9 disturbances as the proxy.) |
| **G1** | Criterion 4 freq-reach band [0.05, 1.5] Hz fragile for Bus 9 stiff sourcing | Criterion 4 now requires per-bus sub-rate reporting; the 80 % aggregate is informed by both buses. |
| **G2** | Criterion 8 learning trend unobservable at WARMUP_STEPS=2000 + 50 ep | New § 3.1 WARMUP_STEPS contract: lock 500 for Phase 4. Criterion 8 now meaningful. |
| **G3** | Phase 5 criteria 2/3 overlap [-12, -10]; criterion 4 disambiguates | Documented in criteria 3 / 4; criterion 4 made the actual disambiguator (≥ 20 % improvement). |
| **Q1** (sequencing risk) | Gap 3 JSON schema risks rework if Gap 1 disturbance vocab not finalized | Phase 4 sub-plan ordering Gap 1 → Gap 2 → Gap 3 means Gap 1 vocabulary lands first, JSON schema then encodes it. |
| **Q2** (sequencing risk) | Phase 5.3 single 2000-ep run with no resume guardrail | New P5.0 step: verify `train_simulink.py --resume` + checkpoint-every-100-ep contract before P5.3. |
| **M1** | No Phase 4 → Phase 5 handoff contract | New § 3.2 with full schema; P4.4 verdict emits this artifact; Phase 5 launcher refuses to start without it. |
| **M2** | No Phase 5.3 resume guardrail | Covered by new P5.0 step + criterion 1 mid-train-crash-with-resume PASS. |
| **M3** | No per-step `r_f`/`r_h`/`r_d` logging during training | P5.3 step now requires component logging to events.jsonl. |
| **M4** | `evaluation/paper_eval.py` output schema undefined | New § 5.1.1 metrics.json schema. |
| **M5** | Q1 (fixed vs resampled) bracket experiment not budgeted | New P5.2.5 OPTIONAL step with 300-ep parallel run. |
| **M6** | Buffer / fixed-scenario interaction unanalyzed | New § 6.5 buffer-interaction analysis. |
| **Top-3** | Apply S1, S2, G2 fixes first | All applied above. |

### Round-2 critic revisions (2026-04-27)

A second-pass critic review found that some of the round-1 fixes assumed code state that did not actually exist. All round-2 issues applied:

| Round-2 ID | Issue | Fix in this doc |
|---|---|---|
| **R2-Blocker1** | Round-1 Gap 1 main path "drives LoadStep/9 conductance through existing workspace-variable mechanism" — verification: `build_kundur_cvs_v3.m:200-205` creates `G_perturb_*` / `LoadStep_t_*` / `LoadStep_amp_*` workspace vars but NO Simulink block reads them. LoadStep blocks at lines 316-336 use hardcoded `Resistance='1e9'`. Workspace vars float unused. | Gap 1 modification surface rewritten. **Default path is now Pm-step proxy (Path C)** using existing `apply_workspace_var` on `Pm_step_t_<i>` / `Pm_step_amp_<i>`. LoadStep build-edit (Path A) is an explicit Phase 5 scope-expansion option, NOT a Phase 4 main path. New 3-row path table replaces the round-1 §4.1 fallback. |
| **R2-Blocker2** | `KUNDUR_DISTURBANCE_TYPE` "expose" wording implied partial existence; codebase has zero matches | Phrasing corrected to "add" (NEW). Same for `--scenario-set` / `--scenario-index` flags on train_simulink.py. |
| **R2-Verification1** | `train_simulink.py --resume` claim verified ✓ (`train_simulink.py:71-74, 252-284`) | No change needed |
| **R2-Verification2** | `bridge.apply_workspace_var` claim verified ✓ (`simulink_bridge.py:735`) | No change needed |
| **R2-Verification3** | `events.jsonl` per-step component logging claim — verified PARTIAL: `ArtifactWriter` writes to `events.jsonl` but only per-episode aggregates; per-step `r_f`/`r_h`/`r_d` does not exist | New § 3.5 documenting this as new instrumentation work in P5.3 (~30 lines, confined to `train_simulink.py` + ArtifactWriter) |
| **R2-Verification4** | "Checkpoint every 100 ep" claim is WRONG: `CHECKPOINT_INTERVAL=50` in `config_simulink_base.py:23` | New § 3.6 documenting that Phase 5 launcher must pass `--save-interval 100` explicitly; P5.0 entry audit verifies CLI honors it |
| **R2-Math1** | Round-1 said `WARMUP_STEPS=2000 = 40 ep`. Buffer-fill rate is 4 agents × 50 steps/ep = **200 transitions/ep**, so 2000/200 = **10 ep**, not 40. WARMUP=500 → 2.5 ep, not 10 | § 3.1 rewritten with correct math. Phase 4 default is **kept at WARMUP_STEPS=2000** (criterion 8 IS observable at this setting; the round-1 panic to 500 was based on wrong arithmetic). 500 is now an optional sweep variable, not a default override. |
| **R2-Numerical1** | Criterion 4 freq-reach floor 50 mHz unreachable under `DIST_MIN/DIST_MAX = [0.1, 0.5]` if Gap 1 switched to true LoadStep — Bus 7 needs ≥ 200 MW and Bus 9 unreachable in paper-feasible range | New § 3.3 DIST × disturbance-type interaction table. Phase 4 default Pm-step proxy at 0.1–0.5 sys-pu IS gate-compatible (P2.2 measured 64–94 mHz). True LoadStep is a Phase 5 scope-expansion that requires explicit DIST raise + criterion 4 floor relaxation. |
| **R2-Numerical2** | Phase 5 criteria 2/3 hardcoded `[-12, -5]` / `[-25, -10]` only valid for unnormalized variant. If P5.1 picks per-M (target ≈ −0.16) or per-M-per-N (≈ −0.04), bands are off by orders of magnitude | New § 3.4 table giving paper_target ± 50 % for all 3 normalization variants. Criteria 2 / 3 wording rewritten to derive band from P5.1-locked variant. |
| **R2-Sequencing1** | Gap 2 PHI sweep tuned under Pm-step proxy may not transfer to true LoadStep if Phase 5 path-A activates | Documented in Gap 1 path table (§ Gap 1 modification surface): path-A trigger requires Phase 5 PHI re-sweep. Not a Phase 4 concern. |
| **R2-Sequencing2** | "Halt and revisit Q7" if all 5 PHI candidates fail — no exit / continuation rule | Gap 2 stopping rule extended with explicit all-fail exit rule (3 user decision options + `phase4_exit_diagnostic.md` artifact). No silent fallback. |
