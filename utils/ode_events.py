"""Discrete event primitives for ODE multi-VSG simulation.

Events are applied at the start of each control step. The schedule is
frozen (immutable) so that environments can safely share it across resets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

import numpy as np


@dataclass(frozen=True, eq=False)
class DisturbanceEvent:
    """Replace the current network-wide Δu vector at time `t` (s).

    Note: eq=False disables auto-generated __eq__/__hash__ — ndarray fields
    are not hashable. Use object identity for comparison.
    """
    t: float
    delta_u: np.ndarray  # shape (N,)

    def __post_init__(self) -> None:
        arr = np.asarray(self.delta_u, dtype=np.float64)
        object.__setattr__(self, "delta_u", arr)


@dataclass(frozen=True)
class LineTripEvent:
    """Remove the (i,j) edge from the network Laplacian at time `t`."""
    t: float
    bus_i: int
    bus_j: int

    def __post_init__(self) -> None:
        if self.bus_i == self.bus_j:
            raise ValueError(
                f"LineTripEvent: bus_i and bus_j must differ, got {self.bus_i}"
            )
        if self.bus_i < 0 or self.bus_j < 0:
            raise ValueError(
                f"LineTripEvent: bus indices must be non-negative, got ({self.bus_i}, {self.bus_j})"
            )


Event = Union[DisturbanceEvent, LineTripEvent]


@dataclass(frozen=True)
class EventSchedule:
    """Sorted, immutable list of events applied in order of `t`.

    Hashable because it contains only a tuple of events (no direct ndarray).
    """
    events: tuple[Event, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        times = [e.t for e in self.events]
        if any(t_next < t_prev for t_prev, t_next in zip(times, times[1:])):
            raise ValueError(f"Event times must be non-decreasing, got {times}")
        if any(t < 0 for t in times):
            raise ValueError(f"Event times must be non-negative, got {times}")
        # Detect duplicate LineTripEvent for the same (i,j) pair
        tripped: set[tuple[int, int]] = set()
        for ev in self.events:
            if isinstance(ev, LineTripEvent):
                key = (min(ev.bus_i, ev.bus_j), max(ev.bus_i, ev.bus_j))
                if key in tripped:
                    raise ValueError(
                        f"EventSchedule: duplicate LineTripEvent for edge "
                        f"({ev.bus_i}, {ev.bus_j})"
                    )
                tripped.add(key)

    def events_in_window(self, t0: float, t1: float) -> list[Event]:
        """Return events with t0 <= e.t < t1 (half-open, aligns with step start)."""
        return [e for e in self.events if t0 <= e.t < t1]
