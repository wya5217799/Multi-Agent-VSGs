# G3-prep D-pre — NE39 + Legacy Baseline Tripwire Snapshot

**Date:** 2026-04-26
**Branch:** `feature/kundur-cvs-phasor-vsg`
**Worktree:** `.worktrees/kundur-cvs-phasor-vsg/`
**Type:** READ-ONLY SNAPSHOT — no code / model / parameter / threshold change
**Mandate:** Lock the NE39 + legacy contamination tripwire **before** any
G3-prep-A / B / C touches the shared layer.
**Predecessors:**
- Gate 3 entry plan — `2026-04-26_kundur_cvs_gate3_entry_plan.md`
- Stage 2 readiness plan §2 (NE39 baseline snapshot scope) — `2026-04-25_kundur_cvs_stage2_readiness_plan.md`

---

## TL;DR

| Item | Status |
|---|---|
| Worktree HEAD | `1143258` (Gate 3 entry plan committed) |
| `git status --short` post-snapshot | clean for tracked files; only `results/sim_ne39/runs/ne39_simulink_20260425_194644/` and `results/ne39_dpre_tmp/` untracked, both **gitignored** |
| NE39 / legacy / shared files modified by this branch vs `main` | **0** |
| NE39 3-ep short run | **completed** (10.3 min, exit 0) — baseline values recorded for tripwire |
| Snapshot scope | identifiers / hashes / config fields / 3-ep numerics; **no code touched** |

This snapshot is the **frozen reference point** that G3-prep-B (bridge
`step_strategy` field) and G3-prep-C (new CVS step / warmup `.m` files)
must compare against post-prep.

---

## 1. Worktree state

```
HEAD                   : 1143258  (docs(cvs-gate3): add locked entry plan for SAC/RL prep)
Branch                 : feature/kundur-cvs-phasor-vsg
Branch base (vs main)  : 0d02bc0  (chore(governance/batch-6))
Branch ahead of main by: 9 commits, all CVS-path additions (no NE39/legacy/shared modification)

git status --short (pre + post snapshot):
  pre  : (clean — tracked files)
  post : (clean — tracked files; results/* untracked + gitignored)
```

Branch-vs-`main` diff (head 1143258 vs 0d02bc0): 41 files changed, **all
new files** under `probes/kundur/`, `quality_reports/`, `scenarios/kundur/`
(CVS path), and `docs/design/cvs_design.md`. **No file under
`engine/`, `slx_helpers/`, `agents/`, `env/`, `scenarios/contract.py`,
`scenarios/new_england/`, `config.py`, or any legacy Kundur file was
modified.** Confirmed by `git diff --stat main...HEAD` excluding the CVS
path.

---

## 2. Boundary-file SHA-256 baseline (LOCK)

Any post-prep run must reproduce these hashes verbatim.

### 2.1 Shared layer (NE39 + legacy 共享)

| File | SHA-256 |
|---|---|
| `slx_helpers/vsg_bridge/slx_step_and_read.m` | `3175a5afd443d47e0aeba8aab8b2d3618f93fdc5e67669160a9892df61df5300` |
| `slx_helpers/vsg_bridge/slx_episode_warmup.m` | `8ff0c8edb940e98f2350ba6c343add3e3406dd1fe28db811e5f2a7ec2587ed6a` |
| `engine/simulink_bridge.py` | `e4f7399d7cbac7c4e552ccf387f5ec09251810bc8f82827546dfd0908f5ca577` |
| `scenarios/contract.py` | `77e671612fae10d7560b774605e865ba7321f945b4d06533df6d17dbb7fa3c67` |
| `scenarios/config_simulink_base.py` | `cb737a4bfbe2df6aae28d0d2ab1374af5c742b91619a29529c344f6ecd4a9625` |
| `config.py` (root) | `2445c6c162eebce8c361946dd6cf88d6bdad46e90baf5b9a6673d955fcdf172e` |

### 2.2 NE39 path

| File | SHA-256 |
|---|---|
| `scenarios/new_england/config_simulink.py` | `aac9c8f06725af427ec1cbd273e807a85c1ca828bba71cfb3885e143e19ea425` |
| `scenarios/new_england/train_simulink.py` | `071fb404475bfbfb8bf54fb69f06ba6e08d80cfe1b3b5d31f47ae3245b09dde2` |
| `env/simulink/ne39_simulink_env.py` | `ec2392c69f1f3796bc6c1afe3c6e0a8a148075438fbf6f436b75a331b565c56b` |
| `env/simulink/_base.py` | `542bbdb23ef0315339c4c015d94baa2270a2e6f5e5b9849b2f8ff2831b2b4d90` |
| `scenarios/new_england/simulink_models/NE39bus_v2.slx` | `cfe436e289e1bb5e349372d1a5b7b240c2238a3ad08b7333e47964d1de42607b` |
| `scenarios/new_england/simulink_models/NE39bus_modified.slx` | `dae053c2f3d3a6fc87e4c0e533be5dc5d6d8c0a3c8f79772e27bca818116ca6f` |
| `scenarios/new_england/simulink_models/NE39bus2_PQ.slx` | `00f7e4285e5d3e5086457c5085158b6c29398d7805b20c3c5e8f11cbf855116e` |

### 2.3 Legacy Kundur (pre-CVS)

| File | SHA-256 |
|---|---|
| `scenarios/kundur/kundur_ic.json` | `929f63e41d50253cab689efc9893ebe8aaa762b439c269e5b70be5b6337c3045` |
| `scenarios/kundur/matlab_scripts/compute_kundur_powerflow.m` | `c8bdaba81b641a39751781464bfe7e94d1a21dac7f0964e70af36e31bc0deee0` |
| `scenarios/kundur/simulink_models/build_powerlib_kundur.m` | `caa4f84ec316efcd1041149fb76f03cc1f906e48622956aa7fa7023d96731bdc` |
| `scenarios/kundur/simulink_models/build_kundur_sps.m` | `e9b2eea1ce266f7986577b14bf803758a9800162e30d6a26ed7f28e84e1ecefc` |
| `scenarios/kundur/simulink_models/kundur_vsg.slx` | `295e5e9a151974805e7ea8b544bd7a2dab23733633c7b54893d4be84a2e490a0` |
| `scenarios/kundur/simulink_models/kundur_vsg_sps.slx` | `5c598d6cde1b4895d6e3f8a5fd239ed7a5b092f20c582fa929b2140cfeb7f064` |

---

## 3. NE39 config field dump (key tripwire fields)

From `scenarios/new_england/config_simulink.py` (HEAD `1143258`):

| Field | Value | Source line |
|---|---|---|
| `FN` | `60.0` Hz | L28 (`_CONTRACT.fn`) |
| `DT` | `0.2` s | imported from `_base.DT` (= `_CONTRACT.dt`) |
| `T_EPISODE` | `10.0` s | L33 |
| `STEPS_PER_EPISODE` | `50` | L34 |
| `WARMUP_STEPS` | `2000` | L93 |
| `PHI_F` | `100.0` | L84 |
| `PHI_H`, `PHI_D` | `1.0`, `1.0` | from root `config.py` |
| `NE39_BRIDGE_CONFIG.model_name` | `'NE39bus_v2'` | L116 |
| `NE39_BRIDGE_CONFIG.phase_command_mode` | `'absolute_with_loadflow'` | L131 |
| `NE39_BRIDGE_CONFIG.pe_measurement` | `'vi'` | L128 |
| `NE39_BRIDGE_CONFIG.phase_feedback_gain` | `0.3` | L133 |
| `NE39_BRIDGE_CONFIG.init_phang` | `(-3.646, 0.0, 2.466, 4.423, 3.398, 5.698, 8.494, 2.181)` | L132 |
| `SBASE` | `100.0` MVA | L27 |
| `VSG_P0` | `0.5` pu | L62 |

These fields are inherited from `scenarios/config_simulink_base.py` for
defaults (`DEFAULT_EPISODES = 500`, `MAX_EPISODES = 2000`, `T_WARMUP = 0.5`,
`N_SUBSTEPS = 5`, `DIST_MIN = 1.0`, `DIST_MAX = 3.0`, `TDS_FAIL_PENALTY = -50.0`).

### Known NE39 status (from `scenarios/new_england/NOTES.md` "现在在修")

> "r_f 奖励单位 bug 已修（commit **92d43b8**, `env/simulink/_base.py:207-221`).
>  上一次 run `ne39_simulink_20260417_062136` 在修复前 settled_rate=0.
>  需要新 run 验证：r_f 在总 reward 中的占比从 90% 回落到 ~50%, settled_rate > 0."

`92d43b8` is reachable from HEAD `1143258` (`git merge-base --is-ancestor
92d43b8 HEAD` → yes). The NE39 short run below is the first 3-ep run since
that fix landed in this worktree. Numerics therefore reflect the post-fix
NE39 state — a useful baseline despite NE39's broader open issues.

---

## 4. NE39 3-ep short run

### Command

```bash
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/new_england/train_simulink.py \
  --mode simulink --episodes 3 --resume none
```

### Run identifiers

| Field | Value |
|---|---|
| `run_id` | `ne39_simulink_20260425_194644` |
| `git_hash` (run_meta) | `1143258` |
| `git_dirty` (run_meta) | `true` (pre-run dir `results/ne39_dpre_tmp/` was untracked at start) |
| `seed` | `42` |
| `disturbance_mode` | `gen_trip` |
| `update_repeat` | `10` |
| Wall-clock | `615.6 s` (10.3 min) for 3 episodes |
| Per-ep wall-clock | `214.7 s, 174.4 s, 226.5 s` (mean 205 s/ep) |
| Output dir | `results/sim_ne39/runs/ne39_simulink_20260425_194644/` (gitignored) |

### Per-episode reward

| Ep | reward |
|---|---|
| 1 | -787.43 |
| 2 | -1050.60 |
| 3 | -878.50 |
| mean | **-905.51** |

### Per-episode physics (`physics_summary` from `training_log.json`)

| Ep | max_freq_dev (Hz) | mean_freq_dev (Hz) | settled | settled_moderate | settled_paper | max_power_swing |
|---|---|---|---|---|---|---|
| 1 | 12.754 | 5.238 | False | False | False | 0.535 |
| 2 | 15.006 | 4.778 | False | False | False | 0.531 |
| 3 | 9.412 | 4.960 | False | False | False | 0.539 |

### SAC-side activity

| Quantity | Value |
|---|---|
| Number of SAC gradient updates | **0** (`alphas`, `critic_losses`, `policy_losses` all empty) |
| Reason | `WARMUP_STEPS = 2000`, but 3 ep × 50 step = 150 transitions « 2000 → SAC has not begun updating |
| Actor entropy `α` | 1.000 (initial value, no update) |

This is **expected** for a 3-ep run and matches Gate 3 entry plan §3
("smoke is plumbing, not learning"). The numerics characterise the env +
bridge + sim wiring, not the policy.

### Observations / known signals

- `max_freq_dev` 9.4–15.0 Hz: 2/3 ep above the 12 Hz "abort" threshold from
  the readiness plan §1 D5 batch 22 lesson. **Recorded as the baseline,
  not a tripwire failure** — NE39 is in a known under-validated state per
  `scenarios/new_england/NOTES.md` "现在在修". The contamination tripwire
  asks whether **post-prep** runs *deviate* from this baseline by > 30 %,
  not whether the baseline itself is good.
- `settled` and `settled_paper` False on all 3 ep: consistent with the
  post-r_f-fix NE39 state still awaiting a longer learning run.
- No NaN / Inf, no sim crash, exit 0.
- No omega clip breach reported (would have surfaced in physics summary).

---

## 5. Tripwire reference values (locked)

These are the numbers any future NE39 short run during G3-prep-B / C
must reproduce within the readiness-plan §2 R1 tolerance (deviation < 30 %
on reward magnitude / max_freq_dev / settled_rate, < 20 pp on settled_rate).

| Metric | Baseline value | Tripwire band |
|---|---|---|
| `mean(ep_reward) over 3 ep` | -905.51 | post-prep mean ∈ [-1177, -634] (±30 %) |
| `mean(max_freq_dev_hz)` | 12.39 | post-prep mean ∈ [8.67, 16.11] (±30 %) |
| `mean(mean_freq_dev_hz)` | 4.99 | informational |
| `mean(max_power_swing)` | 0.535 | informational |
| `mean(settled_paper)` | 0/3 = 0.0 | post-prep ≥ -20 pp (i.e., still ≥ 0; cannot regress below) |
| `wall_clock_s_total` | 615.6 | post-prep total ≤ 800 s (sanity, allow some FR overhead) |
| `git_hash NE39 + shared files` (§2.1, 2.2) | recorded | byte-for-byte unchanged |

`settled_rate` (= last-10-step ω in ±0.1 Hz) is not in the current
training log schema; the closest proxy is `settled_paper` (3/3 False).
Tripwire interpretation: a post-prep regression below 0/3 is mathematically
impossible, so the practical tripwire is "False on all 3 ep" — same shape.

---

## 6. Result-folder hygiene

- `results/sim_ne39/runs/ne39_simulink_20260425_194644/` is **gitignored**
  via `.gitignore` (lines 25 / 27 cover `*.json` and `*.log`); checkpoints
  (`*.pt`) covered by line 32.
- `results/ne39_dpre_tmp/run.log` is **gitignored** (line 27, `*.log`).
- This snapshot does **not** stage either path; only this markdown is a
  candidate for commit.

---

## 7. Boundary confirmation

| Item | Status |
|---|---|
| `engine/simulink_bridge.py` | UNCHANGED (SHA-256 verbatim per §2.1) |
| `slx_helpers/vsg_bridge/*` | UNCHANGED (per §2.1) |
| `scenarios/contract.py::KUNDUR / NE39` | UNCHANGED (per §2.1) |
| NE39 anything (`scenarios/new_england/*`, `env/simulink/ne39_*.py`, `env/simulink/_base.py`, NE39 `.slx`) | UNCHANGED (per §2.2) |
| legacy Kundur (`compute_kundur_powerflow.m`, `kundur_ic.json`, `build_kundur_sps.m`, `build_powerlib_kundur.m`, `kundur_vsg.slx`, `kundur_vsg_sps.slx`) | UNCHANGED (per §2.3) |
| `agents/`, `config.py`, reward / observation / action | UNCHANGED |
| CVS-path artefacts (`build_kundur_cvs.m`, `kundur_cvs.slx`, `kundur_ic_cvs.json`, `compute_kundur_cvs_powerflow.m`, probes, verdict markdowns) | UNCHANGED — none touched in this snapshot |
| Gate 3 / SAC / RL training code path | NOT entered in any way; this run is a **read-only baseline observation** of the NE39 path that already exists |
| Main worktree (`fix/governance-review-followups`) | UNCHANGED |
| Plan §5 thresholds in code | UNCHANGED |
| G3-prep-A / B / C / D / E steps | NOT executed; this is D-pre |

---

## 8. What the snapshot does NOT do

- No code / model / parameter / threshold edit anywhere in the worktree.
- No NE39 reward / config tuning even though `max_freq_dev > 12 Hz` in
  2/3 ep — the snapshot's job is to **record** state, not improve it.
- No CVS-side run.
- No Gate 3 / SAC / RL training start.
- No commit. The user decides whether to commit this markdown.

---

## 9. Reproduction

```bash
# Inside the CVS worktree, with MCP MATLAB shared session running:
"C:/Users/27443/miniconda3/envs/andes_env/python.exe" \
  scenarios/new_england/train_simulink.py \
  --mode simulink --episodes 3 --resume none

# Verify boundary-file SHA-256 against §2 above (Bash example):
sha256sum slx_helpers/vsg_bridge/slx_step_and_read.m \
          slx_helpers/vsg_bridge/slx_episode_warmup.m \
          engine/simulink_bridge.py \
          scenarios/contract.py \
          scenarios/config_simulink_base.py
```

Expected wall-clock: ~10 min for 3 ep on the recorded hardware.

---

## 10. Next step (gated on user decision)

This snapshot leaves the worktree in the same state as before it ran
(only gitignored result files added). The user picks one of:

| Choice | Effect |
|---|---|
| **Commit this snapshot only** | preserves the tripwire reference; nothing else changes; G3-prep-A / B / C are still locked |
| Hold (no commit) | snapshot stays on disk only; numbers above are still the reference for any G3-prep step the user authorises later |
| Rerun with different seed / episode count | a separate user authorisation; not done here |

No further action is taken until the user explicitly authorises G3-prep-A,
G3-prep-B, G3-prep-C, G3-prep-D-commit, or G3-prep-E.
