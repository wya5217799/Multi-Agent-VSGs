# Phase 0 SMIB Discrete Oracle — VERDICT: GO Phase 1

**Date:** 2026-05-03
**Plan:** `quality_reports/plans/2026-05-03_discrete_rebuild_phase0_smib_first.md`
**Worktree:** `C:\Users\27443\Desktop\Multi-Agent-VSGs-discrete`
**Branch:** `discrete-rebuild`
**Outcome:** **ALL 4 GATES PASS — proceed to Phase 1 full v3 Discrete rebuild**

---

## 1. Acceptance gate results

| Gate | Threshold | Actual | Status | Margin |
|---|---|---|---|---|
| **P0.1 Compile** | 0 errors in update | 0 errors, 0 warnings | ✅ PASS | clean |
| **P0.2 IC settle** | omega ∈ 1.0 ± 0.005, std < 0.001 | mean = 1.000022, std = 3.6e-6 | ✅ PASS | 200× margin on dev, 280× on std |
| **P0.3 max\|Δf\|** | ≥ 0.3 Hz @ 248 MW step | **4.9026 Hz** | ✅ PASS | **16× over threshold** |
| **P0.4 Speed** | 5s sim < 10s wall | 0.96s wall | ✅ PASS | 10× margin |

---

## 2. Test setup

- **Topology:** SMIB islanded — 1 ESS (sin → 3 single-phase CVS → Y-config) + Zvsg (R+L per phase) + Three-Phase V-I Measurement + 40 MW constant load + LoadStep (Three-Phase Breaker → 248 MW Three-Phase Series RLC Load)
- **Architecture:** all-SPS (single library, no PS↔SPS domain mismatch)
- **powergui:** SimulationMode = `Discrete`, SampleTime = 50 µs
- **Solver:** Fixed-step `FixedStepAuto`, FixedStep = 50 µs
- **VSG params:** M = 24 (vsg-base), D = 4.5 (vsg-base), Pm = 0.2 (vsg-pu)
- **Load params:** P_const = 40 MW (matches Pm × VSG_SN); LoadStep = 248 MW step at t = 2.0s

---

## 3. Detailed waveform

| Time | omega | Pe (vsg-pu) | Note |
|---|---|---|---|
| t = 0.0s | 1.000000 | — | IC start |
| t = 0.5s | 1.000022 ± 3e-6 | ≈ 0.20 | settled |
| t = 2.0s (just pre-step) | 1.000027 | 0.1993 | matches Pm |
| t = 2.5s (mid-transient) | drops fast | 1.2121 | VSG ramping up to meet new load |
| t = 4.0s+ (late) | 0.9152 (Δf = -4.24 Hz) | 1.2408 | new steady drop (Pm doesn't auto-adjust) |
| Pre-step settle | mean = 1.000027, std = 1.3e-5 | — | quiet baseline |
| Post-step extremum | min = 0.9020 (Δf = -4.90 Hz) | — | nadir |

**Physical interpretation:**
- Pre-step Pe ≈ Pm (0.20) confirms swing-eq + IC alignment is correct.
- 248 MW step is 6.2× larger than VSG capacity (40 MW Pm), so swing-eq integrates rapidly downward — Δf reaches 4.9 Hz nadir, far above paper-scale 0.3 Hz threshold.
- Late frequency settles at -4.24 Hz because Pm is fixed (no governor). For oracle this is **intentional** — we want to verify the LoadStep mechanism delivers signal, not test full primary control.

---

## 4. What this verdict means

### 4.1 Falsifies the 2026-05-01 REJECT verdict

The 2026-05-01 `p0_discrete_oracle_verdict.md` rejected Discrete on three grounds:
1. ❌ Cheap oracle compile-failed (RI2C → CVS Phasor-bound architecture)
2. ❌ Engineering surprise (signal architecture pervades all 7 sources)
3. ⚠️ F4 v3 +18% considered sufficient anchor

**Today's finding falsifies #1 and #2:**
- The architectural blocker was specific to v3's choice of `spsControlledVoltageSourceLib/Controlled Voltage Source` driven by RI2C complex-signal pattern.
- The SMIB spike pattern (`spsControlledVoltageSourceLib/Controlled Voltage Source` driven by **real-valued sin signal**, 3 single-phase blocks in Y-config) is **natively Discrete-compatible** and produces paper-scale Δf signal.
- No new block types needed; same library, different signal-architecture choice.

### 4.2 Implications for Phase 1

- Phase 1 source-chain rebuild is **mechanical replication** of the spike SMIB pattern × 7 (4 ESS + 3 SG):
  - Replace each `RI2C_<src> → CVS_<src>` pair with `[sinA, sinB, sinC] × Vpk_ph → 3× single-phase CVS in Y-config`
  - Each rebuilt source has 3 CVS blocks instead of 1, but each block is simpler (real signal in)
- LoadStep mechanism: replace `LoadStep_bus14/15` Series RLC R-block with `Three-Phase Breaker + Three-Phase Series RLC Load` (verified working in this oracle)
- CCS injection: existing `spsControlledCurrentSourceLib/Controlled Current Source` should still work (driven by sin signals instead of complex phasor)

### 4.3 Speed projection for full v3

- SMIB (1 source + 1 load + 1 step): 5s sim in 0.96s wall = **5.2× real-time**
- Full v3 has 7 sources + 18 lines + 6 dispatch types — likely 5-10× slower than SMIB
- Projected full v3 Discrete: 5s sim in 5-10s wall = **0.5-1.0× real-time**
- Compare to current Phasor (ode23t) v3: 5s sim in ~1-2s wall ≈ 2.5-5× real-time
- **Discrete is 2.5-10× slower than Phasor on full v3** — acceptable for RL training (vs 50-100× for continuous EMT)

---

## 5. Phase 1 GO recommendation

**Recommend committing to full v3 Discrete rebuild**, with the following adjustments to the original Phase 1 plan:

1. **Source chain rebuild simpler than estimated**: 1-2 days (not 2-3 days) per Phase 1.1 sub-task
2. **IC re-derivation simpler than estimated**: NR computes complex-phasor steady state; for Discrete we need (V_pk, δ) for each source — direct conversion from existing IC JSON, no re-NR needed (Phase 1.2 reduces from 2-3 days to 0.5-1 day)
3. **Measurement blocks**: `powerlib/Measurements/Three-Phase V-I Measurement` works in Discrete (verified in oracle); reuse as-is from v3 (Phase 1.3 reduces from 2-3 days to <1 day)

**Revised Phase 1 estimate:** 8-12 days (was 10-15)

---

## 6. Artifacts

- Build script: `probes/kundur/spike/build_minimal_smib_discrete.m`
- Generated model: `probes/kundur/spike/minimal_smib_discrete.slx`
- Trace data: `quality_reports/plans/phase0_oracle_trace.mat`
- This verdict: `quality_reports/plans/2026-05-03_phase0_smib_discrete_verdict.md`

---

## 7. Out-of-scope notes (for Phase 1 attention)

- **Pe oscillation**: Discrete time-domain V·I produces instantaneous P that oscillates at 2× f_n (=100 Hz) — visible as ~0.4 Hz std in late window. For training, may need a low-pass filter on Pe before feeding swing-eq to reduce numerical noise. Optional, not blocking.
- **Late frequency drift**: -4.24 Hz steady offset is expected for SMIB without primary control (no governor). Full v3 has SG with governor — this issue does not propagate.
- **Sample time choice**: 50 µs chosen as standard SPS Discrete recommendation. Could explore 100 µs or 200 µs in Phase 1 to gain speed (SMIB at 200 µs would likely halve wall time).

---

*Phase 0 PASS, 2026-05-03. Recommend GO Phase 1.*
