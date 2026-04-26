# Phase 3.4 Verdict — 5-Episode Smoke (kundur_cvs_v3) — PASS

> **Status: PASS — v3 wiring round-trip confirmed end-to-end on the MATLAB-side smoke probe. ALL 8 gates green.**
> **Date:** 2026-04-26
> **Probe (running):** [`probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m`](../../../../probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m)
> **Summary JSON:** [`p34_5ep_smoke_mcp.json`](p34_5ep_smoke_mcp.json)
> **Helper fix (R-h1):** `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m:76` (model-name-derived sidecar lookup)

---

## 1. Path used: MATLAB-side via simulink-tools MCP

The original Python `matlab.engine` smoke probe (`probe_5ep_smoke.py`) **hung 24 min** in cold engine init while a concurrent NE39 500-ep training (`scenarios/new_england/train_simulink.py`, PID 75660 + MATLAB engine PID 70996, started 20:29:49 with cumulative CPU ~6800 s) held shared MATLAB resources. Diagnosis classified as `HANG / NO VERDICT` — neither physics fail nor model fail.

Per user authorization, this probe re-runs the same end-to-end wiring check **inside the MCP MATLAB engine** (long-lived, pre-warmed, separate from the NE39 training engine). No `matlab.engine` cold start. NE39 training was kept running.

---

## 2. Gate results (5 episodes × 50 steps × DT 0.2 s = 50 s sim time, 71 s wall)

| Gate | Got | Pass |
|---|---|---|
| `identity_ok` | profile_id=kundur_cvs_v3, model_name=kundur_cvs_v3, IC schema_version=3, topology_variant=v3_paper_kundur_16bus, runtime_mat exists | ✅ |
| `runtime_mat_v3_correct` | `kundur_cvs_v3_runtime.mat` (NOT `kundur_cvs_runtime.mat`) — R-h1 fix verified at runtime | ✅ |
| `warmup_passed` | `slx_episode_warmup_cvs` returns ω=[1.0000, 1.0000, 1.0005, 1.0003], Pe=[−0.325, −0.374, −0.407, −0.338] sys-pu, δ=[0.429, 0.026, 0.083, 0.047] rad — all finite, all near NR steady | ✅ |
| `all_5_episodes_complete` | 5/5 episodes ran the full 50 steps each (250 step round-trips total) | ✅ |
| `no_nan_inf` | per-step omega/Pe scanned every step, all finite | ✅ |
| `no_clip_or_fail` | no IntW clip, no `tds_failed`, no helper status fail | ✅ |
| `omega_non_stale` | per-episode max\|ω−1\| in [2.34e−3, 2.64e−3] pu (= 117–132 mHz) | ✅ |
| `max_freq_dev_nonzero` | per-ep max_freq_dev_hz in [0.117, 0.132] Hz, consistent with the +/−0.4 sys-pu Pm-step on ES1 | ✅ |

**ALL_PASS = 1.**

---

## 3. Per-episode summary

| ep | sign | steps | wall (s) | ω_dev_max (pu) | max_freq_dev (Hz) | reward_proxy mean |
|---|---|---|---|---|---|---|
| 0 | +0.4 | 50/50 |  9.00 | 2.465 e-3 | 0.1232 | −1.18 e-7 |
| 1 | −0.4 | 50/50 | 10.76 | 2.638 e-3 | 0.1319 | −1.29 e-7 |
| 2 | +0.4 | 50/50 | 13.14 | 2.359 e-3 | 0.1179 | −1.19 e-7 |
| 3 | −0.4 | 50/50 | 15.53 | 2.337 e-3 | 0.1169 | −1.13 e-7 |
| 4 | +0.4 | 50/50 | 17.63 | 2.605 e-3 | 0.1302 | −1.25 e-7 |

Reward-proxy = `−mean((ω−1)²)`, paper-aligned r_f sign. Magnitudes ~ 1e-7 reflect the small ω excursion under random M/D actions (M ∈ [22.5, 28.5], D ∈ [3.0, 9.0]). Smoke does NOT measure RL learning quality — only that the env→bridge→helper→sim→state-readout pipeline produces sane signals every step.

---

## 4. End-to-end contract verified

```
KUNDUR_MODEL_PROFILE = …/kundur_cvs_v3.json     ← P3.1
   ↓ load_kundur_model_profile (model_profile.py)
profile.model_name = 'kundur_cvs_v3'
   ↓ config_simulink.py dispatch (P3.2)
VSG_PE0_DEFAULT_SYS = [-0.369]*4  (from kundur_ic_cvs_v3.json schema 3)
T_WARMUP = 10.0  (smoke-stage, P3.3b)
KUNDUR_BRIDGE_CONFIG.step_strategy = 'cvs_signal'
KUNDUR_BRIDGE_CONFIG.omega_signal  = 'omega_ts_{idx}'
   ↓ env apply_disturbance predicate (P3.3)
CVS Pm-step branch matches 'kundur_cvs_v3'  →  Pm_step_t/amp on ES1
   ↓ slx_episode_warmup_cvs.m (R-h1 fix, this commit)
runtime_mat = '<dir>/kundur_cvs_v3_runtime.mat'  (model-name-derived)
warmup sim StopTime=10s  →  finite ω/Pe/δ from omega_ts_1..4
   ↓ slx_step_and_read_cvs.m (P3.0b interface ✓)
simOut.get('omega_ts_<int>')  →  per-step state extraction
   ↓ probe collects 5 × 50 step samples
NaN/Inf-clean, omega-non-stale, freq-dev-nonzero
```

The chain has no v2/NE39/legacy contamination at any stage.

---

## 5. Boundary respected

| Item | Status |
|---|---|
| `slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m` | **edited (R-h1)**: 1 line — sidecar basename derived from `model_name` (was hardcoded `'kundur_cvs_runtime.mat'`); v2 regression-clean (`'kundur_cvs' + '_runtime.mat'` = same filename) |
| `probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m` | **NEW** (MATLAB-side probe; runs inside MCP MATLAB engine; no Python `matlab.engine` cold-start) |
| `results/harness/kundur/cvs_v3_phase3/p34_5ep_smoke_mcp.json` | **NEW** (this run's machine-readable summary) |
| `results/harness/kundur/cvs_v3_phase3/phase3_p34_5ep_smoke_verdict.md` | **REWRITTEN** (replaces the prior diagnostic-only verdict from the Python probe attempt) |
| `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m` | **untouched** (P3.0b logger naming was the previous interface fix; helper itself unchanged) |
| `engine/simulink_bridge.py` | **untouched** |
| `env/simulink/kundur_simulink_env.py` | **untouched** since P3.3 (`3afc7bf`) |
| `scenarios/kundur/config_simulink.py` | **untouched** since P3.3b (`3afc7bf`) |
| `scenarios/kundur/model_profiles/kundur_cvs_v3.json` | **untouched** since P3.1 (`5874234`) |
| `scenarios/kundur/kundur_ic_cvs_v3.json`, NR script, `build_kundur_cvs_v3.m`, `.slx`, `_runtime.mat` | **untouched** since `cbc5dda` (P3.0b) |
| `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py`, `scenarios/kundur/train_simulink.py`, `utils/` | **untouched** |
| Topology / IC / NR / dispatch values / V_spec / line per-km params / disturbance physics / reward / SAC / training | **untouched** |
| v2 (`kundur_cvs.slx`, `kundur_ic_cvs.json`, `build_kundur_cvs.m`, `compute_kundur_cvs_powerflow.m`, `kundur_cvs_runtime.mat`) | **untouched** |
| NE39 (`scenarios/new_england/`, `env/simulink/ne39_simulink_env.py`) | **untouched** |
| NE39 500-ep training (PID 75660 / 70996) | running, untouched |

---

## 6. Note on the obsoleted Python probe

`probes/kundur/v3_dryrun/probe_5ep_smoke.py` (created during the first P3.4 attempt) is **NOT staged** in this commit. It served only as the original probe wrapper that triggered the discovery of:
- the R-h1 helper-sidecar BLOCKER (now fixed in this commit)
- the cold-start `matlab.engine` resource contention issue with concurrent NE39 training (now bypassed by the MATLAB-side probe)

The MATLAB-side probe `probe_5ep_smoke_mcp.m` supersedes it for the v3 smoke purpose. The Python probe remains in the working tree as untracked for archival reference and can be deleted in a separate cleanup.

The earlier failed run's JSON (`p34_5ep_smoke.json`, timestamp 21:20 from the Python probe) is **NOT staged** — superseded by `p34_5ep_smoke_mcp.json` in this commit.

---

## 7. Files staged in this commit

```
slx_helpers/vsg_bridge/slx_episode_warmup_cvs.m              (modified — R-h1)
probes/kundur/v3_dryrun/probe_5ep_smoke_mcp.m                (NEW — MATLAB-side probe)
results/harness/kundur/cvs_v3_phase3/p34_5ep_smoke_mcp.json  (NEW — PASS summary)
results/harness/kundur/cvs_v3_phase3/phase3_p34_5ep_smoke_verdict.md  (REWRITTEN — this PASS verdict)
```

NOT staged:
- `probes/kundur/v3_dryrun/probe_5ep_smoke.py` (obsoleted Python probe — kept in working tree for audit; not part of this commit's PASS evidence)
- `results/harness/kundur/cvs_v3_phase3/p34_5ep_smoke.json` (old failed Python-run JSON; not part of this commit's PASS evidence)

---

## 8. Halt — Phase 3 complete

Phase 3 cumulative status:

| Sub | Outcome | Commit |
|---|---|---|
| P3.0 audit | discovered logger BLOCKER + warmup BLOCKER (latent) | `cbc5dda` |
| P3.0b/c logger interface | PASS | `cbc5dda` |
| P3.1 profile JSON | PASS | `5874234` |
| P3.2 config dispatch | PASS | `f4624a0` |
| P3.3 env predicate + P3.3b T_WARMUP=10s smoke-stage | PASS | `3afc7bf` |
| P3.4 5-ep smoke | **PASS (this commit, after R-h1)** | (this commit) |

**Phase 3 RL-readiness gate cleared.** v3 model integrates cleanly with profile loader, config dispatch, bridge, env disturbance routing, helper warmup + step. No NaN/Inf/clip; per-ep frequency excursion in paper-aligned 0.1–0.13 Hz band. Concurrent NE39 training is unaffected.

**Phase 4 is now wiring-unblocked but NOT auto-started.** Awaiting explicit user GO for the 50-ep gate / dual-PHI experiment.
