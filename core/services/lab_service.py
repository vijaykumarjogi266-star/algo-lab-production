from core.models.lab import (
    Artifact,
    Experiment,
    Project,
    Research,
    Run,
)
from core.storage.registry import Registry


class LabService:
    """Application service for controlled Algo Lab operations."""

    def __init__(self, registry: Registry | None = None) -> None:
        self.registry = registry or Registry()

    def create_project(
        self,
        project_id: str,
        name: str,
        description: str,
    ) -> Project:
        project = Project(
            id=project_id,
            name=name,
            description=description,
        )

        self.registry.add(project)
        return project

    def create_research(
        self,
        research_id: str,
        project_id: str,
        question: str,
        hypothesis: str,
    ) -> Research:
        if not self.registry.exists(project_id):
            raise KeyError(f"Project not found: {project_id}")

        research = Research(
            id=research_id,
            project_id=project_id,
            question=question,
            hypothesis=hypothesis,
        )

        self.registry.add(research)
        return research

    def create_experiment(
        self,
        experiment_id: str,
        research_id: str,
        name: str,
        objective: str,
        configuration: dict,
    ) -> Experiment:
        if not self.registry.exists(research_id):
            raise KeyError(f"Research not found: {research_id}")

        experiment = Experiment(
            id=experiment_id,
            research_id=research_id,
            name=name,
            objective=objective,
            configuration=configuration,
        )

        self.registry.add(experiment)
        return experiment

    def start_run(
        self,
        run_id: str,
        experiment_id: str,
        parameters: dict,
    ) -> Run:
        if not self.registry.exists(experiment_id):
            raise KeyError(f"Experiment not found: {experiment_id}")

        run = Run(
            id=run_id,
            experiment_id=experiment_id,
            parameters=parameters,
        )

        self.registry.add(run)
        return run

    def register_artifact(
        self,
        artifact_id: str,
        run_id: str,
        artifact_type: str,
        location: str,
        metadata: dict | None = None,
    ) -> Artifact:
        if not self.registry.exists(run_id):
            raise KeyError(f"Run not found: {run_id}")

        artifact = Artifact(
            id=artifact_id,
            run_id=run_id,
            artifact_type=artifact_type,
            location=location,
            metadata=metadata or {},
        )

        self.registry.add(artifact)
        return artifact
