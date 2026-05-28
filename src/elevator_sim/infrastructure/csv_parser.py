"""CSV input parser with Pydantic validation.

Adapts external CSV format into domain PassengerRequest value objects.
Validates each row at the I/O boundary — invalid rows are rejected with
clear error messages before they reach the domain.
"""

from __future__ import annotations

import csv
from pathlib import Path

from pydantic import BaseModel, field_validator

from elevator_sim.domain.model import InvalidRequestError, PassengerRequest


class CsvRow(BaseModel):
    """Pydantic model for a single CSV row — validates at the I/O boundary."""

    time: int
    id: str
    source: int
    dest: int

    @field_validator("time")
    @classmethod
    def time_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"time must be >= 0, got {v}")
        return v

    @field_validator("source", "dest")
    @classmethod
    def floor_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"floor must be >= 1, got {v}")
        return v

    def to_domain(self) -> PassengerRequest:
        """Convert to domain value object."""
        return PassengerRequest(
            request_time=self.time,
            passenger_id=self.id,
            source=self.source,
            dest=self.dest,
        )


def parse_csv(path: Path, num_floors: int | None = None) -> list[PassengerRequest]:
    """Parse a CSV file into a list of PassengerRequest value objects.

    Args:
        path: Path to the CSV file.
        num_floors: If provided, validate that floors are within bounds.

    Returns:
        List of PassengerRequest, sorted by request_time.

    Raises:
        InvalidRequestError: On validation failure.
        FileNotFoundError: If the file doesn't exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")

    requests: list[PassengerRequest] = []
    errors: list[str] = []
    seen_ids: set[str] = set()

    with open(path, newline="") as f:
        reader = csv.DictReader(f)

        for line_num, row in enumerate(reader, start=2):  # +2 for header + 1-indexed
            try:
                parsed = CsvRow(
                    time=int(row["time"]),
                    id=row["id"].strip(),
                    source=int(row["source"]),
                    dest=int(row["dest"]),
                )
            except (ValueError, KeyError) as e:
                errors.append(f"Line {line_num}: {e}")
                continue

            # Duplicate ID check
            if parsed.id in seen_ids:
                errors.append(f"Line {line_num}: duplicate passenger ID '{parsed.id}'")
                continue
            seen_ids.add(parsed.id)

            # Source == dest check
            if parsed.source == parsed.dest:
                errors.append(
                    f"Line {line_num}: passenger '{parsed.id}' has source == dest "
                    f"(floor {parsed.source})"
                )
                continue

            # Floor bounds check
            if num_floors is not None:
                if parsed.source > num_floors:
                    errors.append(
                        f"Line {line_num}: passenger '{parsed.id}' source floor "
                        f"{parsed.source} exceeds num_floors {num_floors}"
                    )
                    continue
                if parsed.dest > num_floors:
                    errors.append(
                        f"Line {line_num}: passenger '{parsed.id}' dest floor "
                        f"{parsed.dest} exceeds num_floors {num_floors}"
                    )
                    continue

            requests.append(parsed.to_domain())

    if errors:
        error_summary = "\n".join(errors[:10])
        suffix = f"\n... and {len(errors) - 10} more errors" if len(errors) > 10 else ""
        raise InvalidRequestError(
            f"CSV validation failed with {len(errors)} error(s):\n{error_summary}{suffix}"
        )

    return sorted(requests, key=lambda r: r.request_time)
