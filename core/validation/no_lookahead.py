from dataclasses import dataclass
from datetime import datetime


@dataclass
class TemporalValidationResult:
    passed: bool
    errors: list[str]


class NoLookaheadValidator:
    """Validate that data timestamps do not cross an experiment boundary."""

    def validate(
        self,
        data_timestamps: list[datetime],
        evaluation_time: datetime,
    ) -> TemporalValidationResult:
        errors: list[str] = []

        for timestamp in data_timestamps:
            if timestamp > evaluation_time:
                errors.append(
                    "Data timestamp exceeds evaluation time: "
                    f"{timestamp.isoformat()}"
                )

        return TemporalValidationResult(
            passed=not errors,
            errors=errors,
        )
