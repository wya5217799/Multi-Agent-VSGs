# Option G — Switch + R-bank load step at Bus 14/15, Phasor-first then Discrete-fallback

**Date:** 2026-04-30
**Status:** DRAFT v2 (Bus 14/15 LOCKED post-paper-re-read) — awaiting operator approval before Day 0
**Goal:** Replace the project's mechanical Pm-step disturbance protocol with a
true electrical load-step (Three-Phase Breaker + Series RLC R-bank) **at
Bus 14 (-248 MW trip) and Bus 15 (+188 MW engage)** matching paper Yang 2023
Sec.IV-A literally, driving the 4-ESS reward landscape into paper-class
spatial mode-shape coupling and closing the 29 pp gap between project F4 v3
(+18 %) and paper DDIC (+47 %).
**Strategy:** A-first (Switch + Phasor) with hard fail-over to B (Switch +
Discrete) if Probe G sign-pair smoke shows insufficient signal.
**Pre-authorized scope:** breaks credibility close lock #4 (default disturbance
type) and #1 (build script + .slx); kept locks #2 (SAC architecture),
#3 (reward formula), #5 (NE39 untouched).

**Bus selection LOCKED to 14/15 (NOT Bus 7/9). Rationale (decision 2026-04-30
post Option E ABORT, full PDF re-read):**
- Paper Sec.IV-A line 5605: *"Four energy storage systems **with loads** are
  separately connected to different areas in the system."* → ESS bus IS load
  bus; not "ESS terminal vs load center" dichotomy.
- Paper Sec.IV-C line 5606: *"Load step 1 and load step 2 represent the
  sudden load reduction of **248MW at bus 14** and the sudden load increase
  of **188MW at bus 15**, respectively."* → Bus 14/15 explicit.
- Paper Sec.IV-C line 5607: *"the frequency of the bus which is the **nearest
  to the disturbance bus** changes the fastest. The frequency of the bus
  where ES1 and ES2 are located changes relatively slowly as they are
  **relatively far from the disturbance bus**."* → mode shape spatial
  structure across the 4 ESS is paper-INTENTIONAL; Bus 14/15 disturbance is
  near ES3/ES4 and far from ES1/ES2, exactly the asymmetry paper exploits.
- Project v3 (`build_kundur_cvs_v3.m::loadstep_defs`) already places LoadStep
  at Bus 14/15 via 1 km Pi-line (`L_10_14`, `L_9_15`) → matches paper
  "near vs far" Fig.6 description; the 1 km Pi-line is the implicit ESS
  interconnect impedance, not a paper-deviating buffer.
- D-T1 dictionary entry "Bus 14/15 是 ESS 终端而非 load 节点" was a
  misreading of paper Sec.IV-A "with loads"; D-T1 will be updated separately
  (out of this plan's scope; tracked as a side-task in §11).
- Bus 7/9 was Option E's choice (ABORT'd today). They are mid-area load
  centers in Fig.3, but **paper does NOT switch load there**. Re-using Bus
  7/9 for Option G would contradict paper text and re-introduce the same
  CCS-attenuation failure mode that just ABORT'd.

---

## 0. Mandatory pre-read (~ 25 min, in order)

1. `results/harness/kundur/cvs_v3_option_e_smoke/OPTION_E_ABORT_VERDICT.md` —
   today's ABORT verdict; locks "CCS injection at any Phasor bus is
   attenuated ~5000×". Establishes why this plan rejects CCS path entirely.
2. `results/harness/kundur/cvs_v3_f4_retrain_eval/F4_V3_RETRAIN_FINAL_VERDICT.md`
   — current SOTA: F4 hybrid + DIST=3.0 + PHI=5e-4 → +18 % at best.pt
   (~ ep 325 of 500). 29 pp gap to paper +47 %.
3. `results/harness/kundur/cvs_v3_f4_phi0_eval/B_EXPERIMENTS_FINAL_VERDICT.md`
   — B-a/c/d ablations; +18 % is the project ceiling under
   (mechanical Pm-step + Phasor + PHI=5e-4).
4. `results/harness/kundur/cvs_v3_probe_b/PROTOCOL_GRADIENT_DEGENERACY_STOP_VERDICT.md`
   — single-point Pm-step protocols only excite 1.33-of-4 agents.
5. `docs/paper/kundur-paper-project-terminology-dictionary.md` §3 D-T1 / D-T2 /
   D-T6 — **D-T1 entry needs update** (see §11): paper Bus 14/15 are
   **simultaneously** ESS terminals AND load buses ("with loads"); the
   "ESS terminal vs load center" dichotomy in the current dictionary is a
   misread. LoadStep R-block compile-freeze (D-T2); ES2 universal dead
   under SG-side (D-T6) — both still valid.
5b. `C:\Users\27443\Desktop\论文\A_Distributed_...VSGs.pdf` Sec.IV-A
    (5605) + Sec.IV-C (5606-5607) + Fig.3 + Fig.6 — re-read these 4
    locations to internalize "with loads" + "load step at bus 14/15" +
    "near vs far disturbance bus" mode-shape description. ~ 5 min.
6. `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m`:
   - lines 174-181 (load_defs / loadstep_defs / ccs_load_defs)
   - lines 365-425 (Phase A++ Trip CCS pattern at Bus 14/15 — REFERENCE
     PATTERN, except CCS will be replaced by Switch + R-bank)
   - lines 854-925 (anchor-and-tie register pattern)
   - lines 999-1011 (runtime_consts seed)
7. `scenarios/kundur/disturbance_protocols.py` — adapter pattern; new
   `LoadStepSwitchRBank` follows `LoadStepCcsLoadCenter` shape.
8. `scenarios/kundur/workspace_vars.py` — new `SWITCH_R_LOAD_AMP` family.
9. `evaluation/paper_eval.py` lines 425-465 (scenario routing) + lines 717-727
   (CLI choices) + lines 854-870 (bus_choices selection) — new mode
   `switch_r_load`.
10. Git log:
    - `e11ee0a` Option E ABORT (today's loss)
    - `e3620ec` Option E framework (reusable schema/adapter/dispatch chain)
    - `9ade9a1` Option E build (CCS sections, dormant)
    - `6a38eb7` F4 v3 retrain — current SOTA anchor

---

## 1. Context — what this plan does and why

### 1.1 Problem statement (5 sub-problems P1-P5)

| # | Problem | Quantified target |
|---|---------|-------------------|
| **P1** | Load-step physical realization that survives FastRestart | Three-Phase Breaker control input drives R bank in/out at runtime; admittance matrix actually changes (verified by NR difference between breaker-open vs closed) |
| **P2** | Solver choice that propagates admittance change to ESS terminal | At |mag| = 0.5 sys-pu (50 MW), max\|Δf\| at any ESS terminal ≥ 0.3 Hz (paper LoadStep is ~ 0.5 Hz nadir at 248 MW) |
| **P3** | Trigger mechanism (Python → MATLAB) | env writes workspace var, breaker control responds within 1 sample |
| **P4** | NR/IC consistency in **alt (c') Phase 1** default state | Bus 14 R-bank closed (IC = 248 MW R engaged); Bus 15 R-bank open (IC = 0 MW). Verify vsg_pm0_pu unchanged (NR projects ESS as PV bus); SG dispatch absorbs +248 MW (G1/G2/G3 each ≤ 1.0 sys-pu); aggregate residual < 1e-3 |
| **P5** | Training compatibility | retrain wall ≤ 12 hr per 350 ep (10× current 70 min budget); FastRestart works |

P1+P2 are the binding pair (P3-P5 are derivative engineering).

### 1.2 Strategy: A then B

| | Phasor (A) | Discrete (B) |
|---|---|---|
| dispatch | Switch + R-bank | Switch + R-bank (same build) |
| solver swap | none (powergui Phasor mode kept) | powergui Discrete + Ts=50μs |
| build cost | 1-2 day | + 0.5 day (solver block + IC re-validate) |
| retrain | ~70 min × N | ~12 hr × N |
| expected RL improvement | +25-35 % (if signal ≥ 0.2 Hz) | +35-45 % (paper-class) |
| failure mode | Phasor still attenuates wave propagation → max\|Δf\| < 0.1 Hz | Discrete-time integrator stiffness or FastRestart incompatibility |

A failure does NOT throw away work — B reuses ~95 % of A's framework.

### 1.3 NR/IC alt — DECISION: (c') Phase 1 default + (b'') conditional fallback

**Decision finalized 2026-04-30 after PDF re-read + load_defs audit.**
Project `load_defs` (build_kundur_cvs_v3.m line 126-129) currently has
`Load7=967e6`, `Load9=1767e6` — **NO entries at Bus 14 / Bus 15**. So the
project IC currently does NOT include the paper-asserted 248 MW Bus 14
load nor the 188 MW Bus 15 load. Three NR/IC alternatives were evaluated:

| | (a') keep status quo | **(c') Phase 1 — DEFAULT** | (b'') Phase 2 fallback |
|---|---|---|---|
| Bus 14 R-bank default state | open | **closed** (paper IC 248 MW R engaged) | closed (paper IC 248 MW R engaged) |
| Bus 15 R-bank default state | open | **open** (paper IC 0 MW; LS2 is engage) | closed + extra-R open (188 MW IC + 188 MW engage-able) |
| `load_defs` Bus 14/15 changes | none | **none** (R-bank is the load) | none (R-bank is the load) |
| Bus 14 NR effect | none | **+248 MW load → SG redistribute (G3 most)** | +248 MW (same as c') |
| Bus 15 NR effect | none | **none** (default open) | +188 MW load → ESS/SG redistribute |
| LS1 paper sign (Bus 14 trip) | reversed | **✓ matches paper** | ✓ matches paper |
| LS2 paper sign (Bus 15 engage) | ✓ matches paper | **✓ matches paper** | ✓ matches paper |
| Baseline per_M expected | -14.585 (current) | **~-14.85 to -14.95** | ~-15.20 (= paper) |
| Workload vs (a') | 0 | **+0.5 day** (Bus 14 NR re-derive) | +1 day (Bus 14+15 NR + double R-bank) |
| paper-eval comparable | half (LS1 reversed) | **full ratio_vs_DDIC** | full + absolute alignment |

**Phase 1 default = (c')** — Pareto-optimal: paper sign on both LS1 + LS2,
NR partially aligns paper (Bus 14 IC matches), workload moderate.

**Phase 2 fallback = (b'')** — invoked ONLY if (c') retrain RL improvement
falls in the marginal band (+20 % to +30 %, see §4). Adds Bus 15 IC 188 MW
via a second R-bank that is closed-by-default + engage-able extra
R-bank for LS2 dispatch. Cost: +0.5 day on top of (c'), expected gain
+3-5 pp baseline alignment.

**Phase 3 last-resort = B (Discrete solver)** — invoked if both (c') and
(b'') Phasor probes fail to give per-agent Δf > 0.05 Hz at mag = 0.5 sys-pu.

### 1.4 Why this ≠ Option E (which ABORT'd)

- Option E used **Controlled Current Source** (new node injecting current);
  Phasor algebra absorbed the injection into quasi-steady balance with
  ~5000× attenuation across all 4 ESS terminals.
- Option G uses **Three-Phase Breaker + R-bank** (topology change, not new
  node); Phasor admittance matrix is **rebuilt** when the breaker switches,
  so the V/I phasor solution is forced into a new equilibrium that the swing
  equations actually see as Pm-Pe imbalance. This is the structural
  difference that A relies on. If A still fails, B's EMT solver removes the
  Phasor simplification entirely.

---

## 2. What's already done / NOT to redo

From `e3620ec` Option E framework:
- `workspace_vars.py` — extensible spec field `valid_buses` (used by both
  CCS_LOAD_AMP and the new SWITCH_R_LOAD_AMP).
- `disturbance_protocols.py` — adapter base pattern, sentinels, dispatch
  table, `_LOAD_STEP_CCS_LOAD_SENTINELS`-style namespacing.
- `paper_eval.py` — `--disturbance-mode` choices list (extensible) +
  bus_choices selection + evaluate_policy() routing pattern.
- `scenario_loader.py::scenario_to_disturbance_type` — extensible kind
  branch.

From `9ade9a1` Option E build (CCS sections at Bus 7/9 stay in .slx but are
electrically dormant after schema demote):
- `build_kundur_cvs_v3.m` lines 365-425 (Phase A++ Trip CCS at Bus 14/15) —
  closest reference pattern to what we're adding; still in tree, untouched.
- `kundur_cvs_v3.slx` — current build is the rebase target.

---

## 3. Step-by-step execution

### Day 0: Discrete sanity dry-run (~ 4 hr, GO/NO-GO for B feasibility)

Goal: predict A→B upgrade cost before sinking 1-2 days into A. If Discrete
needs swing-eq integrator rewrites, find out now.

#### 0.1 Copy build script (~5 min)

```bash
cp scenarios/kundur/simulink_models/build_kundur_cvs_v3.m \
   scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete_test.m
```

Edit the copy:
- Top of file: change `mdl_name = 'kundur_cvs_v3'` to
  `mdl_name = 'kundur_cvs_v3_disc_test'`.
- powergui block creation: change `'SimulationMode', 'Phasor'` to
  `'SimulationMode', 'Discrete'` and add `'SampleTime', '50e-6'`.
- Save as same path; do NOT save .slx yet.

#### 0.2 Build the test model (async, ~5 min wall)

```python
mcp__simulink-tools__simulink_close_model(model_name="kundur_cvs_v3", save=False)
job = mcp__simulink-tools__simulink_run_script_async(
    code_or_file=(
        "cd('scenarios/kundur/simulink_models'); "
        "build_kundur_cvs_v3_discrete_test();"
    ),
    timeout_sec=900,
)
# poll until done; expect ~5-8 min
```

Acceptance:
- 0 errors. `kundur_cvs_v3_disc_test.slx` saved.
- If errors: read `important_lines`. Common: Discrete-Time Integrator
  required, continuous Integrator block fails. **This is exactly the signal
  we want from Day 0.** Document and decide.

#### 0.3 Compile + sanity sim (~10 min)

```python
mcp__simulink-tools__simulink_load_model(model_name="kundur_cvs_v3_disc_test")
diag = mcp__simulink-tools__simulink_compile_diagnostics(
    model_name="kundur_cvs_v3_disc_test", mode="update"
)
# Expect either: 0 errors (Discrete works with Continuous integrators OK)
# OR: errors mentioning "Continuous block in Discrete model"
```

Then a 5s open-loop sim (no disturbance) to compare omega trajectories vs
the Phasor version:

```python
mcp__simulink-tools__simulink_run_script_async(
    code_or_file="""
    mdl = 'kundur_cvs_v3_disc_test';
    rt = load('scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat');
    fns = fieldnames(rt);
    for k=1:length(fns); assignin('base', fns{k}, rt.(fns{k})); end
    for i=1:4
        assignin('base', sprintf('M_%d',i), 1.0);
        assignin('base', sprintf('D_%d',i), 1.0);
    end
    set_param(mdl, 'StopTime', '5.0');
    out = sim(mdl);
    fns_o = fieldnames(out);
    for i=1:4
        try
            ts = out.(sprintf('omega_ts_%d',i));
            d = ts.Data(:);
            fprintf('RESULT: omega_ts_%d n=%d max=%.6e min=%.6e\\n', i, length(d), max(d), min(d));
        catch ME
            fprintf('RESULT: omega_ts_%d fail: %s\\n', i, ME.message);
        end
    end
    """,
    timeout_sec=600,
)
```

Day 0 GO/NO-GO criteria (decide before A):

| Discrete dry-run outcome | A→B upgrade cost estimate | Plan effect |
|---|---|---|
| 0 errors + omega n > 100 (multi-step) + values within ±5% of Phasor | **+0.5 day** (just solver swap + IC re-validate) | A primary, B fallback cheap |
| 0 errors + omega n=2 (under-sampled) | +1 day (need ToWorkspace SampleTime tuning + decimation) | A primary, B fallback medium |
| Compile errors re Discrete-Time Integrator | **+2 day** (rewrite 9 source swing-eq integrator blocks) | A primary, B fallback high; consider direct B if Day 0 shows broken Phasor too |
| FastRestart broken in Discrete | +0.5 day (turn off FastRestart, accept 2-3× retrain time) | A primary, B + no-FastRestart |
| Sim diverges (numerical instability) | +3 day (solver tuning, Ts sweep, possibly switch to ode23tb) | reconsider whole plan; defer Discrete; pursue A only |

**Decision point:** If Discrete dry-run signals > +2 day upgrade cost,
discuss with operator before proceeding to Day 1. A becomes
"single-shot — if it fails we accept F4 v3 +18 % ceiling and write up."

#### 0.4 Cleanup (~ 5 min)

```bash
# Keep build_kundur_cvs_v3_discrete_test.m on disk (untracked) for B step
# But close + (optional) delete the test .slx to avoid confusion
rm scenarios/kundur/simulink_models/kundur_cvs_v3_disc_test.slx 2>/dev/null
rm scenarios/kundur/simulink_models/kundur_cvs_v3_disc_test_runtime.mat 2>/dev/null
```

Document Day 0 outcome in `quality_reports/plans/option_g_day0_dry_run_notes.md`
(short, 1 page, GO/NO-GO line + cost estimate).

---

### Day 0.5: alt (c') Phase 1 feasibility check at Bus 14/15 (~ 20 min, MUST precede Day 1)

**NR alt is LOCKED to (c') Phase 1** (see §1.3). This audit verifies the
two preconditions for (c') to succeed:

1. `load_defs` does NOT already include Bus 14 / Bus 15 entries (else
   double-count). From the file inspection in §0 pre-read item 6:
   `load_defs` only contains Load7 (967 MW) + Load9 (1767 MW) — Bus 14/15
   are clean for the new R-bank to take ownership. ✅ verified 2026-04-30.

2. SG capacity is sufficient to absorb Bus 14 +248 MW redispatch:
   - Each SG capacity = 7 GVA (paper Sec.IV-A); pre-Option-G dispatch
     Pmg_g ∈ {7.00, 7.00, 7.19} sys-pu (Sbase = 100 MVA, so 700/700/719 MW).
   - +248 MW total ÷ 3 SGs ≈ +0.83 sys-pu/SG ⇒ post-redispatch ~7.83 sys-pu
     each (still < SG capacity 70 sys-pu, very safe).

Run the audit:

```bash
# Confirm load_defs has no Bus 14/15 entries:
grep -n "load_defs\s*=" scenarios/kundur/simulink_models/build_kundur_cvs_v3.m
grep -n "'Load1[45]'" scenarios/kundur/simulink_models/build_kundur_cvs_v3.m
# Expected: 0 hits for 'Load14'/'Load15' (only Load7, Load9 in load_defs).

# Confirm SG capacity headroom:
PY="/c/Users/27443/miniconda3/envs/andes_env/python.exe"
"$PY" -c "
import json
ic = json.load(open('scenarios/kundur/kundur_ic_cvs_v3.json'))
import numpy as np
sg_pm0 = np.array(ic.get('sg_pm0_sys_pu', ic.get('powerflow', {}).get('dyn_pinj_sys_pu', [])[:3]))
print(f'pre-Option-G sg_pm0_sys_pu = {sg_pm0}')
expected_post = sg_pm0 + 2.48 / 3.0  # split +2.48 sys-pu across 3 SGs
print(f'expected post-(c\\') sg_pm0_sys_pu ≈ {expected_post}')
# Each SG individual capacity (paper) = 7 GVA / 100 MVA = 70 sys-pu, abundant
print('all SG within capacity:', all(p < 70.0 for p in expected_post))
"
```

**Acceptance:** both conditions pass. If load_defs has Bus 14/15 entries
(unlikely but possible if someone added them recently), STOP and decide
whether to remove them (and update IC) or revert to alt (a') — discuss
with operator.

**Output:** 1-paragraph note in `quality_reports/plans/option_g_day0_feasibility_audit.md`
documenting (c') Phase 1 preconditions PASSED + planned NR redispatch.

---

### Day 1-2: A — Switch + R-bank build (Phasor)

#### 1.1 Build script edit (~2 hr code)

Edit `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m`:

##### 1.1.1 Add load-step bus definition (around line 181, after ccs_load_defs)

```matlab
% Option G (2026-04-30): Switch + R-bank LoadStep at paper Bus 14 / 15.
% Paper Sec.IV-A: "Four ESS WITH LOADS separately connected to different
% areas". Bus 14/15 are simultaneously ESS terminals AND load buses.
% Paper Sec.IV-C: "Load step 1 ... 248MW at bus 14"
%                 "Load step 2 ... 188MW at bus 15"
% Drives a Three-Phase Breaker + Series RLC R-bank topology change at
% runtime; replaces the compile-frozen LoadStep R-block (D-T2 dead).
%
% NR alt = (c') Phase 1 default (see §1.3 of plan):
%   Bus 14 R-bank default state = CLOSED (R engaged at IC = 248 MW load
%          present in NR; paper LS1 trip = open breaker = remove load)
%   Bus 15 R-bank default state = OPEN  (R disengaged at IC = 0 MW load
%          on Bus 15 in NR; paper LS2 engage = close breaker = add load)
%   load_defs (line 126-129) UNCHANGED — R-bank IS the Bus 14/15 load,
%          not "extra on top of an existing entry".
%
% Paper-faithful sign on both LS1 + LS2:
%   Bus 14 (paper LS1 trip): IC has 248 MW load via closed R-bank;
%          dispatch sets SwitchRLoad_amp_bus14 = 0 → breaker opens →
%          R disengages → freq UP (paper sign ✓)
%   Bus 15 (paper LS2 engage): IC has 0 MW on Bus 15;
%          dispatch sets SwitchRLoad_amp_bus15 = 188e6 → breaker closes →
%          R engages 188 MW → freq DOWN (paper sign ✓)
%
% Schema convention (driven by Compare-to-zero block):
%   amp > eps → breaker closed → R engaged
%   amp <= 0  → breaker open   → R disengaged
%
% Asymmetric IC defaults are implemented via per-bus `default_state`
% column; the runtime_consts seed (§1.1.3) writes the matching amp value
% so the t=0 breaker InitialState and the workspace var are consistent.
switch_r_load_defs = {
    % name,                bus, label,    paper_amp_W, default_state
    'SwitchRLoad_bus14',  14, 'bus14',  248e6,        'closed';
    'SwitchRLoad_bus15',  15, 'bus15',  188e6,        'open';
};
```

##### 1.1.2 Build loop (insert after Phase A++ CCS Trip section, ~line 425)

```matlab
% Option G: Three-Phase Breaker + Series RLC R-bank at paper LoadStep buses.
% Topology:
%   Bus_<N>  --[Breaker (ctrl)]--[R-bank (Series RLC R)]--[GND]
% At t=0, breaker closed, R engaged at IC value (taken from runtime_consts).
% At dispatch trigger: env writes SwitchRLoad_amp_bus<N> to non-zero
% (engage) or zero (trip). The Constant block driving the breaker control
% gate decodes this: ctrl = (amp > eps).
for k = 1:size(switch_r_load_defs, 1)
    name           = switch_r_load_defs{k, 1};
    bus            = switch_r_load_defs{k, 2};
    bus_label      = switch_r_load_defs{k, 3};
    paper_amp_w    = switch_r_load_defs{k, 4};
    default_state  = switch_r_load_defs{k, 5};   % 'closed' | 'open'

    brk_name   = sprintf('Breaker_%s',   name);
    rbank_name = sprintf('Rbank_%s',     name);
    ctrl_name  = sprintf('CtrlAmp_%s',   name);
    decode_nm  = sprintf('CtrlGate_%s',  name);  % Compare-to-zero -> bool
    gnd_name   = sprintf('GND_%s',       name);

    yposG  = 1100 + (k-1) * 110;
    bxG    = 1100;

    % 1. Constant: workspace var amp (W). Default seed value matches
    %    `default_state` — see runtime_consts (§1.1.3).
    add_block('simulink/Sources/Constant', [mdl '/' ctrl_name], ...
        'Position', [bxG-200 yposG bxG-140 yposG+20], ...
        'Value', sprintf('SwitchRLoad_amp_%s', bus_label));

    % 2. Compare-to-zero: amp > eps -> 1 (closed) else 0 (open)
    add_block('simulink/Logic and Bit Operations/Compare To Zero', ...
        [mdl '/' decode_nm], ...
        'Position', [bxG-100 yposG bxG-40 yposG+20], ...
        'relop', '>');

    add_line(mdl, [ctrl_name '/1'], [decode_nm '/1'], ...
        'autorouting', 'smart');

    % 3. Three-Phase Breaker (single-phase model: 1 LConn + 1 RConn + ctrl)
    %    Use 'powerlib/Elements/Breaker' (single-phase) for Phasor.
    %    InitialState matches per-bus default_state (alt c' Phase 1):
    %       Bus 14 -> InitialState '1' (closed, IC R engaged)
    %       Bus 15 -> InitialState '0' (open, IC R disengaged)
    if strcmp(default_state, 'closed')
        brk_initial = '1';
    else
        brk_initial = '0';
    end
    add_block('powerlib/Elements/Breaker', [mdl '/' brk_name], ...
        'Position', [bxG yposG bxG+60 yposG+60], ...
        'BreakerControl', 'external', ...
        'InitialState', brk_initial);
    add_line(mdl, [decode_nm '/1'], [brk_name '/1'], ...
        'autorouting', 'smart');

    % 4. R-bank: Series RLC R block. Resistance fixed at paper IC value
    %    V^2 / paper_amp_w (compile-frozen string is OK here — it's a
    %    constant; the topology change comes from breaker, not from
    %    re-evaluating R).
    R_paper = (Vbase_const^2) / paper_amp_w;  % ohms

    add_block('powerlib/Elements/Series RLC Branch', [mdl '/' rbank_name], ...
        'Position', [bxG+90 yposG bxG+150 yposG+60], ...
        'BranchType', 'R', ...
        'Resistance', sprintf('%.6e', R_paper));

    % 5. Wire breaker RConn -> rbank LConn -> GND
    add_block('powerlib/Elements/Ground', [mdl '/' gnd_name], ...
        'Position', [bxG+200 yposG+30 bxG+240 yposG+50]);

    add_line(mdl, [brk_name '/RConn1'], [rbank_name '/LConn1'], ...
        'autorouting', 'smart');
    add_line(mdl, [rbank_name '/RConn1'], [gnd_name '/LConn1'], ...
        'autorouting', 'smart');

    % 6. Bus anchoring: breaker LConn registered at bus
    register(bus, [brk_name '/LConn1']);

    % 7. UserData mark for downstream introspection
    set_param([mdl '/' brk_name], 'UserDataPersistent', 'on', ...
        'UserData', struct('bus', bus, 'bus_label', bus_label, ...
                           'mode', 'switch_r_load_breaker', ...
                           'default_state', default_state, ...
                           'paper_amp_w', paper_amp_w));
end
```

##### 1.1.3 Runtime consts seed (insert after CCS load runtime seed, ~line 1011)

```matlab
% Option G runtime seed — alt (c') Phase 1: asymmetric default state
% per paper Sec.IV-C semantics (LS1 trip, LS2 engage):
%   Bus 14 default = closed → seed amp > 0 to match (paper IC R = 248 MW
%          engaged; SwitchRLoad_amp_bus14 = 248e6 ⇒ Compare-to-zero outputs
%          1 ⇒ breaker closed at t=0 ⇒ R engaged ⇒ NR includes 248 MW load
%          on Bus 14).
%   Bus 15 default = open  → seed amp = 0 to match (paper IC has no Bus 15
%          load; SwitchRLoad_amp_bus15 = 0 ⇒ Compare-to-zero outputs 0 ⇒
%          breaker open at t=0 ⇒ R disengaged ⇒ NR has no Bus 15 load).
% Adapter (LoadStepSwitchRBank.apply) flips the amp at trigger time:
%   Bus 14 trip dispatch: write SwitchRLoad_amp_bus14 = 0 → breaker opens
%   Bus 15 engage dispatch: write SwitchRLoad_amp_bus15 = 188e6 → breaker
%          closes
runtime_consts.SwitchRLoad_amp_bus14 = double(248e6);  % closed at IC (LS1)
runtime_consts.SwitchRLoad_amp_bus15 = double(0.0);    % open at IC (LS2)
```

> **NR/IC = alt (c') Phase 1 default — see §1.3 of plan.**
>
> The seed values above are NOT alt-conditional — they are the (c') hard
> defaults: Bus 14 amp = 248e6 (closed at IC); Bus 15 amp = 0 (open at IC).
> This implements paper LS1 trip at Bus 14 (default load present, dispatch
> removes it) and paper LS2 engage at Bus 15 (default no load, dispatch
> adds it).
>
> **NR re-derive REQUIRED**: Bus 14 IC now has +248 MW load that did not
> exist in the pre-Option-G IC. Step 3 NR/IC validation must re-run
> `compute_kundur_cvs_v3_powerflow` AFTER this build, regenerate
> `kundur_ic_cvs_v3.json`, and verify:
>   - vsg_pm0_pu unchanged (< 1e-6) — ESS dispatch is PV-bus, NR projects
>     the +248 MW onto SG capacity, not ESS.
>   - sg_pm0_sys_pu shifts: G1/G2/G3 each absorb roughly +0.83 sys-pu
>     (split 248/3 MW). Per-SG end value should remain ≤ 1.0 sys-pu;
>     paper-realistic SG capacity 7 GVA each, so post-redispatch dispatch
>     ratio ~0.78-0.80 — safe.
>   - aggregate_residual_pu < 1e-3 (NR converges; system feasible).
>
> If any of these fail (e.g. SG ≥ 1.0 sys-pu, NR diverges, vsg_pm0_pu
> changes), see plan §6 rollback options.
>
> **Phase 2 (b'') fallback** (see §3.5) adds a *second* R-bank at Bus 15
> with `default_state='closed'` and `paper_amp_w=188e6`, plus extends
> the existing Bus 15 R-bank to be the *engage extra* one. This is only
> built if Phase 1 (c') retrain RL improvement falls in the +20–30 %
> marginal band (§4 acceptance).

#### 1.2 Schema entry (~ 30 min code)

`scenarios/kundur/workspace_vars.py`:

```python
_V3_LOAD_STEP_BUSES = frozenset({14, 15})  # already implicit; add explicit constant
# (or reuse _V3_BUSES if back-compat allows; cleaner to make explicit)

# Add to _SCHEMA dict, after CCS_LOAD_AMP entry:
"SWITCH_R_LOAD_AMP": WorkspaceVarSpec(
    template="SwitchRLoad_amp_bus{bus}",
    family=IndexFamily.PER_BUS,
    profiles=frozenset({PROFILE_CVS_V3}),
    description=(
        "Three-Phase Breaker + R-bank load-step amp at Bus 14/15 (W, "
        "system base). Option G (2026-04-30): replaces the compile-frozen "
        "Series RLC R LoadStep block (D-T2). Sign convention: +amp = "
        "engage R (freq DOWN); 0 amp = breaker open / R disengage "
        "(freq UP, paper LoadStep trip direction). Channel marked "
        "effective on the basis of build (compile clean) + IC equivalence "
        "(Pm0 diff < 1e-6 vs pre-Option-G IC); demote on Probe G "
        "sign-pair smoke failure."
    ),
    valid_buses=_V3_LOAD_STEP_BUSES,
),
```

#### 1.3 Adapter (~ 1 hr code)

`scenarios/kundur/disturbance_protocols.py` — new family `LoadStepSwitchRBank`,
mirror `LoadStepCcsLoadCenter` shape. **Adapter implements alt (c') Phase 1
asymmetric default state** (Bus 14 closed, Bus 15 open):

- ls_bus accepts {14, 15, "random_load_step"} (sentinel namespace
  `_LOAD_STEP_SWITCH_R_SENTINELS = frozenset({"random_load_step"})`)
- random_load_step → 50/50 pick of (bus=14, paper LS1 trip) vs
                                   (bus=15, paper LS2 engage)
- Magnitude semantic, alt (c') Phase 1 — opposite-direction-from-default:
    - **bus=14 (paper LS1 trip)**: default state CLOSED ⇒ apply writes
      `SwitchRLoad_amp_bus14 = 0` to open the breaker → R disengages →
      the IC 248 MW load disappears → freq UP. Magnitude scaling NOT
      modulated (paper LS1 is a single fixed step, the breaker is
      binary); `|magnitude_sys_pu|` is checked against a minimum
      threshold (e.g. ≥ 0.1 sys-pu) to gate the trigger but the actual
      amp written is always 0 W. This keeps the dispatch binary and
      paper-faithful.
    - **bus=15 (paper LS2 engage)**: default state OPEN ⇒ apply writes
      `SwitchRLoad_amp_bus15 = 188e6` to close the breaker → R engages
      188 MW load → freq DOWN. Same magnitude-gates-trigger semantics.
- Sign of magnitude_sys_pu in (c') Phase 1: positive keeps paper
  direction (Bus 14 trip / Bus 15 engage); negative is a no-op
  (out-of-domain in (c') Phase 1, since each bus has a single fixed
  paper direction). For training with random sign:
    - if mag > 0: dispatch as above
    - if mag < 0: dispatch is **skipped** (zero disturbance); the
      scenario is silently a "null disturbance" sample. SAC sees the
      no-disturbance case as a regularization signal.
    - Alternative (more aggressive): treat mag < 0 as "wrong-direction
      flip" — Bus 14 mag<0 → engage the existing 248 MW R-bank as
      *extra* on top, requiring a second R-bank (deferred to Phase 2
      (b''), see §3.5).
- Silence PM + PMG families (mirror LoadStepCcsLoadCenter).
- Use `require_effective=True` when resolving SWITCH_R_LOAD_AMP; the
  schema starts effective on build + IC re-derive + Step 3 acceptance,
  demote on Probe G smoke failure (mirror Option E pattern).

Smoke test:
```python
class MockBridge:
    def __init__(self): self.writes = []
    def apply_workspace_var(self, k, v): self.writes.append((k, float(v)))

class MockCfg:
    model_name = 'kundur_cvs_v3'; n_agents = 4; sbase_va = 100e6

p14 = resolve_disturbance('loadstep_switch_r_bus14')
mb = MockBridge()
trace = p14.apply(mb, +0.5, np.random.default_rng(0), 2.0, MockCfg())
assert mb.writes[0] == ('SwitchRLoad_amp_bus14', 0.0)  # trip
# (or whatever convention the adapter implements)
```

Add 3 dispatch entries:
```python
"loadstep_switch_r_bus14": lambda: LoadStepSwitchRBank(ls_bus=14),
"loadstep_switch_r_bus15": lambda: LoadStepSwitchRBank(ls_bus=15),
"loadstep_switch_r_random_load_step":
    lambda: LoadStepSwitchRBank(ls_bus="random_load_step"),
```

Default training disturbance type: `loadstep_switch_r_random_load_step`
(50/50 between paper LS1 trip @ Bus 14 and paper LS2 engage @ Bus 15);
this is the most paper-faithful 4-ESS coordination training set.

#### 1.4 scenario_loader + config_simulink + paper_eval (~ 30 min)

`scenarios/kundur/scenario_loader.py`:
```python
if scenario.disturbance_kind == "switch_r_load":
    if scenario.target in (14, 15):
        return f"loadstep_switch_r_bus{scenario.target}"
    raise ValueError(f"unsupported switch_r_load target {scenario.target}")
```

`scenarios/kundur/config_simulink.py::KUNDUR_DISTURBANCE_TYPES_VALID`:
```python
"loadstep_switch_r_bus14",
"loadstep_switch_r_bus15",
"loadstep_switch_r_random_load_step",
```

`evaluation/paper_eval.py`:
- `--disturbance-mode` choices: add `"switch_r_load"`
- main() bus_choices: `elif args.disturbance_mode == "switch_r_load": bus_choices = (14, 15)`
- evaluate_policy() routing: insert before `bus == 7` branch:
  ```python
  if bus in (14, 15) and disturbance_mode == "switch_r_load":
      _kind, _target = "switch_r_load", int(bus)
  ```

#### 1.5 Probe G smoke driver (~ 30 min)

`probes/kundur/probe_g_sign_pair.py` — copy `probe_e_sign_pair.py` with:
- protocol = `loadstep_switch_r_busN`
- mode = `switch_r_load`
- bus options {14, 15}
- Same PASS_HZ=0.05 / ABORT_HZ=0.01 thresholds

#### 1.6 Build async + verify (~ 20 min wall)

```python
mcp__simulink-tools__simulink_close_model(model_name="kundur_cvs_v3", save=False)
job = mcp__simulink-tools__simulink_run_script_async(
    code_or_file=(
        "cd('scenarios/kundur/simulink_models'); build_kundur_cvs_v3();"
    ),
    timeout_sec=900,
)
# poll until done
```

Acceptance:
- 0 errors. .slx saved (~ 510-530 KB; +5-10 blocks per breaker × 2 buses).
- runtime.mat has SwitchRLoad_amp_bus14/15.
- Compile clean after assignin runtime_consts to base.

### Step 3 (Day 2): NR/IC re-derive + consistency check (alt c' specific)

**Different from Option E Step 3** — Option G alt (c') Phase 1 changes the
NR baseline by adding +248 MW load on Bus 14. NR must be re-run AND
`kundur_ic_cvs_v3.json` regenerated, NOT just verified for equality.

#### 3.1 Backup current IC + regenerate

```bash
cp scenarios/kundur/kundur_ic_cvs_v3.json \
   scenarios/kundur/kundur_ic_cvs_v3.json.pre_option_g.bak
```

```python
# Run NR with new build (Bus 14 R-bank closed at IC = 248 MW load engaged)
mcp__simulink-tools__simulink_run_script(
    code_or_file="""
    cd('C:\\Users\\27443\\Desktop\\Multi-Agent  VSGs');
    addpath('scenarios/kundur/matlab_scripts');
    out_path = 'scenarios/kundur/kundur_ic_cvs_v3.json';
    pf = compute_kundur_cvs_v3_powerflow(out_path);
    fprintf('RESULT: converged=%d max_mismatch_pu=%.3e\\n', ...
            pf.converged, pf.max_mismatch_pu);
    fprintf('RESULT: vsg_pm0_pu = %s\\n', mat2str(pf.vsg_pm0_pu, 5));
    fprintf('RESULT: sg_pm0_sys_pu = %s\\n', mat2str(pf.dyn_pinj_sys_pu(1:3), 5));
    """,
    timeout_sec=180,
)
```

#### 3.2 Acceptance for alt (c') Phase 1

```bash
PY="/c/Users/27443/miniconda3/envs/andes_env/python.exe"
"$PY" -c "
import json, numpy as np
old = json.load(open('scenarios/kundur/kundur_ic_cvs_v3.json.pre_option_g.bak'))
new = json.load(open('scenarios/kundur/kundur_ic_cvs_v3.json'))

# vsg_pm0_pu MUST be unchanged (ESS is PV-bus in NR; +248 MW Bus 14 load
# absorbed by SG redispatch, not ESS).
diff_vsg = np.max(np.abs(np.array(old['vsg_pm0_pu']) - np.array(new['vsg_pm0_pu'])))
print(f'vsg_pm0_pu max abs diff: {diff_vsg:.3e}  (acceptance < 1e-6)')
assert diff_vsg < 1e-6, 'vsg_pm0_pu changed — ESS PV-bus assumption broken'

# sg_pm0_sys_pu SHOULD increase by ~+0.83 sys-pu / SG (split 248/3 MW),
# total +2.48 sys-pu across 3 SGs.
old_sg = np.array(old['sg_pm0_sys_pu'])
new_sg = np.array(new['sg_pm0_sys_pu'])
total_delta = float(np.sum(new_sg - old_sg))
print(f'sg_pm0_sys_pu: old = {old_sg}')
print(f'sg_pm0_sys_pu: new = {new_sg}')
print(f'sg_pm0_sys_pu: total delta = {total_delta:+.3f} sys-pu  (expected ~ +2.48)')
assert 2.0 < total_delta < 3.0, f'SG redispatch unexpected: {total_delta}'
assert all(s <= 1.0 for s in new_sg), f'SG dispatch exceeds 1.0 sys-pu: {new_sg}'
print('Step 3 (alt c\\') PASS: vsg_pm0 unchanged + SG redispatch +2.48 + all SG <= 1.0 sys-pu')
"
```

If acceptance fails:

| failure | likely cause | action |
|---|---|---|
| vsg_pm0_pu changed | NR projects Bus 14 load onto ESS instead of SG | flip ESS PV→Slack handling in compute script (out of scope; defer); fall back to alt (a') current keep-status-quo |
| SG sys-pu > 1.0 | SG capacity exceeded by +248 MW redispatch | unphysical; verify SG capacity setting in NR script or reduce paper LS1 magnitude in (c') |
| NR diverges | system infeasible with +248 MW load | regenerate runtime.mat with corrected Pmg defaults; if persists, flag (c') as build-broken and consider alt (b'') |

#### 3.3 Regenerate runtime.mat

```python
# After NR regenerates IC, the build script needs to be re-run so
# runtime_consts.mat picks up the new sg/wind Pm0 values:
mcp__simulink-tools__simulink_run_script_async(
    code_or_file=(
        "cd('scenarios/kundur/simulink_models'); build_kundur_cvs_v3();"
    ),
    timeout_sec=600,
)
# poll until done; .slx + runtime.mat both refreshed
```

### Step 4 (Day 2-3): Probe G sign-pair smoke (CRITICAL GATE)

Run Probe G at Bus 14 then Bus 15, mag = ±0.5 sys-pu.

Acceptance (plan §5):
- per-agent (|nadir_diff| + |peak_diff|) > 0.05 Hz on at least 1 agent
  on EITHER Bus 14 or Bus 15 → A PASS, proceed to Step 5.
- All agents diff in [0.01, 0.05) Hz → MARGINAL → A weak; consider B.
- All agents diff < 0.01 Hz on both buses → A FAIL → escalate to B.

### Step 5a (Day 3, A PASS path): 50-scenario no_control eval + retrain

Mirror Option E Step 6-8, but with `--disturbance-mode switch_r_load`.
Wall: ~ 12 min no_control + 70 min retrain + 30 min 3-policy eval.

### Step 5a' (Day 3.5, A PASS but MARGINAL — Phase 2 (b'') upgrade)

**Trigger condition:** alt (c') Phase 1 retrain best.pt RL improvement
falls in [+18 %, +30 %) — beats F4 v3 baseline but does not close the
gap to paper +47 %. Hypothesis: Bus 15 IC = 0 (no LS2 paper IC load
during default operation) suppresses ES4's "near-disturbance" reward
share, capping mode-shape diversity. Adding a closed-by-default Bus 15
R-bank with paper IC 188 MW load + an extra engage-able R-bank for LS2
dispatch should align baseline NR closer to paper -15.20 and unlock ES4.

**Cost: +0.5 day** (build edit + NR re-derive + retrain).

#### 5a'.1 Build script edit — add Bus 15 base R-bank + extra R-bank

```matlab
% Phase 2 (b'') upgrade — adds the paper-IC 188 MW load on Bus 15 as a
% closed-by-default R-bank (renamed RbankBase_bus15) AND keeps the
% existing engage-able R-bank (renamed RbankExtra_bus15) for LS2 dispatch.
% Bus 14 unchanged (already alt c' default closed at 248 MW).
switch_r_load_defs = {
    % name,                     bus, label,    paper_amp_W, default_state, role
    'SwitchRLoad_bus14',       14, 'bus14',  248e6,        'closed',  'paper_LS1';
    'SwitchRLoadBase_bus15',   15, 'bus15',  188e6,        'closed',  'paper_IC';   % NEW
    'SwitchRLoadExtra_bus15',  15, 'bus15',  188e6,        'open',    'paper_LS2';
};
```

The build loop (§1.1.2) needs to disambiguate `bus_label` vs unique
block name when 2+ entries share a bus — use the full `name` field for
block path uniqueness. Two breakers + two R-banks at Bus 15.

#### 5a'.2 Adapter update — add Bus 15 base/extra distinction

`LoadStepSwitchRBank.apply()` for bus=15 in Phase 2 must now write
**both** `SwitchRLoadBase_bus15_amp` (kept = 188e6, baseline IC R) and
`SwitchRLoadExtra_bus15_amp` (toggled 0 ↔ 188e6 for LS2 dispatch).
Schema gets a new `SWITCH_R_LOAD_EXTRA_AMP` family.

#### 5a'.3 NR re-derive

Now Bus 14 has +248 MW (closed Base R) and Bus 15 has +188 MW (closed
Base R, extra R open). Total +436 MW load → SG redispatch ≈ +1.45 sys-pu
each. Same Step 3 acceptance protocol but with updated expected delta.

#### 5a'.4 Retrain (~70 min) + 3-policy eval (~30 min)

Same protocol as 5a but with the Phase 2 build. Expected gain over
Phase 1: +3-7 pp baseline alignment (ES4 r_f share boost) + +2-4 pp
absolute RL improvement.

**Phase 2 acceptance:** RL improvement ≥ +30 %. If still < +30 % after
Phase 2 (b''), escalate to Step 5b (Discrete solver, Phase 3).

### Step 5b (Day 4-7, A or A+(b'') FAIL → B path): Discrete solver swap

Apply Day 0 dry-run learnings:
- powergui Discrete + Ts=50μs in main build_kundur_cvs_v3.m
- (if Day 0 said integrators need rewriting): rewrite 9 source swing-eq
  Continuous Integrator → Discrete-Time Integrator
- Re-run NR (compute_kundur_cvs_v3_powerflow) — verify Pm0 still matches
  (within Discrete numerical tolerance, ~1e-5)
- Re-run Probe G smoke — should PASS now with paper-class signal
- 350 ep retrain in Discrete: ~12 hr wall (instead of 70 min)
- 3-policy eval: ~ 4 hr (Discrete is slower per scenario)

### Step 6 (Day 4-8): Final RL verdict + commits

Same commit chain shape as Option E (build + framework + smoke verdict +
retrain + verdict). Either:
- A path: 4-5 commits, ~Day 4 done
- B path: 5-6 commits, ~Day 7-8 done

---

## 4. Acceptance criteria summary

Phase chain: **Phase 1 (c') → conditional Phase 2 (b'') → conditional
Phase 3 B (Discrete)**. Each phase gated on prior phase's outcome.

| Stage | Gate | Phase 1 PASS → STOP | Phase 1 MARGINAL → Phase 2 | Phase 1 FAIL → Phase 3 |
|-------|------|---|---|---|
| Day 0 | Discrete dry-run no integrator-rewrite needed | n/a | n/a | predictive: feasible/not |
| Day 1-2 | Phase 1 (c') build clean, compile, vsg_pm0 unchanged, SG ≤ 1.0 | yes | yes | yes |
| Day 2 | Step 3 NR re-derive: total SG delta ≈ +2.48 sys-pu | pass | pass | pass |
| Day 2-3 | Probe G max diff (Hz) | ≥ 0.05 (≥ 1 agent) | 0.01-0.05 | < 0.01 (all agents) |
| Day 3-4 | Phase 1 retrain RL improvement | **≥ +30 %** → STOP | **+18 to +30 %** → Phase 2 | n/a (probe failed) |
| Day 4 | Phase 2 (b'') build + retrain RL improvement | n/a | **≥ +30 %** → STOP, else Phase 3 | n/a |
| Day 5-7 | Phase 3 B retrain RL improvement | n/a | n/a | ≥ +30 % (B PASS) |

**Stretch goal:** ≥ +40 % (closes 22 pp of 29 pp gap; gap-to-paper 7 pp)
**Realistic goal:** ≥ +30 % (closes 12 pp; comparable to typical
state-of-the-art Phasor + Switch+R replication)
**Floor (above which the plan is "successful"):** ≥ +25 % (beats F4 v3
+18 % by 7 pp; demonstrates dispatch+IC fix contributes meaningfully
even if doesn't reach paper level)

### Phase decision tree (compact)

```
Phase 1 (c')  build (1 day) + Probe G (15 min) + retrain (70 min)
    ├── Probe G < 0.01 Hz       → Phase 3 B (Discrete)
    ├── Probe G in [0.01, 0.05) → Phase 1 weak → consider Phase 3 B directly
    ├── Probe G ≥ 0.05 + retrain ≥ +30 %  → STOP, write up
    ├── Probe G ≥ 0.05 + retrain in [+18, +30) → Phase 2 (b'')
    └── Probe G ≥ 0.05 + retrain < +18 %  → unexpected; debug Phase 1 reward landscape
                                              before Phase 2

Phase 2 (b'') build edit (0.5 day) + retrain (70 min) + 3-policy eval
    ├── retrain ≥ +30 % → STOP, write up
    ├── retrain in [+25, +30) → marginal Phase 2 success; decide:
    │       (i) accept +25-30 % as ceiling (write up), or
    │       (ii) Phase 3 B for +5 pp more
    └── retrain < +25 % → Phase 3 B

Phase 3 B Discrete (Day 0 dry-run cost-aware) build solver swap
    + IC re-derive + retrain (12 hr) + 3-policy eval (4 hr)
    ├── retrain ≥ +35 % → STOP (best case)
    ├── retrain in [+18, +35) → STOP, write up "Discrete cap"
    └── retrain < +18 % → catastrophic; rollback all, accept F4 v3 +18 %
```

---

## 5. Risk register

| # | Risk | Probability | Mitigation |
|---|------|---|---|
| 1 | A signal still weak (Phasor attenuates Switch wave) | MEDIUM | Probe G gates at Step 4; B fallback ready |
| 2 | Discrete integrator rewrite needed (~+2 day) | LOW | Day 0 dry-run predicts; if hit, A→B cost is up-front clear |
| 3 | NR (c') re-derive fails: vsg_pm0_pu changes, or SG > 1.0 sys-pu, or NR diverges | LOW (load_defs verified Bus 14/15 clean; SG capacity 70 sys-pu) | Day 0.5 feasibility audit + Step 3 §3.2 acceptance gates; if fail, fall back to alt (a') keep-status-quo or escalate to alt (b'') Phase 2 |
| 4 | Discrete sim diverges (numerical instability) | LOW | Day 0 dry-run; ode23tb fallback; Ts sweep |
| 5 | FastRestart broken in Discrete | LOW | Disable FastRestart, accept 2-3× retrain time |
| 6 | Bus 14/15 paper-asymmetric LS1/LS2 protocol mismatch | MEDIUM | Adapter design choice; 50/50 random_load_step picks one direction per scenario; preserves paper protocol shape |
| 7 | Bus 14/15 wiring (1 km Pi-line) gives weaker signal than paper "without Pi-line" assumption | LOW | Paper Fig.6 also shows asymmetric "near vs far" mode shape — 1 km Pi-line interpretation is consistent with paper text. If signal still weak under both A and B, the gap is in solver / reward landscape, NOT bus location |
| 8 | retrain wall in B is too long for sweep | MEDIUM | Day 0 sets expectations; if > 12 hr/run, reduce to 1-2 best PHI/DIST runs only |
| 9 | Bus 14/15 = ESS terminal direct connection (D-T1 misread baggage) propagates into wrong fix | LOW | This plan re-reads paper PDF directly; D-T1 dictionary update is a side task (§11), not a blocker. Plan 选择 Bus 14/15 是 paper-faithful (Sec.IV-A "with loads" + Sec.IV-C "load step at bus 14/15" + Fig.6 "near vs far"), not Bus 7/9 |

---

## 6. Rollback procedures

### If Day 0 dry-run fails badly (>+3 day for Discrete)

Stop plan; write `option_g_day0_abort_notes.md`; recommend operator
accept F4 v3 +18 % as ceiling, write paper.

### If A FAIL + B PASS

A artifacts kept (Switch + R-bank framework reusable). Keep all schema +
adapter + dispatch changes. Solver swap commit notes B as the path that
worked.

### If A FAIL + B FAIL

Probe G again says < 0.01 Hz under Discrete + Switch — would mean
fundamental wiring issue. Roll back .slx + build script; keep Python
framework. Recommend accept F4 v3 +18 % ceiling.

### If Day 3 A PASS but retrain RL improvement < +18 %

Means Switch+R provides signal but reward landscape still degenerate (PHI
lock too tight, ES2 still dead). Try B as next move; or PHI sweep on A
artifacts (cheap, ~3-4 hr).

---

## 7. What NOT to do

1. **Don't skip Day 0.** Predicting A→B upgrade cost is the entire reason
   to do Day 0; otherwise you're guessing whether to direct-B-or-A-first.
2. **Don't change PHI lock or DIST_MAX during this plan.** Same reasons as
   Option E §7. Run a separate PHI sweep after the dispatch protocol
   converges.
3. **Don't touch reward formula, SAC, env, bridge.** Out of scope.
4. **Don't run multiple sims in parallel.** Single MATLAB engine.
5. **Don't bypass Probe G smoke.** A failure must be verified with sign-pair
   data, not assumed; otherwise B might be triggered unnecessarily.
6. **Don't roll back Option E commits.** Schema framework is reused.
7. **Don't merge to main with Probe G smoke = MARGINAL** without explicit
   operator decision. Marginal A is a real ambiguity case.

---

## 8. References

### Project-level
- `CLAUDE.md` — path dictionary
- `AGENTS.md` — MCP routing
- `scenarios/kundur/NOTES.md` — project memory
- `docs/paper/kundur-paper-project-terminology-dictionary.md` — D-T mapping

### Today's commit chain (3 commits — Option E)
```
e11ee0a  test(kundur-cvs-v3): Option E ABORT — Probe E sign-pair Bus 7/9 << 0.01 Hz
e3620ec  feat(kundur-cvs-v3): Option E dispatch framework — schema/adapter/loader/eval CLI/probe
9ade9a1  feat(kundur-cvs-v3): Option E build — CCS @ Bus 7/9 load center (electrically dormant)
```

### Yesterday's commit chain (5 commits — F4 v3 SOTA)
```
1a76f44  test(kundur-cvs-v3): B-c PHI=0 ablation FAILED — F4 v3 +18% is project ceiling
589c2d2  test(kundur-cvs-v3): B-a action ablation + B-d DIST_MAX scan — ES2 dead weight
6a38eb7  test(kundur-cvs-v3): F4 v3 retrain — first 4-agent paper-class anchor (+18% RL improvement)
2baecda  feat(kundur-cvs-v3): F4 sign-flip + DIST=3.0 hits paper-baseline magnitude
4df9857  feat(kundur-cvs-v3): Option F4 (HybridSgEssMultiPoint) implementation + sign-pair PASS
```

### Key file paths for Option G
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3.m` — main build
  script (edit for switch_r_load_defs + build loop + runtime seed)
- `scenarios/kundur/simulink_models/build_kundur_cvs_v3_discrete_test.m` —
  Day 0 sanity dry-run copy
- `scenarios/kundur/simulink_models/kundur_cvs_v3.slx` — to be rebuilt
- `scenarios/kundur/simulink_models/kundur_cvs_v3_runtime.mat` — auto-rebuilt
- `scenarios/kundur/disturbance_protocols.py` — add LoadStepSwitchRBank
- `scenarios/kundur/workspace_vars.py` — add SWITCH_R_LOAD_AMP family
- `scenarios/kundur/scenario_loader.py` — switch_r_load route
- `scenarios/kundur/config_simulink.py` — 3 valid types
- `evaluation/paper_eval.py` — switch_r_load mode + bus_choices + routing
- `probes/kundur/probe_g_sign_pair.py` — new smoke driver

### Reference implementations
- `LoadStepCcsInjection` at `scenarios/kundur/disturbance_protocols.py`
  lines ~530-605 — pattern for Family Phasor CCS (now ABORT'd, but
  adapter shape is reusable)
- `LoadStepCcsLoadCenter` lines ~615-735 — closest pattern; copy + replace
  CCS writes with breaker amp writes
- `build_kundur_cvs_v3.m` lines 365-425 — Phase A++ Trip CCS pattern;
  reference for the (Constant → Decoder → Element → GND) shape
- `build_kundur_cvs_v3.m` lines 174-180 — load_defs / shunt_defs / etc.
  reference for pure-element registration pattern (no decoder needed)

### Tools (MCP simulink-tools, see AGENTS.md)
- Build: `simulink_run_script_async` + `simulink_poll_script`
- Compile: `simulink_compile_diagnostics`
- Block placement: built-in `add_block` / `add_line` (within
  build_kundur_cvs_v3.m), or `simulink_add_block` for one-off edits
- Block introspection: `simulink_explore_block` + `simulink_query_params`
  (use `simulink_run_script` directly if validation fails)
- Async sim: `simulink_run_script_async`

---

## 9. Time budget

| step | Phase 1 (c') only | Phase 1+2 (c→b'') | Phase 1+2+3 (→Discrete) |
|------|------------------:|------------------:|------------------------:|
| Day 0 (Discrete dry-run + GO/NO-GO) | 4 hr | 4 hr | 4 hr |
| Day 0.5 ((c') feasibility audit) | 0.5 hr | 0.5 hr | 0.5 hr |
| Day 1-2 ((c') build + framework + NR re-derive) | 12 hr | 12 hr | 12 hr |
| Day 2 (Step 3 NR validate + IC regen) | 1 hr | 1 hr | 1 hr |
| Day 2-3 (compile + Probe G) | 3 hr | 3 hr | 3 hr |
| Day 3 ((c') retrain + 3-policy eval) | 4 hr | 4 hr | 4 hr |
| Day 3.5 (decision: STOP / Phase 2 / Phase 3) | 0.5 hr | 0.5 hr | 0.5 hr |
| Day 4 ((b'') Phase 2 build + retrain) | (skip) | 6 hr | 6 hr |
| Day 4.5 (Phase 2 decision: STOP / Phase 3) | (skip) | 0.5 hr | 0.5 hr |
| Day 5-7 (Phase 3 B Discrete swap + retrain + eval) | (skip) | (skip) | 22 hr |
| Final day (verdict + commits) | 4 hr | 4 hr | 4 hr |
| **Total wall** | **~29 hr (~3.5 day)** | **~35.5 hr (~4.5 day)** | **~57.5 hr (~7 day)** |

**Optimistic path (Phase 1 → STOP)**: 3.5 day, RL improvement ≥ +30 %  
**Likely path (Phase 1 → Phase 2 → STOP)**: 4.5 day, RL improvement ≥ +30 %  
**Pessimistic path (Phase 1+2 fail, Phase 3)**: 7 day, RL improvement ≥ +30 %  
**Worst case (all fail, accept F4 v3 ceiling)**: 4-5 day spent, write up F4 v3 +18 % as project ceiling

---

## 10. STOP — END OF PLAN

When fresh agent picks this up:
1. Read this plan top-to-bottom.
2. Read the 10 pre-read files in §0.
3. Verify state: `git log --oneline -5` matches §8 commit chain;
   `git status --porcelain` should show only untracked or unrelated files.
4. Execute Day 0 first, ALWAYS. Day 0 GO/NO-GO decides everything.
5. Each Probe gate failure: STOP, write partial verdict, present to user.
6. Each gate pass: commit + proceed.
7. After Step 6: present verdict + RL improvement comparison vs F4 v3 + paper.

User decisions needed at the end:
- Merge Option G commits to main, OR keep on feature branch
- If Option G succeeded (improvement > +25 %): publish as new project SOTA
- If Option G gave marginal gain (+18-25 %): document as "physical layer
  unblocks signal but solver/architecture caps improvement"
- If Option G failed at Probe G smoke: combine with Option E ABORT verdict
  → write final architecture-paper-finding writeup; accept F4 v3 +18 %
  as project ceiling

---

## 11. Side task — D-T1 dictionary update (out of plan scope, ~ 15 min)

`docs/paper/kundur-paper-project-terminology-dictionary.md` §3 row D-T1
currently says:

> "Bus 14/15 是 ESS 终端而非 load 节点 ... 字面 bus 编号一致，物理位置错位
> （1 km Pi-line 远离 load center Bus 7/9）"

This is a misread of paper Sec.IV-A. The correct entry is:

> "Bus 14/15 是 ESS **接入** bus，paper 中明确为 'with loads'（Sec.IV-A
> 5605），即 ESS 终端 *同时* 是 load bus。LoadStep 在 Bus 14/15 = paper
> 文字 PRIMARY (Sec.IV-C 5606) + Fig.6 'near vs far disturbance bus' mode
> shape描述 自洽。项目 v3 用 1 km Pi-line 连 Bus 14/15 ↔ Bus 9/10 是
> ESS 接入阻抗的工程实现，不违背 paper。**Option E 选 Bus 7/9 是基于此处
> 的 misread，已 ABORT；Option G 选 Bus 14/15。**"

Update should happen **before** Option G commits land so any future
code reader sees the corrected D-T1 + Option G citing it. Schedule: do
the update during Day 0 (~15 min, while waiting for async build poll).

---

## 12. Open questions to resolve before Day 0

1. **alt (c') vs (b'') NR scope** — RESOLVED 2026-04-30: locked to
   (c') Phase 1 default (Bus 14 closed @ 248 MW IC, Bus 15 open). (b'')
   reserved as conditional Phase 2 fallback (§3.5) if Phase 1 retrain
   falls in marginal +18-30 % band. Adapter implementation per (c'):
   Bus 14 dispatch writes amp = 0 (open breaker → trip), Bus 15
   dispatch writes amp = 188e6 (close breaker → engage). Negative
   `magnitude_sys_pu` is treated as null disturbance in Phase 1; Phase 2
   may extend to bidirectional via second R-bank.
2. **default disturbance type** — switch the project's
   `KUNDUR_DISTURBANCE_TYPE` env var default to
   `loadstep_switch_r_random_load_step` ONCE Probe G PASS verified, OR
   keep the current `pm_step_proxy_random_gen` and only enable Option G
   via env var override during evaluation. Recommend the latter for first
   commit (preserves F4 v3 SOTA reproducibility) and switch default in
   the final RL verdict commit if Option G becomes new SOTA.
3. **PHI lock** — Plan §7.2 says "don't touch PHI in this plan", but if
   Option G physical signal is paper-class (≥ 0.3 Hz at ESS), the
   correct PHI may differ from F4 v3's 5e-4 lock. Consider a follow-up
   PHI sweep plan after Option G converges; this plan does NOT pre-empt
   that decision.

---

*End of `2026-04-30_option_g_switch_rbank_phasor_first_then_discrete.md`*
*Author: 2026-04-30 main session, post Option E ABORT, post-paper-PDF re-read*
*Bus selection: 14/15 (LOCKED, Yang 2023 Sec.IV-A "with loads" + IV-C "load step at bus 14/15")*
*Estimated wall: 3-8 day depending on A success and B feasibility*
