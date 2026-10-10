"""
Market Tick Event & Ingestion Pipeline Schemas.
Conforms to Canonical Data Standards (Stage 6):
- Strictly UTC timezone-aware timestamps
- Positive prices, non-negative quantities and volumes
- Quality flags: VALID, SUSPICIOUS, QUARANTINED
"""

from datetime import datetime, timezone
import math
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator, model_validator
from data.schemas.contracts import DataQualityStatus, Exchange


class DataSource(str, Enum):
    ANGEL_ONE = "ANGEL_ONE"
    OTHER_PROVIDER = "OTHER_PROVIDER"
    CACHE = "CACHE"
    MOCK = "MOCK"


class CollectionMode(str, Enum):
    FORWARD = "FORWARD"
    REPLAY = "REPLAY"


class FeedHealth(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    UNVERIFIED = "UNVERIFIED"


class ExecutionMode(str, Enum):
    NONE = "NONE"
    PAPER = "PAPER"


class AccountingValidationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNVALIDATED = "UNVALIDATED"


class MarketDataProvenance(BaseModel):
    """Complete provenance and audit metadata for market data runs and streams."""
    data_source: DataSource = Field(default=DataSource.MOCK, description="Primary data source")
    collection_mode: CollectionMode = Field(default=CollectionMode.FORWARD, description="Data collection mode")
    feed_health: FeedHealth = Field(default=FeedHealth.UNVERIFIED, description="Current health status of the feed")
    execution_mode: ExecutionMode = Field(default=ExecutionMode.NONE, description="Execution environment mode")
    accounting_validation: AccountingValidationStatus = Field(
        default=AccountingValidationStatus.UNVALIDATED,
        description="Accounting ledger reconciliation status"
    )
    provider_name: str = Field(default="ANGEL_ONE", description="Provider adapter identifier")
    feed_received_at: Optional[datetime] = Field(default=None, description="Timestamp of most recent local receipt")
    latest_event_at: Optional[datetime] = Field(default=None, description="Timestamp of most recent exchange tick")
    real_connection_observed: bool = Field(default=False, description="Whether an authentic upstream socket/REST connection was observed")
    active_subscriptions: List[str] = Field(default_factory=list, description="Currently subscribed symbols or tokens")
    accounting_blockers: List[str] = Field(
        default_factory=lambda: [
            "UNRECONCILED_HISTORICAL_SOAK_GST_ARITHMETIC",
            "INCONSISTENT_TURNOVER_LEVY_DERIVATION",
            "BASELINE_TRADE_LOG_ABSENCE_NOT_RECONSTRUCTABLE",
        ],
        description="Outstanding accounting blockers preventing strategy promotion"
    )
    code_version: str = Field(default="2026-09-25.v1", description="Adapter code revision")


class MarketTickEvent(BaseModel):
    """Normalized real-time tick event emitted by market data providers."""

    provider: str = Field(default="ANGEL_ONE", description="Provider identifier")
    symbol: str = Field(min_length=1, max_length=30, description="Canonical symbol")
    token: str = Field(min_length=1, max_length=20, description="Provider instrument token")
    exchange: str = Field(default="NSE", description="Exchange identifier")
    
    exchange_timestamp: datetime = Field(description="Exchange generation timestamp (UTC)")
    receive_timestamp: datetime = Field(description="Local receipt timestamp (UTC)")
    sequence_id: int = Field(ge=0, description="Monotonically increasing sequence or packet counter")

    last_traded_price: float = Field(gt=0.0, description="Last traded price in INR")
    last_traded_quantity: int = Field(ge=0, description="Last trade lot quantity")
    cumulative_volume: int = Field(ge=0, description="Cumulative day volume traded")
    
    average_traded_price: Optional[float] = Field(default=None, gt=0.0, description="Volume-weighted average price")
    total_turnover_inr: Optional[float] = Field(default=None, ge=0.0, description="Total traded value in INR")
    
    best_bid: Optional[float] = Field(default=None, gt=0.0, description="Top of book bid price")
    best_ask: Optional[float] = Field(default=None, gt=0.0, description="Top of book ask price")
    
    subscription_mode: int = Field(default=2, ge=1, le=3, description="1=LTP, 2=Quote, 3=SnapQuote")
    quality_status: DataQualityStatus = Field(default=DataQualityStatus.VALID)
    session_id: str = Field(default="default_session", description="Feed session identifier")
    
    # Provenance fields
    data_source: DataSource = Field(default=DataSource.MOCK)
    collection_mode: CollectionMode = Field(default=CollectionMode.FORWARD)

    @field_validator("exchange_timestamp", "receive_timestamp")
    @classmethod
    def validate_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC required)")
        return v.astimezone(timezone.utc)

    @field_validator("last_traded_price", "average_traded_price", "best_bid", "best_ask", mode="before")
    @classmethod
    def validate_no_nan_or_inf(cls, v: Any) -> Any:
        if v is not None and isinstance(v, (int, float)):
            if math.isnan(v) or math.isinf(v):
                raise ValueError("NaN or Infinite values strictly prohibited in market data")
        return v

    @model_validator(mode="after")
    def validate_bid_ask_spread(self) -> "MarketTickEvent":
        if self.best_bid is not None and self.best_ask is not None:
            if self.best_bid > self.best_ask:
                # Crossed market detection
                self.quality_status = DataQualityStatus.SUSPICIOUS
        return self
