"""Unit tests for the simulation engine — tick-level correctness."""

from __future__ import annotations

import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(50),
)

from elevator_sim.domain.model import (
    PassengerRequest,
    PassengerStatus,
    SimulationConfig,
)
from elevator_sim.domain.strategies import get_strategy
from elevator_sim.engine.simulation import SimulationEngine


class TestSimulationEngine:
    def test_single_passenger_direct_trip(self) -> None:
        """One passenger, one elevator: floor 1→5 should take 4 ticks of travel."""
        config = SimulationConfig(num_floors=10, num_elevators=1, max_capacity=5)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()

        requests = [PassengerRequest(0, "p1", 1, 5)]
        result = engine.run(requests)

        p = result.passengers[0]
        assert p.status == PassengerStatus.DELIVERED
        assert p.wait_time == 0   # Elevator starts at floor 1, passenger at floor 1
        assert p.travel_time == 4  # 4 floors of travel
        assert p.total_time == 4

    def test_passenger_on_different_floor(self) -> None:
        """Elevator at floor 1, passenger at floor 5→8: wait=4, travel=3."""
        config = SimulationConfig(num_floors=10, num_elevators=1, max_capacity=5)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()

        requests = [PassengerRequest(0, "p1", 5, 8)]
        result = engine.run(requests)

        p = result.passengers[0]
        assert p.status == PassengerStatus.DELIVERED
        assert p.wait_time == 4   # Elevator travels 1→5
        assert p.travel_time == 3  # Then 5→8
        assert p.total_time == 7

    def test_two_passengers_same_direction(self) -> None:
        """Two passengers going up from floor 1 — both should be served efficiently."""
        config = SimulationConfig(num_floors=10, num_elevators=1, max_capacity=5)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()

        requests = [
            PassengerRequest(0, "p1", 1, 5),
            PassengerRequest(0, "p2", 1, 8),
        ]
        result = engine.run(requests)

        p1 = next(p for p in result.passengers if p.passenger_id == "p1")
        p2 = next(p for p in result.passengers if p.passenger_id == "p2")

        assert p1.status == PassengerStatus.DELIVERED
        assert p2.status == PassengerStatus.DELIVERED
        assert p1.total_time == 4   # 1→5
        assert p2.total_time == 7   # 1→8

    def test_delayed_request(self) -> None:
        """Requests arriving at different times are handled correctly."""
        config = SimulationConfig(num_floors=10, num_elevators=1, max_capacity=5)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()

        requests = [
            PassengerRequest(0, "p1", 1, 5),
            PassengerRequest(10, "p2", 1, 3),
        ]
        result = engine.run(requests)

        assert all(p.status == PassengerStatus.DELIVERED for p in result.passengers)

    def test_position_log_format(self) -> None:
        """Position log has one entry per tick with correct format."""
        config = SimulationConfig(num_floors=10, num_elevators=2, max_capacity=5)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()

        requests = [PassengerRequest(0, "p1", 1, 3)]
        result = engine.run(requests)

        assert len(result.position_log) > 0
        first = result.position_log[0]
        assert "tick" in first
        assert "positions" in first
        assert len(first["positions"]) == 2  # 2 elevators

    def test_duplicate_passenger_id_handled(self) -> None:
        """Duplicate passenger IDs should be skipped (logged, not crashed)."""
        config = SimulationConfig(num_floors=10, num_elevators=1, max_capacity=5)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()

        requests = [
            PassengerRequest(0, "p1", 1, 5),
            PassengerRequest(0, "p1", 1, 8),  # Duplicate ID
        ]
        result = engine.run(requests)

        # Should only have one passenger (duplicate skipped)
        assert len(result.passengers) == 1

    def test_no_peek_ahead(self) -> None:
        """Requests at future ticks should not affect earlier dispatch decisions.

        The no-peek-ahead constraint: the engine sees only requests with
        time <= current tick.
        """
        config = SimulationConfig(num_floors=10, num_elevators=2, max_capacity=5)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()

        requests = [
            PassengerRequest(0, "p1", 1, 10),
            PassengerRequest(100, "p2", 1, 5),  # Far future
        ]
        result = engine.run(requests)

        p1 = next(p for p in result.passengers if p.passenger_id == "p1")
        # p1 should be assigned at tick 0, not delayed by p2's future arrival
        assert p1.assigned_time == 0

    def test_deterministic_output(self) -> None:
        """Same inputs produce identical outputs."""
        config = SimulationConfig(num_floors=10, num_elevators=2, max_capacity=5)
        requests = [
            PassengerRequest(0, "p1", 1, 5),
            PassengerRequest(0, "p2", 3, 7),
            PassengerRequest(5, "p3", 10, 1),
        ]

        results = []
        for _ in range(3):
            engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
            engine.initialize()
            results.append(engine.run(requests))

        # All runs should have the same total ticks and passenger outcomes
        for r in results[1:]:
            assert r.total_ticks == results[0].total_ticks
            for p_a, p_b in zip(results[0].passengers, r.passengers):
                assert p_a.total_time == p_b.total_time
                assert p_a.wait_time == p_b.wait_time
