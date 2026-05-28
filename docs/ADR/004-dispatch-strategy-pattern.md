# ADR-004: Dispatch Strategy as Pluggable Port

## Status
Accepted

## Context
The brief requires a "scheduler algorithm of your choice" and the bonus section asks for multiple algorithms (round robin, nearest car, zone-based) and fairness-vs-efficiency comparison. The dispatch decision — which elevator serves a new request — is the core algorithmic concern.

## Decision
Model the dispatch algorithm as a **Strategy pattern** behind a Python `Protocol`:

```python
class DispatchStrategy(Protocol):
    def select_elevator(
        self,
        request: PassengerRequest,
        elevators: Sequence[Elevator],
        pending_requests: Sequence[PassengerRequest],
    ) -> ElevatorId: ...
```

This is a **port** in hexagonal terms — the domain defines the contract, implementations are pluggable. The engine calls `strategy.select_elevator()` during the dispatch micro-step of each tick.

### Implementations planned
1. **NearestCar** — Score each eligible elevator by distance to pickup floor, weighted by direction alignment and current load. Industry-standard baseline for destination dispatch.
2. **RoundRobin** — Assign requests cyclically. Fairness baseline — no optimization, but guarantees even load distribution. Useful as a control for comparison.
3. **ZoneBased** — Partition floors into zones, assign each zone to a subset of elevators. Models real-world express/local elevator banks. Interacts with ServicePolicy (express elevators).

### Why Protocol, not ABC
A Protocol is structural subtyping — any object with the right method signature satisfies it. This avoids inheritance coupling. Strategy implementations don't need to `import` or `extend` a base class. They just implement the method. This is cleaner for testing (plain objects or lambdas as test doubles) and for extension (add a strategy in a new file, register it by name, done).

### Strategy selection at runtime
Strategies are registered in a dictionary keyed by name. The CLI accepts a strategy name (or "all" for comparison mode). No reflection, no classpath scanning, no plugin framework — a dict literal is sufficient for 3-5 strategies.

### What the strategy receives
The strategy gets a **snapshot** of system state: immutable view of all elevators (position, direction, current passengers, capacity remaining, service policy) and pending requests. It cannot mutate state — it returns an elevator ID, and the engine executes the assignment. This enforces the boundary: strategy is a pure decision function, engine owns the mutation.

## Consequences
- Adding a new strategy is a single file + one dict entry. No engine changes.
- Multi-strategy comparison is trivial: run same input through each strategy, collect results.
- Strategies are independently testable: given this state snapshot, assert this assignment.
- Trade-off: each strategy sees global state (all elevators). At 2,000 elevators this is a scalability concern — would need spatial indexing. Acceptable at our scale (up to 20 elevators). Noted in ADR-003's production section.
