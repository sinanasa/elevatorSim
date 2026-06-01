# Demo Script — Panel Walkthrough

Target: ~15 minutes demo, ~15 minutes architecture walkthrough, ~30 minutes Q&A.

## Pre-Demo Setup

```bash
# Terminal ready with virtualenv activated
cd elevatorSim
source .venv/bin/activate

# Verify tests pass (run before panel enters)
pytest -v --tb=short
```

---

## Part 1: Live Demo (~15 minutes)

### 1.1 — Show the Input (1 min)

```bash
cat tests/fixtures/sample_requests.csv
```

"10 passengers across 50 floors, arriving at different times.
This is the simple scenario — I'll also show you 500 passengers
for the strategy comparison."

### 1.2 — Single Strategy Run (2 min)

```bash
elevator-sim run tests/fixtures/sample_requests.csv
```

Point out:
- Statistics output: wait times, travel times, total times
- Min/max/avg/median/P95/StdDev — "these are the metrics an operations
  team would monitor"
- Observations section: "The system flags that 60% had zero wait time
  and that wait disparity is 3.5x — it generates actionable insights,
  not just raw numbers."

### 1.3 — Strategy Comparison (4 min)

**Use the 500-request stress test — this is where strategies diverge.**

```bash
elevator-sim compare tests/fixtures/stress_500.csv
```

This is the key demo moment. Walk through the comparison table:
- "NearestCar: lowest average total time (67.5) — optimizes for efficiency.
  But highest max wait (306) — it creates outliers."
- "RoundRobin: highest average (94.9) — slower overall. But lowest max
  wait (271) — fairer to worst-case passengers."
- "ZoneBased: sits between the two (83.8 avg, 290 max wait) — the compromise."
- "No strategy dominates both axes. The system surfaces this trade-off.
  In a real building, the operations team picks their point on this curve."

If asked about the 10-request sample: "With 10 requests and 6 distributed
elevators, NearestCar and ZoneBased converge — not enough contention to
force different decisions. Under load, they diverge clearly."

### 1.4 — Visualization (2 min)

```bash
elevator-sim visualize tests/fixtures/stress_500.csv --output-dir demo_output
open demo_output/efficiency_vs_fairness.png
open demo_output/time_distributions.png
```

Show the charts:
- Scatter plot first: "This is the efficiency-fairness frontier. NearestCar
  top-left: fast average, high worst-case. RoundRobin bottom-right: slower
  average, better worst-case. You pick your point on this curve."
- Box plots: "Distribution shapes, not just averages. Look at the outliers
  on NearestCar's wait time — that's the fairness cost of proximity
  optimization."

### 1.5 — Configuration via Environment (1 min)

```bash
ELEVATOR_SIM_STRATEGY=round_robin elevator-sim run tests/fixtures/sample_requests.csv
```

"Configuration flows through Pydantic Settings: env vars with the
ELEVATOR_SIM_ prefix, CLI flags, then defaults. Typed and validated
at startup. If I set ELEVATOR_SIM_STRATEGY=invalid, it fails immediately
with the list of valid options."

### 1.6 — Docker (1 min)

```bash
docker build -t elevator-sim .
docker run --rm -v $(pwd)/tests/fixtures:/data elevator-sim run /data/sample_requests.csv
```

"Single-stage build, slim image. No compose — there's nothing to compose.
That's an intentional decision documented in ADR-001."

### 1.7 — Test Suite (3 min)

```bash
pytest -v --tb=short
```

Highlight while tests run:
- "57 tests, three layers: unit, property-based, integration"
- "The property-based tests use Hypothesis to verify formal invariants —
  capacity never exceeded, no double assignment, all passengers delivered —
  across randomized inputs. This maps directly to model-checking vocabulary:
  safety, liveness, fairness."
- "The integration test has a hand-traced scenario with tick-by-tick
  expected values documented in the test docstring. I can walk you through
  that trace."

### 1.8 — Stress Test (1 min, if time permits)

```bash
elevator-sim compare tests/fixtures/stress_3000.csv
```

"3,000 passengers, all delivered across all strategies. Average wait is
520-556 ticks — passengers waiting 17x longer than they travel. That's
the saturation signal: the answer is more elevators, not a better algorithm."

---

## Part 2: Architecture Walkthrough (~15 minutes)

### 2.1 — Project Structure (2 min)

```bash
tree src/elevator_sim -I __pycache__
```

"Hexagonal architecture. Domain is pure — no imports from infrastructure,
no I/O. Engine orchestrates. Infrastructure adapts. CLI delivers.
Arrows point inward. If I add a REST API, it's a new adapter alongside
CLI — domain doesn't change."

### 2.2 — Domain Model (4 min)

Open `src/elevator_sim/domain/model.py`.

Walk through:
- **PassengerRequest** — frozen dataclass, value object, computed direction
- **Passenger** — entity with state machine (WAITING -> ASSIGNED -> RIDING -> DELIVERED).
  "Each transition is guarded. Invalid transitions raise typed exceptions."
- **Elevator** — the FSM. SCAN algorithm for movement. "Dropoff before pickup
  is load-bearing — it frees capacity. That ordering is enforced in the engine
  and documented in ADR-005."
- **ServicePolicy** — "Express elevators are configuration, not subclasses.
  A frozen set of served floors. This avoids duplicating the FSM."
- **ElevatorSnapshot** — "Strategies receive read-only views. They cannot
  mutate elevator state. That's a deliberate boundary."

### 2.3 — Strategy Pattern (3 min)

Open `src/elevator_sim/domain/strategies.py`.

- **Protocol, not ABC**: "Structural subtyping. No inheritance coupling.
  A test double is any object with the right shape."
- **NearestCar scoring**: distance + direction penalty + load penalty.
  "Three-factor scoring. The weights are constructor parameters —
  testable and tunable."
- **Registry**: "Dictionary lookup by name. No reflection, no plugin
  framework. Adding a strategy is: write a class, register it, done."

### 2.4 — Tick Loop (3 min)

Open `src/elevator_sim/engine/simulation.py`.

"Six phases per tick, strict order. This is the application layer —
it orchestrates domain objects but contains no business rules."

Point out:
- Invariant checks after each phase (capacity, double assignment, service policy)
- Termination condition: all ingested AND all delivered
- Safety bound preventing infinite loops
- Event emission for audit trail

### 2.5 — ADRs and Rejected Patterns (3 min)

```bash
ls docs/ADR/
```

"Nine ADRs. The ones I want to highlight are the rejections:"
- **ADR-003 (CQRS/Event Sourcing rejected)**: "Read and write models don't
  diverge here. But I document exactly when they would — 2,000 elevators,
  real-time dashboards, audit requirements."
- **ADR-007 (Persistence rejected)**: "No state survives across runs.
  Postgres would be theater."
- "Every rejection names the conditions under which the pattern becomes
  justified. That's the architectural judgment signal."

---

## Part 3: Anticipated Q&A (~30 minutes)

### Likely Questions and Prepared Answers

**Q: Why no database?**
"ADR-007. Input is CSV, output is files. No query patterns, no cross-run
state. Postgres would add schema migration, connection management, and
ORM mapping for zero user value. If we needed to store results for
comparison across parameter sweeps, that's when persistence earns its place."

**Q: How would this scale to 2,000 elevators?**
"The domain model survives unchanged. The engine would need event sourcing
for replay and debugging (ADR-003 documents this). The strategy layer
would need spatial indexing — the current O(n) scan over elevator snapshots
doesn't scale. And we'd want CQRS: the real-time dashboard reads diverge
from the dispatch writes."

**Q: Why SCAN instead of LOOK?**
"SCAN is the industry baseline for elevator scheduling — it prevents
starvation that naive nearest-floor causes. LOOK (only go as far as the
last request in that direction) would be a refinement, but SCAN is
simpler to verify and the difference matters less than the dispatch
strategy choice."

**Q: What about real-time requests?**
"That changes the delivery mechanism from CLI to WebSocket/SSE, adds
async I/O (ADR-006), and introduces a fundamentally different dispatch
problem — you can no longer see the full request set. The domain model
and strategies still apply, but the engine would need to become event-driven
rather than tick-driven."

**Q: How did you use AI?**
"AI as an accelerator. Every architectural decision — hexagonal layout,
pattern selection, pattern rejection, testing strategy — was authored
by me. The AI generated implementation code that I reviewed, modified,
and can defend line by line. I can defend every choice because I made
every choice."

**Q: What would you do with another week?**
"Three things in priority order. Dynamic strategy switching — detect the
traffic pattern and switch at runtime. RoundRobin during low load,
NearestCar during peak, ZoneBased for express hours. The Protocol is
already pluggable, so it's a one-line swap in the engine. Second,
look-ahead dispatch — pre-position idle elevators based on historical
patterns. Third, dwell time — add a DWELLING state to the FSM for
realistic door-open delays. One enum value, no architectural change."

**Q: NearestCar and ZoneBased produce the same results on the small sample?**
"Correct. With 6 elevators distributed across 50 floors and only 10
requests, there's not enough contention to force different decisions.
The zone filter either matches the same elevator NearestCar would pick
by proximity, or finds no zone-local elevator and falls back to NearestCar.
Under 500 requests they diverge clearly — different ticks, different
averages, different max waits. That's expected and correct behavior."

---

## Demo Cleanup

```bash
rm -rf demo_output/
```
