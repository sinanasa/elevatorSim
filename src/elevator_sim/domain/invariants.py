"""Domain invariants — safety, liveness, and fairness checks.

These functions encode the formal properties of the simulation (ADR-009).
They are called by the engine during execution (fail-fast on violation)
and by Hypothesis property-based tests (generative verification).

Mapping to temporal logic (from formal methods / SMV model checking):

  Safety (AG ¬bad):
    - capacity_respected:        AG (|elevator.passengers| <= capacity)
    - service_policy_respected:  AG (elevator.floor ∈ elevator.policy)
    - no_double_assignment:      AG (∀p: |assigned_elevators(p)| <= 1)
    - valid_request:             precondition on input

  Liveness (AG(p → AF q)):
    - all_passengers_delivered:  AG(requested → AF delivered)

  Fairness (bounded wait disparity):
    - bounded_wait_disparity:    max_wait <= K * avg_wait under sub-capacity load
"""

from __future__ import annotations

from elevator_sim.domain.model import (
    CapacityViolationError,
    Elevator,
    InvalidRequestError,
    Passenger,
    PassengerRequest,
    PassengerStatus,
    ServicePolicyViolationError,
)


# ---------------------------------------------------------------------------
# Safety invariants
# ---------------------------------------------------------------------------

def capacity_respected(elevator: Elevator) -> bool:
    """AG ¬overflow: elevator never holds more passengers than capacity."""
    if len(elevator.passengers) > elevator.capacity:
        raise CapacityViolationError(
            f"Elevator {elevator.id} has {len(elevator.passengers)} passengers "
            f"but capacity is {elevator.capacity}"
        )
    return True


def service_policy_respected(elevator: Elevator) -> bool:
    """AG policy_respected: elevator only stops at floors in its service policy.

    Checked when an elevator has passengers boarding or alighting.
    An elevator may *pass through* non-served floors while in transit.
    """
    if not elevator.service_policy.serves(elevator.current_floor):
        # Only a violation if the elevator is actually stopping here
        # (has passengers to pick up or drop off at this floor)
        has_dropoff = any(
            p.dest == elevator.current_floor for p in elevator.passengers
        )
        has_pickup = any(
            r.source == elevator.current_floor for r in elevator.assigned_requests
        )
        if has_dropoff or has_pickup:
            raise ServicePolicyViolationError(
                f"Elevator {elevator.id} stopping at floor {elevator.current_floor} "
                f"which is outside its service policy '{elevator.service_policy.name}'"
            )
    return True


def no_double_assignment(passengers: list[Passenger]) -> bool:
    """AG ¬double_assign: each passenger assigned to at most one elevator."""
    assigned = {}
    for p in passengers:
        if p.assigned_elevator_id is not None:
            if p.passenger_id in assigned:
                prev_elevator = assigned[p.passenger_id]
                if prev_elevator != p.assigned_elevator_id:
                    raise AssertionError(
                        f"Passenger {p.passenger_id} assigned to elevators "
                        f"{prev_elevator} and {p.assigned_elevator_id}"
                    )
            assigned[p.passenger_id] = p.assigned_elevator_id
    return True


def valid_request(request: PassengerRequest, num_floors: int) -> bool:
    """Precondition: request fields are within bounds."""
    if request.source < 1 or request.source > num_floors:
        raise InvalidRequestError(
            f"Passenger {request.passenger_id}: source floor {request.source} "
            f"out of range [1, {num_floors}]"
        )
    if request.dest < 1 or request.dest > num_floors:
        raise InvalidRequestError(
            f"Passenger {request.passenger_id}: dest floor {request.dest} "
            f"out of range [1, {num_floors}]"
        )
    if request.source == request.dest:
        raise InvalidRequestError(
            f"Passenger {request.passenger_id}: source and dest are both "
            f"floor {request.source}"
        )
    if request.request_time < 0:
        raise InvalidRequestError(
            f"Passenger {request.passenger_id}: request_time {request.request_time} "
            f"is negative"
        )
    return True


# ---------------------------------------------------------------------------
# Liveness checks (post-simulation verification)
# ---------------------------------------------------------------------------

def all_passengers_delivered(passengers: list[Passenger]) -> bool:
    """AG(requested → AF delivered): every request is eventually served.

    Called after simulation completes. If any passenger is not delivered,
    the simulation has a liveness violation (potential deadlock or starvation).
    """
    undelivered = [
        p for p in passengers
        if p.status != PassengerStatus.DELIVERED
    ]
    if undelivered:
        details = ", ".join(
            f"{p.passenger_id} (status={p.status.name})" for p in undelivered[:5]
        )
        suffix = f" and {len(undelivered) - 5} more" if len(undelivered) > 5 else ""
        raise AssertionError(
            f"Liveness violation: {len(undelivered)} passengers not delivered: "
            f"{details}{suffix}"
        )
    return True


# ---------------------------------------------------------------------------
# Fairness checks (post-simulation analysis)
# ---------------------------------------------------------------------------

def bounded_wait_disparity(
    passengers: list[Passenger],
    max_multiplier: float = 5.0,
) -> tuple[bool, str]:
    """Fairness check: no passenger's wait is excessively worse than average.

    Under sub-capacity load, max_wait should be bounded by some multiple
    of avg_wait. This is a soft property — we report rather than raise,
    since violation may indicate a poor strategy rather than a bug.

    Args:
        passengers: All delivered passengers.
        max_multiplier: Maximum allowed ratio of max_wait to avg_wait.

    Returns:
        (passed, message) tuple.
    """
    delivered = [p for p in passengers if p.wait_time is not None]
    if not delivered:
        return True, "No delivered passengers to evaluate."

    wait_times = [p.wait_time for p in delivered if p.wait_time is not None]
    avg_wait = sum(wait_times) / len(wait_times)
    max_wait = max(wait_times)

    if avg_wait == 0:
        return True, "All passengers had zero wait time."

    ratio = max_wait / avg_wait
    passed = ratio <= max_multiplier
    message = (
        f"Wait disparity: max={max_wait}, avg={avg_wait:.1f}, "
        f"ratio={ratio:.1f}x (threshold={max_multiplier}x)"
    )
    return passed, message
