# ADR-XXXX: Title of Architectural Decision

## Status
- **Status:** Proposed | Accepted | Superseded | Deprecated
- **Date:** YYYY-MM-DD
- **Author:** Author Name (@github-handle)
- **Deciders:** Decision Committee / Lead Engineer

## Context
Describe the context and problem statement. What technical, business, or risk factors motivated this decision?

## Decision
Detail the chosen architectural approach. What are the concrete design choices, components, and interfaces?

## Non-Negotiable Safety Invariant Compliance
- Does this decision preserve `LIVE_TRADING_ENABLED = False`?
- Does it maintain independent risk engine authority?
- Does it prevent synthetic data substitution in production paper paths?

## Consequences
### Positive
- Benefit 1
- Benefit 2

### Negative / Trade-offs
- Trade-off 1
- Trade-off 2

## Compliance & Verification Evidence
- Link to relevant tests:
- Verification command:
