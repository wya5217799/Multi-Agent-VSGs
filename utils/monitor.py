"""TrainingMonitor: domain-level training diagnostics for GridGym.

Detects reward scaling bugs, action collapse, simulation failures,
and other domain-specific issues during RL training on power systems.

Implements ``TrainingCallback`` so it can be composed via ``CallbackList``.
Existing callers can continue using ``log_and_check()`` directly.
"""
from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path

import numpy as np
from typing import Any

from utils.training_callback import EpisodeResult, TrainingCallback


# Default check configurations
_DEFAULT_CHECKS = {
    "reward_magnitude":       {"action": "stop"},
    "reward_component_ratio": {"dominant": "r_f", "dominance_threshold": 0.5, "action": "warn"},
    "action_collapse":        {"std_threshold": 0.05, "window": 50, "action": "warn"},
    "action_saturation":      {"threshold": 0.8, "action": "warn"},
    "reward_plateau":         {"window": 100, "improvement_threshold": 0.01, "action": "warn"},
    "reward_divergence":      {"window": 50, "action": "stop"},
    "tds_failure_rate":       {"threshold": 0.2, "window": 50, "action": "warn"},
    "freq_out_of_range":      {"threshold_hz": 2.0, "window": 10, "min_episodes": 3, "action": "warn"},
    "physics_frozen":         {"window": 10, "epsilon": 1e-9, "action": "stop"},
    "agent_reward_disparity": {"window": 50, "std_threshold": 2.0, "action": "warn"},
    "loss_explosion":         {"multiplier": 10.0, "window": 20, "action": "warn"},
    "early_stopping":         {"patience": 500, "min_improvement": 0.02, "action": "warn"},
}


class TrainingMonitor(TrainingCallback):
    """Domain-level training diagnostics for power system RL environments.

    Implements ``TrainingCallback`` so it can be used in a ``CallbackList``.
    The ``on_episode_end(result)`` method is a thin wrapper around the
    existing ``log_and_check()`` API, which remains unchanged for callers
    that invoke it directly.
    """

    def __init__(
        self,
        calibration_episodes: int = 20,
        checks: dict[str, dict] | None = None,
        log_interval: int = 10,
        best_reward_callback: callable | None = None,
    ):
        self.calibration_episodes = calibration_episodes
        self.log_interval = log_interval

        # Merge user checks with defaults; track which keys user explicitly set
        self._user_checks = checks or {}
        self._checks = {}
        for name, defaults in _DEFAULT_CHECKS.items():
            user = self._user_checks.get(name, {})
            self._checks[name] = {**defaults, **user}

        # Data storage
        self._episode_rewards: list[float] = []
        self._reward_components: list[dict[str, float]] = []
        self._action_stats: list[dict[str, Any]] = []
        self._env_health: list[dict[str, Any]] = []
        self._per_agent_rewards: list[dict[int, float]] = []
        self._sac_losses: list[list[dict[str, float]]] = []

        # Calibration state
        self._calibrated = False
        self._calibration_data: dict[str, Any] = {}

        # Best reward tracking
        self._best_reward_callback = best_reward_callback
        self._best_reward = float('-inf')
        self._best_episode = -1

        # Early stopping state
        self._early_stop_best_reward = float('-inf')
        self._early_stop_best_ep_idx = 0

        # Trigger history
        self._trigger_history: list[dict[str, Any]] = []

        # Cooldown: suppress repeated warnings of same type
        self._last_trigger_ep: dict[str, int] = {}
        self._cooldown_episodes = 50  # minimum episodes between same warning

    def log_and_check(
        self,
        episode: int,
        rewards: float,
        reward_components: dict[str, float],
        actions: np.ndarray,
        info: dict[str, Any],
        per_agent_rewards: dict[int, float] | None = None,
        sac_losses: list[dict[str, float]] | None = None,
    ) -> bool:
        """Record episode data and run diagnostic checks.

        Args:
            episode: Episode number.
            rewards: Scalar total reward (all agents summed).
            reward_components: Named reward components, e.g. {"r_f": -1400, "r_h": -5}.
            actions: Shape (n_steps, n_agents, action_dim).
            info: Must contain "tds_failed" (bool) and "max_freq_deviation_hz" (float).
            per_agent_rewards: Per-agent rewards, e.g. {0: -100, 1: -200}.
            sac_losses: Per-agent SAC losses, e.g. [{"critic_loss": 0.5, ...}, ...].

        Returns:
            True if any check triggered a "stop" action.
        """
        # Store data
        self._episode_rewards.append(rewards)
        self._reward_components.append(dict(reward_components))

        # Store per-agent rewards
        if per_agent_rewards is not None:
            self._per_agent_rewards.append(dict(per_agent_rewards))

        # Store SAC losses
        if sac_losses is not None:
            self._sac_losses.append(list(sac_losses))

        # Best reward tracking
        if rewards > self._best_reward:
            self._best_reward = rewards
            self._best_episode = episode
            if self._best_reward_callback is not None:
                self._best_reward_callback(episode, rewards)

        # Compute action statistics per agent
        # actions shape: (steps, agents, action_dim)
        per_agent_std = np.std(actions, axis=0).mean(axis=-1)  # (agents,)
        per_agent_mean = np.mean(actions, axis=0).mean(axis=-1)  # (agents,)
        saturation_ratio = float(np.mean(np.abs(actions) > 0.95))
        self._action_stats.append({
            "per_agent_std": per_agent_std.tolist(),
            "per_agent_mean": per_agent_mean.tolist(),
            "saturation_ratio": saturation_ratio,
        })

        # Store env health
        self._env_health.append({
            "tds_failed": info.get("tds_failed", False),
            "max_freq_deviation_hz": info.get("max_freq_deviation_hz", 0.0),
            "max_power_swing": info.get("max_power_swing"),
        })

        # Calibration phase
        n = len(self._episode_rewards)
        if not self._calibrated and n >= self.calibration_episodes:
            self._calibrate()

        # Periodic summary
        if n > 0 and n % self.log_interval == 0:
            self._log_summary(episode)

        # Run checks (skip during calibration unless user set manual thresholds)
        if n < self.calibration_episodes:
            return self._run_manual_checks(episode)

        return self._run_all_checks(episode)

    # ─── TrainingCallback implementation ───

    def on_episode_end(self, result: EpisodeResult) -> bool:
        """Implement TrainingCallback: delegate to log_and_check().

        Allows TrainingMonitor to be used inside a CallbackList without
        changing any existing direct callers of log_and_check().
        """
        return self.log_and_check(
            episode=result.episode,
            rewards=result.rewards,
            reward_components=result.reward_components,
            actions=result.actions,
            info=result.info,
            per_agent_rewards=result.per_agent_rewards,
            sac_losses=result.sac_losses,
        )

    # ─── Calibration ───

    def _calibrate(self):
        """Auto-calibrate thresholds from collected baseline data."""
        self._calibrated = True  # Set early to prevent re-entry on exception
        rewards = np.array(self._episode_rewards[:self.calibration_episodes])
        self._calibration_data["reward_mean"] = float(np.mean(rewards))
        self._calibration_data["reward_std"] = float(np.std(rewards))

        # Action std baseline: mean per-agent std across calibration episodes
        all_stds = [s["per_agent_std"] for s in self._action_stats[:self.calibration_episodes]]
        self._calibration_data["action_std_baseline"] = float(np.mean(all_stds))

        # TDS failure baseline
        fails = [h["tds_failed"] for h in self._env_health[:self.calibration_episodes]]
        self._calibration_data["tds_failure_baseline"] = float(np.mean(fails))

        # Critic loss baseline (if SAC losses were logged during calibration)
        cal_losses = self._sac_losses[:self.calibration_episodes]
        if cal_losses:
            all_critic = [
                loss["critic_loss"]
                for ep_losses in cal_losses
                for loss in ep_losses
                if "critic_loss" in loss
            ]
            if all_critic:
                self._calibration_data["critic_loss_baseline"] = float(np.mean(all_critic))

        self._print_calibration_summary()

    def _print_calibration_summary(self):
        d = self._calibration_data
        mu, sigma = d["reward_mean"], d["reward_std"]
        lo, hi = mu - 3 * sigma, mu + 3 * sigma
        act_std = d["action_std_baseline"]
        tds_rate = d["tds_failure_baseline"]
        print(f"[Monitor] Calibration complete ({self.calibration_episodes} episodes).")
        print(f"          Reward baseline: mu={mu:.1f}, std={sigma:.1f} -> magnitude range: [{lo:.0f}, {hi:.0f}]")
        print(f"          Action std baseline: {act_std:.2f} -> collapse threshold: {act_std * 0.1:.3f}")
        print(f"          TDS failure baseline: {tds_rate * 100:.1f}% -> alert threshold: {max(tds_rate * 2, 0.3) * 100:.1f}%")

    # ─── Sliding window statistics ───

    def get_moving_stats(self, window: int = 50) -> dict:
        """Return windowed statistics over the last `window` episodes.

        Returns:
            Dict with keys: reward_mean, reward_std, action_std_mean,
            saturation_ratio_mean, tds_failure_rate, freq_deviation_mean.
        """
        n = len(self._episode_rewards)
        if n == 0:
            return {
                "reward_mean": 0.0,
                "reward_std": 0.0,
                "action_std_mean": 0.0,
                "saturation_ratio_mean": 0.0,
                "tds_failure_rate": 0.0,
                "freq_deviation_mean": 0.0,
            }

        w = min(window, n)
        rewards = np.array(self._episode_rewards[-w:])

        action_stds = [np.mean(s["per_agent_std"]) for s in self._action_stats[-w:]]
        sat_ratios = [s["saturation_ratio"] for s in self._action_stats[-w:]]

        health = self._env_health[-w:]
        fail_count = sum(1 for h in health if h["tds_failed"])
        freq_devs = [h["max_freq_deviation_hz"] for h in health]

        return {
            "reward_mean": float(np.mean(rewards)),
            "reward_std": float(np.std(rewards)),
            "action_std_mean": float(np.mean(action_stds)),
            "saturation_ratio_mean": float(np.mean(sat_ratios)),
            "tds_failure_rate": float(fail_count / w),
            "freq_deviation_mean": float(np.mean(freq_devs)),
        }

    # ─── Multi-run comparison ───

    @classmethod
    def compare_runs(cls, checkpoints: list[str]) -> None:
        """Load multiple monitor checkpoint JSON files and print a comparison table.

        Args:
            checkpoints: List of file paths to JSON checkpoint files.
        """
        runs = []
        for path_str in checkpoints:
            path = Path(path_str)
            with open(path, "r") as f:
                data = json.load(f)
            runs.append((path.name, data))

        if not runs:
            print("[Monitor] No checkpoint files provided.")
            return

        print(f"\n[Monitor] === Multi-Run Comparison ({len(runs)} runs) ===\n")
        header = (
            f"{'Run':<30} {'Episodes':>8} {'Final R':>10} {'Best R':>10} "
            f"{'Best Ep':>8} {'TDS Fail':>9} {'Checks':>7}"
        )
        print(header)
        print("-" * len(header))

        for name, data in runs:
            rewards = data.get("_episode_rewards", data.get("episode_rewards", []))
            n_episodes = len(rewards)
            final_reward = rewards[-1] if rewards else 0.0
            best_reward = max(rewards) if rewards else 0.0
            best_ep = rewards.index(best_reward) if rewards else 0

            env_health = data.get("_env_health", data.get("env_health", []))
            total_tds = sum(1 for h in env_health if h.get("tds_failed", False))

            trigger_history = data.get("_trigger_history", data.get("trigger_history", []))
            n_checks = len(trigger_history)

            print(
                f"{name:<30} {n_episodes:>8} {final_reward:>10.1f} {best_reward:>10.1f} "
                f"{best_ep:>8} {total_tds:>9} {n_checks:>7}"
            )

        print()

    # ─── Check infrastructure ───

    def _emit_check(self, check_name: str, episode: int, action: str, message: str):
        """Record trigger and print warning/stop message (with cooldown)."""
        self._trigger_history.append({
            "check": check_name, "episode": episode, "action": action, "message": message,
        })

        # Cooldown: suppress repeated warnings (stops always print)
        if action != "stop":
            last_ep = self._last_trigger_ep.get(check_name, -999)
            if episode - last_ep < self._cooldown_episodes:
                return  # suppress
        self._last_trigger_ep[check_name] = episode

        icon = "[STOP]" if action == "stop" else "[!]"
        label = "TRAINING STOPPED" if action == "stop" else "WARNING"
        print(f"\n{icon} [Monitor] {label}: {check_name} @ Ep {episode}")
        print(f"  {message}")
        if action == "stop":
            print(f"  Training terminated.\n")

    def _run_all_checks(self, episode: int) -> bool:
        results = []
        results.append(self._check_reward_magnitude(episode))
        results.append(self._check_reward_component_ratio(episode))
        results.append(self._check_action_collapse(episode))
        results.append(self._check_action_saturation(episode))
        results.append(self._check_reward_plateau(episode))
        results.append(self._check_reward_divergence(episode))
        results.append(self._check_tds_failure_rate(episode))
        results.append(self._check_freq_out_of_range(episode))
        results.append(self._check_physics_frozen(episode))
        results.append(self._check_agent_reward_disparity(episode))
        results.append(self._check_loss_explosion(episode))
        results.append(self._check_early_stopping(episode))
        return "stop" in results

    def _run_manual_checks(self, episode: int) -> bool:
        """During calibration, run checks with explicit thresholds or severe physics checks."""
        results = []
        if "expected_range" in self._user_checks.get("reward_magnitude", {}):
            results.append(self._check_reward_magnitude(episode))
        results.append(self._check_physics_frozen(episode))
        return "stop" in results

    # ─── Check: reward_magnitude ───

    def _check_reward_magnitude(self, episode: int) -> str | None:
        """Returns 'stop', 'warn', or None."""
        cfg = self._checks["reward_magnitude"]
        if cfg["action"] == "ignore":
            return None

        current = self._episode_rewards[-1]

        # Manual mode: user specified expected_range
        if "expected_range" in cfg:
            lo, hi = cfg["expected_range"]
            if current < lo or current > hi:
                deviation = abs(current / min(abs(lo), abs(hi), 1e-8))
                self._emit_check("reward_magnitude", episode, cfg["action"],
                    f"Observed reward = {current:.0f}, expected range ({lo}, {hi}). "
                    f"Deviation: {deviation:.0f}x.")
                return cfg["action"]
            return None

        # Auto mode: relative detection from calibration baseline
        if not self._calibrated:
            return None
        mu = self._calibration_data["reward_mean"]
        if abs(mu) < 1e-8:
            return None
        ratio = abs(current / mu)
        if ratio >= 100:
            self._emit_check("reward_magnitude", episode, cfg["action"],
                f"Reward {current:.0f} is {ratio:.0f}x baseline ({mu:.0f}).")
            return cfg["action"]
        return None

    # ─── Check: reward_component_ratio ───

    def _check_reward_component_ratio(self, episode: int) -> str | None:
        cfg = self._checks["reward_component_ratio"]
        if cfg["action"] == "ignore":
            return None

        components = self._reward_components[-1]
        dominant_name = cfg.get("dominant", "r_f")
        threshold = cfg.get("dominance_threshold", 0.5)

        if dominant_name not in components:
            return None

        total_abs = sum(abs(v) for v in components.values())
        if total_abs < 1e-8:
            return None

        dominant_ratio = abs(components[dominant_name]) / total_abs
        if dominant_ratio < threshold:
            breakdown = ", ".join(f"{k}: {abs(v)/total_abs*100:.1f}%" for k, v in components.items())
            self._emit_check("reward_component_ratio", episode, cfg["action"],
                f"'{dominant_name}' is only {dominant_ratio*100:.1f}% of total reward "
                f"(threshold: {threshold*100:.0f}%). Breakdown: {breakdown}")
            return cfg["action"]
        return None

    # ─── Check: action_collapse ───

    def _check_action_collapse(self, episode: int) -> str | None:
        cfg = self._checks["action_collapse"]
        if cfg["action"] == "ignore":
            return None

        window = cfg.get("window", 50)
        if len(self._action_stats) < window:
            return None

        # Use auto-calibrated threshold unless user explicitly set one
        threshold = cfg.get("std_threshold", 0.05)
        if self._calibrated and "std_threshold" not in self._user_checks.get("action_collapse", {}):
            baseline = self._calibration_data.get("action_std_baseline", 0.5)
            threshold = baseline * 0.1

        recent = self._action_stats[-window:]
        n_agents = len(recent[0]["per_agent_std"])

        for agent_idx in range(n_agents):
            agent_stds = [s["per_agent_std"][agent_idx] for s in recent]
            if all(s < threshold for s in agent_stds):
                avg_std = np.mean(agent_stds)
                self._emit_check("action_collapse", episode, cfg["action"],
                    f"Agent {agent_idx} action std = {avg_std:.4f} "
                    f"(threshold: {threshold:.4f}) over last {window} episodes.\n"
                    f"  Interpretation: Agent may be learning a near-zero policy (\"do nothing\").\n"
                    f"  Suggestion: Check reward scaling -- ensure frequency reward dominates.")
                return cfg["action"]
        return None

    # ─── Check: action_saturation ───

    def _check_action_saturation(self, episode: int) -> str | None:
        cfg = self._checks["action_saturation"]
        if cfg["action"] == "ignore":
            return None

        threshold = cfg.get("threshold", 0.8)
        sat_ratio = self._action_stats[-1]["saturation_ratio"]

        if sat_ratio > threshold:
            self._emit_check("action_saturation", episode, cfg["action"],
                f"Action saturation = {sat_ratio*100:.1f}% (threshold: {threshold*100:.0f}%).\n"
                f"  Most actions are at boundary +/-0.95. Action space may be too small.")
            return cfg["action"]
        return None

    # ─── Check: reward_plateau ───

    def _check_reward_plateau(self, episode: int) -> str | None:
        cfg = self._checks["reward_plateau"]
        if cfg["action"] == "ignore":
            return None

        window = cfg.get("window", 100)
        threshold = cfg.get("improvement_threshold", 0.01)
        if len(self._episode_rewards) < window:
            return None

        recent = self._episode_rewards[-window:]
        min_r, max_r = min(recent), max(recent)

        if abs(min_r) < 1e-8:
            # Near-zero rewards: use absolute difference
            if max_r - min_r < 1e-6:
                self._emit_check("reward_plateau", episode, cfg["action"],
                    f"Reward stuck near zero for {window} episodes.")
                return cfg["action"]
            return None

        improvement = (max_r - min_r) / max(abs(min_r), 1e-8)
        if improvement < threshold:
            self._emit_check("reward_plateau", episode, cfg["action"],
                f"Reward range [{min_r:.1f}, {max_r:.1f}] over last {window} episodes.\n"
                f"  Improvement: {improvement*100:.2f}% (threshold: {threshold*100:.1f}%).\n"
                f"  Training may be stuck in a local optimum.")
            return cfg["action"]
        return None

    # ─── Check: reward_divergence ───

    def _check_reward_divergence(self, episode: int) -> str | None:
        cfg = self._checks["reward_divergence"]
        if cfg["action"] == "ignore":
            return None

        window = cfg.get("window", 50)
        if len(self._episode_rewards) < window:
            return None

        recent = np.array(self._episode_rewards[-window:])
        x = np.arange(window)

        # Linear fit: reward = slope * x + intercept
        coeffs = np.polyfit(x, recent, 1)
        slope = coeffs[0]

        if slope >= 0:
            return None  # Not declining

        # R-squared
        predicted = np.polyval(coeffs, x)
        ss_res = np.sum((recent - predicted) ** 2)
        ss_tot = np.sum((recent - np.mean(recent)) ** 2)
        r_squared = 1.0 - ss_res / max(ss_tot, 1e-8)

        if r_squared < 0.3:
            return None  # Too noisy, not a real trend

        # Normalized slope: total change over window relative to mean
        mean_reward = abs(np.mean(recent))
        if mean_reward < 1e-8:
            return None
        normalized = abs(slope * window) / mean_reward

        if normalized > 0.1:
            self._emit_check("reward_divergence", episode, cfg["action"],
                f"Reward declining over last {window} episodes.\n"
                f"  Slope: {slope:.1f}/ep, R^2={r_squared:.2f}, "
                f"total change: {abs(slope * window):.0f} ({normalized*100:.0f}% of mean).\n"
                f"  Training may be diverging.")
            return cfg["action"]
        return None

    # ─── Check: tds_failure_rate ───

    def _check_tds_failure_rate(self, episode: int) -> str | None:
        cfg = self._checks["tds_failure_rate"]
        if cfg["action"] == "ignore":
            return None

        window = cfg.get("window", 50)
        if len(self._env_health) < window:
            return None

        # Use auto-calibrated threshold unless user explicitly set one
        threshold = cfg.get("threshold", 0.2)
        if self._calibrated and "threshold" not in self._user_checks.get("tds_failure_rate", {}):
            baseline = self._calibration_data.get("tds_failure_baseline", 0.0)
            threshold = max(baseline * 2, 0.3)

        recent = self._env_health[-window:]
        fail_count = sum(1 for h in recent if h["tds_failed"])
        rate = fail_count / window

        if rate > threshold:
            self._emit_check("tds_failure_rate", episode, cfg["action"],
                f"TDS failure rate: {fail_count}/{window} = {rate*100:.1f}% "
                f"(threshold: {threshold*100:.0f}%).\n"
                f"  Simulation may be numerically unstable.")
            return cfg["action"]
        return None

    # ─── Check: freq_out_of_range ───

    def _check_freq_out_of_range(self, episode: int) -> str | None:
        cfg = self._checks["freq_out_of_range"]
        if cfg["action"] == "ignore":
            return None

        window = cfg.get("window", 10)
        min_episodes = cfg.get("min_episodes", 3)
        threshold_hz = cfg.get("threshold_hz", 2.0)

        if len(self._env_health) < window:
            return None

        recent = self._env_health[-window:]
        violations = sum(1 for h in recent if h["max_freq_deviation_hz"] > threshold_hz)

        if violations >= min_episodes:
            self._emit_check("freq_out_of_range", episode, cfg["action"],
                f"Frequency exceeded +/-{threshold_hz} Hz in {violations}/{window} recent episodes "
                f"(threshold: {min_episodes} episodes).\n"
                f"  VSG parameters may be causing system instability.")
            return cfg["action"]
        return None

    # ─── Check: physics_frozen ───

    def _check_physics_frozen(self, episode: int) -> str | None:
        cfg = self._checks["physics_frozen"]
        if cfg["action"] == "ignore":
            return None

        window = cfg.get("window", 10)
        epsilon = cfg.get("epsilon", 1e-9)
        if len(self._env_health) < window:
            return None

        recent = self._env_health[-window:]
        swings = [h.get("max_power_swing") for h in recent]
        if any(s is None for s in swings):
            return None

        if all(abs(float(s)) <= epsilon for s in swings):
            self._emit_check("physics_frozen", episode, cfg["action"],
                f"max_power_swing <= {epsilon:g} for the last {window} episodes.\n"
                f"  Electrical power response appears frozen; M/D changes may not reach the grid.")
            return cfg["action"]
        return None

    # ─── Check: agent_reward_disparity ───

    def _check_agent_reward_disparity(self, episode: int) -> str | None:
        cfg = self._checks["agent_reward_disparity"]
        if cfg["action"] == "ignore":
            return None

        window = cfg.get("window", 50)
        std_threshold = cfg.get("std_threshold", 2.0)

        if len(self._per_agent_rewards) < window:
            return None

        recent = self._per_agent_rewards[-window:]
        agent_ids = sorted(recent[0].keys())
        if len(agent_ids) < 2:
            return None

        # Compute mean reward per agent over the window
        agent_means = {}
        for aid in agent_ids:
            agent_means[aid] = float(np.mean([r[aid] for r in recent]))

        values = np.array(list(agent_means.values()))
        overall_mean = float(np.mean(values))
        overall_std = float(np.std(values))

        if overall_std < 1e-8:
            return None

        for aid in agent_ids:
            if agent_means[aid] < overall_mean - std_threshold * overall_std:
                self._emit_check("agent_reward_disparity", episode, cfg["action"],
                    f"Agent {aid} mean reward = {agent_means[aid]:.1f} over last {window} episodes.\n"
                    f"  Cross-agent mean = {overall_mean:.1f}, std = {overall_std:.1f}.\n"
                    f"  Agent is >{std_threshold:.1f} std devs below mean.")
                return cfg["action"]
        return None

    # ─── Check: loss_explosion ───

    def _check_loss_explosion(self, episode: int) -> str | None:
        cfg = self._checks["loss_explosion"]
        if cfg["action"] == "ignore":
            return None

        window = cfg.get("window", 20)
        multiplier = cfg.get("multiplier", 10.0)

        if len(self._sac_losses) < window:
            return None
        if not self._calibrated:
            return None

        baseline = self._calibration_data.get("critic_loss_baseline")
        if baseline is None or baseline < 1e-8:
            return None

        recent = self._sac_losses[-window:]
        if not recent or not recent[0]:
            return None
        for agent_idx in range(len(recent[0])):
            agent_losses = [
                ep_losses[agent_idx]["critic_loss"]
                for ep_losses in recent
                if agent_idx < len(ep_losses) and "critic_loss" in ep_losses[agent_idx]
            ]
            if not agent_losses:
                continue
            mean_loss = float(np.mean(agent_losses))
            if mean_loss > multiplier * baseline:
                self._emit_check("loss_explosion", episode, cfg["action"],
                    f"Agent {agent_idx} critic_loss = {mean_loss:.2f} over last {window} episodes.\n"
                    f"  Baseline: {baseline:.2f}, ratio: {mean_loss/baseline:.1f}x "
                    f"(threshold: {multiplier:.0f}x).")
                return cfg["action"]
        return None

    # ─── Check: early_stopping ───

    def _check_early_stopping(self, episode: int) -> str | None:
        cfg = self._checks["early_stopping"]
        if cfg["action"] == "ignore":
            return None

        patience = cfg.get("patience", 150)
        min_improvement = cfg.get("min_improvement", 0.02)

        current = self._episode_rewards[-1]
        ep_idx = len(self._episode_rewards) - 1

        # Update best
        if self._early_stop_best_reward < -1e30:
            # First episode
            self._early_stop_best_reward = current
            self._early_stop_best_ep_idx = ep_idx
            return None

        # Check for improvement (relative or absolute if near zero)
        if abs(self._early_stop_best_reward) > 1e-8:
            improvement = (current - self._early_stop_best_reward) / abs(self._early_stop_best_reward)
        else:
            improvement = current - self._early_stop_best_reward

        if improvement > min_improvement:
            self._early_stop_best_reward = current
            self._early_stop_best_ep_idx = ep_idx
            return None

        # Check patience
        episodes_since = ep_idx - self._early_stop_best_ep_idx
        if episodes_since >= patience:
            self._emit_check("early_stopping", episode, cfg["action"],
                f"No improvement >{min_improvement*100:.1f}% for {episodes_since} episodes "
                f"(patience: {patience}).\n"
                f"  Best reward: {self._early_stop_best_reward:.1f} @ ep {self._early_stop_best_ep_idx}.\n"
                f"  Current: {current:.1f}. Consider stopping or adjusting hyperparameters.")
            return cfg["action"]
        return None

    # ─── Persistence & export ───

    def save_checkpoint(self, path: str):
        """Save all monitor state to a JSON file."""
        data = {
            "calibration_episodes": self.calibration_episodes,
            "_calibrated": self._calibrated,
            "_calibration_data": self._calibration_data,
            "_episode_rewards": self._episode_rewards,
            "_reward_components": self._reward_components,
            "_action_stats": self._action_stats,
            "_env_health": self._env_health,
            "_trigger_history": self._trigger_history,
            "_per_agent_rewards": self._per_agent_rewards,
            "_sac_losses": self._sac_losses,
            "_best_reward": self._best_reward,
            "_best_episode": self._best_episode,
            "_early_stop_best_reward": self._early_stop_best_reward,
            "_early_stop_best_ep_idx": self._early_stop_best_ep_idx,
            "_last_trigger_ep": self._last_trigger_ep,
            "_user_checks": self._user_checks,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=lambda o: float(o) if hasattr(o, 'item') else str(o))

    @classmethod
    def load_checkpoint(cls, path: str) -> "TrainingMonitor":
        """Create a TrainingMonitor from a saved checkpoint JSON."""
        with open(path) as f:
            data = json.load(f)

        user_checks = data.get("_user_checks", {})
        monitor = cls(calibration_episodes=data["calibration_episodes"], checks=user_checks)
        monitor._episode_rewards = data["_episode_rewards"]
        monitor._reward_components = data["_reward_components"]
        monitor._action_stats = data["_action_stats"]
        monitor._env_health = data["_env_health"]
        monitor._trigger_history = data["_trigger_history"]
        monitor._calibration_data = data["_calibration_data"]
        monitor._calibrated = data["_calibrated"]
        monitor._per_agent_rewards = [
            {int(k): v for k, v in d.items()}
            for d in data.get("_per_agent_rewards", [])
        ]
        monitor._sac_losses = data.get("_sac_losses", [])
        monitor._best_reward = data.get("_best_reward", float('-inf'))
        monitor._best_episode = data.get("_best_episode", -1)
        monitor._early_stop_best_reward = data.get("_early_stop_best_reward", float('-inf'))
        monitor._early_stop_best_ep_idx = data.get("_early_stop_best_ep_idx", 0)
        monitor._last_trigger_ep = data.get("_last_trigger_ep", {})

        # If enough episodes exist, ensure calibrated
        if not monitor._calibrated and len(monitor._episode_rewards) >= monitor.calibration_episodes:
            monitor._calibrate()

        return monitor

    def export_csv(self, path: str):
        """Export per-episode data to CSV."""
        n = len(self._episode_rewards)
        if n == 0:
            return

        # Determine number of agents from first action_stats entry
        n_agents = len(self._action_stats[0]["per_agent_mean"])

        # Build header
        header = ["episode", "reward", "r_f", "r_h", "r_d"]
        for i in range(n_agents):
            header.append(f"action_mean_agent_{i}")
        for i in range(n_agents):
            header.append(f"action_std_agent_{i}")
        header.extend(["saturation_ratio", "tds_failed", "max_freq_deviation_hz", "max_power_swing"])

        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)

            for ep in range(n):
                comps = self._reward_components[ep]
                stats = self._action_stats[ep]
                health = self._env_health[ep]

                row = [
                    ep,
                    self._episode_rewards[ep],
                    comps.get("r_f", 0.0),
                    comps.get("r_h", 0.0),
                    comps.get("r_d", 0.0),
                ]
                for i in range(n_agents):
                    row.append(stats["per_agent_mean"][i])
                for i in range(n_agents):
                    row.append(stats["per_agent_std"][i])
                row.append(stats["saturation_ratio"])
                row.append(int(health["tds_failed"]))
                row.append(health["max_freq_deviation_hz"])
                row.append(health.get("max_power_swing"))

                writer.writerow(row)

    def export_tensorboard(self, log_dir: str):
        """Export data to TensorBoard format."""
        try:
            from torch.utils.tensorboard import SummaryWriter
        except ImportError:
            print("[Monitor] WARNING: torch.utils.tensorboard not available. "
                  "Skipping TensorBoard export.")
            return

        n = len(self._episode_rewards)
        if n == 0:
            return

        writer = SummaryWriter(log_dir=log_dir)

        for ep in range(n):
            # Reward scalars
            writer.add_scalar("reward/total", self._episode_rewards[ep], ep)

            comps = self._reward_components[ep]
            for key, val in comps.items():
                writer.add_scalar(f"reward/{key}", val, ep)

            # Action stats
            stats = self._action_stats[ep]
            mean_std = float(np.mean(stats["per_agent_std"]))
            writer.add_scalar("action/mean_std", mean_std, ep)
            writer.add_scalar("action/saturation_ratio",
                              stats["saturation_ratio"], ep)

            # Environment health
            health = self._env_health[ep]
            writer.add_scalar("env/max_freq_deviation_hz",
                              health["max_freq_deviation_hz"], ep)

            # Rolling TDS failure rate (window=50)
            window = 50
            start = max(0, ep - window + 1)
            recent = self._env_health[start:ep + 1]
            tds_rate = sum(1 for h in recent if h["tds_failed"]) / len(recent)
            writer.add_scalar("env/tds_failure_rate", tds_rate, ep)

        writer.close()

    # ─── Output formatting ───

    def _log_summary(self, episode: int):
        r = self._episode_rewards[-1]
        comps = self._reward_components[-1]
        total_abs = sum(abs(v) for v in comps.values())
        comp_str = ", ".join(
            f"{k}: {abs(v)/max(total_abs,1e-8)*100:.1f}%" for k, v in comps.items()
        )
        stats = self._action_stats[-1]
        mu_str = "[" + ", ".join(f"{m:.2f}" for m in stats["per_agent_mean"]) + "]"
        std_str = "[" + ", ".join(f"{s:.2f}" for s in stats["per_agent_std"]) + "]"

        # TDS failures in recent log_interval
        recent_health = self._env_health[-self.log_interval:]
        tds_fails = sum(1 for h in recent_health if h["tds_failed"])
        max_freq = max(h["max_freq_deviation_hz"] for h in recent_health)

        print(f"[Monitor] Ep {episode} | Reward: {r:.1f} ({comp_str})")
        print(f"          Actions mu: {mu_str}  std: {std_str}")
        print(f"          TDS fails: {tds_fails}/{len(recent_health)} ({tds_fails/len(recent_health)*100:.1f}%) | Freq peak: {max_freq:.2f} Hz")

        # Per-agent rewards (if available)
        if self._per_agent_rewards:
            par = self._per_agent_rewards[-1]
            par_str = ", ".join(f"a{aid}: {rv:.1f}" for aid, rv in sorted(par.items()))
            print(f"          Per-agent rewards: [{par_str}]")

        # SAC losses (if available)
        if self._sac_losses:
            losses = self._sac_losses[-1]
            critic_vals = [l["critic_loss"] for l in losses if "critic_loss" in l]
            alpha_vals = [l["alpha"] for l in losses if "alpha" in l]
            if critic_vals:
                mean_critic = float(np.mean(critic_vals))
                parts = [f"mean critic_loss: {mean_critic:.3f}"]
                if alpha_vals:
                    mean_alpha = float(np.mean(alpha_vals))
                    parts.append(f"mean alpha: {mean_alpha:.3f}")
                print(f"          SAC: {', '.join(parts)}")

    def summary(self):
        n = len(self._episode_rewards)
        if n == 0:
            print("[Monitor] No episodes recorded.")
            return

        cal_status = "complete" if self._calibrated else f"incomplete ({n}/{self.calibration_episodes} ep)"
        first_r = self._episode_rewards[0]
        last_r = self._episode_rewards[-1]
        best_r = max(self._episode_rewards)
        best_ep = self._episode_rewards.index(best_r)
        worst_r = min(self._episode_rewards)
        worst_ep = self._episode_rewards.index(worst_r)

        total_tds = sum(1 for h in self._env_health if h["tds_failed"])
        max_freq = max(h["max_freq_deviation_hz"] for h in self._env_health)
        max_freq_ep = max(range(n), key=lambda i: self._env_health[i]["max_freq_deviation_hz"])

        print(f"\n[Monitor] === Training Summary ===")
        print(f"  Episodes: {n} | Calibration: {cal_status}")
        print(f"  Reward:   {first_r:.0f} (ep 0) -> {last_r:.0f} (ep {n-1})")
        print(f"  Best:     {best_r:.0f} @ ep {best_ep} | Worst: {worst_r:.0f} @ ep {worst_ep}")

        # Best reward episode (from callback tracking)
        if self._best_episode >= 0:
            print(f"  Best reward callback: {self._best_reward:.0f} @ ep {self._best_episode}")

        # Per-agent reward range
        if self._per_agent_rewards:
            agent_ids = sorted(self._per_agent_rewards[0].keys())
            agent_totals = {
                aid: [r[aid] for r in self._per_agent_rewards if aid in r]
                for aid in agent_ids
            }
            agent_means = {aid: float(np.mean(vals)) for aid, vals in agent_totals.items()}
            best_agent = max(agent_means, key=agent_means.get)
            worst_agent = min(agent_means, key=agent_means.get)
            print(f"  Per-agent reward (mean): best agent {best_agent} = {agent_means[best_agent]:.1f}, "
                  f"worst agent {worst_agent} = {agent_means[worst_agent]:.1f}")

        # Loss trend summary
        if self._sac_losses:
            all_critic = [
                float(np.mean([l["critic_loss"] for l in ep if "critic_loss" in l]))
                for ep in self._sac_losses
                if any("critic_loss" in l for l in ep)
            ]
            if len(all_critic) >= 2:
                early = float(np.mean(all_critic[:min(20, len(all_critic))]))
                late = float(np.mean(all_critic[-min(20, len(all_critic)):]))
                trend = "decreasing" if late < early * 0.9 else ("increasing" if late > early * 1.1 else "stable")
                print(f"  Loss trend: critic_loss early={early:.3f} -> late={late:.3f} ({trend})")

        if self._trigger_history:
            print(f"\n  Checks triggered:")
            # Group by check name
            counts = Counter(t["check"] for t in self._trigger_history)
            for check_name, count in counts.items():
                first_ep = next(t["episode"] for t in self._trigger_history if t["check"] == check_name)
                action = next(t["action"] for t in self._trigger_history if t["check"] == check_name)
                icon = "[STOP]" if action == "stop" else "[!]"
                label = "STOP" if action == "stop" else "WARN"
                print(f"    {check_name:<28} {icon} {label:<5} @ ep {first_ep:<5} ({count} time{'s' if count > 1 else ''})")
        else:
            print(f"\n  No checks triggered.")

        print(f"\n  TDS failures: {total_tds}/{n} ({total_tds/n*100:.1f}%)")
        print(f"  Freq peak deviation: {max_freq:.2f} Hz (ep {max_freq_ep})")
        print()
