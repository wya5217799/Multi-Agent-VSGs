# TrainingMonitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a domain-level training diagnostic module (`TrainingMonitor`) that detects training problems (reward scaling bugs, action collapse, simulation failures) within the first 50 episodes instead of after 2000.

**Architecture:** Single `TrainingMonitor` class in `utils/monitor.py`. 8 detection rules operate on environment-layer data (rewards, actions, simulation health). Auto-calibration with manual override. Zero extra dependencies (Python stdlib + NumPy only).

**Tech Stack:** Python 3.9+, NumPy

**Spec:** `docs/superpowers/specs/2026-03-23-training-monitor-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `utils/__init__.py` | **Create** | Make `utils` a Python package (empty file) |
| `utils/monitor.py` | **Create** | TrainingMonitor class — all 8 checks, calibration, output |
| `tests/test_monitor.py` | **Create** | Unit tests for all checks, calibration, edge cases |
| `env/ode/multi_vsg_env.py` | **Modify** | Track episode-peak `max_freq_deviation_hz` in info dict |
| `env/andes/base_env.py` | **Modify** | Track episode-peak `max_freq_deviation_hz` in info dict |
| `scenarios/kundur/train_ode.py` | **Modify** | Integrate TrainingMonitor (~10 lines) |
| `scenarios/kundur/train_andes.py` | **Modify** | Integrate TrainingMonitor (~10 lines) |

---

## Task 1: TrainingMonitor Skeleton

**Files:**
- Create: `utils/monitor.py`
- Create: `tests/test_monitor.py`

- [ ] **Step 1: Write test for constructor and log_and_check interface**

```python
# tests/test_monitor.py
import numpy as np
import pytest
from utils.monitor import TrainingMonitor


class TestMonitorSkeleton:
    def test_default_construction(self):
        m = TrainingMonitor()
        assert m.calibration_episodes == 20
        assert m.log_interval == 10

    def test_custom_construction(self):
        m = TrainingMonitor(calibration_episodes=10, log_interval=5)
        assert m.calibration_episodes == 10
        assert m.log_interval == 5

    def test_log_and_check_returns_false_during_calibration(self):
        m = TrainingMonitor(calibration_episodes=5)
        actions = np.random.randn(50, 4, 2)  # (steps, agents, action_dim)
        result = m.log_and_check(
            episode=0,
            rewards=-1500.0,
            reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
            actions=actions,
            info={"tds_failed": False, "max_freq_deviation_hz": 0.3},
        )
        assert result is False

    def test_data_accumulates(self):
        m = TrainingMonitor(calibration_episodes=5)
        actions = np.random.randn(50, 4, 2)
        for ep in range(3):
            m.log_and_check(
                episode=ep, rewards=-1500.0 + ep * 10,
                reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                actions=actions,
                info={"tds_failed": False, "max_freq_deviation_hz": 0.3},
            )
        assert len(m._episode_rewards) == 3
        assert len(m._reward_components) == 3
        assert len(m._action_stats) == 3
        assert len(m._env_health) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:\Users\27443\Desktop\Multi-Agent  VSGs" && python -m pytest tests/test_monitor.py::TestMonitorSkeleton -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.monitor'`

- [ ] **Step 3: Create `utils/__init__.py` and implement skeleton**

Create an empty `utils/__init__.py` to make `utils` a Python package:

```python
# utils/__init__.py
```

Then create the monitor module:

```python
# utils/monitor.py
"""TrainingMonitor: domain-level training diagnostics for GridGym.

Detects reward scaling bugs, action collapse, simulation failures,
and other domain-specific issues during RL training on power systems.
"""

from collections import Counter

import numpy as np
from typing import Any


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
}


class TrainingMonitor:
    """Domain-level training diagnostics for power system RL environments."""

    def __init__(
        self,
        calibration_episodes: int = 20,
        checks: dict[str, dict] | None = None,
        log_interval: int = 10,
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

        # Calibration state
        self._calibrated = False
        self._calibration_data: dict[str, Any] = {}

        # Trigger history
        self._trigger_history: list[dict[str, Any]] = []

    def log_and_check(
        self,
        episode: int,
        rewards: float,
        reward_components: dict[str, float],
        actions: np.ndarray,
        info: dict[str, Any],
    ) -> bool:
        """Record episode data and run diagnostic checks.

        Args:
            episode: Episode number.
            rewards: Scalar total reward (all agents summed).
            reward_components: Named reward components, e.g. {"r_f": -1400, "r_h": -5}.
            actions: Shape (n_steps, n_agents, action_dim).
            info: Must contain "tds_failed" (bool) and "max_freq_deviation_hz" (float).

        Returns:
            True if any check triggered a "stop" action.
        """
        # Store data
        self._episode_rewards.append(rewards)
        self._reward_components.append(dict(reward_components))

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

    def _calibrate(self):
        """Auto-calibrate thresholds from collected baseline data."""
        self._calibrated = True
        # Placeholder — implemented in Task 2
        pass

    def _run_manual_checks(self, episode: int) -> bool:
        """Run only checks with user-specified (non-auto) thresholds."""
        # Placeholder — implemented in Task 3+
        return False

    def _run_all_checks(self, episode: int) -> bool:
        """Run all enabled checks."""
        # Placeholder — implemented in Task 3+
        return False

    def _log_summary(self, episode: int):
        """Print periodic training summary."""
        # Placeholder — implemented in Task 9
        pass

    def summary(self):
        """Print final training summary."""
        # Placeholder — implemented in Task 9
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "C:\Users\27443\Desktop\Multi-Agent  VSGs" && python -m pytest tests/test_monitor.py::TestMonitorSkeleton -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add utils/__init__.py utils/monitor.py tests/test_monitor.py
git commit -m "feat(monitor): add TrainingMonitor skeleton with data collection"
```

---

## Task 2: Calibration Engine

**Files:**
- Modify: `utils/monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write calibration tests**

```python
class TestCalibration:
    def _feed_episodes(self, m, n, reward=-1500.0, action_std=0.5, tds_fail=False):
        """Helper: feed n episodes with given characteristics."""
        for ep in range(n):
            actions = np.random.randn(50, 4, 2) * action_std
            m.log_and_check(
                episode=ep, rewards=reward,
                reward_components={"r_f": reward * 0.95, "r_h": reward * 0.025, "r_d": reward * 0.025},
                actions=actions,
                info={"tds_failed": tds_fail, "max_freq_deviation_hz": 0.3},
            )

    def test_calibration_triggers_after_n_episodes(self):
        m = TrainingMonitor(calibration_episodes=10)
        self._feed_episodes(m, 9)
        assert not m._calibrated
        self._feed_episodes(m, 1)  # 10th episode
        assert m._calibrated

    def test_calibration_sets_reward_baseline(self):
        m = TrainingMonitor(calibration_episodes=5)
        rewards = [-1500, -1400, -1600, -1450, -1550]
        for ep, r in enumerate(rewards):
            actions = np.random.randn(50, 4, 2) * 0.5
            m.log_and_check(
                episode=ep, rewards=r,
                reward_components={"r_f": r * 0.95, "r_h": r * 0.025, "r_d": r * 0.025},
                actions=actions,
                info={"tds_failed": False, "max_freq_deviation_hz": 0.3},
            )
        assert "reward_mean" in m._calibration_data
        assert "reward_std" in m._calibration_data
        assert abs(m._calibration_data["reward_mean"] - np.mean(rewards)) < 1e-6

    def test_calibration_sets_action_std_baseline(self):
        m = TrainingMonitor(calibration_episodes=5)
        self._feed_episodes(m, 5, action_std=0.5)
        assert "action_std_baseline" in m._calibration_data
        assert m._calibration_data["action_std_baseline"] > 0

    def test_calibration_sets_tds_failure_baseline(self):
        m = TrainingMonitor(calibration_episodes=10)
        for ep in range(10):
            actions = np.random.randn(50, 4, 2)
            m.log_and_check(
                episode=ep, rewards=-1500,
                reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                actions=actions,
                info={"tds_failed": (ep % 10 == 0), "max_freq_deviation_hz": 0.3},
            )
        assert "tds_failure_baseline" in m._calibration_data

    def test_incomplete_calibration(self):
        """Training ends before calibration completes."""
        m = TrainingMonitor(calibration_episodes=20)
        self._feed_episodes(m, 5)
        assert not m._calibrated
        # summary should note incomplete calibration
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_monitor.py::TestCalibration -v`
Expected: FAIL — calibration_data not populated

- [ ] **Step 3: Implement `_calibrate()`**

In `utils/monitor.py`, replace the `_calibrate` placeholder:

```python
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

    self._print_calibration_summary()

def _print_calibration_summary(self):
    d = self._calibration_data
    mu, sigma = d["reward_mean"], d["reward_std"]
    lo, hi = mu - 3 * sigma, mu + 3 * sigma
    act_std = d["action_std_baseline"]
    tds_rate = d["tds_failure_baseline"]
    print(f"[Monitor] Calibration complete ({self.calibration_episodes} episodes).")
    print(f"          Reward baseline: \u03bc={mu:.1f}, \u03c3={sigma:.1f} \u2192 magnitude range: [{lo:.0f}, {hi:.0f}]")
    print(f"          Action std baseline: {act_std:.2f} \u2192 collapse threshold: {act_std * 0.1:.3f}")
    print(f"          TDS failure baseline: {tds_rate * 100:.1f}% \u2192 alert threshold: {max(tds_rate * 2, 0.3) * 100:.1f}%")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_monitor.py::TestCalibration -v`
Expected: All passed

- [ ] **Step 5: Commit**

```bash
git add utils/monitor.py tests/test_monitor.py
git commit -m "feat(monitor): implement auto-calibration engine"
```

---

## Task 3: Reward Checks (magnitude + component_ratio)

**Files:**
- Modify: `utils/monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write tests for reward_magnitude**

```python
class TestRewardMagnitude:
    def test_manual_range_triggers_stop(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_magnitude": {"expected_range": (-3000, -200), "action": "stop"}},
        )
        actions = np.random.randn(50, 4, 2)
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # Episode 5: reward way out of range
        result = m.log_and_check(5, rewards=-10_000_000, reward_components={"r_f": -1400, "r_h": -5e6, "r_d": -5e6},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is True  # stop triggered

    def test_manual_range_no_trigger_in_range(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_magnitude": {"expected_range": (-3000, -200), "action": "stop"}},
        )
        actions = np.random.randn(50, 4, 2)
        for ep in range(6):
            result = m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                                     actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is False

    def test_auto_mode_relative_detection(self):
        """Without manual expected_range, uses relative detection from baseline."""
        m = TrainingMonitor(calibration_episodes=5)
        actions = np.random.randn(50, 4, 2)
        # Calibration: reward ~ -1500
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # Sudden jump to 200x baseline
        result = m.log_and_check(5, rewards=-300_000, reward_components={"r_f": -1400, "r_h": -150000, "r_d": -150000},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is True

    def test_ignore_action(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_magnitude": {"expected_range": (-3000, -200), "action": "ignore"}},
        )
        actions = np.random.randn(50, 4, 2)
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        result = m.log_and_check(5, rewards=-10_000_000, reward_components={"r_f": -1400, "r_h": -5e6, "r_d": -5e6},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is False  # ignored
```

- [ ] **Step 2: Write tests for reward_component_ratio**

```python
class TestRewardComponentRatio:
    def test_dominant_below_threshold_triggers_warn(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"reward_component_ratio": {"dominant": "r_f", "dominance_threshold": 0.5, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2)
        for ep in range(3):
            m.log_and_check(ep, rewards=-10e6, reward_components={"r_f": -1400, "r_h": -5e6, "r_d": -5e6},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # r_f is 0.01% — way below 50% threshold. Warn but don't stop.
        result = m.log_and_check(3, rewards=-10e6, reward_components={"r_f": -1400, "r_h": -5e6, "r_d": -5e6},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert result is False  # warn, not stop
        assert any(t["check"] == "reward_component_ratio" for t in m._trigger_history)

    def test_dominant_above_threshold_no_trigger(self):
        m = TrainingMonitor(calibration_episodes=3)
        actions = np.random.randn(50, 4, 2)
        for ep in range(4):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "reward_component_ratio" for t in m._trigger_history)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_monitor.py::TestRewardMagnitude tests/test_monitor.py::TestRewardComponentRatio -v`
Expected: FAIL — checks not implemented

- [ ] **Step 4: Implement `_check_reward_magnitude` and `_check_reward_component_ratio`**

Add to `utils/monitor.py` in the `TrainingMonitor` class:

```python
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
```

Also add the helper and update `_run_all_checks`:

```python
def _emit_check(self, check_name: str, episode: int, action: str, message: str):
    """Record trigger and print warning/stop message."""
    self._trigger_history.append({
        "check": check_name, "episode": episode, "action": action, "message": message,
    })
    icon = "\U0001f6d1" if action == "stop" else "\u26a0"
    label = "TRAINING STOPPED" if action == "stop" else "WARNING"
    print(f"\n{icon} [Monitor] {label}: {check_name} @ Ep {episode}")
    print(f"  {message}")
    if action == "stop":
        print(f"  Training terminated.\n")

def _run_all_checks(self, episode: int) -> bool:
    results = []
    results.append(self._check_reward_magnitude(episode))
    results.append(self._check_reward_component_ratio(episode))
    # More checks added in later tasks
    return "stop" in results

def _run_manual_checks(self, episode: int) -> bool:
    """During calibration, only run reward_magnitude if user set expected_range."""
    results = []
    if "expected_range" in self._user_checks.get("reward_magnitude", {}):
        results.append(self._check_reward_magnitude(episode))
    # All other checks wait until calibration completes (spec section 4.2)
    return "stop" in results
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_monitor.py::TestRewardMagnitude tests/test_monitor.py::TestRewardComponentRatio -v`
Expected: All passed

- [ ] **Step 6: Commit**

```bash
git add utils/monitor.py tests/test_monitor.py
git commit -m "feat(monitor): implement reward_magnitude and reward_component_ratio checks"
```

---

## Task 4: Action Checks (collapse + saturation)

**Files:**
- Modify: `utils/monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write tests**

```python
class TestActionCollapse:
    def test_single_agent_collapse_triggers(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"action_collapse": {"std_threshold": 0.05, "window": 3, "action": "warn"}},
        )
        for ep in range(5):
            actions = np.random.randn(50, 4, 2) * 0.5
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # Agent 2 collapses to near-zero std, others stay active
        for ep in range(5, 8):
            actions = np.random.randn(50, 4, 2) * 0.5
            actions[:, 2, :] = 0.001 * np.random.randn(50, 2)  # Agent 2 near zero
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert any(t["check"] == "action_collapse" for t in m._trigger_history)

    def test_no_collapse_when_std_healthy(self):
        m = TrainingMonitor(calibration_episodes=3, checks={"action_collapse": {"std_threshold": 0.05, "window": 3, "action": "warn"}})
        for ep in range(6):
            actions = np.random.randn(50, 4, 2) * 0.5
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "action_collapse" for t in m._trigger_history)


class TestActionSaturation:
    def test_saturation_triggers(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"action_saturation": {"threshold": 0.8, "action": "warn"}},
        )
        for ep in range(3):
            actions = np.random.randn(50, 4, 2) * 0.5
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # 90% of actions at boundaries
        actions = np.ones((50, 4, 2)) * 0.99
        result = m.log_and_check(3, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                                 actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert any(t["check"] == "action_saturation" for t in m._trigger_history)

    def test_no_saturation_when_normal(self):
        m = TrainingMonitor(calibration_episodes=3)
        for ep in range(4):
            actions = np.random.randn(50, 4, 2) * 0.3
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "action_saturation" for t in m._trigger_history)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_monitor.py::TestActionCollapse tests/test_monitor.py::TestActionSaturation -v`

- [ ] **Step 3: Implement `_check_action_collapse` and `_check_action_saturation`**

```python
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
                f"  Suggestion: Check reward scaling \u2014 ensure frequency reward dominates.")
            return cfg["action"]
    return None

def _check_action_saturation(self, episode: int) -> str | None:
    cfg = self._checks["action_saturation"]
    if cfg["action"] == "ignore":
        return None

    threshold = cfg.get("threshold", 0.8)
    sat_ratio = self._action_stats[-1]["saturation_ratio"]

    if sat_ratio > threshold:
        self._emit_check("action_saturation", episode, cfg["action"],
            f"Action saturation = {sat_ratio*100:.1f}% (threshold: {threshold*100:.0f}%).\n"
            f"  Most actions are at boundary \u00b10.95. Action space may be too small.")
        return cfg["action"]
    return None
```

Add to `_run_all_checks`:
```python
results.append(self._check_action_collapse(episode))
results.append(self._check_action_saturation(episode))
```

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/test_monitor.py::TestActionCollapse tests/test_monitor.py::TestActionSaturation -v`

- [ ] **Step 5: Commit**

```bash
git add utils/monitor.py tests/test_monitor.py
git commit -m "feat(monitor): implement action_collapse and action_saturation checks"
```

---

## Task 5: Training Trend Checks (plateau + divergence)

**Files:**
- Modify: `utils/monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write tests**

```python
class TestRewardPlateau:
    def test_plateau_triggers_after_flat_window(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_plateau": {"window": 10, "improvement_threshold": 0.01, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        # 5 calibration + 10 flat episodes
        for ep in range(15):
            m.log_and_check(ep, rewards=-1500.0, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert any(t["check"] == "reward_plateau" for t in m._trigger_history)

    def test_no_plateau_when_improving(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_plateau": {"window": 10, "improvement_threshold": 0.01, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(15):
            m.log_and_check(ep, rewards=-1500.0 + ep * 50, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "reward_plateau" for t in m._trigger_history)


class TestRewardDivergence:
    def test_divergence_triggers_on_declining_trend(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"reward_divergence": {"window": 10, "action": "stop"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        # 5 calibration at -1500, then 10 episodes of worsening rewards
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        result = False
        for ep in range(5, 15):
            result = m.log_and_check(ep, rewards=-1500 - (ep - 5) * 500,
                                     reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                                     actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
            if result:
                break
        assert result is True

    def test_no_divergence_when_stable(self):
        m = TrainingMonitor(calibration_episodes=5, checks={"reward_divergence": {"window": 10, "action": "stop"}})
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(15):
            m.log_and_check(ep, rewards=-1500 + np.random.randn() * 10,
                            reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "reward_divergence" for t in m._trigger_history)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement `_check_reward_plateau` and `_check_reward_divergence`**

```python
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
            f"  Slope: {slope:.1f}/ep, R\u00b2={r_squared:.2f}, "
            f"total change: {abs(slope * window):.0f} ({normalized*100:.0f}% of mean).\n"
            f"  Training may be diverging.")
        return cfg["action"]
    return None
```

Add both to `_run_all_checks`.

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add utils/monitor.py tests/test_monitor.py
git commit -m "feat(monitor): implement reward_plateau and reward_divergence checks"
```

---

## Task 6: Environment Health Checks (tds_failure + freq_range)

**Files:**
- Modify: `utils/monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write tests**

```python
class TestTdsFailureRate:
    def test_high_failure_rate_triggers(self):
        m = TrainingMonitor(
            calibration_episodes=5,
            checks={"tds_failure_rate": {"threshold": 0.2, "window": 5, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # 3/5 episodes fail → 60% > 20% threshold
        for ep in range(5, 10):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": (ep < 8), "max_freq_deviation_hz": 0.3})
        assert any(t["check"] == "tds_failure_rate" for t in m._trigger_history)


class TestFreqOutOfRange:
    def test_persistent_freq_violation_triggers(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"freq_out_of_range": {"threshold_hz": 2.0, "window": 5, "min_episodes": 2, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(3):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # 3 episodes with freq > 2 Hz (exceeds min_episodes=2)
        for ep in range(3, 8):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 3.5})
        assert any(t["check"] == "freq_out_of_range" for t in m._trigger_history)

    def test_single_spike_no_trigger(self):
        m = TrainingMonitor(
            calibration_episodes=3,
            checks={"freq_out_of_range": {"threshold_hz": 2.0, "window": 5, "min_episodes": 3, "action": "warn"}},
        )
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(3):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        # 1 spike, rest normal
        m.log_and_check(3, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                        actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 5.0})
        for ep in range(4, 8):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        assert not any(t["check"] == "freq_out_of_range" for t in m._trigger_history)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement both checks**

```python
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
            f"Frequency exceeded \u00b1{threshold_hz} Hz in {violations}/{window} recent episodes "
            f"(threshold: {min_episodes} episodes).\n"
            f"  VSG parameters may be causing system instability.")
        return cfg["action"]
    return None
```

Add both to `_run_all_checks`.

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add utils/monitor.py tests/test_monitor.py
git commit -m "feat(monitor): implement tds_failure_rate and freq_out_of_range checks"
```

---

## Task 7: Output Formatting (log_summary + summary)

**Files:**
- Modify: `utils/monitor.py`
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write tests**

```python
class TestOutputFormatting:
    def test_log_summary_prints(self, capsys):
        m = TrainingMonitor(calibration_episodes=3, log_interval=5)
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        captured = capsys.readouterr()
        assert "[Monitor]" in captured.out
        assert "Ep 4" in captured.out  # 0-indexed, logged at ep 4 (5th episode)

    def test_summary_prints_final_report(self, capsys):
        m = TrainingMonitor(calibration_episodes=3, log_interval=100)
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(5):
            m.log_and_check(ep, rewards=-1500 + ep * 100,
                            reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        m.summary()
        captured = capsys.readouterr()
        assert "Training Summary" in captured.out
        assert "Episodes: 5" in captured.out

    def test_summary_with_incomplete_calibration(self, capsys):
        m = TrainingMonitor(calibration_episodes=20, log_interval=100)
        actions = np.random.randn(50, 4, 2) * 0.5
        for ep in range(3):
            m.log_and_check(ep, rewards=-1500, reward_components={"r_f": -1400, "r_h": -5, "r_d": -3},
                            actions=actions, info={"tds_failed": False, "max_freq_deviation_hz": 0.3})
        m.summary()
        captured = capsys.readouterr()
        assert "incomplete" in captured.out.lower() or "not complete" in captured.out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement `_log_summary` and `summary`**

```python
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
    print(f"          Actions \u03bc: {mu_str}  \u03c3: {std_str}")
    print(f"          TDS fails: {tds_fails}/{len(recent_health)} ({tds_fails/len(recent_health)*100:.1f}%) | Freq peak: {max_freq:.2f} Hz")

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

    print(f"\n[Monitor] \u2550\u2550\u2550 Training Summary \u2550\u2550\u2550")
    print(f"  Episodes: {n} | Calibration: {cal_status}")
    print(f"  Reward:   {first_r:.0f} (ep 0) \u2192 {last_r:.0f} (ep {n-1})")
    print(f"  Best:     {best_r:.0f} @ ep {best_ep} | Worst: {worst_r:.0f} @ ep {worst_ep}")

    if self._trigger_history:
        print(f"\n  Checks triggered:")
        # Group by check name
        counts = Counter(t["check"] for t in self._trigger_history)
        for check_name, count in counts.items():
            first_ep = next(t["episode"] for t in self._trigger_history if t["check"] == check_name)
            action = next(t["action"] for t in self._trigger_history if t["check"] == check_name)
            icon = "\U0001f6d1" if action == "stop" else "\u26a0"
            label = "STOP" if action == "stop" else "WARN"
            print(f"    {check_name:<28} {icon} {label:<5} @ ep {first_ep:<5} ({count} time{'s' if count > 1 else ''})")
    else:
        print(f"\n  No checks triggered.")

    print(f"\n  TDS failures: {total_tds}/{n} ({total_tds/n*100:.1f}%)")
    print(f"  Freq peak deviation: {max_freq:.2f} Hz (ep {max_freq_ep})")
    print()
```

- [ ] **Step 4: Run tests, verify pass**

- [ ] **Step 5: Commit**

```bash
git add utils/monitor.py tests/test_monitor.py
git commit -m "feat(monitor): implement log_summary and summary output formatting"
```

---

## Task 8: Add max_freq_deviation_hz to Environment Info Dicts

**Files:**
- Modify: `env/ode/multi_vsg_env.py`
- Modify: `env/andes/base_env.py`

- [ ] **Step 1: Write test for ODE env info dict**

```python
# tests/test_monitor.py
class TestEnvInfoCompat:
    def test_ode_env_info_has_max_freq_deviation(self):
        """ODE env step() info dict must include max_freq_deviation_hz."""
        import config as cfg
        from env.ode.multi_vsg_env import MultiVSGEnv
        env = MultiVSGEnv()
        obs = env.reset()
        actions = {i: np.zeros(cfg.ACTION_DIM) for i in range(cfg.N_AGENTS)}
        _, _, _, info = env.step(actions)
        assert "max_freq_deviation_hz" in info
        assert isinstance(info["max_freq_deviation_hz"], float)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_monitor.py::TestEnvInfoCompat::test_ode_env_info_has_max_freq_deviation -v`
Expected: FAIL — key not in info

- [ ] **Step 3: Add `max_freq_deviation_hz` to ODE env `step()`**

In `env/ode/multi_vsg_env.py`, in the `step()` method where the info dict is constructed (near line 175), add:

```python
# After computing freq_hz — max across all generators for this step:
max_freq_deviation_hz = float(np.max(np.abs(state['omega'])) / (2 * np.pi))

# In the info dict:
info = {
    # ... existing fields ...
    'max_freq_deviation_hz': max_freq_deviation_hz,
}
```

Note: This is per-step, not episode-peak. The training script integration (Task 9) tracks `ep_max_freq = max(ep_max_freq, info["max_freq_deviation_hz"])` across all steps to get the episode-peak value before passing it to the monitor.

- [ ] **Step 4: Run test, verify pass**

- [ ] **Step 5: Add same field to ANDES `base_env.py` info dict**

In `env/andes/base_env.py`, in the `step()` method where info is constructed, add:

```python
max_freq_deviation_hz = float(np.max(np.abs(np.array(omega_list))))
# (omega is already in Hz deviation in the ANDES env)

info['max_freq_deviation_hz'] = max_freq_deviation_hz
```

Note: Read the ANDES env's `step()` to determine the exact frequency deviation units before adding. The ANDES env may use different units than the ODE env.

- [ ] **Step 6: Commit**

```bash
git add env/ode/multi_vsg_env.py env/andes/base_env.py tests/test_monitor.py
git commit -m "feat(env): add max_freq_deviation_hz to ODE and ANDES env info dicts"
```

---

## Task 9: Integrate TrainingMonitor into Training Scripts

**Files:**
- Modify: `scenarios/kundur/train_ode.py`
- Modify: `scenarios/kundur/train_andes.py`

- [ ] **Step 1: Integrate into `train_ode.py`**

Read the current `scenarios/kundur/train_ode.py` carefully before modifying. Add approximately these changes:

At top of file:
```python
import numpy as np
from utils.monitor import TrainingMonitor
```

Before the training loop:
```python
monitor = TrainingMonitor()
```

Inside the episode loop, collect actions and accumulate reward components:
```python
ep_actions_list = []
ep_r_f, ep_r_h, ep_r_d = 0.0, 0.0, 0.0
ep_max_freq = 0.0
```

Inside the step loop, after `env.step()`:
```python
ep_actions_list.append(np.array([actions[i] for i in range(cfg.N_AGENTS)]))
ep_r_f += info["r_f"]
ep_r_h += info["r_h"]
ep_r_d += info["r_d"]
ep_max_freq = max(ep_max_freq, info.get("max_freq_deviation_hz", 0.0))
```

Note: `ep_r_f/r_h/r_d` accumulate per-step values across the entire episode, matching how `episode_freq_rewards` etc. are already tracked in the existing training loop. `ep_max_freq` tracks the peak frequency deviation across all steps (not just the last step).

After the step loop (end of episode), before existing logging:
```python
should_stop = monitor.log_and_check(
    episode=episode,
    rewards=sum(episode_rewards[i][-1] for i in range(cfg.N_AGENTS)),
    reward_components={
        "r_f": ep_r_f,
        "r_h": ep_r_h,
        "r_d": ep_r_d,
    },
    actions=np.array(ep_actions_list),
    info={
        "tds_failed": False,  # ODE env doesn't have TDS failures
        "max_freq_deviation_hz": ep_max_freq,
    },
)
if should_stop:
    break
```

After the training loop:
```python
monitor.summary()
```

- [ ] **Step 2: Integrate into `train_andes.py`**

Same pattern as train_ode.py, but:
- `tds_failed` comes from `info.get("tds_failed", False)` (ANDES env already returns this)
- The info dict field names may differ slightly — read the file before modifying

- [ ] **Step 3: Smoke test ODE training**

Run: `cd "C:\Users\27443\Desktop\Multi-Agent  VSGs" && python scenarios/kundur/train_ode.py 2>&1 | head -50`

Verify: Monitor calibration message appears after episode 20. Periodic summaries print every 10 episodes. No crashes.

- [ ] **Step 4: Commit**

```bash
git add scenarios/kundur/train_ode.py scenarios/kundur/train_andes.py
git commit -m "feat(training): integrate TrainingMonitor into Kundur training scripts"
```

---

## Task 10: End-to-End Smoke Test

**Files:**
- Modify: `tests/test_monitor.py`

- [ ] **Step 1: Write e2e test with real ODE env**

```python
class TestEndToEnd:
    def test_monitor_with_real_ode_env(self):
        """Full integration: ODE env + random actions + monitor."""
        import config as cfg
        from env.ode.multi_vsg_env import MultiVSGEnv
        from utils.monitor import TrainingMonitor

        env = MultiVSGEnv()
        monitor = TrainingMonitor(calibration_episodes=3, log_interval=2)

        for episode in range(5):
            obs = env.reset()
            ep_actions_list = []
            last_info = {}

            for step in range(10):  # Short episodes for test speed
                actions = {i: np.random.uniform(-1, 1, size=cfg.ACTION_DIM) for i in range(cfg.N_AGENTS)}
                obs, rewards, done, info = env.step(actions)
                ep_actions_list.append(np.array([actions[i] for i in range(cfg.N_AGENTS)]))
                last_info = info
                if done:
                    break

            total_reward = sum(rewards.values()) if isinstance(rewards, dict) else rewards
            should_stop = monitor.log_and_check(
                episode=episode,
                rewards=float(total_reward),
                reward_components={"r_f": last_info["r_f"], "r_h": last_info["r_h"], "r_d": last_info["r_d"]},
                actions=np.array(ep_actions_list),
                info={"tds_failed": False, "max_freq_deviation_hz": last_info.get("max_freq_deviation_hz", 0.0)},
            )

        monitor.summary()
        assert len(monitor._episode_rewards) == 5
```

- [ ] **Step 2: Run test**

Run: `python -m pytest tests/test_monitor.py::TestEndToEnd -v -s`
Expected: PASS with monitor output visible

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/test_monitor.py -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_monitor.py
git commit -m "test(monitor): add end-to-end smoke test with real ODE environment"
```

---

## Summary

| Task | Description | Estimated Steps |
|------|-------------|----------------|
| 1 | TrainingMonitor skeleton | 5 |
| 2 | Calibration engine | 5 |
| 3 | Reward checks (magnitude + ratio) | 6 |
| 4 | Action checks (collapse + saturation) | 5 |
| 5 | Trend checks (plateau + divergence) | 5 |
| 6 | Env health checks (tds + freq) | 5 |
| 7 | Output formatting | 5 |
| 8 | Env info dict modification | 6 |
| 9 | Training script integration | 4 |
| 10 | E2E smoke test | 4 |
| **Total** | | **50 steps** |
