"""End-to-end integration test: CSV input → simulation → verified output.

This test exercises the full pipeline: file parsing, engine execution,
statistics computation, and output generation. It uses a hand-traced
scenario with known-good expected values.

Hand-traced scenario (verified manually):
  - 1 elevator, 5 floors, capacity 2
  - 3 passengers with known expected outcomes

  Tick-by-tick trace:
    t=0:  Ingest p1(1→4), p2(1→3). Dispatch both to E0. Pickup both at floor 1.
          E0 moves 1→2. [E0 at floor 2, carrying p1,p2]
    t=1:  E0 moves 2→3. [E0 at floor 3]
    t=2:  Dropoff p2 at floor 3. E0 moves 3→4. [E0 at floor 4, carrying p1]
    t=3:  Dropoff p1 at floor 4. E0 now idle at floor 4. [E0 at floor 4, empty]
    t=4:  (nothing — p3 arrives at t=5)
    t=5:  Ingest p3(5→1). Dispatch to E0. E0 moves 4→5. [E0 at floor 5]
    t=6:  Pickup p3 at floor 5. E0 moves 5→4. [E0 at floor 4, carrying p3]
    t=7:  E0 moves 4→3. [E0 at floor 3]
    t=8:  E0 moves 3→2. [E0 at floor 2]
    t=9:  E0 moves 2→1. Dropoff p3. [E0 at floor 1, empty]

  Expected outcomes:
    p1: wait=0, travel=3, total=3  (floor 1→4, pickup t=0, deliver t=3)
    p2: wait=0, travel=2, total=2  (floor 1→3, pickup t=0, deliver t=2)
    p3: wait=1, travel=4, total=5  (floor 5→1, request t=5, pickup t=6, deliver t=10)

  Wait — let me retrace more carefully:
    t=0:  Ingest p1(1→4), p2(1→3). Dispatch both to E0.
          Dropoff: nobody. Pickup: p1,p2 at floor 1. Move: E0 1→2. Record.
    t=1:  Dropoff: nobody at floor 2. Move: E0 2→3. Record.
    t=2:  Dropoff: p2 at floor 3. Pickup: nobody. Move: E0 3→4. Record.
    t=3:  Dropoff: p1 at floor 4. E0 idle. Move: none. Record.
    ...idle ticks...
    t=5:  Ingest p3(5→1). Dispatch to E0. Pickup: nobody (E0 at 4, p3 at 5).
          Move: E0 4→5. Record.
    t=6:  Pickup: p3 at floor 5. Move: E0 5→4. Record.
    t=7:  E0 4→3.
    t=8:  E0 3→2.
    t=9:  E0 2→1. Dropoff p3. Record.

  Corrected outcomes:
    p1: pickup_t=0, deliver_t=3. wait=0, travel=3, total=3.
    p2: pickup_t=0, deliver_t=2. wait=0, travel=2, total=2.
    p3: request_t=5, pickup_t=6, deliver_t=10. wait=1, travel=4, total=5.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import structlog

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(50),
)

from elevator_sim.domain.model import PassengerStatus, ServicePolicy, SimulationConfig
from elevator_sim.domain.strategies import get_strategy
from elevator_sim.engine.simulation import SimulationEngine
from elevator_sim.infrastructure.csv_parser import parse_csv
from elevator_sim.infrastructure.output_writer import write_position_log, write_statistics


class TestEndToEnd:
    """Full pipeline: CSV → simulation → output → verification."""

    def test_hand_traced_scenario(self, tmp_path: Path) -> None:
        """Verify simulation matches hand-traced tick-by-tick execution."""
        # Write input CSV
        csv_content = "time,id,source,dest\n0,p1,1,4\n0,p2,1,3\n5,p3,5,1\n"
        input_file = tmp_path / "input.csv"
        input_file.write_text(csv_content)

        # Parse
        requests = parse_csv(input_file, num_floors=5)
        assert len(requests) == 3

        # Run simulation
        config = SimulationConfig(num_floors=5, num_elevators=1, max_capacity=2)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()
        result = engine.run(requests)

        # Verify all delivered
        assert all(p.status == PassengerStatus.DELIVERED for p in result.passengers)

        # Verify specific outcomes against hand-traced values
        passengers = {p.passenger_id: p for p in result.passengers}

        p1 = passengers["p1"]
        assert p1.wait_time == 0, f"p1 wait: expected 0, got {p1.wait_time}"
        assert p1.travel_time == 3, f"p1 travel: expected 3, got {p1.travel_time}"
        assert p1.total_time == 3, f"p1 total: expected 3, got {p1.total_time}"

        p2 = passengers["p2"]
        assert p2.wait_time == 0, f"p2 wait: expected 0, got {p2.wait_time}"
        assert p2.travel_time == 2, f"p2 travel: expected 2, got {p2.travel_time}"
        assert p2.total_time == 2, f"p2 total: expected 2, got {p2.total_time}"

        p3 = passengers["p3"]
        assert p3.wait_time == 1, f"p3 wait: expected 1, got {p3.wait_time}"
        assert p3.travel_time == 4, f"p3 travel: expected 4, got {p3.travel_time}"
        assert p3.total_time == 5, f"p3 total: expected 5, got {p3.total_time}"

    def test_output_files_generated(self, tmp_path: Path) -> None:
        """Verify position log and statistics files are written correctly."""
        csv_content = "time,id,source,dest\n0,p1,1,3\n"
        input_file = tmp_path / "input.csv"
        input_file.write_text(csv_content)

        requests = parse_csv(input_file, num_floors=5)
        config = SimulationConfig(num_floors=5, num_elevators=1, max_capacity=5)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()
        result = engine.run(requests)

        # Write outputs
        pos_path = tmp_path / "positions.csv"
        stats_path = tmp_path / "stats.txt"
        write_position_log(result, pos_path)
        write_statistics(result, stats_path)

        assert pos_path.exists()
        assert stats_path.exists()

        # Verify position log format
        pos_content = pos_path.read_text()
        lines = pos_content.strip().split("\n")
        assert lines[0] == "tick,elevator_0"  # Header
        assert len(lines) > 1  # At least header + one data row

        # Verify statistics contain expected sections
        stats_content = stats_path.read_text()
        assert "Wait Times" in stats_content
        assert "Travel Times" in stats_content
        assert "Total Times" in stats_content

    def test_csv_validation_rejects_bad_input(self, tmp_path: Path) -> None:
        """Verify that malformed CSV is rejected with clear errors."""
        csv_content = "time,id,source,dest\n0,p1,1,1\n"  # source == dest
        input_file = tmp_path / "bad.csv"
        input_file.write_text(csv_content)

        import pytest
        from elevator_sim.domain.model import InvalidRequestError

        with pytest.raises(InvalidRequestError, match="source == dest"):
            parse_csv(input_file, num_floors=5)

    def test_sample_fixture_file(self) -> None:
        """Verify the sample fixture file parses and runs successfully."""
        fixture = Path(__file__).parent.parent / "fixtures" / "sample_requests.csv"
        if not fixture.exists():
            import pytest
            pytest.skip("Sample fixture not found")

        requests = parse_csv(fixture, num_floors=50)
        assert len(requests) == 10

        config = SimulationConfig(num_floors=50, num_elevators=6, max_capacity=10)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize()
        result = engine.run(requests)

        assert all(p.status == PassengerStatus.DELIVERED for p in result.passengers)
        assert len(result.passengers) == 10

    def test_express_elevator_routing(self, tmp_path: Path) -> None:
        """Verify passengers are routed only to elevators that serve their floors.

        Setup: 4 elevators, 50 floors
          E0, E1: full-service (all floors)
          E2, E3: express (floor 1 + floors 30-50)

        Passengers requesting mid-floors (e.g., 10->20) must NOT be assigned
        to express elevators — those floors aren't in the express policy.
        Passengers requesting high floors (e.g., 1->40) CAN go to express.
        """
        csv_content = (
            "time,id,source,dest\n"
            "0,p_low,5,15\n"      # mid-floor: only E0/E1 eligible
            "0,p_high,1,40\n"     # high-floor: all 4 eligible
            "0,p_mid,10,20\n"     # mid-floor: only E0/E1 eligible
            "0,p_express,35,45\n" # express-only floors: all 4 eligible
            "5,p_cross,1,50\n"    # lobby to top: all 4 eligible
        )
        input_file = tmp_path / "express_test.csv"
        input_file.write_text(csv_content)

        requests = parse_csv(input_file, num_floors=50)

        full_service = ServicePolicy.full_service(50)
        express = ServicePolicy(
            served_floors=frozenset({1} | set(range(30, 51))),
            name="express-high",
        )
        policies = [full_service, full_service, express, express]

        config = SimulationConfig(num_floors=50, num_elevators=4, max_capacity=10)
        engine = SimulationEngine(config=config, strategy=get_strategy("nearest_car"))
        engine.initialize(service_policies=policies)
        result = engine.run(requests)

        # All passengers delivered
        assert all(p.status == PassengerStatus.DELIVERED for p in result.passengers)

        # Mid-floor passengers must be on full-service elevators (E0 or E1)
        passengers = {p.passenger_id: p for p in result.passengers}
        assert passengers["p_low"].assigned_elevator_id in (0, 1), \
            f"p_low assigned to express elevator {passengers['p_low'].assigned_elevator_id}"
        assert passengers["p_mid"].assigned_elevator_id in (0, 1), \
            f"p_mid assigned to express elevator {passengers['p_mid'].assigned_elevator_id}"
