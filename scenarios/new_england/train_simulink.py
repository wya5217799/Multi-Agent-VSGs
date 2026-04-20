"""
Training script for Multi-Agent SAC on Modified NE 39-Bus System.

Usage:
    # Standalone mode (no MATLAB, fast prototyping):
    python train.py --mode standalone --episodes 500

    # Simulink mode (requires MATLAB):
    python train.py --mode simulink --episodes 500

    # Resume training:
    python train.py --mode standalone --episodes 1000 --resume checkpoints/best.pt
"""

import argparse
import datetime
import os
import sys
import time
import json
from pathlib import Path
from tqdm import tqdm
from torch.utils.tensorboard import SummaryWriter

# Add project root to path before importing repo-local utilities.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from collections import deque
import numpy as np

from env.simulink.ne39_simulink_env import NE39BusEnv, NE39BusStandaloneEnv
from env.simulink.sac_agent_standalone import SACAgent
from utils.monitor import TrainingMonitor
from utils.run_meta import save_run_meta, update_run_meta
from utils.artifact_writer import ArtifactWriter
from utils.run_protocol import (
    generate_run_id,
    get_run_dir,
    infer_run_dir_from_output_paths,
    write_training_status,
)
from utils.training_log import load_or_create_log
from utils.notifier import notify
import scenarios.new_england.config_simulink as _cfg_module
from scenarios.new_england.config_simulink import (
    N_AGENTS, OBS_DIM, ACT_DIM, HIDDEN_SIZES,
    LR, GAMMA, TAU_SOFT, BUFFER_SIZE, BATCH_SIZE, WARMUP_STEPS,
    DEFAULT_EPISODES, CHECKPOINT_INTERVAL, EVAL_INTERVAL,
)




def _sample_disturbance(ep: int, args, env) -> "tuple[str, object]":
    """Sample training disturbance for this episode.

    Returns (mode, value):
      ('gen_trip', 'GENROU_N') — trip a random VSG; matches the eval scenario.
      ('apply',    magnitude)  — legacy signed Pe-step disturbance.

    Curriculum transition is keyed on absolute episode index so that resumed
    runs automatically pick up where they left off.
    """
    use_gen_trip = (
        args.disturbance_mode == "gen_trip"
        or (args.disturbance_mode == "curriculum"
            and ep >= args.curriculum_warmup_episodes)
    )
    if use_gen_trip:
        n_agents = getattr(env, "N_ESS", 8)
        idx = int(np.random.randint(1, n_agents + 1))
        return "gen_trip", f"GENROU_{idx}"
    else:
        mag = float(np.random.uniform(env.DIST_MIN, env.DIST_MAX))
        if np.random.random() > 0.5:
            mag = -mag
        return "apply", mag


def parse_args():
    parser = argparse.ArgumentParser(description="Train MARL-VSG on Modified NE 39-Bus")
    parser.add_argument("--mode", choices=["standalone", "simulink"], default="simulink",
                        help="Simulation backend")
    parser.add_argument("--episodes", type=int, default=DEFAULT_EPISODES)
    parser.add_argument("--eval-interval", type=int, default=EVAL_INTERVAL)
    parser.add_argument("--save-interval", type=int, default=CHECKPOINT_INTERVAL)
    parser.add_argument("--checkpoint-dir", default=None,
                        help="Checkpoint directory (default: results/sim_ne39/runs/<run_id>/checkpoints/)")
    parser.add_argument("--resume", type=str, default=None,
                        help="Resume from checkpoint")
    parser.add_argument("--x-line", type=float, default=0.10,
                        help="VSG connecting line reactance")
    parser.add_argument("--comm-delay", type=int, default=0,
                        help="Communication delay in steps")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--update-repeat", type=int, default=10,
                        help="Gradient updates per env step (10 for Simulink, 1 for standalone)")
    parser.add_argument("--log-file", default=None,
                        help="Training log JSON path (default: results/sim_ne39/runs/<run_id>/logs/training_log.json)")
    parser.add_argument("--disturbance-mode",
                        choices=["gen_trip", "apply", "curriculum"],
                        default="gen_trip",
                        help=(
                            "Training disturbance type. "
                            "'gen_trip': randomly trip one VSG each episode (default, matches eval). "
                            "'apply': legacy Pe-step disturbance (±5-15 MW, much smaller than eval). "
                            "'curriculum': use 'apply' for first --curriculum-warmup-episodes, "
                            "then switch to 'gen_trip'."
                        ))
    parser.add_argument("--curriculum-warmup-episodes", type=int, default=50,
                        help="Episodes using apply_disturbance before switching to gen_trip "
                             "(only used when --disturbance-mode=curriculum).")
    args = parser.parse_args()
    checkpoint_was_default = args.checkpoint_dir is None
    log_was_default = args.log_file is None

    # Derive run-namespaced defaults so every training launch is isolated.
    args.run_id = generate_run_id(f"ne39_{args.mode}")
    run_dir = get_run_dir("ne39", args.run_id)
    if args.checkpoint_dir is None:
        args.checkpoint_dir = str(run_dir / "checkpoints")
    if args.log_file is None:
        args.log_file = str(run_dir / "logs" / "training_log.json")
    if checkpoint_was_default and log_was_default:
        args.run_dir = str(run_dir)
    else:
        explicit_run_dir = infer_run_dir_from_output_paths(args.checkpoint_dir, args.log_file)
        if explicit_run_dir is not None:
            args.run_dir = str(explicit_run_dir)
    return args


def make_env(args):
    """Create environment based on mode."""
    if args.mode == "standalone":
        return NE39BusStandaloneEnv(
            x_line=args.x_line,
            comm_delay_steps=args.comm_delay,
            training=True,
        )
    else:
        return NE39BusEnv(
            model_name="NE39bus_v2",
            x_line=args.x_line,
            comm_delay_steps=args.comm_delay,
            training=True,
        )


def evaluate(env, agent, n_eval=3, return_details=False):
    """Run evaluation episodes and return average reward."""
    env.training = False
    try:
        total_rewards = []
        per_agent_reward_rows = []
        episode_physics = []

        for _ in range(n_eval):
            obs, _ = env.reset()
            ep_reward = np.zeros(env.N_ESS)
            ep_max_freq_dev = 0.0
            ep_sum_freq_dev = 0.0
            ep_step_count_actual = 0
            ep_tail_freq_devs = deque(maxlen=10)
            ep_P_es_min = np.full(env.N_ESS, np.inf)
            ep_P_es_max = np.full(env.N_ESS, -np.inf)

            # Apply a fixed disturbance for consistent evaluation
            env.gen_trip("GENROU_2", trip_time=0.5)

            for step in range(int(env.T_EPISODE / env.DT)):
                actions = agent.select_actions_multi(obs, deterministic=True)
                obs, rewards, terminated, truncated, info = env.step(actions)
                ep_reward += rewards

                step_freq_dev = info.get("max_freq_deviation_hz", 0.0)
                ep_max_freq_dev = max(ep_max_freq_dev, step_freq_dev)
                ep_sum_freq_dev += step_freq_dev
                ep_step_count_actual += 1
                ep_tail_freq_devs.append(step_freq_dev)
                p_es = info.get("P_es", None)
                if p_es is not None:
                    p_arr = np.asarray(p_es)
                    ep_P_es_min = np.minimum(ep_P_es_min, p_arr)
                    ep_P_es_max = np.maximum(ep_P_es_max, p_arr)
                if terminated or truncated:
                    break

            total_rewards.append(float(ep_reward.mean()))
            per_agent_reward_rows.append(ep_reward.astype(float))
            ep_mean_freq_dev = ep_sum_freq_dev / max(ep_step_count_actual, 1)
            ep_settled          = bool(ep_tail_freq_devs and all(d < 0.10 for d in ep_tail_freq_devs))
            ep_settled_moderate = bool(ep_tail_freq_devs and all(d < 0.15 for d in ep_tail_freq_devs))
            ep_settled_paper    = bool(ep_tail_freq_devs and all(d < 0.20 for d in ep_tail_freq_devs))
            if (ep_step_count_actual > 0
                    and not np.any(np.isinf(ep_P_es_max))
                    and not np.any(np.isinf(ep_P_es_min))):
                ep_power_swing = float(np.max(ep_P_es_max - ep_P_es_min))
            else:
                ep_power_swing = 0.0
            episode_physics.append({
                "max_freq_dev_hz":  float(ep_max_freq_dev),
                "mean_freq_dev_hz": float(ep_mean_freq_dev),
                "settled":          ep_settled,
                "settled_moderate": ep_settled_moderate,
                "settled_paper":    ep_settled_paper,
                "max_power_swing":  ep_power_swing,
            })

        eval_reward = float(np.mean(total_rewards)) if total_rewards else 0.0
        if not return_details:
            return eval_reward

        per_agent_mean = (
            np.mean(np.vstack(per_agent_reward_rows), axis=0)
            if per_agent_reward_rows else np.zeros(env.N_ESS)
        )
        return {
            "type": "eval",
            "eval_reward": eval_reward,
            "n_eval": n_eval,
            "per_agent_rewards": {
                str(i): float(per_agent_mean[i]) for i in range(env.N_ESS)
            },
            "disturbance": {
                "kind": "gen_trip",
                "gen_name": "GENROU_2",
                "trip_time": 0.5,
            },
            "physics": {
                "max_freq_dev_hz":      float(max((p["max_freq_dev_hz"] for p in episode_physics), default=0.0)),
                "mean_freq_dev_hz":     float(np.mean([p["mean_freq_dev_hz"] for p in episode_physics])) if episode_physics else 0.0,
                "settled":              bool(episode_physics and all(p["settled"] for p in episode_physics)),
                "settled_rate":         float(np.mean([p["settled"] for p in episode_physics])) if episode_physics else 0.0,
                "settled_rate_moderate":float(np.mean([p.get("settled_moderate", p["settled"]) for p in episode_physics])) if episode_physics else 0.0,
                "settled_rate_paper":   float(np.mean([p.get("settled_paper",    p["settled"]) for p in episode_physics])) if episode_physics else 0.0,
                "max_power_swing":      float(max((p["max_power_swing"] for p in episode_physics), default=0.0)),
            },
            "episodes": episode_physics,
        }
    finally:
        env.training = True


def train(args):
    """Main training loop."""
    np.random.seed(args.seed)

    # Per-run output directory
    if not hasattr(args, "run_id"):
        args.run_id = generate_run_id(f"ne39_{args.mode}")
    run_dir_default = get_run_dir("ne39", args.run_id)
    if args.checkpoint_dir is None:
        args.checkpoint_dir = str(run_dir_default / "checkpoints")
    if args.log_file is None:
        args.log_file = str(run_dir_default / "logs" / "training_log.json")
    if not hasattr(args, "run_dir"):
        inferred_run_dir = infer_run_dir_from_output_paths(args.checkpoint_dir, args.log_file)
        if inferred_run_dir is not None:
            args.run_dir = str(inferred_run_dir)
    run_id = args.run_id
    # Determine run_dir path (no mkdir yet — deferred until backend is ready)
    if hasattr(args, "run_dir"):
        run_dir = Path(args.run_dir)
    else:
        run_dir = Path(args.checkpoint_dir)

    # Create environment and agent
    env = make_env(args)
    agent = SACAgent(
        obs_dim=OBS_DIM,
        act_dim=ACT_DIM,
        hidden_sizes=HIDDEN_SIZES,
        lr=LR,
        gamma=GAMMA,
        tau=TAU_SOFT,
        buffer_size=BUFFER_SIZE,
        batch_size=BATCH_SIZE,
        warmup_steps=WARMUP_STEPS,
        reward_scale=1e-3,
        alpha_max=5.0,
    )

    start_episode = 0
    # Normalise --resume: the string literal "none" means "force fresh start".
    force_fresh = (args.resume or "").lower() == "none"
    resume_path = None if force_fresh else args.resume

    # Auto-resume: if no --resume given but a checkpoint directory already
    # contains episode checkpoints, load the latest one automatically.
    # This prevents the "alpha reset" collapse that occurs when a fresh
    # SACAgent (alpha=1.0) is appended onto an existing training_log.json.
    if resume_path is None and not force_fresh:
        ckpt_dir = args.checkpoint_dir
        if os.path.isdir(ckpt_dir):
            ep_ckpts = sorted(
                [
                    f for f in os.listdir(ckpt_dir)
                    if f.startswith("ep") and f.endswith(".pt")
                ],
                key=lambda name: int(name[2:-3]),
            )
            if ep_ckpts:
                resume_path = os.path.join(ckpt_dir, ep_ckpts[-1])
                print(
                    f"[train] Auto-resume: found existing checkpoint "
                    f"'{ep_ckpts[-1]}' — resuming (pass --resume none to start fresh)."
                )
            elif os.path.exists(os.path.join(ckpt_dir, "final.pt")):
                resume_path = os.path.join(ckpt_dir, "final.pt")
                print("[train] Auto-resume: loading final.pt.")

    if resume_path and os.path.exists(resume_path):
        meta = agent.load(resume_path)
        start_episode = meta.get("start_episode", 0)
        print(f"Resumed from {resume_path} (starting at episode {start_episode})")

    # ── Phase B: Bootstrap backend ─────────────────────────────────────────────
    # First env.reset() triggers MATLAB startup / load_model / warmup.
    # If this fails, raise immediately; run_dir not yet created, no orphaned files.
    #
    # NE39-specific: disturbance is applied mid-episode via gen_trip() or
    # apply_disturbance() at step 5 (t=1.0s), NOT via reset options.
    # The disturbance is sampled here so it is ready for the first episode.
    obs, _ = env.reset()
    _ep_dist_mode, _ep_dist_val = _sample_disturbance(start_episode, args, env)

    # ── Phase C: Commit outputs (only after backend is ready) ──────────────────
    if hasattr(args, "run_dir"):
        (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    else:
        run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[train] run_id={run_id}, output={run_dir}")

    _started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _logs_dir = str(Path(args.log_file).parent)
    write_training_status(run_dir, {
        "status": "running",
        "run_id": run_id,
        "scenario": "ne39",
        "episodes_total": args.episodes,
        "episodes_done": 0,
        "started_at": _started_at,
        "logs_dir": _logs_dir,
        "last_reward": None,
        "last_eval_reward": None,
    })
    # Checkpoint directory
    os.makedirs(args.checkpoint_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.log_file), exist_ok=True)
    _live_log = str(Path(args.log_file).parent / "live.log")
    tb_writer = None
    tb_writer = SummaryWriter(log_dir=str(run_dir / "tb"))

    _log_dir = os.path.dirname(args.log_file)
    fresh_run = start_episode == 0
    writer = ArtifactWriter(_log_dir, reset_existing=fresh_run)
    writer.log_event(start_episode, "training_start", {
        "scenario": "sim_ne39",
        "n_agents": env.N_ESS if hasattr(env, "N_ESS") else None,
        "config": {
            "mode": args.mode,
            "episodes": args.episodes,
            "disturbance_mode": args.disturbance_mode,
            "curriculum_warmup_episodes": args.curriculum_warmup_episodes,
        },
    })
    _prev_trigger_len = 0
    _last_eval_reward: float | None = None
    _stop_reason: str | None = None

    meta_dir = getattr(args, "run_dir", args.checkpoint_dir)
    save_run_meta(meta_dir, args, _cfg_module)

    monitor = TrainingMonitor()

    log = load_or_create_log(args.log_file, fresh=fresh_run)

    best_eval_reward = -float("inf")
    print(f"\n{'='*60}")
    print(f"Training MARL-VSG on Modified NE 39-Bus System")
    print(f"Mode: {args.mode} | Episodes: {args.episodes} | Seed: {args.seed}")
    print(f"{'='*60}\n")

    t_start = time.time()
    monitor_stopped = False

    end_episode = start_episode + args.episodes
    _pbar = tqdm(
        range(start_episode, end_episode),
        desc="NE39", unit="ep",
        total=args.episodes, initial=0,
        dynamic_ncols=True,
    )
    for ep in _pbar:
        # Phase B already reset episode start_episode; subsequent episodes reset here.
        # NE39: reset() takes no disturbance options; disturbance is sampled here
        # and applied at step 5 (t=1.0s) in the inner loop below.
        if ep > start_episode:
            obs, _ = env.reset()
            _ep_dist_mode, _ep_dist_val = _sample_disturbance(ep, args, env)
        ep_reward = np.zeros(env.N_ESS)
        ep_losses = {"critic": [], "policy": [], "alpha": []}
        actions_history = []
        ep_components = {"r_f": 0.0, "r_h": 0.0, "r_d": 0.0}
        last_info: dict = {}

        # physics_summary accumulators
        ep_max_freq_dev = 0.0
        ep_sum_freq_dev = 0.0
        ep_step_count_actual = 0
        ep_tail_freq_devs = deque(maxlen=10)
        ep_P_es_min = np.full(env.N_ESS, np.inf)
        ep_P_es_max = np.full(env.N_ESS, -np.inf)

        for step in range(int(env.T_EPISODE / env.DT)):
            # Apply disturbance at episode t=1.0s (step 5).
            # 5 control steps of RL before the disturbance hit improves early
            # stability: the model reaches a more settled state first.
            if step == int(1.0 / env.DT):  # t = 1.0s into episode
                if _ep_dist_mode == "gen_trip":
                    env.gen_trip(_ep_dist_val, trip_time=1.0)
                else:
                    env.apply_disturbance(magnitude=_ep_dist_val)

            # Select actions (exploration during training)
            actions = agent.select_actions_multi(obs, deterministic=False)

            # Environment step
            next_obs, rewards, terminated, truncated, info = env.step(actions)

            actions_history.append(actions)
            for k in ep_components:
                ep_components[k] += info.get("reward_components", {}).get(k, 0.0)
            last_info = info

            # accumulate physics_summary (fix: track max over all steps, not last step)
            step_freq_dev = info.get("max_freq_deviation_hz", 0.0)
            ep_max_freq_dev = max(ep_max_freq_dev, step_freq_dev)
            ep_sum_freq_dev += step_freq_dev
            ep_step_count_actual += 1
            ep_tail_freq_devs.append(step_freq_dev)
            p_es = info.get("P_es", None)
            if p_es is not None:
                p_arr = np.asarray(p_es)
                ep_P_es_min = np.minimum(ep_P_es_min, p_arr)
                ep_P_es_max = np.maximum(ep_P_es_max, p_arr)

            # Store transitions
            done = terminated or truncated
            agent.store_multi_transitions(obs, actions, rewards, next_obs, done)

            # Dynamic update_repeat: ramp from 1 → target as buffer fills.
            # Prevents critic overfitting when buffer is small.
            # (buffer//warmup gives 1 at warmup, 2 at 2x warmup, etc.)
            effective_repeat = min(
                args.update_repeat,
                max(1, len(agent.buffer) // agent.warmup_steps),
            )
            for _ in range(effective_repeat):
                update_info = agent.update()
                if update_info:
                    ep_losses["critic"].append(update_info.get("critic_loss", 0))
                    ep_losses["policy"].append(update_info.get("policy_loss", 0))
                    ep_losses["alpha"].append(update_info.get("alpha", 0))

            obs = next_obs
            ep_reward += rewards

            if terminated or truncated:
                break

        # Logging
        mean_reward = ep_reward.mean()
        log["episode_rewards"].append(float(mean_reward))

        # --- real-time progress bar + live log --------------------------------
        _avg10 = float(np.mean(log["episode_rewards"][-10:]))
        _pbar.set_postfix(
            R=f"{mean_reward:+.1f}",
            avg10=f"{_avg10:+.1f}",
            a=f"{agent.alpha:.3f}",
            df=f"{ep_max_freq_dev:.2f}Hz",
        )
        _ts = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S")
        _elapsed = time.time() - t_start
        try:
            with open(_live_log, "a", encoding="utf-8") as _lf:
                _lf.write(
                    f"{_ts} [EP {ep+1:4d}/{end_episode}] "
                    f"R={mean_reward:+8.2f} avg10={_avg10:+8.2f} "
                    f"a={agent.alpha:.4f} df={ep_max_freq_dev:.3f}Hz "
                    f"buf={len(agent.buffer)} t={_elapsed:.0f}s\n"
                )
        except OSError:
            pass  # observability loss is acceptable; training must not abort
        # --- TensorBoard -------------------------------------------------------
        tb_writer.add_scalar("train/reward", mean_reward, ep)
        tb_writer.add_scalar("train/avg10_reward", _avg10, ep)
        tb_writer.add_scalar("train/alpha", agent.alpha, ep)
        tb_writer.add_scalar("train/freq_dev_hz", ep_max_freq_dev, ep)
        tb_writer.add_scalar("train/buffer_size", len(agent.buffer), ep)
        if ep_losses["critic"]:
            tb_writer.add_scalar("train/critic_loss", float(np.mean(ep_losses["critic"])), ep)
            tb_writer.add_scalar("train/policy_loss", float(np.mean(ep_losses["policy"])), ep)
        # -----------------------------------------------------------------------

        write_training_status(run_dir, {
            "status": "running",
            "run_id": run_id,
            "scenario": "ne39",
            "episodes_total": args.episodes,
            "episodes_done": ep - start_episode + 1,
            "last_reward": float(mean_reward),
            "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "started_at": _started_at,
            "logs_dir": _logs_dir,
            "last_eval_reward": _last_eval_reward,
        })

        # compute and record episode physics_summary
        ep_mean_freq_dev = ep_sum_freq_dev / max(ep_step_count_actual, 1)
        # Three parallel settled criteria — keep strict version unchanged so
        # historical comparisons stay valid; add paper-aligned versions.
        ep_settled          = bool(ep_tail_freq_devs and all(d < 0.10 for d in ep_tail_freq_devs))
        ep_settled_moderate = bool(ep_tail_freq_devs and all(d < 0.15 for d in ep_tail_freq_devs))
        ep_settled_paper    = bool(ep_tail_freq_devs and all(d < 0.20 for d in ep_tail_freq_devs))
        if (ep_step_count_actual > 0
                and not np.any(np.isinf(ep_P_es_max))
                and not np.any(np.isinf(ep_P_es_min))):
            ep_power_swing = float(np.max(ep_P_es_max - ep_P_es_min))
        else:
            ep_power_swing = 0.0
        log["physics_summary"].append({
            "max_freq_dev_hz":    float(ep_max_freq_dev),
            "mean_freq_dev_hz":   float(ep_mean_freq_dev),
            "settled":            ep_settled,           # strict  |Δf| < 0.10 Hz
            "settled_moderate":   ep_settled_moderate,  # paper SS|Δf| < 0.15 Hz
            "settled_paper":      ep_settled_paper,     # relaxed |Δf| < 0.20 Hz
            "max_power_swing":    ep_power_swing,
        })
        if ep_losses["critic"]:
            log["critic_losses"].append(float(np.mean(ep_losses["critic"])))
            log["policy_losses"].append(float(np.mean(ep_losses["policy"])))
            log["alphas"].append(float(np.mean(ep_losses["alpha"])))

        # Monitor: diagnostic checks
        # Pass one aggregated dict (shared-weight SAC = one logical agent)
        sac_losses_for_monitor = (
            [{"critic_loss": float(np.mean(ep_losses["critic"])),
              "policy_loss": float(np.mean(ep_losses["policy"])),
              "alpha": float(np.mean(ep_losses["alpha"]))}]
            if ep_losses["critic"] else None
        )
        stop_triggered = monitor.log_and_check(
            episode=ep,
            rewards=float(mean_reward),
            reward_components=ep_components,
            actions=np.stack(actions_history) if actions_history else np.zeros((1, env.N_ESS, 2)),
            info={
                "tds_failed": last_info.get("tds_failed", False),
                "max_freq_deviation_hz": ep_max_freq_dev,  # episode peak, not last-step value
                "max_power_swing": ep_power_swing,
            },
            per_agent_rewards={i: float(ep_reward[i]) for i in range(env.N_ESS)},
            sac_losses=sac_losses_for_monitor,
        )
        # Route any new monitor triggers to events.jsonl
        _new_triggers = monitor._trigger_history[_prev_trigger_len:]
        for t in _new_triggers:
            writer.log_event(ep, "monitor_alert", {"rule": t})
        _prev_trigger_len = len(monitor._trigger_history)

        if stop_triggered:
            _stop_reason = _new_triggers[-1] if _new_triggers else None
            writer.log_event(ep, "monitor_stop", {"triggered_by": "monitor"})
            _pbar.write(f"[Monitor] Hard stop at episode {ep}. Saving checkpoint.")
            agent.save(
                os.path.join(args.checkpoint_dir, f"monitor_stop_ep{ep}.pt"),
                metadata={"start_episode": ep + 1},
            )
            monitor_stopped = True
            break


        # Evaluation
        if (ep + 1) % args.eval_interval == 0:
            _last_eval_reward = None
            eval_details = evaluate(env, agent, return_details=True)
            eval_reward = float(eval_details["eval_reward"])
            _last_eval_reward = eval_reward
            writer.log_metric(ep, eval_details)
            writer.log_event(ep, "eval", {"eval_reward": eval_reward})
            log["eval_rewards"].append({"episode": ep + 1, "reward": eval_reward})
            _pbar.write(f"  >>> Eval reward: {eval_reward:+.2f}")
            tb_writer.add_scalar("eval/reward", eval_reward, ep)

            if eval_reward > best_eval_reward:
                best_eval_reward = eval_reward
                agent.save(
                    os.path.join(args.checkpoint_dir, "best.pt"),
                    metadata={"start_episode": ep + 1},
                )
                _pbar.write(f"  >>> New best! Saved to {args.checkpoint_dir}/best.pt")

        # --- artifact writer: append episode metrics ---
        writer.log_metric(ep, {
            "reward": float(mean_reward),
            "reward_components": ep_components,
            "alpha": float(np.mean(ep_losses["alpha"])) if ep_losses["alpha"] else None,
            "critic_loss": float(np.mean(ep_losses["critic"])) if ep_losses["critic"] else None,
            "policy_loss": float(np.mean(ep_losses["policy"])) if ep_losses["policy"] else None,
            "eval_reward": _last_eval_reward if (ep + 1) % args.eval_interval == 0 else None,
            "physics": {
                "max_freq_dev_hz":  float(ep_max_freq_dev),
                "mean_freq_dev_hz": float(ep_mean_freq_dev),
                "settled":          ep_settled,
                "settled_moderate": ep_settled_moderate,
                "settled_paper":    ep_settled_paper,
                "max_power_swing":  ep_power_swing,
            },
            "disturbance": {
                "mode":  _ep_dist_mode,
                "value": _ep_dist_val if _ep_dist_mode == "apply" else 0.0,
            },
        })

        # Rolling latest checkpoint — overwritten every episode.
        # Ensures max loss on unexpected restart = 1 episode (~7 min for NE39).
        agent.save(
            os.path.join(args.checkpoint_dir, "latest.pt"),
            metadata={"start_episode": ep + 1},
        )

        # Periodic checkpoint (with replay buffer for full resume quality)
        if (ep + 1) % args.save_interval == 0:
            agent.save(
                os.path.join(args.checkpoint_dir, f"ep{ep+1}.pt"),
                metadata={"start_episode": ep + 1},
                save_buffer=True,
            )
            writer.log_event(ep, "checkpoint", {"file": f"ep{ep+1}.pt"})

        # Graceful-save: user drops a "save_now" file in run_dir to request
        # an immediate full checkpoint (model + buffer) before restarting.
        _flag = run_dir / "save_now"
        if _flag.exists():
            _snap = os.path.join(args.checkpoint_dir, f"safe_stop_ep{ep+1}.pt")
            _pbar.write(f"[SaveNow] Flag detected — saving full checkpoint to {_snap}")
            agent.save(_snap, metadata={"start_episode": ep + 1}, save_buffer=True)
            _flag.unlink()
            writer.log_event(ep, "checkpoint", {"file": f"safe_stop_ep{ep+1}.pt", "trigger": "save_now"})
            _pbar.write("[SaveNow] Done. Safe to restart. Training continues.")

        # Update latest_state every 50 episodes
        if (ep + 1) % 50 == 0:
            _recent_rewards = log["episode_rewards"][-50:]
            _recent_physics = log["physics_summary"][-50:]
            writer.update_state({
                "episode": ep,
                "reward_mean_50": float(np.mean(_recent_rewards)),
                "alpha": float(agent.alpha),
                "settled_rate_50": float(np.mean(
                    [p["settled"] for p in _recent_physics])) if _recent_physics else 0.0,
                "settled_rate_50_moderate": float(np.mean(
                    [p.get("settled_moderate", p["settled"]) for p in _recent_physics])
                ) if _recent_physics else 0.0,
                "settled_rate_50_paper": float(np.mean(
                    [p.get("settled_paper", p["settled"]) for p in _recent_physics])
                ) if _recent_physics else 0.0,
                "buffer_size": len(agent.buffer),
            })

    try:
        # Final save
        agent.save(
            os.path.join(args.checkpoint_dir, "final.pt"),
            metadata={"start_episode": start_episode + args.episodes},
        )
        _recent_rewards = log["episode_rewards"][-50:]
        _recent_physics = log["physics_summary"][-50:]
        if _recent_rewards:
            writer.update_state({
                "episode": ep,
                "reward_mean_50": float(np.mean(_recent_rewards)),
                "alpha": float(agent.alpha),
                "settled_rate_50": float(np.mean(
                    [p["settled"] for p in _recent_physics])) if _recent_physics else 0.0,
                "settled_rate_50_moderate": float(np.mean(
                    [p.get("settled_moderate", p["settled"]) for p in _recent_physics])
                ) if _recent_physics else 0.0,
                "settled_rate_50_paper": float(np.mean(
                    [p.get("settled_paper", p["settled"]) for p in _recent_physics])
                ) if _recent_physics else 0.0,
                "buffer_size": len(agent.buffer),
            })
        writer.log_event(
            start_episode + args.episodes - 1,
            "training_end",
            {"total_episodes": start_episode + args.episodes},
        )

        # Save log
        with open(args.log_file, "w") as f:
            json.dump(log, f, indent=2)
        print(f"\nTraining log saved to {args.log_file}")

        log_dir = os.path.dirname(args.log_file)
        monitor.export_csv(os.path.join(log_dir, "monitor_data.csv"))
        monitor.save_checkpoint(os.path.join(log_dir, "monitor_state.json"))
        print(f"Monitor data exported to {log_dir}/")

        final_status = "monitor_stopped" if monitor_stopped else "completed"
        _final_status_dict: dict = {
            "status": final_status,
            "run_id": run_id,
            "scenario": "ne39",
            "episodes_total": args.episodes,
            "episodes_done": len(log["episode_rewards"]),
            "last_reward": float(log["episode_rewards"][-1]) if log["episode_rewards"] else None,
            "finished_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "started_at": _started_at,
            "logs_dir": _logs_dir,
            "last_eval_reward": _last_eval_reward,
        }
        if final_status == "monitor_stopped":
            _final_status_dict["stop_reason"] = _stop_reason
        write_training_status(run_dir, _final_status_dict)
        _eps_done = len(log["episode_rewards"])
        _last_r = log["episode_rewards"][-1] if log["episode_rewards"] else 0.0
        notify(
            f"NE39 [{final_status.replace('_', ' ')}]",
            f"{_eps_done} eps | last reward: {_last_r:+.0f} | best eval: {best_eval_reward:+.0f}",
        )
    except Exception as _train_exc:
        try:
            write_training_status(run_dir, {
                "status": "failed",
                "run_id": run_id,
                "scenario": "ne39",
                "episodes_total": args.episodes,
                "episodes_done": len(log["episode_rewards"]),
                "last_reward": float(log["episode_rewards"][-1]) if log["episode_rewards"] else None,
                "failed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "started_at": _started_at,
                "logs_dir": _logs_dir,
                "last_eval_reward": _last_eval_reward,
                "error": str(_train_exc),
            })
        except Exception:
            pass
        notify("NE39 Training FAILED", str(_train_exc)[:120])
        raise
    finally:
        _pbar.close()
        if tb_writer is not None:
            tb_writer.close()
        try:
            update_run_meta(meta_dir, {
                "finished_at": datetime.datetime.now().isoformat(),
                "total_episodes": start_episode + args.episodes,
            })
        except Exception:
            pass  # metadata loss is acceptable; don't shadow the real error
        env.close()

    total_time = time.time() - t_start
    print(f"\nTraining complete in {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"Best eval reward: {best_eval_reward:+.2f}")


if __name__ == "__main__":
    from utils.python_env_check import check_python_env
    check_python_env(r"C:\Users\27443\miniconda3\envs\andes_env\python.exe")
    args = parse_args()
    train(args)
