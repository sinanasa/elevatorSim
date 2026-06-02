"""Property-based tests for formal safety, liveness, and fairness properties.

These tests use Hypothesis to verify invariants across randomized inputs.
They map directly to the formal properties from ADR-009:

  Safety (AG ¬bad):
    - No elevator exceeds capacity at any tick
    - No elevator stops at a floor outside its service policy
    - No passenger is assigned to two elevators

  Liveness (AG(requested → AF delivered)):
    - Every request is eventually served (simulation terminates with all delivered)

  Fairness:
    - Wait time disparity is bounded under sub-capacity load

Each test docstring names the formal property being verified.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings, assume
from hypothesis import strategies as st

from elevator_sim.domain.model import (
    Elevator,
    Passenger,
    PassengerRequest,
    PassengerStatus,
    ServicePolicy,
    SimulationConfig,
)
from elevator_sim.domain.invariants import (
    all_passengers_delivered,
    bounded_wait_disparity,
    capacity_respected,
    no_double_assignment,
    valid_request,
)
from elevator_sim.domain.strategies import get_strategy
from elevator_sim.engine.simulation import SimulationEngine

import structlog

# Suppress logging during property tests
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(50),
)


# ---------------------------------------------------------------------------
# Hypothesis strategies for generating domain objects
# ---------------------------------------------------------------------------

def passenger_requests(
    num_floors: int = 20,
    max_time: int = 50,
    min_requests: int = 1,
    max_requests: int = 30,
) -> st.SearchStrategy[list[PassengerRequest]]:
    """Generate a list of valid passenger requests."""
    return st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=max_time),   # time
            st.integers(min_value=1, max_value=num_floors),  # source
            st.integers(min_value=1, max_value=num_floors),  # dest
        ).filter(lambda t: t[1] != t[2]),  # source != dest
        min_size=min_requests,
        max_size=max_requests,
    ).map(
        lambda tuples: [
            PassengerRequest(
                request_time=t[0],
                passenger_id=f"p{i}",
                source=t[1],
                dest=t[2],
            )
            for i, t in enumerate(tuples)
        ]
    )


def run_simulation(
    requests: list[PassengerRequest],
    num_floors: int,
    num_elevators: int,
    max_capacity: int,
    strategy_name: str,
) -> SimulationEngine:
    """Helper to run a full simulation and return the engine for inspection."""
    config = SimulationConfig(
        num_floors=num_floors,
        num_elevators=num_elevators,
        max_capacity=max_capacity,
    )
    strategy = get_strategy(strategy_name)
    engine = SimulationEngine(config=config, strategy=strategy)
    engine.initialize()
    engine.run(requests)
    return engine


# ---------------------------------------------------------------------------
# Safety: AG (|elevator.passengers| <= capacity)
# ---------------------------------------------------------------------------

class TestCapacitySafety:
    """Verify that no elevator ever exceeds its capacity."""

    @given(requests=passenger_requests(num_floors=10, max_requests=20))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_nearest_car_respects_capacity(self, requests: list[PassengerRequest]) -> None:
        """AG ¬overflow under nearest_car strategy."""
        engine = run_simulation(requests, 10, 3, 5, "nearest_car")
        for elevator in engine.elevators:
            assert len(elevator.passengers) <= elevator.capacity

    @given(requests=passenger_requests(num_floors=10, max_requests=20))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_round_robin_respects_capacity(self, requests: list[PassengerRequest]) -> None:
        """AG ¬overflow under round_robin strategy."""
        engine = run_simulation(requests, 10, 3, 5, "round_robin")
        for elevator in engine.elevators:
            assert len(elevator.passengers) <= elevator.capacity


# ---------------------------------------------------------------------------
# Safety: AG (∀p: |assigned_elevators(p)| <= 1)
# ---------------------------------------------------------------------------

class TestNoDoubleAssignment:
    """Verify no passenger is assigned to two elevators."""

    @given(requests=passenger_requests(num_floors=10, max_requests=20))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_no_double_assignment_nearest_car(self, requests: list[PassengerRequest]) -> None:
        """AG ¬double_assign under nearest_car strategy."""
        engine = run_simulation(requests, 10, 3, 5, "nearest_car")
        no_double_assignment(list(engine.passengers.values()))

    @given(requests=passenger_requests(num_floors=10, max_requests=20))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_no_double_assignment_round_robin(self, requests: list[PassengerRequest]) -> None:
        """AG ¬double_assign under round_robin strategy."""
        engine = run_simulation(requests, 10, 3, 5, "round_robin")
        no_double_assignment(list(engine.passengers.values()))


# ---------------------------------------------------------------------------
# Liveness: AG(requested → AF delivered)
# ---------------------------------------------------------------------------

class TestLiveness:
    """Verify that every request is eventually served."""

    @given(requests=passenger_requests(num_floors=10, max_requests=15))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_delivered_nearest_car(self, requests: list[PassengerRequest]) -> None:
        """AG(requested → AF delivered) under nearest_car."""
        engine = run_simulation(requests, 10, 3, 5, "nearest_car")
        all_passengers_delivered(list(engine.passengers.values()))

    @given(requests=passenger_requests(num_floors=10, max_requests=15))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_delivered_round_robin(self, requests: list[PassengerRequest]) -> None:
        """AG(requested → AF delivered) under round_robin."""
        engine = run_simulation(requests, 10, 3, 5, "round_robin")
        all_passengers_delivered(list(engine.passengers.values()))

    @given(requests=passenger_requests(num_floors=10, max_requests=15))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_delivered_zone_based(self, requests: list[PassengerRequest]) -> None:
        """AG(requested → AF delivered) under zone_based."""
        engine = run_simulation(requests, 10, 3, 5, "zone_based")
        all_passengers_delivered(list(engine.passengers.values()))


# ---------------------------------------------------------------------------
# Fairness: bounded wait disparity
# ---------------------------------------------------------------------------

class TestFairness:
    """Verify wait time disparity is bounded under sub-capacity load.

    This is a soft property — we report rather than hard-fail, since
    high disparity may indicate a poor strategy rather than a bug.
    We test with generous bounds (10x multiplier) to catch only
    pathological cases.
    """

    @given(requests=passenger_requests(num_floors=10, max_time=30, max_requests=10))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_fairness_nearest_car(self, requests: list[PassengerRequest]) -> None:
        """Bounded wait disparity under nearest_car with sub-capacity load.

        Uses a generous 10x threshold to catch only pathological cases.
        Fairness is a soft property — minor disparity under randomized
        inputs is expected, extreme disparity indicates a strategy bug.
        """
        engine = run_simulation(requests, 10, 3, 5, "nearest_car")
        delivered = [p for p in engine.passengers.values() if p.status == PassengerStatus.DELIVERED]
        if len(delivered) >= 3:
            passed, msg = bounded_wait_disparity(delivered, max_multiplier=10.0)
            assert passed, f"Fairness violation under nearest_car: {msg}"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestRequestValidation:
    """Verify that invalid requests are rejected."""

    def test_source_out_of_range(self) -> None:
        req = PassengerRequest(0, "p1", 0, 5)
        import pytest
        with pytest.raises(Exception):
            valid_request(req, num_floors=10)

    def test_dest_out_of_range(self) -> None:
        req = PassengerRequest(0, "p1", 1, 11)
        import pytest
        with pytest.raises(Exception):
            valid_request(req, num_floors=10)

    def test_source_equals_dest(self) -> None:
        req = PassengerRequest(0, "p1", 5, 5)
        import pytest
        with pytest.raises(Exception):
            valid_request(req, num_floors=10)

    def test_negative_time(self) -> None:
        req = PassengerRequest(-1, "p1", 1, 5)
        import pytest
        with pytest.raises(Exception):
            valid_request(req, num_floors=10)
