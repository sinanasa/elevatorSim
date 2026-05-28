# ADR-001: Language and Stack Selection

## Status
Accepted

## Context
The brief mandates Python ("Build a Python model"). We need to select the supporting libraries and justify what we include and — equally important — what we exclude.

The problem is a discrete-time simulation with a scoring/optimization kernel (dispatch algorithm), configurable parameters, CSV I/O, and statistical reporting. There is no API consumer, no persistent state across runs, no concurrent users.

## Decision

### Language: Python 3.11+
Mandated by brief. Fit is genuine: the simulation benefits from expressive modeling (dataclasses for value objects, Protocol for strategy port, enum for FSM states), and the analytics bonus benefits from matplotlib in the ecosystem.

### Included
| Dependency | Purpose | Justification |
|---|---|---|
| pydantic v2 | Config validation, CSV row schema | Typed boundary at I/O edge. Validates simulation parameters and input rows before they reach the domain. |
| pydantic-settings | Env var → typed config | Single mechanism for CLI args + env vars → Settings object. |
| structlog | Structured logging | JSON output with correlation IDs (run_id, tick, elevator_id). Essential for debugging simulation behavior. |
| click | CLI framework | Typed CLI arguments, subcommands, help text. Lighter than typer, no magic. |
| hypothesis | Property-based testing | Generative verification of safety/liveness/fairness invariants. Maps to formal properties (see ADR-009). |
| pytest | Test runner | Standard. |
| matplotlib | Visualization (optional) | Histogram and chart output for fairness-vs-efficiency analysis. Optional dependency group. |

### Excluded with rationale
| Excluded | Why |
|---|---|
| FastAPI / any web framework | No API consumer exists. CLI is the only delivery mechanism. Adding an API would be Architecture C theater (see ADR-002). |
| SQLAlchemy / Postgres / SQLite | No persistence needed. Input is CSV, output is CSV + statistics. State lives in memory for a single run. See ADR-007. |
| asyncio | Simulation is inherently sequential — tick N must complete before N+1. No I/O to overlap. See ADR-006. |
| Docker Compose | Nothing to compose. Single-process CLI. Thin Dockerfile included for reproducibility only. |

### Numeric types
All domain quantities are integers: floor numbers, tick counts, passenger counts, elevator IDs. No floating-point arithmetic in the domain. Statistics (averages, percentiles) use Python floats, which is correct — these are reporting values, not financial calculations. No Decimal needed.

## Consequences
- Minimal dependency surface (6 libraries). Each earns its place.
- No framework lock-in. Domain layer imports nothing external.
- If productionized (see ADR-003), the domain layer survives unchanged. Infrastructure adapters get replaced.
