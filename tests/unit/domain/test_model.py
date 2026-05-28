"""Unit tests for domain model: Elevator FSM, Passenger lifecycle, value objects."""

from __future__ import annotations

import pytest

from elevator_sim.domain.model import (
    Direction,
    Elevator,
    InvalidStateTransition,
    Passenger,
    PassengerRequest,
    PassengerStatus,
    ServicePolicy,
)


class TestPassengerRequest:
    def test_direction_up(self) -> None:
        req = PassengerRequest(0, "p1", 1, 10)
        assert req.direction == Direction.UP

    def test_direction_down(self) -> None:
        req = PassengerRequest(0, "p1", 10, 1)
        assert req.direction == Direction.DOWN

    def test_frozen(self) -> None:
        req = PassengerRequest(0, "p1", 1, 10)
        with pytest.raises(AttributeError):
            req.source = 5  # type: ignore[misc]


class TestServicePolicy:
    def test_full_service_covers_all_floors(self) -> None:
        policy = ServicePolicy.full_service(50)
        assert policy.serves(1)
        assert policy.serves(50)
        assert not policy.serves(51)
        assert not policy.serves(0)

    def test_express_policy_skips_floors(self) -> None:
        policy = ServicePolicy(
            served_floors=frozenset({1, 30, 31, 32, 33, 34, 35}),
            name="express-high",
        )
        assert policy.serves(1)
        assert policy.serves(30)
        assert not policy.serves(15)

    def test_can_serve_request_both_floors_required(self) -> None:
        policy = ServicePolicy(
            served_floors=frozenset({1, 10, 20}),
            name="limited",
        )
        req_ok = PassengerRequest(0, "p1", 1, 10)
        req_bad = PassengerRequest(0, "p2", 1, 15)
        assert policy.can_serve_request(req_ok)
        assert not policy.can_serve_request(req_bad)


class TestPassengerLifecycle:
    """Tests the state machine transitions: WAITING → ASSIGNED → RIDING → DELIVERED."""

    def test_full_lifecycle(self) -> None:
        req = PassengerRequest(0, "p1", 1, 10)
        p = Passenger(request=req)

        assert p.status == PassengerStatus.WAITING
        assert p.wait_time is None

        p.assign(elevator_id=1, tick=0)
        assert p.status == PassengerStatus.ASSIGNED
        assert p.assigned_elevator_id == 1

        p.pick_up(tick=3)
        assert p.status == PassengerStatus.RIDING
        assert p.wait_time == 3

        p.deliver(tick=12)
        assert p.status == PassengerStatus.DELIVERED
        assert p.travel_time == 9
        assert p.total_time == 12

    def test_cannot_pick_up_before_assign(self) -> None:
        p = Passenger(request=PassengerRequest(0, "p1", 1, 10))
        with pytest.raises(InvalidStateTransition, match="expected ASSIGNED"):
            p.pick_up(tick=1)

    def test_cannot_deliver_before_pickup(self) -> None:
        p = Passenger(request=PassengerRequest(0, "p1", 1, 10))
        p.assign(elevator_id=1, tick=0)
        with pytest.raises(InvalidStateTransition, match="expected RIDING"):
            p.deliver(tick=5)

    def test_cannot_assign_twice(self) -> None:
        p = Passenger(request=PassengerRequest(0, "p1", 1, 10))
        p.assign(elevator_id=1, tick=0)
        with pytest.raises(InvalidStateTransition, match="expected WAITING"):
            p.assign(elevator_id=2, tick=1)


class TestElevatorFSM:
    """Tests elevator state transitions: movement, direction, target selection."""

    def test_initial_state(self, idle_elevator: Elevator) -> None:
        assert idle_elevator.current_floor == 1
        assert idle_elevator.direction == Direction.IDLE
        assert len(idle_elevator.passengers) == 0

    def test_move_toward_passenger_destination(self) -> None:
        policy = ServicePolicy.full_service(10)
        e = Elevator(id=0, capacity=10, current_floor=1, service_policy=policy)
        p = Passenger(request=PassengerRequest(0, "p1", 1, 5))
        p.assign(elevator_id=0, tick=0)
        p.pick_up(tick=0)
        e.passengers.append(p)

        new_floor = e.move()
        assert new_floor == 2
        assert e.direction == Direction.UP

    def test_move_returns_none_when_idle(self, idle_elevator: Elevator) -> None:
        result = idle_elevator.move()
        assert result is None
        assert idle_elevator.direction == Direction.IDLE

    def test_dropoff_at_destination(self) -> None:
        policy = ServicePolicy.full_service(10)
        e = Elevator(id=0, capacity=10, current_floor=5, service_policy=policy)
        p = Passenger(request=PassengerRequest(0, "p1", 1, 5))
        p.assign(elevator_id=0, tick=0)
        p.pick_up(tick=0)
        e.passengers.append(p)

        delivered = e.dropoff(tick=4)
        assert len(delivered) == 1
        assert delivered[0].passenger_id == "p1"
        assert delivered[0].status == PassengerStatus.DELIVERED
        assert len(e.passengers) == 0

    def test_pickup_respects_capacity(self) -> None:
        policy = ServicePolicy.full_service(10)
        e = Elevator(id=0, capacity=2, current_floor=1, service_policy=policy)

        passengers = []
        for i in range(3):
            p = Passenger(request=PassengerRequest(0, f"p{i}", 1, 5))
            p.assign(elevator_id=0, tick=0)
            passengers.append(p)

        picked_up = e.pickup(passengers, tick=0)
        assert len(picked_up) == 2
        assert len(e.passengers) == 2
        assert passengers[2].status == PassengerStatus.ASSIGNED  # Still waiting

    def test_scan_semantics_continues_direction(self) -> None:
        """SCAN: serve all stops in current direction before reversing."""
        policy = ServicePolicy.full_service(20)
        e = Elevator(id=0, capacity=10, current_floor=5, direction=Direction.UP,
                     service_policy=policy)

        # Passengers going to floors 10 and 3
        p_up = Passenger(request=PassengerRequest(0, "p_up", 5, 10))
        p_up.assign(elevator_id=0, tick=0)
        p_up.pick_up(tick=0)
        e.passengers.append(p_up)

        p_down = Passenger(request=PassengerRequest(0, "p_down", 5, 3))
        p_down.assign(elevator_id=0, tick=0)
        p_down.pick_up(tick=0)
        e.passengers.append(p_down)

        # SCAN should continue UP first (to floor 10), then reverse to 3
        target = e.next_target()
        assert target == 10  # Continues up first

    def test_snapshot_is_read_only(self) -> None:
        policy = ServicePolicy.full_service(10)
        e = Elevator(id=0, capacity=10, current_floor=3, service_policy=policy)
        snap = e.snapshot()

        assert snap.elevator_id == 0
        assert snap.current_floor == 3
        assert snap.is_idle
        assert snap.remaining_capacity == 10

        with pytest.raises(AttributeError):
            snap.current_floor = 5  # type: ignore[misc]

    def test_next_target_prefers_assigned_pickups(self) -> None:
        """Idle elevator should target nearest assigned pickup."""
        policy = ServicePolicy.full_service(20)
        e = Elevator(id=0, capacity=10, current_floor=1, service_policy=policy)
        e.assigned_requests = [
            PassengerRequest(0, "p1", 5, 10),
            PassengerRequest(0, "p2", 15, 3),
        ]

        target = e.next_target()
        assert target == 5  # Nearest to current floor
