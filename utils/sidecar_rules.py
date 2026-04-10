"""Sidecar rule engine for training event detection.

Each rule receives (event_or_metric, SidecarContext) and returns a
Notification(title, body) or None when no notification should fire.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, NamedTuple

import numpy as np


class Notification(NamedTuple):
    title: str
    body: str


@dataclass
class SidecarContext:
    """Mutable state shared across all rule evaluations for one sidecar session."""
    scenario_id: str
    # eval tracking
    last_eval_reward: float | None = None
    last_eval_episode: int = -1
    # decline detection
    reward_window: deque = field(default_factory=lambda: deque(maxlen=30))
    decline_notified_at: int = -(10 ** 6)  # episode of last decline notification (sentinel = never)
    decline_cooldown_eps: int = 50       # min episodes between repeat decline alerts


# ── helpers ───────────────────────────────────────────────────────────────────

def _ols_slope(values: list[float]) -> float:
    """OLS slope of values (positive = improving, negative = declining)."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    x -= x.mean()
    y = np.array(values, dtype=float)
    y -= y.mean()
    denom = float((x * x).sum())
    return float((x * y).sum() / denom) if denom > 1e-12 else 0.0


# ── event-based rules ─────────────────────────────────────────────────────────

def rule_training_start(event: dict, ctx: SidecarContext) -> Notification | None:
    episodes = event.get("total_episodes", "?")
    mode = event.get("mode", "unknown")
    return Notification(
        title=f"训练开始 — {ctx.scenario_id}",
        body=f"计划 {episodes} 集 · 模式: {mode}",
    )


def rule_eval_improvement(event: dict, ctx: SidecarContext) -> Notification | None:
    new_eval = event.get("eval_reward")
    if new_eval is None:
        return None
    ep = event.get("episode", "?")
    old = ctx.last_eval_reward

    ctx.last_eval_reward = float(new_eval)
    ctx.last_eval_episode = ep if isinstance(ep, int) else -1

    if old is None:
        return Notification(
            title=f"首次 Eval — EP{ep}",
            body=f"eval reward: {new_eval:.0f}",
        )

    # Skip percentage comparison when old is near zero (reward scale undefined)
    if abs(old) < 1.0:
        return None if new_eval <= old else Notification(
            title=f"Eval 改善 — EP{ep}",
            body=f"{old:.3f} → {new_eval:.3f}",
        )
    improvement = (new_eval - old) / abs(old)
    if improvement > 0.05:
        return Notification(
            title=f"Eval 改善 — EP{ep}",
            body=f"{old:.0f} → {new_eval:.0f} (+{improvement * 100:.1f}%)",
        )
    return None


def rule_monitor_alert(event: dict, ctx: SidecarContext) -> Notification | None:
    rule_name = event.get("rule", event.get("triggered_by", "unknown"))
    ep = event.get("episode", "?")
    return Notification(
        title=f"⚠ 监控报警 — EP{ep}",
        body=f"规则: {rule_name}",
    )


def rule_checkpoint(event: dict, ctx: SidecarContext) -> Notification | None:
    ep = event.get("episode", "?")
    fname = event.get("file", "checkpoint")
    return Notification(
        title=f"Checkpoint — EP{ep}",
        body=f"已保存: {fname}",
    )


def rule_training_end(event: dict, ctx: SidecarContext) -> Notification | None:
    verdict = event.get("verdict", "UNKNOWN")
    ep = event.get("episode", "?")
    elapsed = event.get("elapsed_min")
    time_str = f" · 用时 {elapsed:.1f} min" if elapsed is not None else ""
    return Notification(
        title=f"训练完成 — {verdict}",
        body=f"EP{ep}{time_str} · {ctx.scenario_id}",
    )


# ── metric-based rules ────────────────────────────────────────────────────────

def rule_reward_decline(episode: int, reward: float, ctx: SidecarContext) -> Notification | None:
    """Fire when reward has been declining across the last 30 episodes.

    Uses OLS slope threshold of -5 per episode. Cooldown prevents
    re-firing within decline_cooldown_eps episodes of the last alert.
    """
    ctx.reward_window.append(reward)
    if len(ctx.reward_window) < ctx.reward_window.maxlen:
        return None
    slope = _ols_slope(list(ctx.reward_window))
    if slope >= -5.0:
        return None
    if episode - ctx.decline_notified_at < ctx.decline_cooldown_eps:
        return None
    ctx.decline_notified_at = episode
    return Notification(
        title=f"⚠ 奖励持续下降 — EP{episode}",
        body=f"最近 {ctx.reward_window.maxlen} 集斜率 {slope:.1f}/ep，建议检查",
    )


# ── dispatch table: event type → handler ─────────────────────────────────────

_RuleFn = Callable[["dict", "SidecarContext"], "Notification | None"]

EVENT_RULES: dict[str, _RuleFn] = {
    "training_start": rule_training_start,
    "eval":           rule_eval_improvement,
    "monitor_alert":  rule_monitor_alert,
    "monitor_stop":   rule_monitor_alert,
    "checkpoint":     rule_checkpoint,
    "training_end":   rule_training_end,
}
