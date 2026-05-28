# ADR-003: CQRS and Event Sourcing — Considered and Rejected (for this scope)

## Status
Accepted (rejected for take-home scope; recommended for production)

## Context
Event Sourcing and CQRS are natural candidates for a system with rich state transitions (elevator movements, passenger lifecycle events) and reporting requirements (statistics, position logs). We evaluated both patterns against two scenarios: the 4-day take-home scope and a hypothetical production deployment.

## Decision — Take-Home Scope
**Rejected.** Neither pattern earns its complexity at this scale.

### Why CQRS doesn't fit here
CQRS is justified when read and write models genuinely diverge: different shapes, different scaling needs, different consistency boundaries. In our simulation:
- The "write model" is the simulation state (elevator positions, passenger assignments).
- The "read model" is statistics (min/max/avg wait times, position logs).
- The statistics are a **trivial fold** over passenger lifecycle data — not an independent model with its own schema, its own update path, or its own scaling concerns.
- There is one writer (the tick loop) and one reader (the statistics computation, after the simulation ends).
- No concurrent read/write access. No eventual consistency concerns.

Adding CQRS here would mean: separate command handlers, separate query handlers, a projection mechanism — all for a system where a single `for` loop over passengers computes the same result. The pattern doesn't earn the indirection.

### Why Event Sourcing doesn't fit here
Event Sourcing provides: replay from event log, temporal queries, audit trail. In our simulation:
- **Replay** is free without ES — the simulation is deterministic. Same CSV + same config + same strategy = identical output. `python -m elevator_sim run input.csv` *is* replay.
- **Temporal queries** ("what was the state at tick 47?") are served by the position log output, which we produce anyway.
- **Audit trail** — there's no compliance requirement on a simulation.

The overhead of an event store, event-to-state rebuild, and projection infrastructure would consume ~1 day of the 4-day window for zero functional benefit.

## Decision — Production Scenario (2,000 elevators, 10,000 floors)
**Recommended.** Both patterns earn their place at production scale.

### Why CQRS earns its place in production
At 2,000 elevators, read and write models genuinely diverge:
- **Write path**: dispatch decisions and state transitions. Must be fast, serialized per-elevator partition. Consistency boundary = single elevator aggregate.
- **Read path**: fleet-wide monitoring dashboards, passenger status queries, analytics aggregations. Must aggregate across thousands of elevators. Different consistency needs (eventual is fine), different scaling profile (many concurrent readers).
- Independent scaling: write path scales by elevator partition, read path scales by adding read replicas / projection workers.

### Why Event Sourcing earns its place in production
- **Debugging**: "Why did elevator 1,847 go to floor 9,000 instead of floor 3?" — replay the event stream for that elevator. Without ES, you're reading logs and inferring causality.
- **Temporal queries**: "What was the fleet state at 14:32 when the fire alarm triggered?" — project events up to that timestamp.
- **Integration backbone**: The event stream feeds downstream systems (building management, security, fire safety, mobile apps) via projections.
- **Audit/compliance**: Commercial buildings may require audit trails for elevator operations.
- **New read models are additive**: A new monitoring dashboard = a new projection over existing events. No schema migration, no write-path changes.

### Production architecture sketch
```
Requests → Command Bus → Elevator Aggregates (partitioned by elevator ID)
                              ↓ (domain events)
                         Event Store
                              ↓ (projections)
               ┌──────────────┼──────────────┐
          Fleet Dashboard   Passenger Status   Analytics
          (CQRS read model)  (CQRS read model)  (batch)
```

### What the take-home domain model preserves
The domain layer (Elevator FSM, Passenger lifecycle, DispatchStrategy protocol, invariant checks) is the **same code** that would live inside the Elevator aggregate in the production architecture. The simulation engine gets replaced by the event-sourced aggregate host. The take-home is the kernel; production wraps it in infrastructure.

## Consequences
- Take-home: no event store overhead, no CQRS ceremony. Simpler, faster to build, honest about scope.
- Production: clear migration path. Domain survives. Infrastructure changes.
- Panel talking point: demonstrates ability to evaluate patterns against context rather than applying them reflexively.
