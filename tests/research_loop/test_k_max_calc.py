"""k_max_calc 单测 (并行启发式)."""
import pytest

from scripts.research_loop.k_max_calc import calc_k_max, calc_budget_pct


def test_budget_pct_fresh():
    assert calc_budget_pct(rounds_used=0, rounds_cap=20,
                            wall_hr_used=0, wall_hr_cap=72,
                            tokens_used=0, tokens_cap=800000) == 1.0


def test_budget_pct_takes_min():
    """三维 min: rounds 50%, hr 80%, tok 30% → 30%."""
    pct = calc_budget_pct(
        rounds_used=10, rounds_cap=20,
        wall_hr_used=14.4, wall_hr_cap=72,
        tokens_used=560000, tokens_cap=800000
    )
    assert abs(pct - 0.30) < 1e-3


def test_k_max_high_budget_returns_4():
    assert calc_k_max(0.50) == 4


def test_k_max_mid_budget_returns_2():
    assert calc_k_max(0.30) == 2


def test_k_max_low_budget_returns_1():
    assert calc_k_max(0.10) == 1


def test_k_max_boundary_high():
    assert calc_k_max(0.40) == 2  # 0.40 是 mid 上限
    assert calc_k_max(0.4001) == 4


def test_k_max_boundary_low():
    assert calc_k_max(0.20) == 1
    assert calc_k_max(0.2001) == 2
