# Algo Lab Rules

## 1. Laboratory Independence

Algo Lab must not depend architecturally on n8n or any other individual
automation platform.

## 2. Reproducibility

Important experiments must be reproducible from versioned code,
configuration, data references, and experiment parameters.

## 3. No Lookahead

Future information must never be used to make decisions about the past.

## 4. Version Control

Important code, configuration, policies, experiments, and research
artifacts must be version controlled.

## 5. Testing

Experimental components must pass their required tests before promotion.

## 6. Independent Review

Important research results require independent review before acceptance.

## 7. Agent Authority

Agents may only perform actions explicitly permitted by their assigned
authority.

## 8. Separation of Responsibilities

Research, experimentation, validation, deployment, and monitoring must
remain logically separated.

## 9. Artifact Preservation

Important outputs must contain sufficient metadata for reproduction
and audit.

## 10. Safe Failure

When uncertainty exists, the system should stop, quarantine, or request
review rather than silently proceeding.

## 11. Human Control

Consequential external actions require explicit authorization unless a
narrowly defined automation policy has already authorized them.

## 12. Tool Neutrality

Replacing n8n, an AI provider, database, cloud provider, or other tool
must not require rebuilding Algo Lab itself.

## 13. Promotion

No research result automatically becomes a production strategy.

Promotion requires passing the applicable stage gates.

## 14. Auditability

Material changes and decisions must be traceable to code, configuration,
experiment, reviewer, and approval records.

## 15. Separation of Data

Raw, processed, experimental, and production datasets must not be mixed
without explicit provenance and validation.

## 16. Security

Secrets must never be committed to Git.

## 17. Fail Closed

Missing permissions, missing evidence, failed tests, or ambiguous
authority must default to refusal or quarantine.

