import unittest

from core.validation.provenance import ProvenanceValidator


class TestProvenanceValidator(unittest.TestCase):

    def setUp(self):
        self.validator = ProvenanceValidator()

    def valid_metadata(self):
        return {
            "run_id": "run-001",
            "status": "COMPLETED",
            "executed_at": "2026-01-01T12:00:00+00:00",
            "parameters_fingerprint": "abc123",
            "result_fingerprint": "def456",
        }

    def test_complete_provenance_passes(self):
        result = self.validator.validate(
            self.valid_metadata()
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.errors, [])

    def test_missing_run_id_fails(self):
        metadata = self.valid_metadata()
        del metadata["run_id"]

        result = self.validator.validate(metadata)

        self.assertFalse(result.passed)
        self.assertIn(
            "Missing required provenance field: run_id",
            result.errors,
        )

    def test_missing_parameter_fingerprint_fails(self):
        metadata = self.valid_metadata()
        del metadata["parameters_fingerprint"]

        result = self.validator.validate(metadata)

        self.assertFalse(result.passed)
        self.assertIn(
            "Missing required provenance field: parameters_fingerprint",
            result.errors,
        )

    def test_empty_fingerprint_fails(self):
        metadata = self.valid_metadata()
        metadata["result_fingerprint"] = ""

        result = self.validator.validate(metadata)

        self.assertFalse(result.passed)
        self.assertIn(
            "Result fingerprint must not be empty.",
            result.errors,
        )


if __name__ == "__main__":
    unittest.main()
