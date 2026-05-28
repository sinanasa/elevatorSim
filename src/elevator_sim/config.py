"""Typed configuration via Pydantic Settings.

Loads from environment variables (prefixed ELEVATOR_SIM_) or CLI arguments.
Validates all parameters before they reach the domain.
"""

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class SimulationSettings(BaseSettings):
    """Simulation configuration loaded from env vars or CLI args.

    All fields have sensible defaults. Override via environment variables
    with the ELEVATOR_SIM_ prefix, e.g.:
        ELEVATOR_SIM_NUM_ELEVATORS=8
    """

    model_config = {"env_prefix": "ELEVATOR_SIM_"}

    num_elevators: int = Field(default=6, ge=1, le=100, description="Number of elevators")
    num_floors: int = Field(default=50, ge=2, le=10000, description="Number of floors")
    max_capacity: int = Field(default=10, ge=1, le=100, description="Max passengers per elevator")
    strategy: str = Field(default="nearest_car", description="Dispatch strategy name")
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json or console")

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        from elevator_sim.domain.strategies import available_strategies

        valid = available_strategies()
        if v not in valid and v != "all":
            raise ValueError(f"Unknown strategy '{v}'. Available: {', '.join(valid)}, all")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"Invalid log level '{v}'. Valid: {', '.join(sorted(valid))}")
        return upper

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, v: str) -> str:
        valid = {"json", "console"}
        if v.lower() not in valid:
            raise ValueError(f"Invalid log format '{v}'. Valid: {', '.join(sorted(valid))}")
        return v.lower()
