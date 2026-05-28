# Elevator Dispatch Simulator

A discrete-time elevator simulation engine that models passenger dispatch
strategies across configurable building configurations. Built as a domain
modeling exercise emphasizing architectural judgment, testable invariants,
and trade-off articulation.

## What It Does

Given a CSV of passenger requests (time, id, source floor, destination floor),
the simulator runs a tick-based simulation with configurable:

- **Number of elevators** and **floors**
- **Elevator capacity**
- **Dispatch strategy** (nearest-car, round-robin, zone-based)
- **Service policies** (express elevators that skip floors)

It produces:

- Per-passenger statistics (wait time, travel time, total time)
- A position log tracking every elevator at every tick
- Multi-strategy comparison with fairness-vs-efficiency analysis
- Optional visualization charts

## Quick Start

```bash
# Clone and install
git clone <repo-url> && cd elevatorSim
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run with sample data
elevator-sim run tests/fixtures/sample_requests.csv

# Compare all strategies
elevator-sim compare tests/fixtures/sample_requests.csv

# Generate charts (requires matplotlib)
pip install -e ".[viz]"
elevator-sim visualize tests/fixtures/sample_requests.csv
```

### Docker

```bash
docker build -t elevator-sim .
docker run --rm -v $(pwd)/tests/fixtures:/data elevator-sim run /data/sample_requests.csv
```

## Input Format

CSV with header row:

```csv
time,id,source,dest
0,p1,1,10
0,p2,5,1
15,p3,20,1
```

- `time`: Non-negative integer tick when the request arrives
- `id`: Unique passenger identifier
- `source`, `dest`: Floor numbers (1-indexed, must differ)

## Configuration

Via environment variables (prefix `ELEVATOR_SIM_`) or CLI flags:

| Env Var | CLI Flag | Default | Description |
|---------|----------|---------|-------------|
| `ELEVATOR_SIM_NUM_ELEVATORS` | `--elevators` | 6 | Number of elevators |
| `ELEVATOR_SIM_NUM_FLOORS` | `--floors` | 50 | Number of floors |
| `ELEVATOR_SIM_MAX_CAPACITY` | `--capacity` | 10 | Max passengers per elevator |
| `ELEVATOR_SIM_STRATEGY` | `--strategy` | nearest_car | Dispatch algorithm |
| `ELEVATOR_SIM_LOG_LEVEL` | `--log-level` | INFO | Logging verbosity |
| `ELEVATOR_SIM_LOG_FORMAT` | `--log-format` | json | Log format (json/console) |

See `.env.example` for a template.

## Testing

```bash
# Run all tests (57 tests)
pytest

# With coverage
pytest --cov=elevator_sim --cov-report=term-missing

# Property-based tests only (Hypothesis)
pytest tests/unit/domain/test_invariants.py -v

# Integration test only
pytest tests/integration/ -v
```

### Test Architecture

Tests are organized into three layers matching the testing strategy (ADR-009):

- **Unit tests** (`tests/unit/domain/`): Elevator FSM transitions, passenger
  lifecycle, dispatch strategy scoring, service policy validation.
- **Property-based tests** (`tests/unit/domain/test_invariants.py`): Hypothesis-driven
  verification of formal properties — safety (no capacity overflow, no double
  assignment), liveness (all passengers delivered), fairness (bounded wait disparity).
- **Integration tests** (`tests/integration/`): Full pipeline from CSV parsing
  through simulation to output verification, with hand-traced expected values.

## Dispatch Strategies

| Strategy | Optimizes For | Trade-off |
|----------|--------------|-----------|
| **nearest_car** | Efficiency (lowest avg total time) | May starve outlier passengers |
| **round_robin** | Even distribution across elevators | Ignores proximity and direction |
| **zone_based** | Locality (floors partitioned into zones) | Falls back to nearest-car cross-zone |

The `compare` command runs the same input through all strategies and reports
which is most efficient vs. most fair.

## How to Extend

**Add a new dispatch strategy:**

1. Create a class implementing the `DispatchStrategy` Protocol in `domain/strategies.py`
2. Register it in `STRATEGY_REGISTRY`
3. It's immediately available via CLI `--strategy your_name`

The Protocol requires a single method:

```python
def select_elevator(
    self,
    request: PassengerRequest,
    elevators: Sequence[ElevatorSnapshot],
    config: SimulationConfig,
) -> int:  # elevator id
```

**Add express elevator configurations:**

Pass `ServicePolicy` instances to `engine.initialize(service_policies=[...])`.
A `ServicePolicy` is a frozen set of floors the elevator serves.

## Project Structure

```
src/elevator_sim/
  domain/          Pure business logic, no I/O
    model.py         Elevator FSM, Passenger lifecycle, value objects
    strategies.py    Dispatch algorithm implementations
    invariants.py    Safety/liveness/fairness checks
    events.py        Domain event definitions
  engine/          Simulation orchestration
    simulation.py    Tick loop with six ordered phases
    clock.py         Phase ordering enum
    runner.py        Multi-strategy comparison runner
  analytics/       Pure computation over results
    statistics.py    TimeStats aggregation
    comparison.py    Strategy ranking and observations
    visualization.py Chart generation (matplotlib)
  infrastructure/  I/O adapters
    csv_parser.py    Pydantic-validated CSV ingestion
    output_writer.py Position log and statistics output
    logging.py       structlog configuration
  cli/             Delivery mechanism
    commands.py      Click-based CLI (run, compare, visualize)
  config.py        Pydantic Settings for typed env-var config
```

See `docs/ARCHITECTURE.md` for the full system overview and
`docs/ADR/` for every architectural decision with rationale.

## Deliberately Out of Scope

These were considered and explicitly excluded for the take-home:

- **Persistence** (ADR-007): No state survives across runs. SQLite/Postgres
  would add schema and ORM ceremony for zero functional benefit.
- **CQRS / Event Sourcing** (ADR-003): Read/write models don't diverge.
  Deterministic replay is free. ADR documents when these would be justified.
- **Async I/O** (ADR-006): Simulation is inherently sequential. No I/O to overlap.
- **Real-time / WebSocket interface**: Would require async, adds no architectural signal.
- **Door dwell time / acceleration modeling**: Noted as future enhancement.
  Current model: instantaneous load/unload, one floor per tick.

Each rejection is documented in an ADR with the conditions under which the
pattern would be appropriate.
