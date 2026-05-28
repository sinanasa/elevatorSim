"""Tests for tick phase ordering."""

from elevator_sim.engine.clock import PHASE_ORDER, TickPhase


class TestTickPhaseOrdering:
    def test_phases_in_correct_order(self) -> None:
        """Verify the canonical micro-step ordering from ADR-005."""
        expected = [
            TickPhase.INGEST,
            TickPhase.DISPATCH,
            TickPhase.DROPOFF,
            TickPhase.PICKUP,
            TickPhase.MOVE,
            TickPhase.RECORD,
        ]
        assert list(PHASE_ORDER) == expected

    def test_dropoff_before_pickup(self) -> None:
        """Critical ordering: dropoff frees capacity before pickup."""
        phases = list(PHASE_ORDER)
        assert phases.index(TickPhase.DROPOFF) < phases.index(TickPhase.PICKUP)

    def test_dispatch_before_dropoff(self) -> None:
        """Dispatch assigns before any physical actions."""
        phases = list(PHASE_ORDER)
        assert phases.index(TickPhase.DISPATCH) < phases.index(TickPhase.DROPOFF)

    def test_move_after_pickup(self) -> None:
        """Passengers board before elevator departs."""
        phases = list(PHASE_ORDER)
        assert phases.index(TickPhase.PICKUP) < phases.index(TickPhase.MOVE)
