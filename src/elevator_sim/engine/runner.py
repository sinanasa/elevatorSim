"""Multi-strategy runner — executes the same input across N strategies.

Powers the fairness-vs-efficiency analysis (bonus item). Runs each
strategy independently against the same request set and collects
comparative results.

The simulation is deterministic, so each strategy run is independent
and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from elevator_sim.domain.model import PassengerRequest, ServicePolicy, SimulationConfig
from elevator_sim.domain.strategies import available_strategies, get_strategy
from elevator_sim.engine.simulation import SimulationEngine, SimulationResult

logger = structlog.get_logger()


@dataclass(frozen=True)
class ComparisonResult:
    """Results of running multiple strategies over the same input."""

    config: SimulationConfig
    results: dict[str, SimulationResult]
    request_count: int


def run_comparison(
    requests: list[PassengerRequest],
    config: SimulationConfig,
    strategy_names: list[str] | None = None,
    service_policies: list[ServicePolicy] | None = None,
) -> ComparisonResult:
    """Run the same request set through multiple strategies and collect results.

    Args:
        requests: Passenger requests (same for all strategies).
        config: Simulation configuration.
        strategy_names: Strategies to compare. Defaults to all registered.
        service_policies: Optional per-elevator service policies.

    Returns:
        ComparisonResult with per-strategy SimulationResults.
    """
    if strategy_names is None:
        strategy_names = available_strategies()

    results: dict[str, SimulationResult] = {}

    for name in strategy_names:
        logger.info("comparison.running_strategy", strategy=name)

        strategy = get_strategy(name)
        engine = SimulationEngine(config=config, strategy=strategy)
        engine.initialize(service_policies=service_policies)

        result = engine.run(list(requests))  # Copy list to avoid mutation issues
        results[name] = result

        logger.info(
            "comparison.strategy_complete",
            strategy=name,
            total_ticks=result.total_ticks,
            passengers_served=len(result.passengers),
        )

    return ComparisonResult(
        config=config,
        results=results,
        request_count=len(requests),
    )
