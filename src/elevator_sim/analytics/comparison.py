"""Multi-strategy comparison analysis.

Computes comparative metrics across strategies for the fairness-vs-efficiency
analysis (bonus item). Pure computation — takes ComparisonResult, returns
structured analysis.
"""

from __future__ import annotations

from dataclasses import dataclass

from elevator_sim.analytics.statistics import PassengerStatistics
from elevator_sim.engine.runner import ComparisonResult


@dataclass(frozen=True)
class StrategyAnalysis:
    """Per-strategy analysis with statistics and ranking."""

    strategy_name: str
    stats: PassengerStatistics
    total_ticks: int
    efficiency_rank: int  # 1 = best avg total time
    fairness_rank: int    # 1 = lowest max wait time


@dataclass(frozen=True)
class ComparisonAnalysis:
    """Comparative analysis across all strategies."""

    analyses: dict[str, StrategyAnalysis]
    most_efficient: str    # strategy with lowest avg total time
    most_fair: str         # strategy with lowest max wait time
    observations: list[str]


def analyze_comparison(comp: ComparisonResult) -> ComparisonAnalysis:
    """Analyze a multi-strategy comparison result.

    Computes per-strategy statistics, ranks by efficiency and fairness,
    and generates observations about trade-offs.
    """
    # Compute stats per strategy
    stats_by_name: dict[str, tuple[PassengerStatistics, int]] = {}
    for name, result in comp.results.items():
        stats = PassengerStatistics.from_passengers(result.passengers)
        stats_by_name[name] = (stats, result.total_ticks)

    # Rank by efficiency (lowest avg total time = rank 1)
    by_efficiency = sorted(
        stats_by_name.keys(),
        key=lambda n: stats_by_name[n][0].total_times.avg,
    )

    # Rank by fairness (lowest max wait time = rank 1)
    by_fairness = sorted(
        stats_by_name.keys(),
        key=lambda n: stats_by_name[n][0].wait_times.max,
    )

    efficiency_ranks = {name: i + 1 for i, name in enumerate(by_efficiency)}
    fairness_ranks = {name: i + 1 for i, name in enumerate(by_fairness)}

    analyses: dict[str, StrategyAnalysis] = {}
    for name, (stats, ticks) in stats_by_name.items():
        analyses[name] = StrategyAnalysis(
            strategy_name=name,
            stats=stats,
            total_ticks=ticks,
            efficiency_rank=efficiency_ranks[name],
            fairness_rank=fairness_ranks[name],
        )

    # Generate observations
    observations = _generate_observations(analyses, by_efficiency, by_fairness)

    return ComparisonAnalysis(
        analyses=analyses,
        most_efficient=by_efficiency[0] if by_efficiency else "",
        most_fair=by_fairness[0] if by_fairness else "",
        observations=observations,
    )


def _generate_observations(
    analyses: dict[str, StrategyAnalysis],
    by_efficiency: list[str],
    by_fairness: list[str],
) -> list[str]:
    """Generate human-readable observations about strategy trade-offs."""
    observations: list[str] = []

    if len(analyses) < 2:
        return ["Only one strategy analyzed — no comparison possible."]

    best_eff = analyses[by_efficiency[0]]
    worst_eff = analyses[by_efficiency[-1]]
    best_fair = analyses[by_fairness[0]]
    worst_fair = analyses[by_fairness[-1]]

    # Efficiency spread
    if worst_eff.stats.total_times.avg > 0:
        eff_spread = (
            (worst_eff.stats.total_times.avg - best_eff.stats.total_times.avg)
            / best_eff.stats.total_times.avg * 100
        )
        if eff_spread > 10:
            observations.append(
                f"Efficiency gap: {worst_eff.strategy_name} averages {eff_spread:.0f}% "
                f"more total time than {best_eff.strategy_name}."
            )

    # Fairness spread
    if best_fair.stats.wait_times.max != worst_fair.stats.wait_times.max:
        observations.append(
            f"Fairness gap: max wait is {best_fair.stats.wait_times.max} ticks "
            f"under {best_fair.strategy_name} vs {worst_fair.stats.wait_times.max} "
            f"under {worst_fair.strategy_name}."
        )

    # Efficiency-fairness trade-off
    if by_efficiency[0] != by_fairness[0]:
        observations.append(
            f"Trade-off: {by_efficiency[0]} optimizes for average performance, "
            f"while {by_fairness[0]} optimizes for worst-case experience. "
            f"No strategy dominates both axes."
        )
    else:
        observations.append(
            f"{by_efficiency[0]} leads on both efficiency and fairness — "
            f"rare, possibly due to low load or small sample."
        )

    # P95 analysis
    for name, analysis in analyses.items():
        if analysis.stats.total_times.p95 > 2 * analysis.stats.total_times.avg:
            observations.append(
                f"Tail latency: {name} P95 total time ({analysis.stats.total_times.p95}) "
                f"is >2x the average ({analysis.stats.total_times.avg:.1f}), indicating "
                f"a heavy tail in the distribution."
            )

    return observations
