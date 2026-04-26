# Phase 4.0 Verdict — Read-Only Entry Audit + Gap 1 Dispatch (Kundur CVS v3)

> **Status:** AUDIT COMPLETE — round-2 critic findings all confirmed against current source. Gap 1 dispatched to Path (C) Pm-step proxy. PASS to enter P4.1.
> **Date:** 2026-04-26
> **Predecessor:** P3.4 5-ep smoke PASS at commit `a5bc173`.
> **HEAD at audit:** `a5bc173f0c18a592ffd78067fee25671637d2a0a`
> **Plan:** [`quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md`](../../../../quality_reports/plans/2026-04-26_kundur_cvs_v3_phase4_phase5_roadmap.md)
> **Mode:** read-only — zero file edits, zero MATLAB calls.

---

## 1. Files inspected

| File | Lines | Purpose for P4.0 |
|---|---|---|
| [`scenarios/kundur/simulink_models/build_kundur_cvs_v3.m`](../../../../scenarios/kundur/simulink_models/build_kundur_cvs_v3.m) | 807 (full survey via grep) | verify whether LoadStep workspace vars wire into the .slx block param |
| [`env/simulink/kundur_simulink_env.py`](../../../../env/simulink/kundur_simulink_env.py) | 678–761 | confirm v3 dispatch in `_apply_disturbance_backend`, identify Gap 1 insertion point |
| [`engine/simulink_bridge.py`](../../../../engine/simulink_bridge.py) | 725–760 | confirm `apply_workspace_var` exists with the contract claimed by the plan |
| [`scenarios/kundur/config_simulink.py`](../../../../scenarios/kundur/config_simulink.py) | 1–253 | confirm PHI_F/PHI_H/PHI_D/DIST/WARMUP values and absence of `KUNDUR_DISTURBANCE_TYPE` |
| [`scenarios/config_simulink_base.py`](../../../../scenarios/config_simulink_base.py) | 1–66 (full) | confirm `CHECKPOINT_INTERVAL` and SAC base hyperparameters |
| [`scenarios/kundur/train_simulink.py`](../../../../scenarios/kundur/train_simulink.py) | 56–80, 240–284 | confirm `--resume` + `--save-interval` flags, identify `--scenario-set/--scenario-index` absence |

Read-only access only. No write, no compile, no engine call. NE39 process untouched.

---

## 2. Round-2 critic claim verification

| Critic ID | Claim | Source citation | Verdict |
|---|---|---|---|
| **R2-Blocker1** | LoadStep workspace path is DEAD: `G_perturb_*`/`LoadStep_t_*`/`LoadStep_amp_*` workspace vars are CREATED but NO Simulink block reads them; LoadStep blocks have hardcoded `Resistance='1e9'` | `build_kundur_cvs_v3.m:200-205` does `assignin('base', 'G_perturb_<k>_S', 0.0)` etc. ✓ created. `build_kundur_cvs_v3.m:316-336` does `set_param([mdl '/' name], 'BranchType', 'R', 'Resistance', '1e9')` — **string literal `'1e9'`**, not a workspace expression like `'1/G_perturb_1_S'`. Full grep on `G_perturb\|LoadStep_t_\|LoadStep_amp_` returns only the 3 `assignin` lines (200–204), the 2 `loadstep_defs` cell entries (320–321, 724–725), the docstring at 134/143–145/318, and the `loadstep_defs` definition at 145–148. **No Constant block, no Gain block, no gating cluster, no `set_param(... 'Resistance', '...G_perturb...')` reference exists.** | **CONFIRMED** — workspace-var path for LoadStep is provably DEAD. |
| **R2-Blocker2** | `KUNDUR_DISTURBANCE_TYPE` constant does not exist; `--scenario-set` / `--scenario-index` flags do not exist; `evaluation/` dir does not exist; `plotting/paper_replication.py` does not exist | grep on `DISTURBANCE\|DIST_MIN\|DIST_MAX\|WARMUP_STEPS\|CHECKPOINT` in `config_simulink.py` returns DIST_MIN/DIST_MAX/WARMUP_STEPS only — no `KUNDUR_DISTURBANCE_TYPE`. grep on `scenario_set\|scenario-set\|scenario_idx\|scenario-index` in `train_simulink.py` returns **No matches found**. `ls evaluation/` → **No such file or directory**. `ls plotting/paper_replication.py` → **No such file or directory**. `scenarios/kundur/scenario_sets/` not in `scenarios/kundur/` listing. `scenarios/kundur/scenario_loader.py` not in listing. | **CONFIRMED** — all NEW-file/NEW-flag claims hold. Plan must "add", not "expose". |
| **R2-Verification1** | `train_simulink.py --resume` exists and works (auto-resume + explicit) | `train_simulink.py:70-74` defines `parser.add_argument("--resume", type=str, default=None, ...)`. `train_simulink.py:252-284` implements normalize-`none`/auto-resume-from-checkpoint-dir/load-meta logic. Auto-resume uses highest-numbered `ep<N>.pt`, falls back to `final.pt`. `agent.load(resume_path)` returns `meta` with `start_episode`. | **CONFIRMED** — Phase 5 mid-train crash recovery is supported by existing CLI. |
| **R2-Verification2** | `bridge.apply_workspace_var(var_name, value)` exists with single-scalar push semantics, no tripload-state coupling | `engine/simulink_bridge.py:735-750` defines the method. Body: `self.session.eval(f"assignin('base', '{var_name}', {float(value):.6g})", nargout=0)`. Docstring explicitly warns against tripload state coupling: "Like apply_disturbance_load, but does NOT touch self._tripload_state". | **CONFIRMED** — Gap 1 Path (C) can use it without bridge edits. |
| **R2-Verification3** | `events.jsonl` exists but only logs per-episode aggregates; per-step `r_f`/`r_h`/`r_d` component logging is NEW work | Not directly verified in this audit (defer to Phase 5.1 entry audit). Plan §3.5 already flags this as new ~30-line work in `train_simulink.py` + `ArtifactWriter`. | **DEFERRED** — verifies at P5.0 entry audit; not P4.0 blocker. |
| **R2-Verification4** | `CHECKPOINT_INTERVAL` is 50, not 100; Phase 5 launcher must pass `--save-interval 100` explicitly | `config_simulink_base.py:23` → `CHECKPOINT_INTERVAL = 50`. `train_simulink.py:65` → `parser.add_argument("--save-interval", type=int, default=CHECKPOINT_INTERVAL)`. CLI default is 50. | **CONFIRMED** — Phase 5.3 launch command must include `--save-interval 100` to honor the §3.2 handoff schema. |
| **R2-Math1** | `WARMUP_STEPS=2000` ÷ (4 agents × 50 steps/ep = 200 transitions/ep) = **10 ep**, not 40 ep | `config_simulink.py:227` → `WARMUP_STEPS = 2000`. v2 reasoning preserved at L186-188. SAC update gating math confirmed by reading earlier in the same file (lines 226–227). | **CONFIRMED** — § 3.1 round-2 math fix stands. Phase 4 default `WARMUP_STEPS=2000` (= 10 ep warmup, 40 ep observable for criterion 8). |

---

## 3. Existing v3 disturbance dispatch (read at `kundur_simulink_env.py:678-733`)

```python
def _apply_disturbance_backend(self, bus_idx, magnitude):
    cfg = self.bridge.cfg
    # P3.3 (2026-04-26): v3 reuses the v2 CVS Pm-step path.
    if cfg.model_name in ('kundur_cvs', 'kundur_cvs_v3'):
        target_indices = tuple(getattr(self, 'DISTURBANCE_VSG_INDICES', (0,)))
        n_tgt = max(len(target_indices), 1)
        amp_focused_pu = float(magnitude) * 100e6 / n_tgt / cfg.sbase_va
        t_now = float(self.bridge.t_current)
        amps_per_vsg = [0.0] * cfg.n_agents
        for idx in target_indices:
            if 0 <= idx < cfg.n_agents:
                amps_per_vsg[idx] = amp_focused_pu
        for i in range(cfg.n_agents):
            self.bridge.apply_workspace_var(f'Pm_step_t_{i+1}',   t_now)
            self.bridge.apply_workspace_var(f'Pm_step_amp_{i+1}', amps_per_vsg[i])
        ...
        return
```

**Status:** the v3 branch already routes Pm-step focused on `DISTURBANCE_VSG_INDICES` (default `(0,)` via `getattr`, never set on the class). **Result: today's v3 always concentrates the full disturbance on VSG[0] = ES1**, which is electrically nearest to Bus 7 (P2.3-L1). This is incidentally aligned with one half of the Gap-1 paper-form proxy (`pm_step_proxy_bus7` = ES1). **Gap 1 Path (C) implementation must extend this branch** to:

1. Read a `disturbance_type` knob (NEW config constant `KUNDUR_DISTURBANCE_TYPE` per plan §Gap 1).
2. Map `pm_step_proxy_bus7` → `DISTURBANCE_VSG_INDICES = (0,)` (= ES1, current behavior).
3. Map `pm_step_proxy_bus9` → `DISTURBANCE_VSG_INDICES = (3,)` (= ES4 per `src_meta:353`, electrically nearest to Bus 9 per P2.3-L1).
4. Map `pm_step_proxy_random_bus` → per-episode random pick of (0,) or (3,).
5. Preserve `pm_step_single_vsg` = current default `(0,)` for backward compat.

No edit to `apply_workspace_var`, no edit to bridge, no edit to `.slx`/build/IC/`_runtime.mat`. All inside the existing `if cfg.model_name in ('kundur_cvs', 'kundur_cvs_v3'):` branch.

---

## 4. Gap 1 dispatch decision

Per plan §1 Gap 1 path table, with R2-Blocker1 confirmed:

| Path | Status | Phase 4 default? |
|---|---|---|
| (A) build-side LoadStep wiring | **BLOCKED** — would touch `build_kundur_cvs_v3.m` (locked at `cbc5dda`); requires explicit user scope-expansion authorization. Not pursued in Phase 4. | NO |
| (B) helper / bridge edit | **BLOCKED** — would touch `engine/simulink_bridge.py` or `slx_helpers/vsg_bridge/*` (forbidden in §0 hard non-goals). Not pursued. | NO |
| (C) Pm-step proxy via existing `apply_workspace_var` | **CLEAR** — env edit + config knob only. Existing v3 branch already does the Pm-step routing; only needs `DISTURBANCE_VSG_INDICES` to switch between ES1 / ES4 per disturbance_type. P2.2 measurements (ES1 +0.20 sys-pu = 69 mHz; ES4 +0.20 sys-pu = 64 mHz) show floor-50-mHz pass under current `DIST_MIN/DIST_MAX = [0.1, 0.5]`. | **YES** |

**Gap 1 default: Path (C) Pm-step proxy.** Path (A) becomes a Phase 5 scope-expansion candidate only if Phase 4.2 PHI sweep shows the proxy cannot produce a learnable r_f signal even at saturation.

---

## 5. Plan-required absences (NEW work in Phase 4 / Phase 5)

| Artifact | Plan phase | Audit finding |
|---|---|---|
| `KUNDUR_DISTURBANCE_TYPE` constant in `scenarios/kundur/config_simulink.py` | Phase 4.1 | absent ✓ |
| `pm_step_proxy_bus7`/`bus9`/`random_bus` branches in `_apply_disturbance_backend` | Phase 4.1 | absent ✓ |
| `probes/kundur/v3_dryrun/probe_loadstep_disturbance_routing.py` (Path (C) form) | Phase 4.1 | absent (`probes/kundur/v3_dryrun/` has 6 prior P2 probes; new probe not yet added) |
| `scenarios/kundur/scenario_sets/v3_paper_train_100.json` + `v3_paper_test_50.json` | Phase 4.3 | absent ✓ |
| `scenarios/kundur/scenario_loader.py` | Phase 4.3 | absent ✓ |
| `--scenario-set` / `--scenario-index` CLI flags on `train_simulink.py` | Phase 4.3 | absent ✓ |
| `evaluation/paper_eval.py` + `evaluation/` package | Phase 5.1 | absent ✓ (top-level `evaluation/` dir does not exist) |
| `plotting/paper_replication.py` | Phase 5.1 | absent ✓ |
| Per-step `r_f`/`r_h`/`r_d` component logging into `events.jsonl` | Phase 5.3 | NOT verified at P4.0; deferred to P5.0 entry audit |
| `--save-interval 100` Phase 5.3 invocation | Phase 5.3 | CLI supports it (default = `CHECKPOINT_INTERVAL=50`); P5.0 audit will require explicit override |

---

## 6. Boundary / non-goal confirmation

- v2 (`kundur_cvs.slx`, `kundur_ic_cvs.json`, `build_kundur_cvs.m`, `compute_kundur_cvs_powerflow.m`, `model_profiles/kundur_cvs.json`, `kundur_cvs_runtime.mat`): **untouched** ✓ (audit only read v3 path).
- Legacy SPS (`kundur_vsg.slx`, `build_powerlib_kundur.m`, `model_profiles/kundur_sps_candidate.json`): **untouched** ✓.
- v3 .slx / NR / IC / build / `_runtime.mat`: **untouched** ✓ (locked at `cbc5dda` + `a5bc173`; audit confirms hardcoded `Resistance='1e9'` stays as-is).
- `engine/simulink_bridge.py`: **untouched** ✓ (read-only confirmation that `apply_workspace_var` already provides what Gap 1 Path (C) needs).
- `slx_helpers/vsg_bridge/slx_step_and_read_cvs.m`, `slx_episode_warmup_cvs.m`: **untouched** ✓ (not opened during P4.0).
- `agents/`, `scenarios/contract.py`, `scenarios/config_simulink_base.py`: **untouched** ✓ (confirmed `CHECKPOINT_INTERVAL=50` in base; Phase 5 will override at CLI).
- NE39 (`scenarios/new_england/`, `env/simulink/ne39_simulink_env.py`): **untouched** ✓ (out of scope; the running NE39 500-ep training is not affected by P4.0 read-only audit).
- ANDES / ODE / legacy paths: **untouched** ✓.

No 2000-ep training launched, no probe runs executed, no MATLAB calls.

---

## 7. Verdict

**PASS** — Phase 4.0 entry audit complete. All round-2 critic blockers (R2-Blocker1, R2-Blocker2) and verifications (R2-Verification1, R2-Verification2, R2-Verification4, R2-Math1) confirmed against current source. Gap 1 dispatched to Path (C) Pm-step proxy. No allow-list violations, no §0 lock breaches.

**Open follow-up items (NOT P4.0 blockers):**
- R2-Verification3 (per-step component logging in `events.jsonl`) — verify at P5.0 entry audit before P5.3 main run.
- Path (A) trigger condition (Phase 4.2 PHI sweep cannot produce learnable r_f on the proxy) — only re-evaluate at end of P4.2.

---

## 8. Next step

**Request user GO for P4.1.**

P4.1 surface (per plan §2 + §Gap 1):

- **NEW file:** `probes/kundur/v3_dryrun/probe_loadstep_disturbance_routing.py` (1-ep smoke under v3 random-action workload; asserts `info['max_freq_dev_hz'] > 0`, per-step `r_f` non-zero ≥ 80 % of post-disturbance steps, no `tds_failed`, workspace-var change verifiable on read-back).
- **EDIT:** `env/simulink/kundur_simulink_env.py::_apply_disturbance_backend` v3 branch (lines 703–733). Add `disturbance_type` dispatch; map `pm_step_proxy_bus7`/`bus9`/`random_bus` to `DISTURBANCE_VSG_INDICES`; preserve current behavior under default `pm_step_single_vsg`.
- **EDIT:** `scenarios/kundur/config_simulink.py`. Add `KUNDUR_DISTURBANCE_TYPE = 'pm_step_proxy_random_bus'` (default for Phase 4) plus enum / docstring.
- **NO 50-ep run at P4.1** (per critic I2 fix). 50-ep training begins at P4.2 PHI sweep.
- **Bridge / build / .slx / IC / runtime.mat all stay untouched.**
- **NE39 500-ep training: do not interrupt.** P4.1 probe spins up its own MATLAB engine in a separate `KundurSimulinkEnv` instance.

Awaiting GO.
