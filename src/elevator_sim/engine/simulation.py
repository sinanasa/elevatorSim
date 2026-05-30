"""Simulation engine — orchestrates the tick loop.

This is the application layer in hexagonal terms. It calls domain objects
but contains no business rules itself. It knows about time sequencing,
micro-step ordering (ADR-005), and event collection.

The engine is deterministic: same input + same config + same strategy =
identical output. This is the CLI equivalent of idempotency.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog

from elevator_sim.domain.events import (
    DomainEvent,
    ElevatorDirectionChanged,
    ElevatorMoved,
    PassengerAssigned,
    PassengerDelivered,
    PassengerPickedUp,
    PassengerRequested,
)
from elevator_sim.domain.invariants import (
    capacity_respected,
    no_double_assignment,
    service_policy_respected,
    valid_request,
)
from elevator_sim.domain.model import (
    Direction,
    DispatchError,
    DispatchStrategy,
    Elevator,
    Passenger,
    PassengerRequest,
    PassengerStatus,
    ServicePolicy,
    SimulationConfig,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Simulation result — returned after the tick loop completes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SimulationResult:
    """Immutable result of a completed simulation run."""

    run_id: str
    strategy_name: str
    config: SimulationConfig
    passengers: tuple[Passenger, ...]
    position_log: tuple[dict[str, int | list[int]], ...]  # per-tick snapshots
    events: tuple[DomainEvent, ...]
    total_ticks: int


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------

@dataclass
class SimulationEngine:
    """Orchestrates the discrete-time simulation tick loop.

    Owns the elevator fleet, passenger registry, event log, and position log.
    Delegates dispatch decisions to the injected strategy.
    Enforces domain invariants after each phase.
    """

    config: SimulationConfig
    strategy: DispatchStrategy
    elevators: list[Elevator] = field(default_factory=list)
    passengers: dict[str, Passenger] = field(default_factory=dict)
    events: list[DomainEvent] = field(default_factory=list)
    position_log: list[dict[str, int | list[int]]] = field(default_factory=list)
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    _current_tick: int = 0

    def initialize(
        self,
        service_policies: list[ServicePolicy] | None = None,
    ) -> None:
        """Create the elevator fleet. Call once before running."""
        for i in range(self.config.num_elevators):
            policy = (
                service_policies[i]
                if service_policies and i < len(service_policies)
                else ServicePolicy.full_service(self.config.num_floors)
            )
            elevator = Elevator(
                id=i,
                capacity=self.config.max_capacity,
                current_floor=1,
                direction=Direction.IDLE,
                service_policy=policy,
            )
            self.elevators.append(elevator)

        logger.info(
            "simulation.initialized",
            run_id=self.run_id,
            strategy=self.strategy.name,
            num_elevators=self.config.num_elevators,
            num_floors=self.config.num_floors,
            max_capacity=self.config.max_capacity,
        )

    def run(self, requests: list[PassengerRequest]) -> SimulationResult:
        """Execute the full simulation and return results.

        Args:
            requests: All passenger requests, sorted by request_time.
                      The engine will not peek ahead — only requests
                      with time <= current tick are visible.
        """
        # Validate all requests up front
        for req in requests:
            valid_request(req, self.config.num_floors)

        # Sort by time to ensure correct ingestion order
        sorted_requests = sorted(requests, key=lambda r: r.request_time)

        # Build a time-indexed lookup for O(1) per-tick ingestion
        requests_by_time: dict[int, list[PassengerRequest]] = {}
        for req in sorted_requests:
            requests_by_time.setdefault(req.request_time, []).append(req)

        # Determine when the simulation ends: all passengers delivered
        # or a safety bound on max ticks
        max_request_time = max(r.request_time for r in sorted_requests) if sorted_requests else 0
        # Safety bound: max request time + enough ticks for worst case.
        # Each batch of passengers (capacity per elevator) requires up to
        # two full building traversals (up + down). Account for total batches
        # needed across the fleet.
        effective_capacity = max(1, self.config.num_elevators * self.config.max_capacity)
        batches = (len(sorted_requests) + effective_capacity - 1) // effective_capacity
        max_ticks = max_request_time + batches * self.config.num_floors * 2 + self.config.num_floors * 2

        logger.info(
            "simulation.started",
            run_id=self.run_id,
            total_requests=len(sorted_requests),
            max_request_time=max_request_time,
            max_ticks=max_ticks,
        )

        self._current_tick = 0
        while self._current_tick <= max_ticks:
            # Phase 1 — INGEST
            new_requests = requests_by_time.get(self._current_tick, [])
            self._phase_ingest(new_requests)

            # Phase 2 — DISPATCH
            self._phase_dispatch()

            # Phase 3 — DROPOFF
            self._phase_dropoff()

            # Phase 4 — PICKUP
            self._phase_pickup()

            # Phase 5 — MOVE
            self._phase_move()

            # Phase 6 — RECORD
            self._record_positions()

            # Check termination: all requests ingested AND all passengers delivered
            all_ingested = len(self.passengers) >= len(sorted_requests)
            if all_ingested and self.passengers and all(
                p.status == PassengerStatus.DELIVERED
                for p in self.passengers.values()
            ):
                logger.info(
                    "simulation.completed",
                    run_id=self.run_id,
                    total_ticks=self._current_tick,
                    passengers_served=len(self.passengers),
                )
                break

            self._current_tick += 1
        else:
            # Safety bound reached — log warning
            undelivered = [
                p.passenger_id for p in self.passengers.values()
                if p.status != PassengerStatus.DELIVERED
            ]
            logger.warning(
                "simulation.max_ticks_reached",
                run_id=self.run_id,
                max_ticks=max_ticks,
                undelivered_count=len(undelivered),
                undelivered_sample=undelivered[:5],
            )

        return SimulationResult(
            run_id=self.run_id,
            strategy_name=self.strategy.name,
            config=self.config,
            passengers=tuple(self.passengers.values()),
            position_log=tuple(self.position_log),
            events=tuple(self.events),
            total_ticks=self._current_tick,
        )

    # -------------------------------------------------------------------
    # Tick phases
    # -------------------------------------------------------------------

    def _phase_ingest(self, new_requests: list[PassengerRequest]) -> None:
        """Phase 1: Register new passenger requests arriving at this tick."""
        for req in new_requests:
            if req.passenger_id in self.passengers:
                logger.warning(
                    "simulation.duplicate_passenger",
                    run_id=self.run_id,
                    tick=self._current_tick,
                    passenger_id=req.passenger_id,
                )
                continue

            passenger = Passenger(request=req)
            self.passengers[req.passenger_id] = passenger

            self.events.append(PassengerRequested(
                tick=self._current_tick,
                passenger_id=req.passenger_id,
                source=req.source,
                dest=req.dest,
            ))

            logger.debug(
                "passenger.requested",
                run_id=self.run_id,
                tick=self._current_tick,
                passenger_id=req.passenger_id,
                source=req.source,
                dest=req.dest,
            )

    def _phase_dispatch(self) -> None:
        """Phase 2: Assign unassigned passengers to elevators via strategy."""
        unassigned = [
            p for p in self.passengers.values()
            if p.status == PassengerStatus.WAITING
        ]

        for passenger in unassigned:
            # Filter elevators by service policy eligibility
            eligible_snapshots = [
                e.snapshot() for e in self.elevators
                if e.service_policy.can_serve_request(passenger.request)
            ]

            if not eligible_snapshots:
                logger.warning(
                    "dispatch.no_eligible_elevators",
                    run_id=self.run_id,
                    tick=self._current_tick,
                    passenger_id=passenger.passenger_id,
                )
                continue

            try:
                elevator_id = self.strategy.select_elevator(
                    passenger.request,
                    eligible_snapshots,
                    self.config,
                )
            except DispatchError:
                logger.warning(
                    "dispatch.strategy_failed",
                    run_id=self.run_id,
                    tick=self._current_tick,
                    passenger_id=passenger.passenger_id,
                )
                continue

            # Execute the assignment
            passenger.assign(elevator_id, self._current_tick)
            self.elevators[elevator_id].assigned_requests.append(passenger.request)

            self.events.append(PassengerAssigned(
                tick=self._current_tick,
                passenger_id=passenger.passenger_id,
                elevator_id=elevator_id,
            ))

            logger.debug(
                "passenger.assigned",
                run_id=self.run_id,
                tick=self._current_tick,
                passenger_id=passenger.passenger_id,
                elevator_id=elevator_id,
            )

        # Invariant check after all dispatches
        no_double_assignment(list(self.passengers.values()))

    def _phase_dropoff(self) -> None:
        """Phase 3: Unload passengers at their destination floors.

        Runs before pickup (ADR-005) to free capacity.
        """
        for elevator in self.elevators:
            delivered = elevator.dropoff(self._current_tick)
            for p in delivered:
                self.events.append(PassengerDelivered(
                    tick=self._current_tick,
                    passenger_id=p.passenger_id,
                    elevator_id=elevator.id,
                    floor=elevator.current_floor,
                ))
                logger.debug(
                    "passenger.delivered",
                    run_id=self.run_id,
                    tick=self._current_tick,
                    passenger_id=p.passenger_id,
                    elevator_id=elevator.id,
                    floor=elevator.current_floor,
                )

            # Invariant: capacity should only decrease after dropoff
            capacity_respected(elevator)

    def _phase_pickup(self) -> None:
        """Phase 4: Load assigned passengers waiting at elevator's current floor."""
        for elevator in self.elevators:
            # Find passengers assigned to this elevator waiting at this floor
            waiting_here = [
                self.passengers[req.passenger_id]
                for req in elevator.assigned_requests
                if req.source == elevator.current_floor
                and self.passengers[req.passenger_id].status == PassengerStatus.ASSIGNED
            ]

            if not waiting_here:
                continue

            picked_up = elevator.pickup(waiting_here, self._current_tick)

            for p in picked_up:
                self.events.append(PassengerPickedUp(
                    tick=self._current_tick,
                    passenger_id=p.passenger_id,
                    elevator_id=elevator.id,
                    floor=elevator.current_floor,
                ))
                logger.debug(
                    "passenger.picked_up",
                    run_id=self.run_id,
                    tick=self._current_tick,
                    passenger_id=p.passenger_id,
                    elevator_id=elevator.id,
                    floor=elevator.current_floor,
                )

            # Invariant: capacity must be respected after loading
            capacity_respected(elevator)
            service_policy_respected(elevator)

    def _phase_move(self) -> None:
        """Phase 5: Each elevator moves one floor toward its next target."""
        for elevator in self.elevators:
            old_floor = elevator.current_floor
            old_direction = elevator.direction

            new_floor = elevator.move()

            if new_floor is not None and new_floor != old_floor:
                self.events.append(ElevatorMoved(
                    tick=self._current_tick,
                    elevator_id=elevator.id,
                    from_floor=old_floor,
                    to_floor=new_floor,
                ))

            if elevator.direction != old_direction:
                self.events.append(ElevatorDirectionChanged(
                    tick=self._current_tick,
                    elevator_id=elevator.id,
                    old_direction=old_direction,
                    new_direction=elevator.direction,
                ))

    def _record_positions(self) -> None:
        """Phase 6: Snapshot elevator positions for the position log."""
        snapshot = {
            "tick": self._current_tick,
            "positions": [e.current_floor for e in self.elevators],
        }
        self.position_log.append(snapshot)
