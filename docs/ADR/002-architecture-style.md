# ADR-002: Architecture Style — Pure Domain Model with Strategy Pattern

## Status
Accepted

## Context
We evaluated three architectures:

**A. Pure Domain Model + Strategy (CLI-driven)** — Single-process simulation. Domain core (Elevator FSM, Passenger lifecycle, dispatch strategies) is pure and I/O-free. Engine layer orchestrates the tick loop. CLI is the delivery mechanism.

**B. Event-Sourced Simulation with CQRS** — Each tick emits domain events. State rebuilt from event stream. Read-side projections compute statistics.

**C. Layered Service (FastAPI + Postgres)** — Full API, persistent storage, async simulation execution.

## Decision
Architecture A. The brief is a domain modeling and algorithm design problem. The complexity budget belongs in the domain — dispatch strategies, elevator FSM, simulation correctness, statistical analysis — not in infrastructure.

### Why not B (Event Sourcing / CQRS)?
See ADR-003 for full analysis. In short: the read/write model divergence that justifies CQRS does not exist at this scale. The simulation is deterministic and sequential. Statistics are a trivial fold over passenger lifecycle data, not an independent read model. Event sourcing provides replay, but the simulation is already replayable — same input + same config = identical output.

### Why not C (Layered Service)?
The API and persistence layers would be theater. No consumer exists for the API. No state needs to persist across runs. The interesting work (domain model, strategies, analysis) would get less time. The panel would rightly question the judgment of wrapping a batch simulation in a SaaS architecture.

### Hexagonal structure
```
cli/ ──→ engine/ ──→ domain/     (dependency direction: outside → inside)
              ↑
infrastructure/  analytics/
```

- **domain/** — Innermost ring. Pure. No I/O, no external imports. Entities (Elevator), value objects (Passenger, ServicePolicy), FSM states, Strategy protocol, invariant checks.
- **engine/** — Application layer. Orchestrates domain objects through the tick loop. Knows about time, sequencing, micro-steps. Does not contain business rules.
- **analytics/** — Pure computation over simulation results. No I/O coupling. Takes data, returns statistics.
- **infrastructure/** — Outer ring. CSV parsing, file output, logging setup. Adapts external formats to/from domain contracts.
- **cli/** — Delivery mechanism. Thin wiring shell. Replaceable.

### No Repository pattern
A Repository here would just wrap `csv.reader` and return domain objects — a forwarding layer with no abstraction value. The CSV parser in infrastructure/ is already an adapter in hexagonal terms. Naming it "Repository" would be ceremony without behavior.

## Consequences
- 100% of complexity budget on domain and algorithms.
- Full testability: domain is pure functions, engine is deterministic.
- No framework lock-in. No infrastructure coupling.
- If productionized (see ADR-003), domain layer survives unchanged. Engine gets replaced by event-sourced aggregate host. Infrastructure adapters swap for real I/O.
- Trade-off: no API, no persistence, no live interaction. Accepted — the brief doesn't require them.
