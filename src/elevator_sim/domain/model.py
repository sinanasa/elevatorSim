"""Domain model: entities, value objects, enums, and the Strategy port.

This module is the innermost ring of the hexagonal architecture. It has zero
I/O dependencies and imports nothing from engine, infrastructure, or cli.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Protocol, Sequence


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Direction(Enum):
    """Elevator direction — also serves as the FSM state.

    Direction and state are unified: an elevator's state IS its direction.
    No separate LOADING/DWELLING state because loading is instantaneous
    (ADR-005). If dwell time is added later, add DWELLING here.
    """

    UP = auto()
    DOWN = auto()
    IDLE = auto()


class PassengerStatus(Enum):
    """Lifecycle states for a passenger request."""

    WAITING = auto()     # Request submitted, not yet assigned
    ASSIGNED = auto()    # Assigned to an elevator, awaiting pickup
    RIDING = auto()      # Inside an elevator
    DELIVERED = auto()   # Arrived at destination


# ---------------------------------------------------------------------------
# Value Objects (immutable)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PassengerRequest:
    """Immutable record of a passenger's request, parsed from CSV input.

    This is a value object — identity-free, compared by content.
    """

    request_time: int
    passenger_id: str
    source: int
    dest: int

    @property
    def direction(self) -> Direction:
        """The direction this request implies."""
        if self.dest > self.source:
            return Direction.UP
        return Direction.DOWN


@dataclass(frozen=True, slots=True)
class ServicePolicy:
    """Defines which floors an elevator may serve.

    Express behavior is configuration, not a type hierarchy (ADR-008).
    The Elevator FSM is identical for express and local cars — only the
    set of legal floors differs.
    """

    served_floors: frozenset[int]
    name: str = "full-service"

    def serves(self, floor: int) -> bool:
        return floor in self.served_floors

    def can_serve_request(self, request: PassengerRequest) -> bool:
        """Both source and destination must be in the served set."""
        return self.serves(request.source) and self.serves(request.dest)

    @classmethod
    def full_service(cls, num_floors: int) -> ServicePolicy:
        """Factory for an elevator that serves all floors."""
        return cls(
            served_floors=frozenset(range(1, num_floors + 1)),
            name="full-service",
        )


@dataclass(frozen=True, slots=True)
class ElevatorSnapshot:
    """Read-only view of an elevator, passed to dispatch strategies.

    Strategies receive snapshots — they cannot mutate elevator state.
    This enforces the boundary: strategy is a pure decision function,
    engine owns the mutation.
    """

    elevator_id: int
    current_floor: int
    direction: Direction
    passenger_count: int
    capacity: int
    service_policy: ServicePolicy
    destinations: tuple[int, ...]
    assigned_pickups: tuple[PassengerRequest, ...]

    @property
    def remaining_capacity(self) -> int:
        return self.capacity - self.passenger_count

    @property
    def is_idle(self) -> bool:
        return self.direction == Direction.IDLE

    @property
    def has_capacity(self) -> bool:
        return self.passenger_count < self.capacity


# ---------------------------------------------------------------------------
# Entities (mutable, identity by ID)
# ---------------------------------------------------------------------------

@dataclass
class Passenger:
    """Tracks the full lifecycle of a passenger through the simulation.

    Entity — identity by passenger_id, mutable state (timestamps, status).
    """

    request: PassengerRequest
    status: PassengerStatus = PassengerStatus.WAITING
    assigned_elevator_id: int | None = None
    assigned_time: int | None = None
    pickup_time: int | None = None
    delivery_time: int | None = None

    @property
    def passenger_id(self) -> str:
        return self.request.passenger_id

    @property
    def source(self) -> int:
        return self.request.source

    @property
    def dest(self) -> int:
        return self.request.dest

    @property
    def wait_time(self) -> int | None:
        """Ticks from request to pickup."""
        if self.pickup_time is None:
            return None
        return self.pickup_time - self.request.request_time

    @property
    def travel_time(self) -> int | None:
        """Ticks from pickup to delivery."""
        if self.pickup_time is None or self.delivery_time is None:
            return None
        return self.delivery_time - self.pickup_time

    @property
    def total_time(self) -> int | None:
        """Ticks from request to delivery."""
        if self.delivery_time is None:
            return None
        return self.delivery_time - self.request.request_time

    def assign(self, elevator_id: int, tick: int) -> None:
        """Transition: WAITING -> ASSIGNED."""
        if self.status != PassengerStatus.WAITING:
            raise InvalidStateTransition(
                f"Cannot assign {self.passenger_id}: status is {self.status.name}, "
                f"expected WAITING"
            )
        self.status = PassengerStatus.ASSIGNED
        self.assigned_elevator_id = elevator_id
        self.assigned_time = tick

    def pick_up(self, tick: int) -> None:
        """Transition: ASSIGNED -> RIDING."""
        if self.status != PassengerStatus.ASSIGNED:
            raise InvalidStateTransition(
                f"Cannot pick up {self.passenger_id}: status is {self.status.name}, "
                f"expected ASSIGNED"
            )
        self.status = PassengerStatus.RIDING
        self.pickup_time = tick

    def deliver(self, tick: int) -> None:
        """Transition: RIDING -> DELIVERED."""
        if self.status != PassengerStatus.RIDING:
            raise InvalidStateTransition(
                f"Cannot deliver {self.passenger_id}: status is {self.status.name}, "
                f"expected RIDING"
            )
        self.status = PassengerStatus.DELIVERED
        self.delivery_time = tick


@dataclass
class Elevator:
    """Elevator aggregate — the primary mutable entity in the domain.

    FSM states are represented by the direction field (ADR-005).
    State transitions are driven by the engine's tick loop.
    """

    id: int
    capacity: int
    current_floor: int = 1
    direction: Direction = Direction.IDLE
    service_policy: ServicePolicy = field(default_factory=lambda: ServicePolicy(
        served_floors=frozenset(), name="uninitialized",
    ))
    passengers: list[Passenger] = field(default_factory=list)
    assigned_requests: list[PassengerRequest] = field(default_factory=list)

    def snapshot(self) -> ElevatorSnapshot:
        """Produce an immutable view for strategy consumption."""
        return ElevatorSnapshot(
            elevator_id=self.id,
            current_floor=self.current_floor,
            direction=self.direction,
            passenger_count=len(self.passengers),
            capacity=self.capacity,
            service_policy=self.service_policy,
            destinations=tuple(p.dest for p in self.passengers),
            assigned_pickups=tuple(self.assigned_requests),
        )

    def dropoff(self, tick: int) -> list[Passenger]:
        """Unload passengers whose destination is the current floor.

        Returns the list of delivered passengers (for event emission).
        Phase 3 of tick micro-steps (ADR-005): dropoff before pickup
        frees capacity.
        """
        delivered = []
        remaining = []
        for p in self.passengers:
            if p.dest == self.current_floor:
                p.deliver(tick)
                delivered.append(p)
            else:
                remaining.append(p)
        self.passengers = remaining
        return delivered

    def pickup(self, waiting_passengers: list[Passenger], tick: int) -> list[Passenger]:
        """Load passengers assigned to this elevator at the current floor.

        Only loads passengers whose source matches current_floor and who
        are in ASSIGNED status. Respects capacity — stops loading when full.
        Returns the list of picked-up passengers (for event emission).

        Args:
            waiting_passengers: All passengers assigned to this elevator
                that are waiting at the current floor.
            tick: Current simulation tick.
        """
        picked_up = []
        for p in waiting_passengers:
            if len(self.passengers) >= self.capacity:
                break
            p.pick_up(tick)
            self.passengers.append(p)
            picked_up.append(p)
            # Remove from assigned requests
            self.assigned_requests = [
                r for r in self.assigned_requests
                if r.passenger_id != p.passenger_id
            ]
        return picked_up

    def move(self) -> int | None:
        """Advance one floor toward the next target.

        Returns the new floor, or None if idle (no targets).
        Phase 5 of tick micro-steps (ADR-005).
        """
        target = self.next_target()
        if target is None:
            self.direction = Direction.IDLE
            return None

        if target > self.current_floor:
            self.current_floor += 1
            self.direction = Direction.UP
        elif target < self.current_floor:
            self.current_floor -= 1
            self.direction = Direction.DOWN
        else:
            # Already at target — recalculate for next target
            self._update_direction()
            return self.current_floor

        return self.current_floor

    def next_target(self) -> int | None:
        """Determine the next floor this elevator should visit.

        Priority: continue in current direction if there are targets that way,
        then reverse if targets exist in the opposite direction, else idle.

        Uses SCAN (elevator algorithm) semantics: serve all stops in the
        current direction before reversing.
        """
        all_targets = self._all_target_floors()
        if not all_targets:
            return None

        if self.direction == Direction.UP:
            # Targets above current floor, in ascending order
            above = sorted(f for f in all_targets if f >= self.current_floor)
            if above:
                return above[0]
            # Nothing above — reverse
            below = sorted((f for f in all_targets if f < self.current_floor), reverse=True)
            return below[0] if below else None

        if self.direction == Direction.DOWN:
            # Targets below current floor, in descending order
            below = sorted((f for f in all_targets if f <= self.current_floor), reverse=True)
            if below:
                return below[0]
            # Nothing below — reverse
            above = sorted(f for f in all_targets if f > self.current_floor)
            return above[0] if above else None

        # IDLE — pick nearest target
        return min(all_targets, key=lambda f: abs(f - self.current_floor))

    def _all_target_floors(self) -> set[int]:
        """All floors this elevator needs to visit: passenger destinations + pickup floors."""
        targets: set[int] = set()
        for p in self.passengers:
            targets.add(p.dest)
        for r in self.assigned_requests:
            targets.add(r.source)
        return targets

    def _update_direction(self) -> None:
        """Recalculate direction based on remaining targets."""
        target = self.next_target()
        if target is None:
            self.direction = Direction.IDLE
        elif target > self.current_floor:
            self.direction = Direction.UP
        elif target < self.current_floor:
            self.direction = Direction.DOWN
        # If target == current_floor, keep current direction
        # (we're at a stop, will recalculate after pickup/dropoff)


# ---------------------------------------------------------------------------
# Strategy Port (Protocol — structural subtyping, ADR-004)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Configuration values strategies may need for scoring decisions."""

    num_floors: int
    num_elevators: int
    max_capacity: int


class DispatchStrategy(Protocol):
    """Port for the dispatch algorithm.

    Strategies receive read-only snapshots and return an elevator ID.
    They are pure decision functions — no mutation, no side effects.
    """

    @property
    def name(self) -> str: ...

    def select_elevator(
        self,
        request: PassengerRequest,
        elevators: Sequence[ElevatorSnapshot],
        config: SimulationConfig,
    ) -> int:
        """Choose which elevator should serve this request.

        Args:
            request: The passenger request to assign.
            elevators: Read-only snapshots of all eligible elevators
                (already filtered by ServicePolicy).
            config: Simulation configuration.

        Returns:
            The elevator_id of the selected elevator.

        Raises:
            DispatchError: If no elevator can serve the request.
        """
        ...


# ---------------------------------------------------------------------------
# Error Types (explicit, not bare exceptions)
# ---------------------------------------------------------------------------

class SimulationError(Exception):
    """Base exception for all simulation errors."""


class InvalidStateTransition(SimulationError):
    """Raised when a passenger or elevator state transition is invalid."""


class CapacityViolationError(SimulationError):
    """Raised when an elevator would exceed its capacity."""


class DispatchError(SimulationError):
    """Raised when no elevator can serve a request."""


class InvalidRequestError(SimulationError):
    """Raised when a passenger request fails validation."""


class ServicePolicyViolationError(SimulationError):
    """Raised when an elevator is directed to a floor outside its service policy."""
