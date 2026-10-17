"""Algo Lab Core Configuration.

Enforces strict environment configuration, database connection parameters,
and non-negotiable safety constraints (e.g. no live trading, mandatory validation).
"""

from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.version import (
    __version__,
    LIFECYCLE_STATE,
    PAPER_ONLY_EXECUTION_POLICY,
    LIVE_TRADING_ENABLED as CANONICAL_LIVE_DISABLED,
    REAL_BROKER_EXECUTION_ENABLED as CANONICAL_BROKER_DISABLED,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Core metadata
    PROJECT_NAME: str = "Algo Lab Quantitative Research OS"
    PROJECT_VERSION: str = __version__
    LIFECYCLE_STATE: str = LIFECYCLE_STATE
    PAPER_ONLY: bool = PAPER_ONLY_EXECUTION_POLICY
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server binding (Private loopback by default)
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"

    # Internal API Authentication
    INTERNAL_API_SECRET: str = Field(
        default="stage27-v1-internal-key-9982",
        description="Internal secret token for loopback API control endpoints.",
    )
    ENFORCE_INTERNAL_AUTH: bool = Field(
        default=True,
        description="Require authentication for state-mutating control endpoints.",
    )

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Database
    POSTGRES_USER: str = "algolab"
    POSTGRES_PASSWORD: str = "algolab_secret"
    POSTGRES_DB: str = "algolab"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = "postgresql+asyncpg://algolab:algolab_secret@localhost:5432/algolab"
    DATABASE_URL_SYNC: str = "postgresql://algolab:algolab_secret@localhost:5432/algolab"

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # "json" or "text"

    # NON-NEGOTIABLE SAFETY CONSTRAINTS
    ALLOW_LIVE_TRADING: bool = Field(
        default=False,
        description="Strictly disallow live trading execution during research & development.",
    )
    ALLOW_REAL_BROKER_EXECUTION: bool = Field(
        default=False,
        description="Never allow connection to real broker accounts for automated execution.",
    )
    LIVE_TRADING_ENABLED: bool = Field(
        default=False,
        description="Non-negotiable invariant: must remain False.",
    )
    REAL_BROKER_EXECUTION_ENABLED: bool = Field(
        default=False,
        description="Non-negotiable invariant: must remain False.",
    )
    REQUIRE_DATA_VALIDATION: bool = Field(
        default=True,
        description="Mandate that corrupted or unvalidated data rejects strategy calculations.",
    )
    ENFORCE_STRICT_LOOKAHEAD_PROTECTION: bool = Field(
        default=True,
        description="Mandate that all backtests only use data available strictly at or before decision time.",
    )

    @field_validator(
        "ALLOW_LIVE_TRADING",
        "ALLOW_REAL_BROKER_EXECUTION",
        "LIVE_TRADING_ENABLED",
        "REAL_BROKER_EXECUTION_ENABLED",
    )
    @classmethod
    def validate_safety_lock(cls, v: bool) -> bool:
        if v is True:
            raise ValueError(
                "CRITICAL SAFETY VIOLATION: Algo Lab strictly prohibits enabling live trading or real broker execution."
            )
        return False


settings = Settings()
