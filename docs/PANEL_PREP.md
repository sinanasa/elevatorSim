# Panel Preparation — Talking Points & Defense Material

This document consolidates every architectural justification, rejected alternative,
and anticipated panel question. Organized by topic for rehearsal.

---

## 1. "Why this architecture?"

**Your answer:** "The brief is a domain modeling and algorithm design problem. I evaluated
three architectures — pure domain model, event-sourced CQRS, and a layered service with
API and persistence. The pure domain model puts 100% of the complexity budget where the
problem actually lives: the dispatch strategies, the elevator state machine, and the
simulation correctness. The other two architectures spend significant effort on
infrastructure that nobody consumes. See ADR-002 and ADR-003."

**If they push on CQRS/ES:** "I also evaluated CQRS and event sourcing against production
criteria — 2,000 elevators, 10,000 floors. At that scale, CQRS earns its place because
read and write models genuinely diverge: the write path is serialized per-elevator, the
read path aggregates fleet-wide for dashboards. Event sourcing gives you replay for
production debugging and an integration backbone for downstream systems. But at simulation
scale, the read model is a trivial fold over passenger data, and replay is free — same
input, same output. I documented both the rejection and the production recommendation in
ADR-003."

**Key phrase:** "The domain layer I built is the same code that survives inside the
event-sourced aggregate in the production architecture. The take-home is the kernel."

---

## 2. "Why Python?"

**Your answer:** "The brief mandates Python. But the fit is genuine — the problem is a
discrete-time simulation with a scoring kernel. Python's expressiveness is well-suited:
dataclasses for value objects, Protocol for the strategy port, enum for FSM states.
Hypothesis gives us property-based testing mapped to formal safety and liveness properties.
The analytics bonus benefits from matplotlib. All domain quantities are integers — no
floating-point risk, no need for Decimal."

**If they ask about alternatives:** "If I had the choice, I'd also consider Java 21 with
sealed interfaces for the FSM states and algebraic data modeling for the elevator aggregate.
The JPA identity map would be useful in the production (event-sourced) version. But for a
4-day simulation, Python's iteration speed wins."

---

## 3. "Walk me through the tick semantics."

**Your answer:** "Each tick decomposes into six ordered micro-steps: ingest, dispatch,
dropoff, pickup, move, record. The ordering is deliberate and draws from formal methods
discipline — in model checking, you resolve nondeterminism within a clock cycle by defining
an atomic transition sequence."

**Key ordering justification:** "Dropoff before pickup is the critical decision. It frees
capacity before loading, preventing false rejection of passengers at a floor where others
are exiting. This matches real elevator behavior — people exit before others board — and
preserves the safety property that no elevator exceeds capacity."

**Formal methods connection:** "I studied formal verification of elevator systems using SMV
in graduate work. The same micro-step decomposition I'm applying here is how you resolve
concurrent events in a model checker. The difference is verification method — SMV exhaustively
checks a finite state space, Hypothesis generatively checks over randomized inputs. The
properties being verified are identical: safety (no capacity overflow, no policy violation),
liveness (all requests eventually served), fairness (bounded wait disparity)."

**If they probe deeper:** "The tick ordering is codified in engine/clock.py as named phases,
not implicit code ordering. Each phase is independently testable. If we needed to model door
dwell time, we'd add a DWELLING state to the FSM and extend the pickup/dropoff phases — the
micro-step ordering doesn't change."

---

## 4. "Tell me about the dispatch strategies."

**Your answer:** "The strategy is a port — a Protocol in Python terms. The engine calls
`strategy.select_elevator()` with a read-only snapshot of system state: elevator positions,
directions, loads, service policies, pending requests. The strategy returns an elevator ID.
It's a pure decision function — no mutation, no side effects."

**Three implementations:**
- "NearestCar is the industry baseline for destination dispatch. Scores by distance, direction
  alignment, and current load."
- "RoundRobin is the fairness control — no optimization, just even distribution. Useful as a
  baseline to measure how much NearestCar actually improves things."
- "ZoneBased partitions floors into zones and restricts assignment to zone-serving elevators.
  This composes with express elevator ServicePolicy — the policy enforces which floors an
  elevator *can* serve, the zone strategy decides which elevator *should* serve a request."

**If they ask why Protocol, not ABC:** "Structural subtyping. Strategy implementations don't
inherit from or import a base class. Any object with the right method signature satisfies the
contract. Cleaner for testing — I can use a plain lambda as a test double. Cleaner for
extension — add a strategy in a new file, register it by name."

---

## 5. "How did you model express elevators?"

**Your answer:** "Express behavior is a ServicePolicy value object — a frozen dataclass
containing the set of floors an elevator may serve. It's configuration, not a type hierarchy.
The Elevator FSM is identical for express and local cars — only the set of legal floors
differs. I rejected a subclass approach (ExpressElevator, LocalElevator) because it would
duplicate the FSM for a one-field difference."

**Safety invariant:** "The invariant 'elevator never stops at a floor outside its service
policy' is a safety property verified by Hypothesis. The dispatch phase filters elevators
by policy before the strategy scores them — this is a precondition enforced by the engine,
not by individual strategy implementations."

---

## 6. "How do you compare fairness vs. efficiency?"

**Your answer:** "The multi-strategy runner executes the same input CSV through every
registered strategy and collects per-strategy statistics: min/max/avg/P95 wait time, total
time, and time distribution. The comparison report shows which strategy optimizes for
throughput (lowest average total time) versus which optimizes for fairness (lowest max wait
time, tightest distribution)."

**Expected finding to discuss:** "NearestCar will likely optimize for average performance
but create outliers — a passenger on a low-demand floor might wait significantly longer
while elevators serve high-traffic routes. RoundRobin will have worse average times but a
tighter distribution. ZoneBased should sit between them — it trades some global optimality
for predictable service within each zone. The trade-off between efficiency and fairness is
fundamental and there's no free lunch — the question is which guarantee the building operator
values."

---

## 7. "What would you do differently with more time?"

**Honest answers, in priority order:**
1. "Door dwell time — add a DWELLING state to the FSM with configurable dwell ticks. Doesn't
   change the architecture, just extends the state machine."
2. "Look-ahead dispatch — the brief says no peek-ahead, but a production system would batch
   requests and optimize assignments across the batch. I'd explore this with a configurable
   look-ahead window."
3. "Productionize toward Architecture B — event-sourced aggregates, real event store, CQRS
   read models for monitoring. The domain layer survives unchanged."
4. "Visualization dashboard — real-time animation of elevator movement using a web frontend.
   The simulation would emit events to a WebSocket consumer."
5. "Load-dependent strategy switching — monitor system load and switch strategies dynamically.
   Under low load, use NearestCar for efficiency. Under high load, switch to ZoneBased for
   predictability."

---

## 8. "What's the hardest part of this problem?"

**Your answer:** "The dispatch decision under incomplete information. The no-peek-ahead
constraint means the strategy must assign an elevator without knowing what requests arrive
next tick. Every assignment is a commitment with opportunity cost — sending elevator 3 to
floor 47 means it's unavailable for a request at floor 48 that arrives next tick. The
strategies are heuristics, not optimal solutions. An optimal solution would require future
knowledge or would need to solve an NP-hard scheduling problem. The interesting engineering
question is how close the heuristics get and under what load patterns they diverge."

---

## 9. "You used AI to build this. How?"

**Your answer:** "I used Claude Code as an accelerator, not an author. Every architectural
decision was mine — I brought the formal methods background, the pattern vocabulary, the
domain reasoning. AI helped me iterate faster on implementation, but I reviewed every line,
pushed back on suggestions that violated boundaries, and rewrote code I couldn't defend.
The DECISIONS.md log records where I accepted and rejected AI output."

**Key principle:** "If I can't explain a piece of code to you right now without looking at
it, it's a liability. Everything in this repo is something I can defend."
