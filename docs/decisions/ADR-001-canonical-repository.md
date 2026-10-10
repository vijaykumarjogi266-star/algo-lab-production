# ADR 001: Canonical Repository Selection

## Decision
`/home/ubuntu/algolab` is designated as the sole canonical repository for the Algo Lab / OMS project.

## Rationale
- Contains the verified implementations of P0 hardened rules: T06, T08, T09, and T15.
- Contains the comprehensive `oms_project/` architecture including durable `capital_reservations` and `OrderLedgerDB`.
- Active test suites and gap registers are located here.

## Rules
- Other repositories (`algolab-from-github`, `algolab-sandbox`, etc.) remain read-only references.
- No new parallel project roots may be created.
- Module imports must follow a strict merge review process verifying architectural fit and testing.
