# Architecture Overview

## System Purpose

A discrete-time elevator dispatch simulator that models passenger requests,
elevator movement, and dispatch strategies to evaluate efficiency and fairness
trade-offs. The system is a CLI tool: CSV in, statistics and position logs out.

## C4 Context

```
┌──────────────────────────────────────────────────────────┐
│                       User (CLI)                         │
│                                                          │
│   elevator-sim run input.csv --strategy nearest_car      │
│   elevator-sim compare input.csv                         │
└──────────────────┬───────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│                  Elevator Simulator                       │
│                                                          │
│   Reads CSV → Runs tick-based simulation → Writes output │
│                                                          │
│   Input:  CSV file (time, id, source, dest)              │
│   Output: Position log (CSV), Statistics (text),         │
│           Comparison report, Charts (PNG)                 │
└──────────────────────────────────────────────────────────┘
```

No external services, no databases, no network calls. Single-process,
single-threaded, deterministic.

## C4 Container (Component Diagram)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         elevator-sim CLI                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │   CLI    │───▶│    Engine    │───▶│       Domain             │  │
│  │ (click)  │    │  (tick loop) │    │                          │  │
│  │          │    │              │    │  model.py    (FSM, VOs)  │  │
│  │ commands │    │ simulation   │    │  strategies  (dispatch)  │  │
│  │          │    │ runner       │    │  invariants  (safety)    │  │
│  │          │    │ clock        │    │  events      (tracking)  │  │
│  └──────────┘    └──────┬───────┘    └──────────────────────────┘  │
│       │                 │                                           │
│       │          ┌──────┴───────┐    ┌──────────────────────────┐  │
│       │          │  Analytics   │    │    Infrastructure        │  │
│       └─────────▶│              │    │                          │  │
│                  │ statistics   │    │  csv_parser   (input)    │  │
│                  │ comparison   │    │  output_writer (output)  │  │
│                  │ visualization│    │  logging      (structlog)│  │
│                  └──────────────┘    └──────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Dependency Rule

Arrows point inward. The domain layer has zero external imports — it is
pure Python with dataclasses and typing only. The engine depends on domain.
Infrastructure and CLI depend on engine and domain. Analytics depends on
domain types only.

```
cli/ ──▶ engine/ ──▶ domain/     (pure, no I/O)
  │        │
  ├──▶ infrastructure/           (I/O adapters)
  └──▶ analytics/                (pure computation)
```

This is hexagonal architecture (ADR-002) without the ceremony of explicit
Port interfaces — the domain's Protocol and dataclass contracts serve as
the ports.

## Data Flow

```
CSV File
  │
  ▼
csv_parser.parse_csv()          Pydantic validation, sorted by time
  │
  │  list[PassengerRequest]
  ▼
SimulationEngine.run()          Tick loop (see below)
  │
  │  SimulationResult
  ├──▶ write_position_log()     CSV: tick, elevator positions
  ├──▶ write_statistics()       Text: min/max/avg/median/P95/StdDev
  └──▶ analyze_comparison()     Rankings, observations (compare mode)
         │
         └──▶ generate_charts() PNG: box plots, scatter, bars (visualize mode)
```

## Tick Loop (Simulation Engine)

Each tick executes six phases in strict order (ADR-005). The ordering is
load-bearing: dropoff before pickup frees capacity; dispatch before dropoff
ensures assignments exist.

```
┌─────────────────────────────────────────────────────────┐
│                     One Tick (t = N)                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Phase 1: INGEST                                        │
│    Collect requests where request_time == N              │
│    Create Passenger entities (status: WAITING)           │
│                                                         │
│  Phase 2: DISPATCH                                      │
│    For each WAITING passenger:                           │
│      Strategy selects elevator → passenger ASSIGNED      │
│    Invariant check: no double assignment                 │
│                                                         │
│  Phase 3: DROPOFF                                       │
│    For each elevator at a passenger's destination:       │
│      Unload → passenger DELIVERED                        │
│    Invariant check: capacity respected                   │
│                                                         │
│  Phase 4: PICKUP                                        │
│    For each elevator at an assigned passenger's source:  │
│      Load (up to capacity) → passenger RIDING            │
│    Invariant checks: capacity, service policy            │
│                                                         │
│  Phase 5: MOVE                                          │
│    Each elevator moves one floor toward next target      │
│    SCAN algorithm: continue direction, reverse at end    │
│                                                         │
│  Phase 6: RECORD                                        │
│    Snapshot all elevator positions for position log      │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Termination: all requests ingested AND all delivered    │
│  Safety bound: max_request_time + num_floors * 4        │
└─────────────────────────────────────────────────────────┘
```

## Domain Model

### Passenger Lifecycle (State Machine)

```
  WAITING ──assign()──▶ ASSIGNED ──pick_up()──▶ RIDING ──deliver()──▶ DELIVERED
```

Each transition is guarded by status checks and emits timing data.
Invalid transitions raise `InvalidStateTransition`.

### Elevator FSM

```
                   ┌──────────┐
          ┌────────│   IDLE   │────────┐
          │        └──────────┘        │
     has target  ▲  no targets  ▲  has target
     going UP    │              │  going DOWN
          │      │              │       │
          ▼      │              │       ▼
    ┌──────────┐ │              │ ┌──────────┐
    │    UP    │─┘   reversal   └─│   DOWN   │
    │          │◀────────────────▶│          │
    └──────────┘                  └──────────┘
```

Movement follows SCAN (elevator algorithm): continue in current direction
until no more targets, then reverse. Targets include both assigned pickup
floors and onboard passenger destinations.

### Key Value Objects

| Type | Purpose | Immutable? |
|------|---------|------------|
| `PassengerRequest` | Input record (time, id, source, dest) | Yes (frozen) |
| `ServicePolicy` | Set of floors an elevator serves | Yes (frozen) |
| `ElevatorSnapshot` | Read-only view for strategy decisions | Yes (frozen) |
| `SimulationConfig` | Building parameters (floors, elevators, capacity) | Yes (frozen) |

### Strategy Protocol

```python
class DispatchStrategy(Protocol):
    @property
    def name(self) -> str: ...

    def select_elevator(
        self,
        request: PassengerRequest,
        elevators: Sequence[ElevatorSnapshot],
        config: SimulationConfig,
    ) -> int: ...
```

Strategies receive read-only snapshots, not mutable elevators. This
prevents strategies from mutating state — a deliberate boundary
(ADR-004).

## Invariants (Formal Properties)

Mapped from formal verification vocabulary (the author's SMV model-checking
background) to runtime assertions:

| Property | Category | Enforcement |
|----------|----------|-------------|
| Passenger count <= capacity | Safety (AG ~overflow) | Checked after every pickup/dropoff |
| Elevator stays within service policy | Safety (AG policy_respected) | Checked after every pickup |
| No passenger assigned to two elevators | Safety (AG ~double_assign) | Checked after every dispatch |
| Every request eventually served | Liveness (AG(req -> AF delivered)) | Verified at simulation end |
| Wait time bounded | Fairness | Analyzed post-simulation |

Property-based tests (Hypothesis) verify these hold across randomized
inputs, complementing the hand-traced integration test.

## Patterns Applied

| Pattern | Where | Why |
|---------|-------|-----|
| Strategy | `domain/strategies.py` | Pluggable dispatch without conditionals |
| Protocol (structural subtyping) | `DispatchStrategy` | Decouples strategy from engine without ABC |
| Value Object | `PassengerRequest`, `ServicePolicy`, `ElevatorSnapshot` | Immutable, equality by value |
| Entity | `Passenger`, `Elevator` | Identity matters, mutable lifecycle |
| Domain Event | `events.py` | Decoupled tracking without observer coupling |
| Hexagonal Architecture | Project layout | Domain purity, testability |
| SCAN Algorithm | `Elevator.move()` | Industry-standard elevator scheduling |

## Patterns Considered and Rejected

| Pattern | ADR | Why Rejected |
|---------|-----|--------------|
| CQRS | ADR-003 | Read/write models don't diverge |
| Event Sourcing | ADR-003 | Deterministic replay is free; no audit requirement |
| Repository | ADR-002 | Would just wrap csv.reader; no abstraction value |
| Async I/O | ADR-006 | Simulation is sequential; no I/O to overlap |
| Persistence | ADR-007 | No state survives across runs |
| Saga / Outbox | N/A | No distributed transactions; single process |

Each rejection ADR documents the conditions under which the pattern
would become justified.

## Error Handling

Custom exception hierarchy rooted in `SimulationError`:

```
SimulationError
  ├── InvalidStateTransition   (passenger lifecycle violation)
  ├── CapacityViolationError   (elevator overloaded)
  ├── DispatchError            (strategy cannot assign)
  ├── InvalidRequestError      (bad input data)
  └── ServicePolicyViolationError  (floor not served)
```

Exceptions are raised at domain boundaries. The engine catches
`DispatchError` to log and continue (a single unassignable request
should not crash the simulation). All others propagate — they indicate
invariant violations that should never occur.

## Cross-Cutting Concerns

- **Structured logging**: structlog with JSON output, contextual fields
  (run_id, tick, elevator_id, passenger_id) for correlation.
- **Typed configuration**: Pydantic Settings with `ELEVATOR_SIM_` prefix,
  validated at startup.
- **Determinism**: Same input + same config + same strategy = identical output.
  No randomness, no timestamps in logic, no floating-point in simulation.
