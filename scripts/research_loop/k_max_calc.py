"""Budget tier → K_max 启发式. AI 可 override (写 rationale)."""

from __future__ import annotations


def calc_budget_pct(
    rounds_used: int, rounds_cap: int,
    wall_hr_used: float, wall_hr_cap: float,
    tokens_used: int, tokens_cap: int,
) -> float:
    """min over 三维剩余比例 (0-1)."""
    return min(
        max(0.0, (rounds_cap - rounds_used) / rounds_cap),
        max(0.0, (wall_hr_cap - wall_hr_used) / wall_hr_cap),
        max(0.0, (tokens_cap - tokens_used) / tokens_cap),
    )


def calc_k_max(budget_pct: float) -> int:
    """启发式: 默认 tier 切片. AI override 走 rationale, 不走这."""
    if budget_pct > 0.40:
        return 4
    if budget_pct > 0.20:
        return 2
    return 1
