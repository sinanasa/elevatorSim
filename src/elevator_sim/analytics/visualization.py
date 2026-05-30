"""Visualization of simulation results using matplotlib.

Optional dependency — only imported when the 'visualize' CLI command is used.
Generates comparison charts for the fairness-vs-efficiency analysis.
"""

from __future__ import annotations

from pathlib import Path

from elevator_sim.analytics.comparison import analyze_comparison
from elevator_sim.analytics.statistics import PassengerStatistics
from elevator_sim.engine.runner import ComparisonResult


def generate_comparison_charts(comp: ComparisonResult, output_dir: Path) -> list[Path]:
    """Generate comparison charts and save to output directory.

    Returns list of generated file paths.
    """
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt

    analysis = analyze_comparison(comp)
    generated: list[Path] = []

    # 1. Wait time distribution (box plot)
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    # Collect data per strategy
    strategy_names = list(comp.results.keys())
    wait_data = []
    travel_data = []
    total_data = []

    for name in strategy_names:
        passengers = comp.results[name].passengers
        wait_data.append([p.wait_time for p in passengers if p.wait_time is not None])
        travel_data.append([p.travel_time for p in passengers if p.travel_time is not None])
        total_data.append([p.total_time for p in passengers if p.total_time is not None])

    # Wait times box plot
    axes[0].boxplot(wait_data, labels=strategy_names)
    axes[0].set_title("Wait Time Distribution")
    axes[0].set_ylabel("Ticks")
    axes[0].tick_params(axis="x", rotation=20)

    # Travel times box plot
    axes[1].boxplot(travel_data, labels=strategy_names)
    axes[1].set_title("Travel Time Distribution")
    axes[1].set_ylabel("Ticks")
    axes[1].tick_params(axis="x", rotation=20)

    # Total times box plot
    axes[2].boxplot(total_data, labels=strategy_names)
    axes[2].set_title("Total Time Distribution")
    axes[2].set_ylabel("Ticks")
    axes[2].tick_params(axis="x", rotation=20)

    fig.suptitle("Strategy Comparison — Time Distributions", fontsize=14)
    plt.tight_layout()
    path = output_dir / "time_distributions.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    generated.append(path)

    # 2. Efficiency vs Fairness scatter
    fig, ax = plt.subplots(figsize=(8, 6))

    # Collect points for plotting and label placement
    points: list[tuple[float, float, str]] = []
    for name in strategy_names:
        stats = PassengerStatistics.from_passengers(comp.results[name].passengers)
        points.append((stats.total_times.avg, stats.wait_times.max, name))

    for x, y, name in points:
        ax.scatter(x, y, s=100, label=name, zorder=5)

    # Place labels with vertical staggering to avoid overlap
    placed: list[tuple[float, float]] = []
    for x, y, name in points:
        dy = 8
        for px, py in placed:
            # Check if this point is close to an already-labeled point
            # using percentage of data range as threshold
            x_range = max(p[0] for p in points) - min(p[0] for p in points) or 1
            y_range = max(p[1] for p in points) - min(p[1] for p in points) or 1
            if abs(x - px) / x_range < 0.1 and abs(y - py) / y_range < 0.1:
                dy = -20  # push below the point
                break
        ax.annotate(
            name, (x, y),
            textcoords="offset points",
            xytext=(10, dy),
            fontsize=9,
        )
        placed.append((x, y))

    ax.set_xlabel("Average Total Time (efficiency →)")
    ax.set_ylabel("Max Wait Time (fairness ↓)")
    ax.set_title("Efficiency vs Fairness Trade-off")
    ax.legend()
    ax.grid(True, alpha=0.3)

    path = output_dir / "efficiency_vs_fairness.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    generated.append(path)

    # 3. Summary bar chart
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    avg_totals = [
        PassengerStatistics.from_passengers(comp.results[n].passengers).total_times.avg
        for n in strategy_names
    ]
    max_waits = [
        PassengerStatistics.from_passengers(comp.results[n].passengers).wait_times.max
        for n in strategy_names
    ]

    colors = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336"]

    axes[0].bar(strategy_names, avg_totals, color=colors[: len(strategy_names)])
    axes[0].set_title("Average Total Time (lower = more efficient)")
    axes[0].set_ylabel("Ticks")
    axes[0].tick_params(axis="x", rotation=20)

    axes[1].bar(strategy_names, max_waits, color=colors[: len(strategy_names)])
    axes[1].set_title("Max Wait Time (lower = more fair)")
    axes[1].set_ylabel("Ticks")
    axes[1].tick_params(axis="x", rotation=20)

    fig.suptitle("Strategy Summary", fontsize=14)
    plt.tight_layout()
    path = output_dir / "strategy_summary.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    generated.append(path)

    # 4. Write observations to text file
    obs_path = output_dir / "analysis.txt"
    lines = ["=== Comparative Analysis ===", ""]
    for obs in analysis.observations:
        lines.append(f"  - {obs}")
    lines.append("")
    lines.append(f"Most efficient strategy: {analysis.most_efficient}")
    lines.append(f"Most fair strategy: {analysis.most_fair}")
    obs_path.write_text("\n".join(lines))
    generated.append(obs_path)

    return generated


