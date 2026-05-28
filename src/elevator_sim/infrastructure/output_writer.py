"""Output writers for simulation results.

Adapts domain results into output files:
  - Position log CSV (one row per tick, elevator positions)
  - Statistics summary (text report to stdout or file)
"""

from __future__ import annotations

import csv
import sys
from io import StringIO
from pathlib import Path

from elevator_sim.engine.simulation import SimulationResult


def write_position_log(result: SimulationResult, path: Path | None = None) -> str:
    """Write the elevator position log to CSV.

    Format: tick,elevator_0,elevator_1,...,elevator_N

    Args:
        result: Simulation result containing position_log.
        path: Output file path. If None, returns as string.

    Returns:
        The CSV content as a string.
    """
    output = StringIO()
    num_elevators = result.config.num_elevators

    # Header
    headers = ["tick"] + [f"elevator_{i}" for i in range(num_elevators)]
    writer = csv.writer(output)
    writer.writerow(headers)

    for entry in result.position_log:
        row = [entry["tick"]] + entry["positions"]
        writer.writerow(row)

    content = output.getvalue()

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    return content


def format_statistics(result: SimulationResult) -> str:
    """Format passenger statistics as a human-readable report.

    Returns:
        Formatted string with min/max/avg wait and total times,
        plus distribution observations.
    """
    passengers = [p for p in result.passengers if p.total_time is not None]

    if not passengers:
        return "No delivered passengers — no statistics to report."

    wait_times = [p.wait_time for p in passengers if p.wait_time is not None]
    travel_times = [p.travel_time for p in passengers if p.travel_time is not None]
    total_times = [p.total_time for p in passengers if p.total_time is not None]

    lines = [
        f"=== Simulation Statistics ({result.strategy_name}) ===",
        f"Run ID: {result.run_id}",
        f"Configuration: {result.config.num_elevators} elevators, "
        f"{result.config.num_floors} floors, capacity {result.config.max_capacity}",
        f"Total ticks: {result.total_ticks}",
        f"Passengers served: {len(passengers)}",
        "",
        "--- Wait Times (ticks from request to pickup) ---",
        _format_stats(wait_times),
        "",
        "--- Travel Times (ticks from pickup to delivery) ---",
        _format_stats(travel_times),
        "",
        "--- Total Times (ticks from request to delivery) ---",
        _format_stats(total_times),
        "",
        "--- Observations ---",
        *_observations(wait_times, travel_times, total_times),
    ]

    return "\n".join(lines)


def write_statistics(
    result: SimulationResult,
    path: Path | None = None,
) -> str:
    """Format and optionally write statistics to file.

    Args:
        result: Simulation result.
        path: Output file path. If None, only returns string.

    Returns:
        Formatted statistics string.
    """
    content = format_statistics(result)

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    return content


def print_statistics(result: SimulationResult) -> None:
    """Print statistics to stdout."""
    print(format_statistics(result), file=sys.stdout)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_stats(values: list[int]) -> str:
    """Format min/max/avg/median/P95 for a list of integer values."""
    if not values:
        return "  No data"

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    avg = sum(sorted_vals) / n
    median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    p95_idx = min(int(n * 0.95), n - 1)
    p95 = sorted_vals[p95_idx]
    std_dev = (sum((v - avg) ** 2 for v in sorted_vals) / n) ** 0.5

    return (
        f"  Min:    {min(sorted_vals)}\n"
        f"  Max:    {max(sorted_vals)}\n"
        f"  Avg:    {avg:.1f}\n"
        f"  Median: {median}\n"
        f"  P95:    {p95}\n"
        f"  StdDev: {std_dev:.1f}"
    )


def _observations(
    wait_times: list[int],
    travel_times: list[int],
    total_times: list[int],
) -> list[str]:
    """Generate notable observations about the time distributions."""
    observations = []

    if not wait_times:
        return ["  No delivered passengers to analyze."]

    avg_wait = sum(wait_times) / len(wait_times)
    max_wait = max(wait_times)
    zero_wait_count = sum(1 for w in wait_times if w == 0)
    zero_wait_pct = zero_wait_count / len(wait_times) * 100

    if zero_wait_pct > 50:
        observations.append(
            f"  - {zero_wait_pct:.0f}% of passengers had zero wait time "
            f"(elevator already at their floor)."
        )

    if max_wait > 0 and avg_wait > 0:
        disparity = max_wait / avg_wait
        if disparity > 3:
            observations.append(
                f"  - High wait disparity: max wait ({max_wait}) is "
                f"{disparity:.1f}x the average ({avg_wait:.1f}). "
                f"Consider fairness-optimizing strategies."
            )

    avg_travel = sum(travel_times) / len(travel_times)
    avg_total = sum(total_times) / len(total_times)

    if avg_wait > avg_travel:
        observations.append(
            f"  - Passengers spend more time waiting ({avg_wait:.1f}) than "
            f"traveling ({avg_travel:.1f}). System may be under-provisioned "
            f"or dispatch strategy suboptimal."
        )

    if not observations:
        observations.append(
            f"  - System performing within normal parameters. "
            f"Avg total time: {avg_total:.1f} ticks."
        )

    return observations
