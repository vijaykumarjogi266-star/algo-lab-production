from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Status(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


class DecisionType(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    HOLD = "hold"
    PROMOTE = "promote"
    QUARANTINE = "quarantine"


@dataclass
class Project:
    id: str
    name: str
    description: str
    status: Status = Status.DRAFT
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Research:
    id: str
    project_id: str
    question: str
    hypothesis: str
    status: Status = Status.DRAFT
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Experiment:
    id: str
    research_id: str
    name: str
    objective: str
    configuration: dict[str, Any]
    status: Status = Status.DRAFT
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Run:
    id: str
    experiment_id: str
    parameters: dict[str, Any]
    status: Status = Status.DRAFT
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass
class Artifact:
    id: str
    run_id: str
    artifact_type: str
    location: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Review:
    id: str
    artifact_id: str
    reviewer: str
    findings: str
    approved: bool
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class Gate:
    id: str
    name: str
    requirement: str
    passed: bool = False


@dataclass
class Decision:
    id: str
    gate_id: str
    decision: DecisionType
    reason: str
    decided_by: str
    created_at: datetime = field(default_factory=utc_now)
