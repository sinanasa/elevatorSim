"""Statistical analysis of simulation results.

Pure computation — takes passenger data, returns statistics.
No I/O coupling. Used by both the output writer and the comparison report.
"""

from __future__ import annotations

from dataclasses import dataclass

from elevator_sim.domain.model import Passenger, PassengerStatus


@dataclass(frozen=True)
class TimeStats:
    """Descriptive statistics for a set of time measurements."""

    min_value: int
    max_value: int
    avg: float
    median: float
    p95: int
    std_dev: float
    count: int

    @classmethod
    def from_values(cls, values: list[int]) -> TimeStats:
        if not values:
            return cls(min_value=0, max_value=0, avg=0.0, median=0.0, p95=0, std_dev=0.0, count=0)

        sorted_v = sorted(values)
        n = len(sorted_v)
        avg = sum(sorted_v) / n
        median = (
            float(sorted_v[n // 2])
            if n % 2 == 1
            else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2.0
        )
        p95_idx = min(int(n * 0.95), n - 1)
        std_dev = (sum((v - avg) ** 2 for v in sorted_v) / n) ** 0.5

        return cls(
            min_value=sorted_v[0],
            max_value=sorted_v[-1],
            avg=avg,
            median=median,
            p95=sorted_v[p95_idx],
            std_dev=std_dev,
            count=n,
        )


@dataclass(frozen=True)
class PassengerStatistics:
    """Complete statistics for a simulation run's passenger outcomes."""

    total_passengers: int
    delivered_passengers: int
    wait_times: TimeStats
    travel_times: TimeStats
    total_times: TimeStats

    @classmethod
    def from_passengers(cls, passengers: tuple[Passenger, ...] | list[Passenger]) -> PassengerStatistics:
        delivered = [
            p for p in passengers
            if p.status == PassengerStatus.DELIVERED
        ]

        wait_vals = [p.wait_time for p in delivered if p.wait_time is not None]
        travel_vals = [p.travel_time for p in delivered if p.travel_time is not None]
        total_vals = [p.total_time for p in delivered if p.total_time is not None]

        return cls(
            total_passengers=len(passengers),
            delivered_passengers=len(delivered),
            wait_times=TimeStats.from_values(wait_vals),
            travel_times=TimeStats.from_values(travel_vals),
            total_times=TimeStats.from_values(total_vals),
        )
