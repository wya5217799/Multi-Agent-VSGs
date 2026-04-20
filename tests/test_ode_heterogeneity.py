"""Parameter heterogeneity helper tests."""
import numpy as np
import pytest

from utils.ode_heterogeneity import generate_heterogeneous_params


def test_zero_spread_returns_uniform():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.0, seed=0)
    np.testing.assert_array_equal(out, base)


def test_mean_preserved_within_tolerance():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.3, seed=0)
    assert abs(float(out.mean()) - 24.0) < 0.1


def test_spread_produces_distinct_values():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.3, seed=0)
    assert len(set(out.tolist())) == len(base)
    assert (out > 0).all()


def test_seed_is_deterministic():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    a = generate_heterogeneous_params(base, spread=0.3, seed=42)
    b = generate_heterogeneous_params(base, spread=0.3, seed=42)
    np.testing.assert_array_equal(a, b)


def test_rejects_negative_spread():
    base = np.array([24.0, 24.0, 24.0, 24.0])
    with pytest.raises(ValueError):
        generate_heterogeneous_params(base, spread=-0.1, seed=0)


def test_enforces_positive_floor():
    # Large spread should still yield strictly positive values
    base = np.array([24.0, 24.0, 24.0, 24.0])
    out = generate_heterogeneous_params(base, spread=0.95, seed=7)
    assert (out > 0).all()
