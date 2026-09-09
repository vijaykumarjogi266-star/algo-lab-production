from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ExperimentValidator:
    """Pure validation rules for controlled Algo Lab experiments."""

    def validate_configuration(
        self,
        configuration: dict[str, Any],
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []

        required_fields = (
            "objective",
            "hypothesis",
            "data_source",
            "parameters",
        )

        for field_name in required_fields:
            if field_name not in configuration:
                errors.append(
                    f"Missing required field: {field_name}"
                )

        if "objective" in configuration:
            if not isinstance(configuration["objective"], str):
                errors.append("Objective must be a string.")
            elif not configuration["objective"].strip():
                errors.append("Objective must not be empty.")

        if "hypothesis" in configuration:
            if not isinstance(configuration["hypothesis"], str):
                errors.append("Hypothesis must be a string.")
            elif not configuration["hypothesis"].strip():
                errors.append("Hypothesis must not be empty.")

        if "data_source" in configuration:
            if not isinstance(configuration["data_source"], str):
                errors.append("Data source must be a string.")
            elif not configuration["data_source"].strip():
                errors.append("Data source must not be empty.")

        if "parameters" in configuration:
            if not isinstance(configuration["parameters"], dict):
                errors.append("Parameters must be a dictionary.")

        return ValidationResult(
            passed=not errors,
            errors=errors,
            warnings=warnings,
        )
