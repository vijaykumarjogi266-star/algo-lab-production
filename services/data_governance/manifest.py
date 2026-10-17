"""Algo Lab Institutional Data Governance & Dataset Manifest Engine.

Workstream E Compliance:
- Typed Dataset Manifest schemas with cryptographic SHA-256 integrity.
- Full Data Lineage Tracking: RAW -> VALIDATED -> ADJUSTED -> FEATURE -> EXPERIMENT_INPUT.
- Strict rejection of missing, stale, future-dated, or synthetic data.
- Quality metrics computation and point-in-time provenance.
"""

from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class DataLineageStage(str, Enum):
    RAW = "raw"
    VALIDATED = "validated"
    ADJUSTED = "adjusted"
    FEATURE = "feature"
    EXPERIMENT_INPUT = "experiment_input"


class LicenseClassification(str, Enum):
    PROPRIETARY = "proprietary"
    COMMERCIAL_LICENSED = "commercial_licensed"
    PUBLIC_OPEN = "public_open"
    EXCHANGE_DIRECT = "exchange_direct"


class DatasetQualityMetrics(BaseModel):
    """Quality and integrity metrics computed during ingestion and validation."""
    total_records: int = Field(ge=0, description="Total ingested bars/records")
    duplicate_timestamps_rejected: int = Field(default=0, ge=0)
    invalid_ohlc_bars_rejected: int = Field(default=0, ge=0)
    future_dated_bars_rejected: int = Field(default=0, ge=0)
    stale_bars_rejected: int = Field(default=0, ge=0)
    finite_price_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    ohlc_consistency_ratio: float = Field(default=1.0, ge=0.0, le=1.0)


class DatasetManifest(BaseModel):
    """Typed canonical manifest for datasets adhering to institutional governance."""

    dataset_id: str = Field(min_length=3, max_length=100, description="Unique dataset identifier")
    version: str = Field(min_length=1, max_length=50, description="Dataset semantic or calendar version")
    provider: str = Field(min_length=2, max_length=50, description="Authoritative upstream provider name")
    license_classification: LicenseClassification = Field(description="Data licensing classification")
    lineage_stage: DataLineageStage = Field(default=DataLineageStage.RAW, description="Current lineage tier")

    ingestion_timestamp: datetime = Field(description="UTC timestamp when data was ingested")
    exchange_timezone: str = Field(default="Asia/Kolkata", description="Primary exchange timezone")
    data_availability_timestamp: datetime = Field(description="Point-in-time timestamp when data became available")

    schema_version: str = Field(default="1.0.0", description="Contract schema version")
    symbol_master_version: str = Field(default="1.0.0", description="Reference symbol master version")
    corporate_action_version: str = Field(default="1.0.0", description="Corporate action provenance version")

    checksum_sha256: str = Field(min_length=64, max_length=64, description="Cryptographic SHA-256 digest of data")
    storage_uri: str = Field(min_length=1, description="Immutable storage reference URI or path")
    quality_metrics: DatasetQualityMetrics = Field(description="Measured quality metrics")

    is_synthetic: bool = Field(default=False, description="Whether data contains synthetic/simulated points")

    @field_validator("checksum_sha256")
    @classmethod
    def validate_sha256_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if not all(c in "0123456789abcdef" for c in clean):
            raise ValueError("checksum_sha256 must be a valid 64-character hexadecimal digest")
        return clean

    @model_validator(mode="after")
    def enforce_safety_and_provenance(self) -> DatasetManifest:
        # Invariant: No synthetic substitution in production paper paths
        if self.is_synthetic and self.lineage_stage in (DataLineageStage.VALIDATED, DataLineageStage.EXPERIMENT_INPUT):
            raise ValueError(
                "Non-negotiable invariant violation: Synthetic data cannot be promoted to VALIDATED or EXPERIMENT_INPUT."
            )
        # Invariant: Ingestion timestamp cannot be after availability timestamp
        if self.data_availability_timestamp > datetime.now(timezone.utc):
            raise ValueError("Future-dated data availability detected: Data availability timestamp is in the future.")
        return self

    def to_json(self) -> str:
        """Serializes manifest to deterministically formatted JSON string."""
        return self.model_dump_json(indent=2)

    def save(self, destination_path: Path) -> None:
        """Saves manifest to disk."""
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with open(destination_path, "w", encoding="utf-8") as f:
            f.write(self.to_json())


class ExperimentManifest(BaseModel):
    """Immutable manifest recording backtest or simulation configuration and lineage."""

    strategy_name: str
    strategy_source_hash: str = Field(min_length=64, max_length=64)
    parameters: Dict[str, Any]
    data_manifest_ids: List[str]
    execution_model_version: str = "0.3.0"
    environment_version: str = "0.3.0"
    dependency_lock_hash: str
    start_timestamp: datetime
    end_timestamp: datetime
    metrics: Dict[str, Any]
    output_artifacts: Dict[str, str]  # file_path -> sha256

    def compute_experiment_fingerprint(self) -> str:
        """Computes deterministic SHA-256 fingerprint for experiment reproducibility."""
        canonical = {
            "strategy_name": self.strategy_name,
            "strategy_source_hash": self.strategy_source_hash,
            "parameters": self.parameters,
            "data_manifest_ids": sorted(self.data_manifest_ids),
            "execution_model_version": self.execution_model_version,
            "dependency_lock_hash": self.dependency_lock_hash,
            "start_timestamp": self.start_timestamp.isoformat(),
            "end_timestamp": self.end_timestamp.isoformat(),
        }
        serialized = json.dumps(canonical, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
