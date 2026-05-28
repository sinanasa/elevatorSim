"""Discrete-time clock with named micro-step phases.

The tick is not atomic — it decomposes into an ordered sequence of phases
(ADR-005). This module codifies that ordering so it's explicit, testable,
and traceable to the formal state transition specification.

Micro-step ordering within each tick:
  Phase 1 — INGEST:   Collect requests arriving at this tick
  Phase 2 — DISPATCH: Assign new requests to elevators via strategy
  Phase 3 — DROPOFF:  Unload passengers at their destination floor
  Phase 4 — PICKUP:   Load assigned passengers at their source floor
  Phase 5 — MOVE:     Each elevator advances one floor toward next target
  Phase 6 — RECORD:   Snapshot state for position log and events

Dropoff before pickup frees capacity — prevents false rejection.
Pickup before move — passengers board before the elevator departs.
"""

from __future__ import annotations

from enum import Enum, auto


class TickPhase(Enum):
    """Named phases within a single simulation tick.

    Order matters — phases execute in enum definition order.
    """

    INGEST = auto()
    DISPATCH = auto()
    DROPOFF = auto()
    PICKUP = auto()
    MOVE = auto()
    RECORD = auto()


# The canonical phase ordering, used by the simulation engine
PHASE_ORDER: tuple[TickPhase, ...] = tuple(TickPhase)
