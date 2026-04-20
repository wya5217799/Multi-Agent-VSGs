"""Generate heterogeneous H/D arrays around a uniform base.

Mean preservation holds before the floor clamp; if any element is clamped
the mean is biased upward by the clipped amount.
"""
from __future__ import annotations

import numpy as np


def generate_heterogeneous_params(
    base: np.ndarray,
    spread: float,
    seed: int,
    floor: float = 1e-3,
) -> np.ndarray:
    """Return a permuted, mean-preserving spread of `base`.

    Parameters
    ----------
    base : np.ndarray, shape (N,)
        Uniform baseline (e.g. H_ES0 = [24, 24, 24, 24]).
    spread : float
        Fractional spread in [0, 1). Each element i is perturbed by up to
        +/- spread * base[i].
    seed : int
        RNG seed for reproducibility.
    floor : float
        Minimum positive value enforced after perturbation.

    Returns
    -------
    np.ndarray, shape (N,)
        Heterogeneous parameters with mean approximately equal to base.mean().
    """
    if not (0 <= spread < 1.0):
        raise ValueError(f"spread must be in [0, 1), got {spread}")
    base = np.asarray(base, dtype=np.float64)
    if spread == 0.0:
        return base.copy()
    rng = np.random.default_rng(seed)
    # Symmetric zero-sum perturbation preserves the mean before floor clamping.
    raw = rng.uniform(-1.0, 1.0, size=base.shape)
    raw -= raw.mean()
    scaled = spread * base * raw
    out = base + scaled
    return np.maximum(out, floor)
