# Probe B STOP Verdict

**Date:** 2026-04-30 02:30 UTC+8
**Protocol:** SG-side `pm_step_proxy_random_gen` (live), single-scenario at G2 (bus=2), magnitudes ±0.5 sys-pu
**Tool:** `probes/kundur/probe_b_sign_pair.py` (commit `deb43e5` + verdict-logic fix)
**Mode:** Read-only — no model / build / .slx / IC / runtime.mat / bridge / SAC / reward / PHI / dispatch changes

---

## Headline finding

> **Measurement layer is OK. The "4-agent collapse" hypothesis from the 2026-04-30 audit was a wrong inference from a different bug.**
>
> **However, single-point disturbance (any of `pm_step_proxy_*`) excites only 1/4 agents above the noise floor — confirming audit R5 (DEGENERATE_GRADIENT) directly.**

---

## What was tested

Two `paper_eval` runs, **same code, same protocol, only magnitude sign flipped**:

| run | bus | mag (sys-pu) | output JSON |
|---|---:|---:|---|
| pos | G2 | +0.500 | `probe_b_pos_gen_b2.json` |
| neg | G2 | -0.500 | `probe_b_neg_gen_b2.json` |

Per-agent diagnostics added to paper_eval (commit `deb43e5`):
- `r_f_global_per_agent`, `max_abs_df_hz_per_agent`, `nadir_hz_per_agent`,
  `peak_hz_per_agent`, `r_f_local_per_agent_eta1`,
  `omega_trace_summary_per_agent` (mean/std/sha256), `omega_source_paths`

---

## 5-hypothesis falsification matrix

| H | Question | Verdict | Evidence |
|---|---|---|---|
| **H1** | Within-run sha256 distinct across 4 agents? | **PASS** | `pos: [f5f8…, fcd6…, 286d…, ff8f…]` 4 distinct |
| **H1b** | Cross-run no aliased hash? | **PASS** | `neg: [f065…, 1087…, 3a38…, 6122…]` zero overlap with pos |
| **H2** | At least 1 agent responds to mag flip (>1e-3 Hz)? | **PASS** | ES1: \|nadir_diff\|+\|peak_diff\| = 0.0967 Hz |
| **H3** | r_f_local_eta1 distinct across agents? | **PASS** | distinct values per agent |
| **H4** | More than 1 agent responds (gradient non-degenerate)? | **FAIL** | 1/4 agents above noise floor |

## Per-agent response to ±0.5 sys-pu at G2

| agent | sname | bus | omega std (pos) | omega std (neg) | \|nadir_diff\|+\|peak_diff\| Hz | sha256 changed pos→neg? |
|---:|---|---:|---:|---:|---:|---|
| 0 | ES1 | 12 | 8.76e-04 | 8.71e-04 | **0.0967** ✓ | yes |
| 1 | ES2 | 16 | 5e-06 | 5e-06 | 2.5e-06 (noise) | yes |
| 2 | ES3 | 14 | 1.4e-05 | 1.4e-05 | 2.7e-06 (noise) | yes |
| 3 | ES4 | 15 | 7.9e-05 | 7.9e-05 | 2.7e-06 (noise) | yes |

ES1 std is **2 orders of magnitude** larger than ES2 (5e-6 ≈ MATLAB float-noise floor). Mag flip changes ES1's per-agent nadir/peak signature visibly; for ES2/3/4 the change is at numerical-noise level.

The sha256 hashes ARE all different per agent and per run — measurements are NOT aliased. But the actual physical content of ES2/3/4 traces is statistically zero (std ≈ 5e-6 to 8e-5 pu = 0.25e-3 to 4e-3 Hz, well below any RL-relevant signal threshold).

---

## What this falsifies

| Claim | Status post-Probe B |
|---|---|
| 2026-04-30 audit said: 4 agents may be aliased to a single shared signal | **FALSIFIED** (H1, H1b, H3 PASS) |
| Earlier `loadstep_metrics.json` 5-scenario bit-identical was measurement collapse | **FALSIFIED** — it was the disturbance-protocol bug (frozen R-block) producing literally zero physical state change. With a live disturbance, traces ARE distinct per agent. |
| Audit R5 said: 3/4 agents have ≈ 0 learning signal under single-point Pm-step | **CONFIRMED** (H4 FAIL) |
| RL improvement is dominated by 1 agent's r_f gradient | **STRONGLY SUPPORTED** by per-agent r_f_global_per_agent: ES1 contributes -0.054 vs ES2/3/4 each ~ -0.006 |

---

## What this does NOT answer

- Whether `loadstep_paper_*` dispatch (still effectively dead under v3) would also produce 1/4 vs 4/4 response. Not testable without physical-layer fix (Option E or G).
- Whether the +10-12% RL improvement claim is causal (E1 PHI=0 ablation aborted at ep 156/200; needs resume).
- Per-agent reward decomposition during training (only paper_eval has Probe B fields; train_simulink does not log per-agent components).
- Whether SG-side at `random_gen` (G1/G2/G3 randomized) gives some scenarios with >1 agent excited (depends on which gen is selected — only tested G2 here).

---

## Recommended next steps

1. **Resume E1a from `ep100.pt`** — Probe B exonerates measurement layer, so PHI=0 ablation will give a meaningful causal signal on R3.
   - Resume command in `results/harness/kundur/cvs_v3_e1_phi0_ablation/E1A_ABORT_NOTE.md`.

2. **Cheap follow-up Probe B at G1 and G3** (~30 min wall) — verifies whether ES1 dominance is a G2-specific artifact or universal across all SG-side scenarios. If ES1 dominates regardless of gen target, the topology is asymmetric in a way the paper's "4-agent coordination" framing assumes is not true.

3. **DO NOT pursue HPO yet** — H4 FAIL means HPO can only tune SAC over a 1-agent learning signal. Even optimal SAC will produce a policy that mostly leverages ES1; ES2/3/4 actions are essentially driven by random exploration, not by gradient. HPO ceiling is bounded by this until disturbance protocol excites multiple agents (Options E/F/G).

4. **Update workspace_vars.py + NOTES.md** to flag the audit R5 finding as confirmed: "single-point Pm-step proxies excite only 1/4 agents in steady state at the chosen disturbance bus".

---

## Files

- `manifest_pos_gen_b2.json` / `manifest_neg_gen_b2.json` — input scenario manifests
- `probe_b_pos_gen_b2.json` / `probe_b_neg_gen_b2.json` — full per-agent metrics
- `probe_b_pos_gen_b2_stdout.log` / `probe_b_neg_gen_b2_stdout.log` — raw paper_eval traces
- `probe_b_verdict_gen_b2.md` — auto-generated falsification matrix (driver output)
- This file: human-readable STOP verdict
