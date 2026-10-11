"""
OMS Project - Schemas & Data Contracts
Defines OrderIntent and Order State Machine Data Models
"""

import time
import uuid
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class ShutdownState(str, Enum):
    RUNNING = "RUNNING"
    SHUTDOWN_REQUESTED = "SHUTDOWN_REQUESTED"
    DRAINING = "DRAINING"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECOVERING = "RECOVERING"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    STOPPED = "STOPPED"
    FAILED_SAFE = "FAILED_SAFE"



class OrderState(str, Enum):
    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    RISK_RESERVED = "RISK_RESERVED"
    SUBMITTING = "SUBMITTING"
    SUBMISSION_UNKNOWN = "SUBMISSION_UNKNOWN"
    SUBMITTED = "SUBMITTED"
    LIVE = "LIVE"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCEL_UNKNOWN = "CANCEL_UNKNOWN"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


class OrderIntent(BaseModel):
    request_id: str = Field(..., description="Unique Request ID for idempotency")
    strategy_id: str = Field(..., description="Target Strategy Identifier")
    symbol: str = Field(..., description="Trading Instrument Symbol (e.g. RELIANCE, NIFTY)")
    side: OrderSide = Field(..., description="Order Side: BUY or SELL")
    qty: float = Field(..., gt=0, description="Order Quantity")
    price: float = Field(..., gt=0, description="Order Price")
    order_type: OrderType = Field(default=OrderType.MARKET, description="Order Type: MARKET or LIMIT")
    reduce_only: bool = Field(default=False, description="Whether this is a reduce-only closing order")
    timestamp: float = Field(default_factory=time.time, description="Client creation timestamp")
    expiry: float = Field(default_factory=lambda: time.time() + 30.0, description="Order Expiry timestamp")
    signature: str = Field(..., description="Cryptographic signature of the intent")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        s = v.strip().upper()
        if not s:
            raise ValueError("Symbol cannot be empty")
        return s


class OrderResult(BaseModel):
    request_id: str
    order_id: str
    strategy_id: str
    symbol: str
    side: str
    qty: float
    price: float
    status: OrderState
    message: str
    timestamp: float = Field(default_factory=time.time)
    reserved_value: float = 0.0
    execution_tx: Optional[str] = None


class NormalizedTick(BaseModel):
    symbol: str
    price: float
    volume: float
    timestamp: float
    utc_iso: str
    sequence: int

