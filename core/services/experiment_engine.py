from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
import hashlib
import json

from core.models.lab import Artifact, Experiment, Project, Research, Run
from core.storage.registry import Registry


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def fingerprint(value: Any) -> str:
    payload = canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class ExecutionResult:
    run_id: str
    status: str
    output: Any
    executed_at: datetime
    parameters_fingerprint: str
    result_fingerprint: str


@dataclass
class ExperimentEngine:
    registry: Registry
    executor: Callable[[dict], Any]
    results: dict[str, ExecutionResult] = field(default_factory=dict)

    def _validate_run_chain(self, run: Run) -> None:
        if not self.registry.exists(run.id):
            raise KeyError(f"Run not found: {run.id}")

        experiment = self.registry.get(run.experiment_id)

        if not isinstance(experiment, Experiment):
            raise TypeError(
                f"Registered object is not an Experiment: {run.experiment_id}"
            )

        research = self.registry.get(experiment.research_id)

        if not isinstance(research, Research):
            raise TypeError(
                f"Registered object is not Research: {experiment.research_id}"
            )

        project = self.registry.get(research.project_id)

        if not isinstance(project, Project):
            raise TypeError(
                f"Registered object is not Project: {research.project_id}"
            )

    def execute(self, run: Run) -> ExecutionResult:
        self._validate_run_chain(run)

        if run.id in self.results:
            raise ValueError(f"Run has already been executed: {run.id}")

        parameters_hash = fingerprint(run.parameters)

        output = self.executor(run.parameters)

        result = ExecutionResult(
            run_id=run.id,
            status="COMPLETED",
            output=output,
            executed_at=utc_now(),
            parameters_fingerprint=parameters_hash,
            result_fingerprint=fingerprint(output),
        )

        self.results[run.id] = result
        return result

    def create_artifact(
        self,
        artifact_id: str,
        result: ExecutionResult,
        artifact_type: str,
        location: str,
    ) -> Artifact:
        metadata = {
            "run_id": result.run_id,
            "status": result.status,
            "executed_at": result.executed_at.isoformat(),
            "parameters_fingerprint": result.parameters_fingerprint,
            "result_fingerprint": result.result_fingerprint,
        }

        artifact = Artifact(
            id=artifact_id,
            run_id=result.run_id,
            artifact_type=artifact_type,
            location=location,
            metadata=metadata,
        )

        self.registry.add(artifact)
        return artifact
