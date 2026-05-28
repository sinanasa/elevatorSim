# ADR-008: Express Elevator Modeling via ServicePolicy

## Status
Accepted

## Context
The bonus section asks to "simulate express elevators that skip certain floors." This requires a mechanism to constrain which floors an elevator serves, and the dispatch strategy must respect those constraints.

## Decision
Model express behavior as a **ServicePolicy** value object attached to each Elevator:

```python
@dataclass(frozen=True)
class ServicePolicy:
    served_floors: frozenset[int]  # floors this elevator may stop at
    name: str                       # e.g., "express-high", "local", "full-service"
```

An elevator with a ServicePolicy can only:
- Pick up passengers whose source floor is in `served_floors`
- Drop off passengers whose dest floor is in `served_floors`
- Be assigned requests where both source AND dest are in `served_floors`

The dispatch strategy filters eligible elevators before scoring: only elevators whose ServicePolicy includes both the request's source and destination are candidates.

### Why a value object, not an Elevator subclass
Express vs. local is a **configuration concern**, not a type distinction. The Elevator FSM behavior is identical — move, load, unload. Only the set of legal floors differs. A subclass hierarchy (ExpressElevator, LocalElevator) would duplicate the FSM for a one-field difference. A value object attached to the entity is the correct DDD modeling.

### Common configurations
- **Full-service:** `served_floors = {1, 2, ..., n}` — serves all floors. Default.
- **Express high-rise:** `served_floors = {1, lobby_floor, sky_lobby, top_floors...}` — serves ground, sky lobby, and upper floors only.
- **Zone-local:** `served_floors = {low..mid}` or `{mid..high}` — serves a contiguous zone.
- **Odd/even:** `served_floors = {1, 3, 5, ...}` — skip-stop service.

These are configured at simulation setup, not hardcoded.

### Interaction with ZoneBased strategy
The ZoneBased dispatch strategy naturally composes with ServicePolicy: it assigns requests to elevators serving the request's zone. ServicePolicy is the enforcement mechanism; ZoneBased is the dispatch intelligence. They're complementary but independent — ServicePolicy is an invariant check (safety property), ZoneBased is an optimization heuristic.

## Consequences
- Express behavior is configured, not coded. New service patterns require no code changes.
- Invariant: "elevator never stops at a floor outside its service policy" — testable as a safety property via Hypothesis.
- Dispatch strategies must filter by ServicePolicy. This is a precondition, not strategy-specific logic — enforced in the engine before the strategy is called.
- Trade-off: ServicePolicy uses a set of floors, not a predicate function. At 10,000 floors, a set of 10,000 ints is ~80KB — negligible. A predicate (`lambda floor: floor % 2 == 1`) would be more compact but harder to serialize, validate, and test. Set is the right choice at this scale.
