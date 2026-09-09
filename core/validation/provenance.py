from dataclasses import dataclass
from typing import Any


@dataclass
class ProvenanceValidationResult:
    passed: bool
    errors: list[str]


class ProvenanceValidator:
    """Validate the minimum provenance required for an experiment result."""

    REQUIRED_FIELDS = (
        "run_id",
        "status",
        "executed_at",
        "parameters_fingerprint",
        "result_fingerprint",
    )

    def validate(
        self,
        metadata: dict[str, Any],
    ) -> ProvenanceValidationResult:
        errors: list[str] = []

        for field_name in self.REQUIRED_FIELDS:
            if field_name not in metadata:
                errors.append(
                    f"Missing required provenance field: {field_name}"
                )

        if "parameters_fingerprint" in metadata:
            if not metadata["parameters_fingerprint"]:
                errors.append(
                    "Parameter fingerprint must not be empty."
                )

        if "result_fingerprint" in metadata:
            if not metadata["result_fingerprint"]:
                errors.append(
                    "Result fingerprint must not be empty."
                )

        return ProvenanceValidationResult(
            passed=not errors,
            errors=errors,
        )
