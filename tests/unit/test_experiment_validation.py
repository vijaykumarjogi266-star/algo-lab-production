import unittest

from core.validation.experiment_validation import ExperimentValidator


class TestExperimentValidator(unittest.TestCase):

    def setUp(self):
        self.validator = ExperimentValidator()

    def valid_configuration(self):
        return {
            "objective": "Test controlled execution",
            "hypothesis": "Identical inputs produce identical results",
            "data_source": "synthetic-test-data",
            "parameters": {
                "seed": 42,
            },
        }

    def test_valid_configuration_passes(self):
        result = self.validator.validate_configuration(
            self.valid_configuration()
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.errors, [])

    def test_missing_required_field_fails(self):
        configuration = self.valid_configuration()
        del configuration["hypothesis"]

        result = self.validator.validate_configuration(configuration)

        self.assertFalse(result.passed)
        self.assertIn(
            "Missing required field: hypothesis",
            result.errors,
        )

    def test_empty_objective_fails(self):
        configuration = self.valid_configuration()
        configuration["objective"] = "   "

        result = self.validator.validate_configuration(configuration)

        self.assertFalse(result.passed)
        self.assertIn(
            "Objective must not be empty.",
            result.errors,
        )

    def test_parameters_must_be_dictionary(self):
        configuration = self.valid_configuration()
        configuration["parameters"] = ["seed", 42]

        result = self.validator.validate_configuration(configuration)

        self.assertFalse(result.passed)
        self.assertIn(
            "Parameters must be a dictionary.",
            result.errors,
        )


if __name__ == "__main__":
    unittest.main()
