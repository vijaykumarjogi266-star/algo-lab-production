"""Health and System Status Schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., description="Overall service status (healthy, degraded, unhealthy)")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Operating environment")
    timestamp: datetime = Field(..., description="Current system timestamp in UTC")


class ReadinessResponse(BaseModel):
    status: str = Field(..., description="Readiness status (ready, not_ready)")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(..., description="Current system timestamp in UTC")
    database: Dict[str, Any] = Field(..., description="Database connectivity status")
    checks: Dict[str, str] = Field(..., description="Individual subsystem readiness states")


class SafetyStatusResponse(BaseModel):
    allow_live_trading: bool
    allow_real_broker_execution: bool
    require_data_validation: bool
    enforce_strict_lookahead_protection: bool
    stage: str
    active_guardrails: List[str]


class SystemInfoResponse(BaseModel):
    name: str
    version: str
    environment: str
    timestamp: datetime
    safety_status: SafetyStatusResponse
    core_principles_count: int


class MarketFeedStatusResponse(BaseModel):
    provider_name: str = Field(default="ANGEL_ONE", description="Provider adapter name")
    data_source: str = Field(default="MOCK", description="Data source: ANGEL_ONE / OTHER_PROVIDER / CACHE / MOCK")
    collection_mode: str = Field(default="FORWARD", description="Collection mode: FORWARD / REPLAY")
    feed_health: str = Field(default="UNVERIFIED", description="Feed health: HEALTHY / STALE / DISCONNECTED / UNVERIFIED")
    latest_event_timestamp_utc: Optional[datetime] = Field(default=None, description="Latest tick timestamp")
    receive_timestamp_utc: Optional[datetime] = Field(default=None, description="Latest receipt timestamp")
    real_connection_observed: bool = Field(default=False, description="Whether real authenticated connection was verified")
    active_subscriptions: List[str] = Field(default_factory=list, description="Subscribed symbols/tokens")
    execution_mode: str = Field(default="PAPER", description="Execution mode: NONE / PAPER")
    accounting_validation_status: str = Field(default="UNVALIDATED", description="VERIFIED / UNVALIDATED")
    accounting_blockers: List[str] = Field(default_factory=list, description="List of unresolved accounting discrepancies")
    code_version: str = Field(default="2026-09-25.v1", description="Adapter build revision")
    diagnostic_details: str = Field(default="", description="Diagnostic details on connectivity and validation")
