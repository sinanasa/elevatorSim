"""Shared test fixtures for the elevator simulation."""

from __future__ import annotations

import pytest

from elevator_sim.domain.model import (
    Direction,
    Elevator,
    Passenger,
    PassengerRequest,
    ServicePolicy,
    SimulationConfig,
)


@pytest.fixture
def full_service_policy() -> ServicePolicy:
    """A service policy that serves all 50 floors."""
    return ServicePolicy.full_service(50)


@pytest.fixture
def express_high_policy() -> ServicePolicy:
    """Express policy: ground floor + floors 30-50."""
    return ServicePolicy(
        served_floors=frozenset({1} | set(range(30, 51))),
        name="express-high",
    )


@pytest.fixture
def config_small() -> SimulationConfig:
    """Small simulation config for fast tests."""
    return SimulationConfig(num_floors=10, num_elevators=2, max_capacity=5)


@pytest.fixture
def config_medium() -> SimulationConfig:
    """Medium simulation config matching the sample CSV."""
    return SimulationConfig(num_floors=50, num_elevators=6, max_capacity=10)


@pytest.fixture
def idle_elevator(full_service_policy: ServicePolicy) -> Elevator:
    """An idle elevator at floor 1 with capacity 10."""
    return Elevator(
        id=0,
        capacity=10,
        current_floor=1,
        direction=Direction.IDLE,
        service_policy=full_service_policy,
    )


@pytest.fixture
def sample_requests() -> list[PassengerRequest]:
    """The sample requests from the brief."""
    return [
        PassengerRequest(0, "passenger1", 1, 51),
        PassengerRequest(0, "passenger2", 1, 37),
        PassengerRequest(10, "passenger3", 20, 1),
    ]
