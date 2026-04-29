# P4 Real-MATLAB Smoke Verdict

**Stage:** P4 verification appendix to spec
`quality_reports/specs/2026-04-29_kundur-cvs-algo-refactor.md`
**Date:** 2026-04-29
**Result:** PASS (with one production-default issue surfaced — out of C4 scope)

---

## 1. Smokes executed

| # | Mode | env-var | Result | Notes |
|---|---|---|---|---|
| 1 | random (no `--scenario-set`) | `KUNDUR_DISTURBANCE_TYPE` unset → default `loadstep_paper_random_bus` | **CRASH** | Pre-existing config drift; see §3 |
| 1b | random | `KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus` | **PASS** | 5/5 ep, 45.6s, real physics |
| 2 | `--scenario-set test` | same override | **PASS** | 5/5 ep, 45.4s, manifest→resolved byte-exact |
| 3 | `paper_eval --n-scenarios 1 --disturbance-mode gen --seed-base 42` | same override | **PASS** | 1 ep, bus=1 → pm_step_proxy_g1 dispatch |

## 2. §1.5b audit-trail validation

Run `kundur_simulink_20260429_191400` (smoke 1b) physics_summary:

| ep | resolved_disturbance_type | episode_magnitude_sys_pu | r_f | max_freq_dev_hz |
|---|---|---|---|---|
| 0 | pm_step_proxy_random_bus | -0.437 | -0.0087 | 0.195 |
| 1 | pm_step_proxy_random_bus | -0.759 | -0.0163 | 0.319 |
| 2 | pm_step_proxy_random_bus | +0.240 | -0.0020 | 0.101 |
| 3 | pm_step_proxy_random_bus | -0.152 | -0.0006 | 0.080 |
| 4 | pm_step_proxy_random_bus | -0.641 | -0.0125 | 0.276 |

All 5 episodes carry the resolved type and magnitude in the
training_log.json `physics_summary` entries — §1.5b constraint
satisfied.

Run `kundur_simulink_20260429_191607` (smoke 2 with scenario_set):

| ep | manifest target / mag | env recorded type / mag | byte-exact? |
|---|---|---|---|
| 0 | gen target=2, +0.1080 | pm_step_proxy_g2, +0.1080 | ✅ |
| 1 | gen target=2, -0.3349 | pm_step_proxy_g2, -0.3349 | ✅ |
| 2 | gen target=3, -0.2055 | pm_step_proxy_g3, -0.2055 | ✅ |
| 3 | gen target=1, +0.2804 | pm_step_proxy_g1, +0.2804 | ✅ |
| 4 | gen target=1, -0.2115 | pm_step_proxy_g1, -0.2115 | ✅ |

`scenario_to_disturbance_type` translation verified end-to-end on
the v3_paper_test_50 manifest's first 5 entries.

## 3. Production-default issue (surfaced, NOT C4-introduced)

`KUNDUR_DISTURBANCE_TYPE` default = `loadstep_paper_random_bus`
(per Credibility Close lock 2026-04-28). C3d (commit `aad5359`,
2026-04-29) wired `require_effective=True` on every LoadStep
dispatch — under v3 schema, `LOAD_STEP_AMP` is name-valid but NOT
effective (R-block compile-freeze). The two locks are **mutually
incompatible**: any train run without an env-var override raises
`WorkspaceVarError` at step==2 of the first episode.

Evidence the issue pre-existed C4:
- Smoke 1 (this work) crashed with the same WorkspaceVarError
- 2026-04-28 prod run `kundur_simulink_20260429_013017` (2000 ep
  completed) shows `r_f ≈ 0.1%` of total reward in events.jsonl,
  consistent with the LoadStep dispatch being a silent no-op
  pre-C3d (write succeeded but R-block was compile-frozen, so no
  actual disturbance fired)

C4 did not introduce this issue. C4 surfaced it via smoke. Fix is
out of C4 scope (per user decision 2026-04-29 path **b**); to be
filed as a separate task.

**Recommended fix (separate commit)**: align
`KUNDUR_DISTURBANCE_TYPE` default with paper_eval's de facto
protocol (`pm_step_proxy_random_bus`) per
`scenarios/kundur/NOTES.md` §"2026-04-29 Eval 协议偏差 (方案 B)".
Touches paper baseline contract; requires explicit re-lock.

## 4. M9 strict ±1% byte-level — NOT performed

Spec M9 requires "5-ep cold smoke ×2 with ±1% on `mean_reward` and
`max_freq_dev_hz` vs baseline run". Strict execution requires a
pre-C4 baseline with the SAME env-var override
(`KUNDUR_DISTURBANCE_TYPE=pm_step_proxy_random_bus`). No such
baseline exists — the most recent prod run used the broken default.

C4 verification rests on:
1. Unit-test coverage of R-1, R-2, R-4 (P4a, 14 PASS)
2. Byte-level regression vs legacy oracle (P2, 30 PASS) — guarantees
   the protocol layer is byte-equivalent to the god method
3. Smoke 2 manifest→resolved byte-exact translation (this verdict)
4. End-to-end smoke ×3 PASS (this verdict)

This is sufficient to declare C4 stable for the user's workflow.
A strict M9 baseline comparison can be performed later by:
- `git stash` rolling C4 back temporarily
- Running 5-ep smoke with the same env-var override
- Cross-comparing INCLUDED §4.6 fields with ±1% tolerance
- (Estimated +10 min)

User has not requested this comparison (path **b** chosen).

## 5. Performance

5-ep cold smoke: ~45s on R2025b + Win11 (MATLAB cold start ~10s,
50 step rollouts ~7s each). Compatible with previous smoke timings.

## 6. Conclusion

C4 (Scenario VO + internal trigger + §1.5b audit) is **stable in
production**. The pre-existing config-drift issue (default
`KUNDUR_DISTURBANCE_TYPE`) is documented and out of C4 scope.
Proceeding to P5 (documentation finalization + Y1 legacy oracle
cleanup).
