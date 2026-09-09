import unittest

from core.services.lab_service import LabService
from core.storage.registry import Registry


class TestLabService(unittest.TestCase):

    def setUp(self):
        self.service = LabService(Registry())

    def test_create_project(self):
        project = self.service.create_project(
            project_id="project-001",
            name="Research Project",
            description="Service layer test",
        )

        self.assertEqual(project.id, "project-001")
        self.assertTrue(self.service.registry.exists("project-001"))

    def test_research_requires_existing_project(self):
        with self.assertRaises(KeyError):
            self.service.create_research(
                research_id="research-001",
                project_id="missing-project",
                question="Test question",
                hypothesis="Test hypothesis",
            )

    def test_experiment_requires_existing_research(self):
        project = self.service.create_project(
            project_id="project-001",
            name="Research Project",
            description="Service layer test",
        )

        self.service.create_research(
            research_id="research-001",
            project_id=project.id,
            question="Test question",
            hypothesis="Test hypothesis",
        )

        experiment = self.service.create_experiment(
            experiment_id="experiment-001",
            research_id="research-001",
            name="Baseline Experiment",
            objective="Validate service behavior",
            configuration={"mode": "test"},
        )

        self.assertEqual(experiment.research_id, "research-001")

    def test_run_requires_existing_experiment(self):
        with self.assertRaises(KeyError):
            self.service.start_run(
                run_id="run-001",
                experiment_id="missing-experiment",
                parameters={"seed": 42},
            )

    def test_artifact_requires_existing_run(self):
        with self.assertRaises(KeyError):
            self.service.register_artifact(
                artifact_id="artifact-001",
                run_id="missing-run",
                artifact_type="test",
                location="artifacts/test.json",
            )

    def test_complete_basic_lifecycle(self):
        project = self.service.create_project(
            project_id="project-001",
            name="Research Project",
            description="Lifecycle test",
        )

        research = self.service.create_research(
            research_id="research-001",
            project_id=project.id,
            question="Does the lifecycle work?",
            hypothesis="All valid objects can be connected.",
        )

        experiment = self.service.create_experiment(
            experiment_id="experiment-001",
            research_id=research.id,
            name="Lifecycle Experiment",
            objective="Test the complete object chain",
            configuration={"mode": "test"},
        )

        run = self.service.start_run(
            run_id="run-001",
            experiment_id=experiment.id,
            parameters={"seed": 42},
        )

        artifact = self.service.register_artifact(
            artifact_id="artifact-001",
            run_id=run.id,
            artifact_type="test-result",
            location="artifacts/test-result.json",
            metadata={"passed": True},
        )

        self.assertEqual(artifact.run_id, run.id)
        self.assertEqual(self.service.registry.count(), 5)


if __name__ == "__main__":
    unittest.main()
