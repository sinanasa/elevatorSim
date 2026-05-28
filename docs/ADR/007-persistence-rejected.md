# ADR-007: Persistence Layer — Considered and Rejected

## Status
Accepted

## Context
The cross-cutting baseline includes "one integration test that exercises the real persistence layer." We evaluated whether a database (Postgres or SQLite) is warranted.

## Decision
Rejected. There is no persistence requirement in the brief:
- Input: CSV file, read once at startup.
- Output: CSV position log + statistics report, written once at completion.
- No state survives across simulation runs.
- No multi-user access.
- No queryable history.

SQLite would add: a schema, a migration, an ORM or raw SQL, connection management, and test fixtures — all for a system that reads a file and writes a file. The "real persistence layer" integration test is satisfied by the end-to-end test: CSV in → simulation → verified file output.

### When persistence would be justified
If the system stored simulation results for historical comparison across runs, or if the multi-strategy runner needed to persist intermediate results for large-scale parameter sweeps, a database would earn its place. Neither applies here.

### Postgres specifically
Postgres is the default for non-trivial persistence, but this brief is genuinely small enough that any database would be theater. The brief asks for a simulation, not a service. Honest scoping.

## Consequences
- No database dependency. No Docker Compose.
- Simpler setup: `pip install` and run.
- Integration testing is file-based: verify output files against expected content.
- Trade-off: no cross-run comparison without re-running. Accepted — the multi-strategy runner handles within-run comparison, which is what the bonus asks for.
