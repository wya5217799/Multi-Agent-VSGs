# Agent State Probe to Simulink Port Feasibility

_Survey date: 2026-05-04. Read-only; no code modified, no env constructed._

## Verdict (1 line): NEEDS_REFACTOR

The port is feasible but requires refactoring in four places: the loader, all three rollout phases, and checkpoint loading. No fundamental algorithmic changes are required; the work is mechanical substitution.

---

## Existing ANDES Interface (FACT)

Sources: env/andes/andes_vsg_env.py, env/andes/base_env.py, scenarios/contract.py, probes/kundur/agent_state/_loader.py

| Attribute | Value | Source |
|---|---|---|
| N_AGENTS | 4 | _CONTRACT.n_agents (KUNDUR ScenarioContract) |
| OBS_DIM | 7 | 3 + 2 * max_neighbors (max_neighbors=2) |
| action_dim | 2 | _CONTRACT.act_dim |
| Checkpoint class | agents.sac.SACAgent | _loader.py |
| Checkpoint schema | {actor, critic, critic_target, log_alpha, *_opt, metadata} | agents/sac.py::save() |

info dict keys from AndesBaseEnv.step():

    time, freq_hz, omega, omega_dot, P_es, M_es, D_es,
    delta_M, delta_D, r_f, r_h, r_d, max_freq_deviation_hz,
    tds_failed, raw_signals

Seeding: env.seed(s) is an ANDES-specific method on the class.
Reset: env.reset(delta_u=None, ...) returns obs (1 value, not (obs, info) tuple).
Step: returns (obs, rewards, done, info) -- 4-tuple; rewards is dict[int, float].

---

## Simulink Interface (FACT)

Sources: env/simulink/kundur_simulink_env.py, env/simulink/_base.py, env/simulink/sac_agent_standalone.py, scenarios/contract.py

| Attribute | Value | Source |
|---|---|---|
| N_AGENTS | 4 | same _CONTRACT.n_agents |
| OBS_DIM | 7 | same _CONTRACT.obs_dim |
| action_dim | 2 | same _CONTRACT.act_dim |
| Checkpoint class | env.simulink.sac_agent_standalone.SACAgent | train_simulink.py import |
| Ckpt schema 2026-04-14 | {policy, critic, critic_target, *_optim, log_alpha, total_steps, _metadata} | confirmed torch.load |
| Ckpt schema 2026-05-03 screen | {multi_agent: bool, n_agents, obs_dim, act_dim, per_agent: list[...], _metadata} | confirmed torch.load |
| obs_dim in ckpt | 7 | per_agent[0][policy][features.0.weight].shape=[128,7] |

NOTE: h1_confirm_phi_f200_500ep run has episodes_done=18, save_interval=50 -- checkpoints/ is EMPTY. Only the 4 screen_* runs from 2026-05-03 have actual .pt files.

info dict keys from KundurSimulinkEnv.step():

    sim_time, omega, M, D, P_es, sim_ok, freq_hz, max_freq_dev_hz,
    max_freq_deviation_hz, tds_failed, omega_saturated, hit_freq_clip,
    reward_components, resolved_disturbance_type, episode_magnitude_sys_pu

Keys in ANDES only: omega_dot, r_f, r_h, r_d, delta_M, delta_D, raw_signals (exists in Simulink but always {}).
Keys in Simulink only: sim_time, M, D, P_es (direct), sim_ok, omega_saturated, hit_freq_clip, reward_components.

raw_signals sub-key d_omega_global_spread: always 0.0 in Simulink. _failure.py handles via .get(..., 0.0) -- no crash, but spread-peak timing is blind.

Seeding: no seed() method on KundurSimulinkEnv. Use env.reset(seed=s) (Gymnasium 0.26).
Reset: env.reset(seed=None, options=None, *, scenario=...) -- returns (obs, info) 2-tuple.
Step: returns (obs, reward, terminated, truncated, info) -- 5-tuple; reward is np.ndarray[N]; action is np.ndarray[N, ACT_DIM].

Engine cold start: ~20 s (engine/mcp_server.py header; shared singleton).
Wall time per episode: ~14 s (50 steps + T_WARMUP=10 s; v3_paper_alignment_audit.md P3.4 smoke).

---

## Required Changes for Port

### 1. probes/kundur/agent_state/_loader.py

Add backend parameter (andes | simulink).

- simulink: instantiate sac_agent_standalone.SACAgent (not agents.sac.SACAgent); same N/obs_dim values.
- 2026-05-03 screen format: one bundle file with per_agent: list. Load per_agent[i] for agent i.
- Both SACAgent classes expose identical select_action(obs, deterministic) -- no wrapper needed.
- Add schema-detection: check for per_agent key at top level to distinguish old per-file from new bundle.

### 2. probes/kundur/agent_state/_ablation.py (lines 34, 38, 39, 45-47, 52)

- env = AndesMultiVSGEnv(...) --> env = KundurSimulinkEnv(...)  (once outside seed loop; reuse).
- env.seed(seed); obs = env.reset() --> obs, _ = env.reset(seed=seed, options={disturbance_magnitude: val}).
- obs, _, done, info = env.step(actions) --> obs, _, term, trunc, info = env.step(action_array); done = term or trunc.
- Convert actions dict: action_array = np.array([actions[i] for i in range(N)], dtype=np.float32).
- AndesMultiVSGEnv.STEPS_PER_EPISODE --> same value 50 on KundurSimulinkEnv.
- info[freq_hz] present unchanged in Simulink. No change needed.

### 3. probes/kundur/agent_state/_failure.py

Same fixes as _ablation.py, plus:

- Lines 34-42: env.ss.PQ.* does not exist on KundurSimulinkEnv. Replace with info[resolved_disturbance_type] + info[episode_magnitude_sys_pu] (already present in Simulink step info).
- info[max_freq_deviation_hz] present unchanged.
- raw_signals spread analysis always 0.0 (see Risk 3).

### 4. probes/kundur/agent_state/agent_state.py

Pass backend flag through to load() and each phase entry.

### 5. Checkpoint path convention

Screen runs: single best.pt bundle per run. Loader must handle per_agent list schema.
Phase A1 (_specialization.py): NO CHANGES NEEDED -- pure synthetic-obs forward-pass, backend-agnostic.

---

## Estimated Wall Budget

| Phase | ANDES | Simulink | Notes |
|---|---|---|---|
| A1 specialization | ~5 s | ~5 s | tensor ops only, no env |
| A2 ablation (50 eps x 5 masks) | ~10 min | ~58 min | 250 episodes x ~14 s |
| A3 failure (50 eps) | ~10 min | ~12 min | 50 episodes x ~14 s |
| Engine cold start | n/a | ~20 s one-time | negligible vs episodes |
| Total | ~20 min | ~70 min | |

---

## Risks

1. CHECKPOINT SCHEMA MISMATCH (HIGH): loader hardcodes agents.sac.SACAgent and per-file layout. Screen runs use a different class and bundle format. Raises KeyError without fix.

2. STEP TUPLE ARITY (HIGH): ANDES 4-tuple vs Simulink 5-tuple. Probe step calls unpack incorrectly -- done gets assigned reward_array (silently corrupts termination).

3. ANDES ENV INTROSPECTION IN _failure.py (HIGH): env.ss.PQ.* absent on KundurSimulinkEnv. Phase A3 crashes at disturbance bus identification without fix.

4. SEED API MISMATCH (HIGH): env.seed(s) + env.reset() fails on Simulink (AttributeError).

5. ACTION FORMAT (MEDIUM): ANDES expects dict[int, np.ndarray]; Simulink expects np.ndarray[N, ACT_DIM].

6. raw_signals ALWAYS EMPTY (LOW): spread-peak timing blind. max_df_hz and cum_rf unaffected.

7. ABLATION WALL TIME (MEDIUM): ~58 min with no checkpointing. Engine crash loses all ablation results. Recommend persisting per-agent ablation result between mask passes.

8. h1_confirm HAS NO CHECKPOINTS (FACT): Use screen_h1_phi_f_200_20260503T124521/checkpoints/best.pt (150 ep, .pt confirmed) as primary subject.

---

## Recommendation

GO -- with the following pre-conditions (~5 hours of mechanical refactoring):

1. Fix loader schema detection: detect per_agent bundle vs per-file; use sac_agent_standalone.SACAgent for Simulink.
2. Fix rollout helpers: backend-conditional env construction, reset(seed=s), 5-tuple unpack, dict-to-array action conversion.
3. Fix _failure.py disturbance introspection: replace env.ss.PQ.* with info keys.
4. Accept spread-peak blindness as documented limitation.
5. Primary subject: screen_h1_phi_f_200_20260503T124521/checkpoints/best.pt.

N_AGENTS=4, OBS_DIM=7, action_dim=2 are identical across both backends. Phase A1 and A2 results will be directly comparable. The cross-backend comparison directly tests whether agent dominance is a Simulink-physics artifact or a topology-level SAC behavior.
