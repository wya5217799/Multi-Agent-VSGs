# Phase 2.1 Verdict — 30 s Zero-Action Stability (kundur_cvs_v3)

> **Status: FAIL — diagnostic-only halt per spec §10. No auto-fix applied.**
> **Date:** 2026-04-26
> **Probe:** [`probes/kundur/v3_dryrun/probe_30s_zero_action.m`](../../../../probes/kundur/v3_dryrun/probe_30s_zero_action.m)
> **Summary JSON:** [`p21_zero_action.json`](p21_zero_action.json)
> **Spec:** [`quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md`](../../../../quality_reports/plans/2026-04-26_cvs_v3_topology_spec.md)

---

## 1. Gate results

| Gate | Required | Got | Pass |
|---|---|---|---|
| ω ∈ [0.999, 1.001] full window | all 7 sources | G1 [0.960, 1.039], G2 [0.962, 1.038], G3 [0.986, 1.014], ES1 [0.991, 1.010], ES2 [1.000, 1.000], ES3 [0.996, 1.004], ES4 [0.999, 1.001] | ❌ |
| |δ| < π/2 − 0.05 (1.5208 rad) | all 7 | max 1.122 (G1) | ✅ |
| |Pe − Pm0| / |Pm0| < 5 % | all 7 | G1 39 %, G2 40 %, G3 19 %, ES1 535 %, ES2 4 %, ES3 153 %, ES4 64 % | ❌ |
| common-mode drift |⟨ω⟩(30 s) − ⟨ω⟩(1 s)| < 2 e-4 pu | — | +4.03 e-4 | ❌ |
| **Overall** | all 4 | 1 / 4 | ❌ |

Wall time: 1.33 s for 30 s sim (6004 samples, ~5 ms step). Solver healthy, no NaN / Inf / clip.

---

## 2. Trajectory snapshot (G1 omega, full window)

| t (s)   | ω (pu)    | comment |
|---|---|---|
| 0.10  | 0.961412  | initial KICK − 3.9 % |
| 1.00  | 0.994147  | recovering |
| 5.00  | 0.996226  | calmer |
| 10.00 | 1.002457  | steady-region drift band |
| 20.00 | 1.001747  | steady-region drift band |
| 30.00 | 0.999767  | steady-region drift band |

Two dynamics layered:
- **Initial kick** t ∈ [0, 1 s]: ω dives ~4 %, recovers within 1 s. All sources affected.
- **Steady-region drift** t ∈ [5, 30 s]: ω hovers in band [0.998, 1.003] instead of pinned 1.0000.

---

## 3. Root-cause diagnosis (no fixes applied)

### 3.1 Steady-region drift — `RC-A` NR/build line model mismatch (HIGH confidence)

The NR script and the build script use **different line models**:

| | NR (`compute_kundur_cvs_v3_powerflow.m:103-130`) | Build (`build_kundur_cvs_v3.m:153-179`) |
|---|---|---|
| Series R | yes (`R_tot = Rk · L`) | yes (matches) |
| Series L | yes (`X_tot = ωL · L`) | yes (matches) |
| Shunt C/2 each end | yes (`ysh = jωC·Zbase·L/2`) | **NO** — `BranchType='RL'` only |

Quantitative impact (worst-case):
- Tie line 7 ↔ 8 (110 km × 3 parallels × 0.009 μF/km): 110 × 0.009 e-6 × 314 × 230 e3² × 3 = **49 MVAr** total shunt cap
- All standard lines combined: ~50 + 50 + 25 + 50 + 50 (others) ≈ ~200 MVAr total reactive injection in NR but ABSENT in build
- Effect: build network is more inductive than NR's network → bus voltages slightly lower than NR-solved → const-Z loads (R + L) consume less real P than NR assumed (P_load_actual = P_nominal · |V|² ; |V|<1) → sources have surplus `Pm − Pe > 0` → swing eq pushes `ω > 1` permanently

This explains:
- ω steady-state slightly above 1 (drift +4 e-4 pu over 29 s)
- Pe deviations large for SG (large Pm) and ESS that sit far from the load buses (ES1 absorbing 5 × NR value as the network re-finds operating point)
- ES2 / ES4 closest to NR (small Pm0, near W2/Bus 9) — drift is tiny

### 3.2 Initial kick — Phasor solver inductor-current IC not pre-loaded (MEDIUM confidence)

At t = 0, the Phasor solver initialises:
- CVS Amplitude / Phase: from NR V_emf magnitude and angle (✓ correct)
- L_int (X_vsg = 0.15 sys-pu, X_gen = 0.0333 sys-pu) inductors: **current at t=0 = 0** (default)
- L_load, L_line: same — zero initial current

The NR steady state assumes inductor currents `I_inj = conj(P_inj − jQ_inj) / V_term`. With zero IC the loop V_emf ↔ V_term takes one solver step plus several time constants L/R to settle. For X_vsg=0.15 sys-pu, R_vsg=0.0015 sys-pu → τ = X/(ωR) = 0.15/(314·0.0015) ≈ 320 ms. So a ~1 s settling for L_int is expected — matches observed kick window.

This is a **design gap** in `build_kundur_cvs_v3.m`: no warmup, no inductor IC loading. v2 mitigated this with `T_WARMUP = 3.0` config knob and (in older powerlib path) a Pref ramp.

### 3.3 What is NOT the cause (ruled out by data)

- Not solver instability — 0 errors, 0 warnings, no Simscape constraint violation, sim wall time 1.33 s for 30 s.
- Not delta clipping — `|δ|max = 1.122 rad ≪ π/2 − 0.05 = 1.521 rad`.
- Not omega clipping — ω stays in [0.96, 1.04], well inside any reasonable clip.
- Not governor droop misconfig — droop term `(1/R)·(ω−1) = 20·(ω−1)` ≈ 0.06 gen-pu at ω=1.003, much smaller than the 39 % G1 Pe deviation.
- Not wind PVS phase mistake — W1/W2 phase set from NR `wind_terminal_voltage_angle_rad` directly.
- Not Pe scaling bug — the Pe / Sscale → src-pu divider is wired correctly in build (verified by per-source Pm₀ matching when the network actually settles).

---

## 4. Per-spec-§10 boundary respected

Per user GO instruction: **gate-fail ⇒ diagnose-only, NO auto-modification of topology, dispatch, line params, IC, or v2 / NE39 / SAC / bridge / env / profile / training.**

This verdict reports root cause and halts. **No file under `scenarios/kundur/`, `env/`, `engine/`, `agents/`, `scenarios/new_england/` modified after the Phase 1 commit `a40adc5`.** No probe-side workaround applied either (e.g. lengthening settle window or relaxing gate).

---

## 5. Decision menu for user

The fix is a known-quantity edit to `build_kundur_cvs_v3.m`. Three options:

### Option A — line shunt C (RC-A primary fix)
Replace `BranchType='RL'` with the Π model: insert `Series RLC type='C'` shunt blocks at each end of every line, capacitance `Ck · L / 2`. ~ 40 new blocks (2 per line × 20 lines). Estimated: 30 min build edit + re-run P2.1.

### Option B — inductor IC pre-loading (RC-B primary fix)
Add `IL_specify='on'` and `IL=[<NR phasor>]` to every Series RLC L block (line, L_int, L_load). Requires adding the NR-derived inductor currents to `kundur_ic_cvs_v3.json` (additive schema bump). v2 NOTES.md explicitly says **this approach failed in the SPS path because Simscape local fixed-step solver zeros L IC at DC analysis** — but Phasor mode may not exhibit the same bug. Risk: medium.

### Option C — settle window adjustment (probe-side workaround, NOT a model fix)
Change probe to start gates at t = 5 s instead of t = 0. Acknowledges that initial 5 s is "warmup" and doesn't count. Steady-region drift gate (Pe within 5 %) likely still fails because RC-A is not addressed. Pure diagnostic relief. Not recommended without RC-A also resolved.

### Option D — combine A + add v2-style warmup
Adopt A then add `T_WARMUP = 5.0` env-side knob (Phase 3 work, not Phase 1.3 work). Best engineering path but largest scope.

---

## 6. Recommendation (request user choice)

Recommend **Option A first** (~30 min), re-run P2.1, then re-evaluate:
- If P2.1 PASS after A → proceed to P2.2 (Pm-step reach).
- If P2.1 still fails after A → escalate to A + B (add inductor IC).
- If A + B both fail → revisit dispatch (e.g. lower ESS V_spec to relieve ES3 Q stress) — this is the only path that requires user re-approval per Q1 lock.

**Phase 2.2 / 2.3 / 2.4 / 2.5 are SUSPENDED** until P2.1 passes; running them on a model that doesn't sit at zero-action steady state would produce uninterpretable results.

---

## 7. Files emitted in this Phase 2.1 attempt

```
probes/kundur/v3_dryrun/probe_30s_zero_action.m              (new)
results/harness/kundur/cvs_v3_phase2/p21_zero_action.json    (new, FAIL summary)
results/harness/kundur/cvs_v3_phase2/phase2_p21_verdict.md   (new, this file)
```

No .slx, no IC, no env, no profile, no SAC, no bridge, no v2, no NE39 modified.

---

## 8. STOP

Awaiting user decision on Option A / B / C / D before continuing Phase 2.
