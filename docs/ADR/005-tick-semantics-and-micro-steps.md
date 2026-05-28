# ADR-005: Tick Semantics and Micro-Step Ordering

## Status
Accepted

## Context
The brief specifies discrete time: "one time unit = one floor of travel" and "your simulation must tick forward one time unit at a time." Within a single tick, multiple operations occur: new requests arrive, dispatch decisions are made, passengers board and exit, elevators move. The ordering of these operations within a tick affects correctness.

This is a well-studied problem in formal verification. In model checking (e.g., SMV), a macro-step decomposes into a sequence of atomic micro-steps with defined ordering to resolve nondeterminism. We apply the same discipline here.

## Decision

Each tick N executes the following phases in strict order:

```
TICK N:
  Phase 1 — INGEST    : Collect all requests with time == N
  Phase 2 — DISPATCH   : Assign new requests to elevators via strategy
  Phase 3 — DROPOFF    : Elevators at a floor unload passengers whose dest == current floor
  Phase 4 — PICKUP     : Elevators at a floor load assigned passengers whose source == current floor
  Phase 5 — MOVE       : Each non-idle elevator moves one floor toward its next target
  Phase 6 — RECORD     : Snapshot elevator positions, emit domain events, update statistics
```

### Why this ordering

**Ingest before dispatch:** The strategy needs to see all requests arriving at this tick, not a partial view. Batch arrival is the correct model — in the real world, the destination dispatch panel collects requests between elevator arrivals and dispatches them together.

**Dispatch before dropoff/pickup:** Newly arriving passengers need elevator assignments before the movement phase. If we dispatched after movement, passengers arriving at tick N would wait an extra tick — their assignment wouldn't take effect until tick N+1's pickup phase.

**Dropoff before pickup:** This is the critical ordering decision. Dropping off passengers first **frees capacity** before loading new ones. Without this ordering, an elevator at capacity would reject pickups even though it's about to unload at this floor. This matches real elevator behavior (people exit before others enter) and avoids false capacity violations.

**Pickup before move:** Passengers waiting at the elevator's current floor board before it departs. An elevator that arrives at a pickup floor loads passengers in the same tick it arrives — no extra tick penalty for boarding. This is consistent with the brief's "one time unit = one floor of travel" — the time cost is movement, not loading.

**Move last:** After all loading/unloading is complete, elevators advance one floor. This ensures the position log at phase 6 reflects the post-movement state.

**Record last:** Captures the end-of-tick state, after all transitions are complete.

### Loading/unloading cost
**Zero ticks.** Loading and unloading are instantaneous when the elevator is at the correct floor. The one-tick cost is exclusively movement (one floor per tick). This was confirmed as the intended model during requirements clarification.

### Formal properties preserved by this ordering
- **Safety — no capacity overflow:** Dropoff before pickup ensures capacity is freed before loading. The pickup phase checks `len(elevator.passengers) < elevator.capacity` after dropoffs.
- **Safety — no lost passengers:** Every assigned passenger is either waiting (pre-pickup), riding (post-pickup, pre-dropoff), or delivered (post-dropoff). No state transition skips a phase.
- **Determinism:** Same input + same tick ordering + same strategy = identical output. The micro-step sequence eliminates nondeterminism within a tick.

## Consequences
- Tick ordering is codified in `engine/clock.py` as named phases, not implicit code order.
- Each phase is independently testable.
- The ordering is documented here and in ARCHITECTURE.md's formal properties section.
- Trade-off: zero-cost loading is a simplification. Real elevators have door dwell time. Noted as a would-extend item. Adding dwell time would mean elevators spend K ticks at a floor when loading/unloading — this is a straightforward extension that doesn't change the micro-step ordering, just inserts a DWELLING state in the FSM.
