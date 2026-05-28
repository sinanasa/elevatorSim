"""Dispatch strategy implementations.

Each strategy satisfies the DispatchStrategy protocol (ADR-004).
Strategies are pure decision functions: given a read-only snapshot of
system state, return an elevator ID. No mutation, no side effects.

Strategies registered in STRATEGY_REGISTRY are available by name at runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from elevator_sim.domain.model import (
    Direction,
    DispatchError,
    ElevatorSnapshot,
    PassengerRequest,
    SimulationConfig,
)


# ---------------------------------------------------------------------------
# Round Robin — fairness baseline
# ---------------------------------------------------------------------------

@dataclass
class RoundRobinStrategy:
    """Assigns requests to elevators in cyclic order.

    No optimization — guarantees even load distribution across elevators.
    Useful as a control baseline for comparing strategy effectiveness.
    Does not consider elevator position, direction, or current load.
    """

    _next_index: int = 0

    @property
    def name(self) -> str:
        return "round_robin"

    def select_elevator(
        self,
        request: PassengerRequest,
        elevators: Sequence[ElevatorSnapshot],
        config: SimulationConfig,
    ) -> int:
        if not elevators:
            raise DispatchError(f"No eligible elevators for {request.passenger_id}")

        selected = elevators[self._next_index % len(elevators)]
        self._next_index = (self._next_index + 1) % len(elevators)
        return selected.elevator_id


# ---------------------------------------------------------------------------
# Nearest Car — industry-standard destination dispatch baseline
# ---------------------------------------------------------------------------

@dataclass
class NearestCarStrategy:
    """Scores each elevator by distance, direction alignment, and load.

    Industry-standard heuristic for destination dispatch systems.
    Balances proximity (serve nearby requests quickly) with direction
    alignment (prefer elevators already heading toward the pickup floor)
    and load awareness (prefer less-loaded elevators).

    Scoring formula:
      score = distance_penalty + direction_penalty + load_penalty

    Lower score = better candidate. Ties broken by elevator ID (determinism).
    """

    # Weights — tunable, but these defaults are reasonable for most buildings
    direction_penalty_weight: float = 2.0
    load_penalty_weight: float = 1.0

    @property
    def name(self) -> str:
        return "nearest_car"

    def select_elevator(
        self,
        request: PassengerRequest,
        elevators: Sequence[ElevatorSnapshot],
        config: SimulationConfig,
    ) -> int:
        if not elevators:
            raise DispatchError(f"No eligible elevators for {request.passenger_id}")

        best_id = -1
        best_score = math.inf

        for snap in elevators:
            score = self._score(snap, request, config)
            # Tie-break by elevator ID for determinism
            if score < best_score or (score == best_score and snap.elevator_id < best_id):
                best_score = score
                best_id = snap.elevator_id

        if best_id == -1:
            raise DispatchError(f"No eligible elevators for {request.passenger_id}")

        return best_id

    def _score(
        self,
        elevator: ElevatorSnapshot,
        request: PassengerRequest,
        config: SimulationConfig,
    ) -> float:
        """Lower is better."""
        distance = abs(elevator.current_floor - request.source)

        # Direction alignment: penalize elevators moving away from pickup
        direction_penalty = self._direction_penalty(elevator, request)

        # Load: prefer elevators with more remaining capacity
        if elevator.capacity > 0:
            load_ratio = elevator.passenger_count / elevator.capacity
        else:
            load_ratio = 1.0
        load_penalty = load_ratio * self.load_penalty_weight * config.num_floors

        return distance + direction_penalty + load_penalty

    def _direction_penalty(
        self,
        elevator: ElevatorSnapshot,
        request: PassengerRequest,
    ) -> float:
        """Penalize elevators heading away from the pickup floor.

        - IDLE: no penalty (can go either way)
        - Moving TOWARD pickup AND same direction as request: no penalty
        - Moving TOWARD pickup BUT opposite direction: moderate penalty
          (will need to reverse after serving current stops)
        - Moving AWAY from pickup: heavy penalty (must finish current
          direction, reverse, then reach pickup)
        """
        if elevator.is_idle:
            return 0.0

        pickup_floor = request.source
        request_dir = request.direction

        moving_toward = (
            (elevator.direction == Direction.UP and pickup_floor >= elevator.current_floor)
            or (elevator.direction == Direction.DOWN and pickup_floor <= elevator.current_floor)
        )

        if moving_toward and elevator.direction == request_dir:
            return 0.0
        elif moving_toward:
            # Heading toward pickup but will need to reverse for delivery
            return self.direction_penalty_weight * 5
        else:
            # Moving away — must reverse to reach pickup
            return self.direction_penalty_weight * 15


# ---------------------------------------------------------------------------
# Zone-Based — partitioned dispatch for express/local configurations
# ---------------------------------------------------------------------------

@dataclass
class ZoneBasedStrategy:
    """Partitions floors into zones and prefers zone-local elevators.

    Composes naturally with ServicePolicy (ADR-008): ServicePolicy
    enforces which floors an elevator *can* serve, this strategy
    optimizes *which* elevator *should* serve within the eligible set.

    Falls back to nearest-car scoring when no zone-local elevator
    has capacity, ensuring no request goes unserved.
    """

    num_zones: int = 3
    _fallback: NearestCarStrategy | None = None

    def __post_init__(self) -> None:
        self._fallback = NearestCarStrategy()

    @property
    def name(self) -> str:
        return "zone_based"

    def select_elevator(
        self,
        request: PassengerRequest,
        elevators: Sequence[ElevatorSnapshot],
        config: SimulationConfig,
    ) -> int:
        if not elevators:
            raise DispatchError(f"No eligible elevators for {request.passenger_id}")

        zone_size = max(1, config.num_floors // self.num_zones)

        # Determine which zone the request's source falls in
        request_zone = (request.source - 1) // zone_size

        # Prefer elevators currently in the same zone with capacity
        zone_local = [
            e for e in elevators
            if (e.current_floor - 1) // zone_size == request_zone
            and e.has_capacity
        ]

        if zone_local:
            # Use nearest-car scoring within the zone
            assert self._fallback is not None
            return self._fallback.select_elevator(request, zone_local, config)

        # Fallback: nearest-car across all eligible elevators
        assert self._fallback is not None
        return self._fallback.select_elevator(request, elevators, config)


# ---------------------------------------------------------------------------
# Strategy Registry
# ---------------------------------------------------------------------------

def _create_strategy(name: str) -> (
    RoundRobinStrategy | NearestCarStrategy | ZoneBasedStrategy
):
    """Factory for strategy instances by name."""
    factories = {
        "round_robin": RoundRobinStrategy,
        "nearest_car": NearestCarStrategy,
        "zone_based": ZoneBasedStrategy,
    }
    if name not in factories:
        available = ", ".join(sorted(factories.keys()))
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return factories[name]()


STRATEGY_REGISTRY: dict[str, type] = {
    "round_robin": RoundRobinStrategy,
    "nearest_car": NearestCarStrategy,
    "zone_based": ZoneBasedStrategy,
}


def get_strategy(name: str) -> RoundRobinStrategy | NearestCarStrategy | ZoneBasedStrategy:
    """Get a strategy instance by name."""
    return _create_strategy(name)


def available_strategies() -> list[str]:
    """Return names of all registered strategies."""
    return sorted(STRATEGY_REGISTRY.keys())
