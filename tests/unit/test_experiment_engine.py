import unittest

from core.models.lab import Experiment, Project, Research, Run
from core.services.experiment_engine import ExperimentEngine, fingerprint
from core.storage.registry import Registry


class TestExperimentEngine(unittest.TestCase):

    def setUp(self):
        self.registry = Registry()

        project = Project(
            id="project-001",
            name="Engine Test",
            description="Experiment engine validation",
        )
        self.registry.add(project)

        research = Research(
            id="research-001",
            project_id=project.id,
            question="Does execution remain reproducible?",
            hypothesis="Identical parameters produce identical fingerprints.",
        )
        self.registry.add(research)

        experiment = Experiment(
            id="experiment-001",
            research_id=research.id,
            name="Engine Experiment",
            objective="Validate controlled execution.",
            configuration={"mode": "test"},
        )
        self.registry.add(experiment)

    def test_fingerprint_is_deterministic(self):
        value = {"b": 2, "a": 1}

        self.assertEqual(
            fingerprint(value),
            fingerprint({"a": 1, "b": 2}),
        )

    def test_execute_run(self):
        run = Run(
            id="run-001",
            experiment_id="experiment-001",
            parameters={"seed": 42},
        )
        self.registry.add(run)

        engine = ExperimentEngine(
            registry=self.registry,
            executor=lambda parameters: {
                "value": parameters["seed"] * 2
            },
        )

        result = engine.execute(run)

        self.assertEqual(result.run_id, "run-001")
        self.assertEqual(result.status, "COMPLETED")
        self.assertEqual(result.output["value"], 84)
        self.assertEqual(
            result.parameters_fingerprint,
            fingerprint({"seed": 42}),
        )

    def test_same_run_cannot_execute_twice(self):
        run = Run(
            id="run-002",
            experiment_id="experiment-001",
            parameters={"seed": 10},
        )
        self.registry.add(run)

        engine = ExperimentEngine(
            registry=self.registry,
            executor=lambda parameters: parameters["seed"],
        )

        engine.execute(run)

        with self.assertRaises(ValueError):
            engine.execute(run)

    def test_create_artifact_contains_provenance(self):
        run = Run(
            id="run-003",
            experiment_id="experiment-001",
            parameters={"seed": 7},
        )
        self.registry.add(run)

        engine = ExperimentEngine(
            registry=self.registry,
            executor=lambda parameters: parameters["seed"] + 1,
        )

        result = engine.execute(run)

        artifact = engine.create_artifact(
            artifact_id="artifact-001",
            result=result,
            artifact_type="execution-result",
            location="artifacts/run-003.json",
        )

        self.assertEqual(artifact.run_id, "run-003")
        self.assertEqual(
            artifact.metadata["parameters_fingerprint"],
            result.parameters_fingerprint,
        )
        self.assertEqual(
            artifact.metadata["result_fingerprint"],
            result.result_fingerprint,
        )
        self.assertTrue(
            self.registry.exists("artifact-001")
        )

    def test_unregistered_run_cannot_execute(self):
        run = Run(
            id="run-unregistered",
            experiment_id="experiment-001",
            parameters={"seed": 1},
        )

        engine = ExperimentEngine(
            registry=self.registry,
            executor=lambda parameters: parameters["seed"],
        )

        with self.assertRaises(KeyError):
            engine.execute(run)

    def test_run_with_missing_experiment_cannot_execute(self):
        run = Run(
            id="run-missing-experiment",
            experiment_id="experiment-missing",
            parameters={"seed": 1},
        )
        self.registry.add(run)

        engine = ExperimentEngine(
            registry=self.registry,
            executor=lambda parameters: parameters["seed"],
        )

        with self.assertRaises(KeyError):
            engine.execute(run)


if __name__ == "__main__":
    unittest.main()
