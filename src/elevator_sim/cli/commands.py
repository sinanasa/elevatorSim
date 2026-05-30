"""CLI entry points — thin wiring shell over the engine.

Three commands:
  - run:       Single strategy, single output
  - compare:   Multi-strategy comparison report
  - visualize: Generate charts (requires matplotlib)

The CLI is a delivery mechanism — it wires infrastructure adapters
to the engine and invokes it. No business logic here.
"""

from __future__ import annotations

from pathlib import Path

import click

from elevator_sim.config import SimulationSettings
from elevator_sim.domain.model import SimulationConfig
from elevator_sim.domain.strategies import available_strategies, get_strategy
from elevator_sim.engine.runner import run_comparison
from elevator_sim.engine.simulation import SimulationEngine
from elevator_sim.infrastructure.csv_parser import parse_csv
from elevator_sim.infrastructure.logging import configure_logging
from elevator_sim.infrastructure.output_writer import (
    format_statistics,
    print_statistics,
    write_position_log,
    write_statistics,
)


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Elevator System Simulation — Destination Dispatch."""
    ctx.ensure_object(dict)


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--elevators", "-e", type=int, default=None, help="Number of elevators")
@click.option("--floors", "-f", type=int, default=None, help="Number of floors")
@click.option("--capacity", "-c", type=int, default=None, help="Max passengers per elevator")
@click.option("--strategy", "-s", type=str, default=None, help="Dispatch strategy name")
@click.option(
    "--output-dir", "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory for position log and stats",
)
@click.option("--log-level", type=str, default=None, help="Log level")
@click.option("--log-format", type=str, default=None, help="Log format: json or console")
def run(
    input_file: Path,
    elevators: int | None,
    floors: int | None,
    capacity: int | None,
    strategy: str | None,
    output_dir: Path | None,
    log_level: str | None,
    log_format: str | None,
) -> None:
    """Run a single simulation with the specified strategy."""
    # Build settings: CLI args override env vars override defaults
    settings = _build_settings(elevators, floors, capacity, strategy, log_level, log_format)
    configure_logging(settings.log_level, settings.log_format)

    config = SimulationConfig(
        num_floors=settings.num_floors,
        num_elevators=settings.num_elevators,
        max_capacity=settings.max_capacity,
    )

    requests = parse_csv(input_file, num_floors=settings.num_floors)
    click.echo(f"Loaded {len(requests)} requests from {input_file}")

    strat = get_strategy(settings.strategy)
    engine = SimulationEngine(config=config, strategy=strat)
    engine.initialize()

    result = engine.run(requests)

    # Output
    print_statistics(result)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        pos_path = output_dir / f"positions_{settings.strategy}.csv"
        stats_path = output_dir / f"statistics_{settings.strategy}.txt"
        write_position_log(result, pos_path)
        write_statistics(result, stats_path)
        click.echo(f"\nPosition log: {pos_path}")
        click.echo(f"Statistics:   {stats_path}")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--elevators", "-e", type=int, default=None, help="Number of elevators")
@click.option("--floors", "-f", type=int, default=None, help="Number of floors")
@click.option("--capacity", "-c", type=int, default=None, help="Max passengers per elevator")
@click.option(
    "--strategies",
    type=str,
    default=None,
    help="Comma-separated list of strategies (default: all)",
)
@click.option(
    "--output-dir", "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory",
)
@click.option("--log-level", type=str, default=None, help="Log level")
@click.option("--log-format", type=str, default=None, help="Log format: json or console")
def compare(
    input_file: Path,
    elevators: int | None,
    floors: int | None,
    capacity: int | None,
    strategies: str | None,
    output_dir: Path | None,
    log_level: str | None,
    log_format: str | None,
) -> None:
    """Compare multiple dispatch strategies on the same input."""
    settings = _build_settings(elevators, floors, capacity, None, log_level, log_format)
    configure_logging(settings.log_level, settings.log_format)

    config = SimulationConfig(
        num_floors=settings.num_floors,
        num_elevators=settings.num_elevators,
        max_capacity=settings.max_capacity,
    )

    strategy_names = (
        [s.strip() for s in strategies.split(",")]
        if strategies
        else available_strategies()
    )

    requests = parse_csv(input_file, num_floors=settings.num_floors)
    click.echo(f"Loaded {len(requests)} requests from {input_file}")
    click.echo(f"Comparing strategies: {', '.join(strategy_names)}\n")

    comp = run_comparison(requests, config, strategy_names=strategy_names)

    # Print comparison summary
    _print_comparison(comp)

    # Write individual results if output dir specified
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, result in comp.results.items():
            write_position_log(result, output_dir / f"positions_{name}.csv")
            write_statistics(result, output_dir / f"statistics_{name}.txt")
        # Write comparison summary
        summary_path = output_dir / "comparison_summary.txt"
        summary_path.write_text(_format_comparison(comp))
        click.echo(f"\nResults written to {output_dir}/")


@cli.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--elevators", "-e", type=int, default=None)
@click.option("--floors", "-f", type=int, default=None)
@click.option("--capacity", "-c", type=int, default=None)
@click.option(
    "--output-dir", "-o",
    type=click.Path(path_type=Path),
    default=Path("output"),
)
@click.option("--log-level", type=str, default="WARNING")
def visualize(
    input_file: Path,
    elevators: int | None,
    floors: int | None,
    capacity: int | None,
    output_dir: Path,
    log_level: str,
) -> None:
    """Generate comparison charts (requires matplotlib)."""
    try:
        from elevator_sim.analytics.visualization import generate_comparison_charts
    except ImportError:
        click.echo("matplotlib is required for visualization. Install with:")
        click.echo("  pip install 'elevator-sim[viz]'")
        raise SystemExit(1)

    settings = _build_settings(elevators, floors, capacity, None, log_level, "console")
    configure_logging(settings.log_level, settings.log_format)

    config = SimulationConfig(
        num_floors=settings.num_floors,
        num_elevators=settings.num_elevators,
        max_capacity=settings.max_capacity,
    )

    requests = parse_csv(input_file, num_floors=settings.num_floors)
    click.echo(f"Loaded {len(requests)} requests. Running all strategies...")

    comp = run_comparison(requests, config)

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        generate_comparison_charts(comp, output_dir)
    except ImportError:
        raise click.ClickException(
            "matplotlib is required for visualization. "
            "Install it with: pip install elevator-sim[viz]"
        )
    click.echo(f"Charts saved to {output_dir}/")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_settings(
    elevators: int | None,
    floors: int | None,
    capacity: int | None,
    strategy: str | None,
    log_level: str | None,
    log_format: str | None,
) -> SimulationSettings:
    """Build settings with CLI overrides."""
    overrides: dict[str, object] = {}
    if elevators is not None:
        overrides["num_elevators"] = elevators
    if floors is not None:
        overrides["num_floors"] = floors
    if capacity is not None:
        overrides["max_capacity"] = capacity
    if strategy is not None:
        overrides["strategy"] = strategy
    if log_level is not None:
        overrides["log_level"] = log_level
    if log_format is not None:
        overrides["log_format"] = log_format

    return SimulationSettings(**overrides)


def _print_comparison(comp: run_comparison.__class__) -> None:  # type: ignore[name-defined]
    """Print comparison results to stdout."""
    click.echo(_format_comparison(comp))


def _format_comparison(comp: object) -> str:
    """Format comparison results as a table."""
    from elevator_sim.engine.runner import ComparisonResult

    assert isinstance(comp, ComparisonResult)

    lines = [
        "=== Strategy Comparison ===",
        f"Requests: {comp.request_count}",
        f"Config: {comp.config.num_elevators} elevators, "
        f"{comp.config.num_floors} floors, capacity {comp.config.max_capacity}",
        "",
        f"{'Strategy':<15} {'Ticks':>6} {'Avg Wait':>9} {'Max Wait':>9} "
        f"{'Avg Total':>10} {'Max Total':>10} {'P95 Total':>10}",
        "-" * 75,
    ]

    for name, result in comp.results.items():
        passengers = [p for p in result.passengers if p.total_time is not None]
        if not passengers:
            lines.append(f"{name:<15} {'N/A':>6}")
            continue

        wait_times = [p.wait_time for p in passengers if p.wait_time is not None]
        total_times = [p.total_time for p in passengers if p.total_time is not None]

        avg_wait = sum(wait_times) / len(wait_times) if wait_times else 0
        max_wait = max(wait_times) if wait_times else 0
        avg_total = sum(total_times) / len(total_times) if total_times else 0
        max_total = max(total_times) if total_times else 0
        sorted_totals = sorted(total_times)
        p95_idx = min(int(len(sorted_totals) * 0.95), len(sorted_totals) - 1)
        p95_total = sorted_totals[p95_idx] if sorted_totals else 0

        lines.append(
            f"{name:<15} {result.total_ticks:>6} {avg_wait:>9.1f} {max_wait:>9} "
            f"{avg_total:>10.1f} {max_total:>10} {p95_total:>10}"
        )

    return "\n".join(lines)
