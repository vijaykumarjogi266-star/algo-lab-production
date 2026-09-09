import unittest

from core.models.lab import (
    Artifact,
    Decision,
    DecisionType,
    Experiment,
    Gate,
    Project,
    Research,
    Review,
    Run,
    Status,
)


class TestLabModels(unittest.TestCase):

    def test_project_creation(self):
        project = Project(
            id="project-001",
            name="Test Project",
            description="Core model validation",
        )

        self.assertEqual(project.id, "project-001")
        self.assertEqual(project.status, Status.DRAFT)

    def test_research_belongs_to_project(self):
        research = Research(
            id="research-001",
            project_id="project-001",
            question="Does the experiment behave as expected?",
            hypothesis="The system should pass the baseline test.",
        )

        self.assertEqual(research.project_id, "project-001")

    def test_experiment_and_run(self):
        experiment = Experiment(
            id="experiment-001",
            research_id="research-001",
            name="Baseline Experiment",
            objective="Validate the experiment framework.",
            configuration={"mode": "test"},
        )

        run = Run(
            id="run-001",
            experiment_id=experiment.id,
            parameters={"seed": 42},
        )

        self.assertEqual(run.experiment_id, experiment.id)
        self.assertEqual(run.parameters["seed"], 42)

    def test_artifact_review_gate_decision(self):
        artifact = Artifact(
            id="artifact-001",
            run_id="run-001",
            artifact_type="test-result",
            location="artifacts/test-result.json",
        )

        review = Review(
            id="review-001",
            artifact_id=artifact.id,
            reviewer="test-reviewer",
            findings="Baseline validation passed.",
            approved=True,
        )

        gate = Gate(
            id="gate-001",
            name="Baseline Gate",
            requirement="Required tests must pass.",
            passed=True,
        )

        decision = Decision(
            id="decision-001",
            gate_id=gate.id,
            decision=DecisionType.ACCEPT,
            reason="All baseline requirements passed.",
            decided_by="test-reviewer",
        )

        self.assertTrue(review.approved)
        self.assertTrue(gate.passed)
        self.assertEqual(decision.decision, DecisionType.ACCEPT)


if __name__ == "__main__":
    unittest.main()
