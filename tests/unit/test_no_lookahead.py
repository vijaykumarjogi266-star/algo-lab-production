import unittest
from datetime import datetime, timezone

from core.validation.no_lookahead import NoLookaheadValidator


class TestNoLookaheadValidator(unittest.TestCase):

    def setUp(self):
        self.validator = NoLookaheadValidator()
        self.evaluation_time = datetime(
            2026,
            1,
            1,
            12,
            0,
            tzinfo=timezone.utc,
        )

    def test_historical_data_passes(self):
        timestamps = [
            datetime(2025, 12, 31, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 11, 59, tzinfo=timezone.utc),
        ]

        result = self.validator.validate(
            timestamps,
            self.evaluation_time,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.errors, [])

    def test_data_at_evaluation_time_passes(self):
        timestamps = [
            self.evaluation_time,
        ]

        result = self.validator.validate(
            timestamps,
            self.evaluation_time,
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.errors, [])

    def test_future_data_fails(self):
        timestamps = [
            datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc),
        ]

        result = self.validator.validate(
            timestamps,
            self.evaluation_time,
        )

        self.assertFalse(result.passed)
        self.assertEqual(len(result.errors), 1)
        self.assertIn(
            "Data timestamp exceeds evaluation time",
            result.errors[0],
        )

    def test_multiple_future_timestamps_are_reported(self):
        timestamps = [
            datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc),
            datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc),
        ]

        result = self.validator.validate(
            timestamps,
            self.evaluation_time,
        )

        self.assertFalse(result.passed)
        self.assertEqual(len(result.errors), 3)


if __name__ == "__main__":
    unittest.main()
