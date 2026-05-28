# ADR-006: Async I/O — Considered and Rejected

## Status
Accepted

## Context
Python's asyncio could be used for the simulation loop or for I/O operations (file reading/writing). We evaluated whether async provides any benefit.

## Decision
Rejected. The simulation is inherently sequential: tick N must complete before tick N+1 begins. There is no I/O to overlap — CSV input is read once at startup, output is written once at completion. The tick loop is CPU-bound computation over in-memory data structures.

Adding async would mean: `async def` on every method in the call chain, `await` at every call site, an event loop to manage — all for a program that never actually suspends. The cognitive overhead is real; the throughput benefit is zero.

### When async would be justified
If the simulation needed to accept real-time requests (WebSocket from a building management system), serve concurrent API queries during a run, or stream results to an external sink, async would earn its place. These are production concerns (see ADR-003), not take-home scope.

## Consequences
- Simpler code: no async/await ceremony.
- Simpler testing: no event loop management in tests.
- No concurrent I/O capability — accepted, as none is needed.
