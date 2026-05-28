"""Domain events — in-process observation mechanism.

Events are immutable records emitted during simulation ticks. They are NOT
persisted to an event store (ADR-003: event sourcing rejected for this scope).
The engine collects them in a list; analytics consumes the list after the run.

These same event types would become the event store payload in the production
architecture (Architecture B). The domain contract survives unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from elevator_sim.domain.model import Direction


class EventType(Enum):
    """Discriminator for domain events."""

    PASSENGER_REQUESTED = auto()
    PASSENGER_ASSIGNED = auto()
    PASSENGER_PICKED_UP = auto()
    PASSENGER_DELIVERED = auto()
    ELEVATOR_MOVED = auto()
    ELEVATOR_DIRECTION_CHANGED = auto()


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base fields shared by all domain events."""

    event_type: EventType
    tick: int


@dataclass(frozen=True, slots=True)
class PassengerRequested(DomainEvent):
    passenger_id: str
    source: int
    dest: int

    def __init__(self, tick: int, passenger_id: str, source: int, dest: int) -> None:
        object.__setattr__(self, "event_type", EventType.PASSENGER_REQUESTED)
        object.__setattr__(self, "tick", tick)
        object.__setattr__(self, "passenger_id", passenger_id)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "dest", dest)


@dataclass(frozen=True, slots=True)
class PassengerAssigned(DomainEvent):
    passenger_id: str
    elevator_id: int

    def __init__(self, tick: int, passenger_id: str, elevator_id: int) -> None:
        object.__setattr__(self, "event_type", EventType.PASSENGER_ASSIGNED)
        object.__setattr__(self, "tick", tick)
        object.__setattr__(self, "passenger_id", passenger_id)
        object.__setattr__(self, "elevator_id", elevator_id)


@dataclass(frozen=True, slots=True)
class PassengerPickedUp(DomainEvent):
    passenger_id: str
    elevator_id: int
    floor: int

    def __init__(
        self, tick: int, passenger_id: str, elevator_id: int, floor: int,
    ) -> None:
        object.__setattr__(self, "event_type", EventType.PASSENGER_PICKED_UP)
        object.__setattr__(self, "tick", tick)
        object.__setattr__(self, "passenger_id", passenger_id)
        object.__setattr__(self, "elevator_id", elevator_id)
        object.__setattr__(self, "floor", floor)


@dataclass(frozen=True, slots=True)
class PassengerDelivered(DomainEvent):
    passenger_id: str
    elevator_id: int
    floor: int

    def __init__(
        self, tick: int, passenger_id: str, elevator_id: int, floor: int,
    ) -> None:
        object.__setattr__(self, "event_type", EventType.PASSENGER_DELIVERED)
        object.__setattr__(self, "tick", tick)
        object.__setattr__(self, "passenger_id", passenger_id)
        object.__setattr__(self, "elevator_id", elevator_id)
        object.__setattr__(self, "floor", floor)


@dataclass(frozen=True, slots=True)
class ElevatorMoved(DomainEvent):
    elevator_id: int
    from_floor: int
    to_floor: int

    def __init__(
        self, tick: int, elevator_id: int, from_floor: int, to_floor: int,
    ) -> None:
        object.__setattr__(self, "event_type", EventType.ELEVATOR_MOVED)
        object.__setattr__(self, "tick", tick)
        object.__setattr__(self, "elevator_id", elevator_id)
        object.__setattr__(self, "from_floor", from_floor)
        object.__setattr__(self, "to_floor", to_floor)


@dataclass(frozen=True, slots=True)
class ElevatorDirectionChanged(DomainEvent):
    elevator_id: int
    old_direction: Direction
    new_direction: Direction

    def __init__(
        self,
        tick: int,
        elevator_id: int,
        old_direction: Direction,
        new_direction: Direction,
    ) -> None:
        object.__setattr__(self, "event_type", EventType.ELEVATOR_DIRECTION_CHANGED)
        object.__setattr__(self, "tick", tick)
        object.__setattr__(self, "elevator_id", elevator_id)
        object.__setattr__(self, "old_direction", old_direction)
        object.__setattr__(self, "new_direction", new_direction)
