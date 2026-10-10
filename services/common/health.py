"""Algo Lab Subsystem Observability & Health Contracts.

Adheres to Requirement 10:
Every major component must expose health information.
Subsystems: DATA_FEED, SESSION, SCANNER, STRATEGY, RISK, PAPER_EXECUTION, ACCOUNTING, PERSISTENCE, RECONCILIATION
States: STARTING, RUNNING, DEGRADED, STOPPING, STOPPED, ERROR
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ComponentName(str, Enum):
    DATA_FEED = "DATA_FEED"
    SESSION = "SESSION"
    SCANNER = "SCANNER"
    STRATEGY = "STRATEGY"
    RISK = "RISK"
    PAPER_EXECUTION = "PAPER_EXECUTION"
    ACCOUNTING = "ACCOUNTING"
    PERSISTENCE = "PERSISTENCE"
    RECONCILIATION = "RECONCILIATION"


class ComponentOperationalState(str, Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class SubsystemHealth(BaseModel):
    """Deterministic operational health state for a single system component."""

    component_name: ComponentName
    state: ComponentOperationalState = ComponentOperationalState.STOPPED
    message: str = "Component initialized"
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: Dict[str, Any] = Field(default_factory=dict)

    def update_state(
        self,
        state: ComponentOperationalState,
        message: str = "",
        metrics: Optional[Dict[str, Any]] = None,
    ):
        self.state = state
        if message:
            self.message = message
        if metrics is not None:
            self.metrics.update(metrics)
        self.last_updated_at = datetime.now(timezone.utc)
