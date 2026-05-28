# Decisions Log

Chronological record of every meaningful design and implementation choice.

---

- [Day 1 09:00] Chose Architecture A (Pure Domain Model + Strategy Pattern, CLI-driven) over Architecture B (Event-Sourced/CQRS) and Architecture C (Layered Service with API/Postgres). Rationale: the brief is a domain modeling and algorithm design problem; 100% of the complexity budget belongs in the domain, not infrastructure. B and C evaluated against production criteria in ADR-003. See ADR-002.

- [Day 1 09:15] Stack: Python 3.11+, Pydantic v2, structlog, Hypothesis, pytest, click. Brief mandates Python. No web framework (no API needed), no database (no persistence needed), no async (simulation is inherently sequential). See ADR-001.

- [Day 1 09:30] Rejected CQRS and Event Sourcing for this scope. Read/write models don't diverge — simulation is sequential, statistics are a trivial fold. Documented what would need to be true for CQRS to earn its place (2000 elevators, production monitoring, fleet-wide dashboards). See ADR-003.

- [Day 1 09:30] Rejected async I/O. Tick N must complete before tick N+1. No concurrent I/O to overlap. async would add cognitive overhead for zero throughput benefit. See ADR-006.

- [Day 1 09:30] Rejected persistence layer. Input is CSV, output is CSV + statistics. No multi-run storage needed. Adding Postgres/SQLite would be complexity theater. See ADR-007.

- [Day 1 09:45] Chose hexagonal layout with domain/engine/analytics/infrastructure/cli boundaries. Domain is pure (no I/O), engine orchestrates, infrastructure adapts. No Repository pattern — would just forward to CSV reader with no abstraction value. See ADR-002.

- [Day 1 09:45] Defined micro-step ordering within a tick: ingest → dispatch → dropoff → pickup → move → record. Dropoff before pickup is deliberate (frees capacity). Grounded in formal methods discipline — maps to atomic transitions within a macro-tick. See ADR-005.

- [Day 1 10:00] All three bonus items in scope: multiple dispatch algorithms, express elevators, fairness-vs-efficiency analysis. Architecture supports all three via Strategy pattern (algorithm swap), ServicePolicy value object (express), and multi-strategy runner (comparison).

- [Day 1 10:00] PANEL_PREP.md created as training material for panel defense. Consolidates justifications by topic.
