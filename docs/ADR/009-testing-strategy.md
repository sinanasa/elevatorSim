# ADR-009: Testing Strategy — Property-Based Tests Mapped to Formal Properties

## Status
Accepted

## Context
The system has well-defined correctness properties that map to formal verification categories: safety (bad things never happen), liveness (good things eventually happen), and fairness (no starvation under bounded load). Traditional unit tests verify specific scenarios; property-based tests verify invariants across randomized inputs.

The author's background in formal methods (SMV model checking for elevator systems) informs this approach. The same properties verified exhaustively by a model checker over a finite state space can be verified generatively by Hypothesis over randomized input sequences.

## Decision

### Test layers

**Unit tests (domain/):**
- Elevator FSM: each state transition given valid/invalid inputs.
- Passenger lifecycle: state progression from requested → assigned → picked_up → delivered.
- Strategy implementations: given a known elevator configuration, assert correct assignment.
- Deterministic, scenario-based, fast.

**Property-based tests (domain/test_invariants.py):**
- Use Hypothesis to generate random request sequences (varying floors, times, volumes).
- Run full simulation ticks and assert invariants hold for ALL generated inputs.
- Mapped to formal property categories:

| Property | Category | Hypothesis assertion |
|---|---|---|
| Elevator passenger count never exceeds capacity | Safety (AG ¬overflow) | `assert len(elevator.passengers) <= capacity` at every tick |
| Elevator never visits floor outside ServicePolicy | Safety (AG policy_respected) | `assert elevator.current_floor in elevator.service_policy.served_floors` at every tick |
| No passenger assigned to multiple elevators | Safety (AG ¬double_assign) | `assert` unique assignment across all elevators |
| Every request eventually served | Liveness (AG(requested → AF delivered)) | After simulation completes, `assert all(p.delivered for p in passengers)` |
| No passenger waits indefinitely | Liveness (bounded wait) | `assert p.wait_time < upper_bound` for reasonable bound |
| Wait time distribution is bounded | Fairness | `assert max_wait <= K * avg_wait` under sub-capacity load |

**Integration test (test_end_to_end.py):**
- CSV file with hand-traced scenario → full simulation → verify output files match expected content.
- Known-good expected values computed manually and documented in test docstring.
- Exercises the full pipeline: CSV parsing → engine → statistics → file output.

### Why Hypothesis over manual fuzzing
Hypothesis provides: shrinking (minimal failing example), replay (seed-based reproducibility), and health checks (detects degenerate generators). Manual fuzzing gives none of these. For invariant verification, Hypothesis is the right tool.

### Coverage targets
- Domain layer: high coverage (>90%). Every FSM transition, every invariant, every strategy.
- Engine layer: moderate coverage. Tick loop correctness, micro-step ordering.
- Infrastructure layer: low coverage. CSV parsing validation (handled by Pydantic). File output format.
- CLI layer: not unit-tested. Exercised by integration test.

## Consequences
- Formal properties are documented and tested, not just implied.
- Hypothesis may find edge cases that scenario-based tests miss (e.g., all passengers requesting the same floor, empty request sequences, single-elevator saturation).
- Trade-off: property-based tests are slower than unit tests. Acceptable — run them in CI, not in the inner development loop. Hypothesis's database caches interesting examples for fast re-runs.
- Panel talking point: connecting Hypothesis to model checking vocabulary demonstrates depth beyond "I wrote some tests."
