"""Unit tests for dispatch strategies."""

from __future__ import annotations

import pytest

from elevator_sim.domain.model import (
    Direction,
    DispatchError,
    ElevatorSnapshot,
    PassengerRequest,
    ServicePolicy,
    SimulationConfig,
)
from elevator_sim.domain.strategies import (
    NearestCarStrategy,
    RoundRobinStrategy,
    ZoneBasedStrategy,
    get_strategy,
    available_strategies,
)


@pytest.fixture
def config() -> SimulationConfig:
    return SimulationConfig(num_floors=50, num_elevators=4, max_capacity=10)


@pytest.fixture
def policy() -> ServicePolicy:
    return ServicePolicy.full_service(50)


def _snap(
    elevator_id: int,
    floor: int,
    direction: Direction,
    passenger_count: int,
    policy: ServicePolicy,
    capacity: int = 10,
) -> ElevatorSnapshot:
    return ElevatorSnapshot(
        elevator_id=elevator_id,
        current_floor=floor,
        direction=direction,
        passenger_count=passenger_count,
        capacity=capacity,
        service_policy=policy,
        destinations=(),
        assigned_pickups=(),
    )


class TestRoundRobin:
    def test_cycles_through_elevators(self, config: SimulationConfig, policy: ServicePolicy) -> None:
        rr = RoundRobinStrategy()
        elevators = [_snap(i, 1, Direction.IDLE, 0, policy) for i in range(3)]
        req = PassengerRequest(0, "p1", 1, 10)

        assert rr.select_elevator(req, elevators, config) == 0
        assert rr.select_elevator(req, elevators, config) == 1
        assert rr.select_elevator(req, elevators, config) == 2
        assert rr.select_elevator(req, elevators, config) == 0  # wraps

    def test_raises_on_empty_list(self, config: SimulationConfig) -> None:
        rr = RoundRobinStrategy()
        with pytest.raises(DispatchError):
            rr.select_elevator(PassengerRequest(0, "p1", 1, 5), [], config)


class TestNearestCar:
    def test_prefers_closer_elevator(self, config: SimulationConfig, policy: ServicePolicy) -> None:
        nc = NearestCarStrategy()
        elevators = [
            _snap(0, 1, Direction.IDLE, 0, policy),
            _snap(1, 25, Direction.IDLE, 0, policy),
        ]
        req = PassengerRequest(0, "p1", 23, 40)
        assert nc.select_elevator(req, elevators, config) == 1

    def test_prefers_same_direction(self, config: SimulationConfig, policy: ServicePolicy) -> None:
        """An elevator heading toward the pickup in the same direction should win
        over a slightly closer one heading away."""
        nc = NearestCarStrategy()
        elevators = [
            _snap(0, 18, Direction.DOWN, 2, policy),  # Heading away from floor 20
            _snap(1, 15, Direction.UP, 2, policy),     # Heading toward floor 20
        ]
        req = PassengerRequest(0, "p1", 20, 40)
        assert nc.select_elevator(req, elevators, config) == 1

    def test_prefers_less_loaded(self, config: SimulationConfig, policy: ServicePolicy) -> None:
        """Between two equidistant idle elevators, prefer the less loaded one."""
        nc = NearestCarStrategy()
        elevators = [
            _snap(0, 10, Direction.IDLE, 8, policy),
            _snap(1, 10, Direction.IDLE, 2, policy),
        ]
        req = PassengerRequest(0, "p1", 10, 30)
        assert nc.select_elevator(req, elevators, config) == 1

    def test_deterministic_tiebreak(self, config: SimulationConfig, policy: ServicePolicy) -> None:
        """Equal scores broken by elevator ID for determinism."""
        nc = NearestCarStrategy()
        elevators = [
            _snap(0, 10, Direction.IDLE, 0, policy),
            _snap(1, 10, Direction.IDLE, 0, policy),
        ]
        req = PassengerRequest(0, "p1", 10, 30)
        assert nc.select_elevator(req, elevators, config) == 0


class TestZoneBased:
    def test_prefers_zone_local_elevator(self, config: SimulationConfig, policy: ServicePolicy) -> None:
        zb = ZoneBasedStrategy(num_zones=3)
        # Floor 40 is in zone 2 (floors 35-50 with 3 zones of ~17 floors)
        elevators = [
            _snap(0, 5, Direction.IDLE, 0, policy),   # Zone 0
            _snap(1, 42, Direction.IDLE, 0, policy),  # Zone 2, same as request
        ]
        req = PassengerRequest(0, "p1", 40, 45)
        assert zb.select_elevator(req, elevators, config) == 1

    def test_falls_back_to_nearest_car(self, config: SimulationConfig, policy: ServicePolicy) -> None:
        """If no zone-local elevator has capacity, fall back to nearest car."""
        zb = ZoneBasedStrategy(num_zones=3)
        # Only elevator is in a different zone but should still be selected
        elevators = [
            _snap(0, 5, Direction.IDLE, 0, policy),
        ]
        req = PassengerRequest(0, "p1", 40, 45)
        assert zb.select_elevator(req, elevators, config) == 0


class TestStrategyRegistry:
    def test_all_strategies_available(self) -> None:
        names = available_strategies()
        assert "nearest_car" in names
        assert "round_robin" in names
        assert "zone_based" in names

    def test_get_strategy_returns_correct_type(self) -> None:
        assert isinstance(get_strategy("nearest_car"), NearestCarStrategy)
        assert isinstance(get_strategy("round_robin"), RoundRobinStrategy)
        assert isinstance(get_strategy("zone_based"), ZoneBasedStrategy)

    def test_unknown_strategy_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy("nonexistent")
