# ADR 004: Uncertain Broker Outcomes (GAP-03)

## Status
Accepted

## Context
When submitting or cancelling orders, network timeouts or broker unavailability can leave the system in an uncertain state where it is unknown if the broker received, accepted, rejected, or executed the order. 
Releasing capital, resubmitting automatically, or assuming cancellation in these states is highly dangerous and can lead to unhedged risk, duplicate fills, or blown capital limits.

## Decision
We have implemented strict rules for handling broker uncertainty:
1. **Submission Uncertainty (T05):** Transition order to `SUBMISSION_UNKNOWN`. Keep capital reservations active. Do not release capital or resubmit. Record the uncertainty in a durable table (`broker_uncertainty_records`).
2. **Cancellation Uncertainty (T10):** Transition order to `CANCEL_UNKNOWN`. Keep residual capital reservations active. Do not treat as cancelled. Record uncertainty.
3. **Execution Handling:** Delayed fills and execution reports will still process identically once, consuming reservations proportionally and moving the order towards a filled state.
4. **Resolution via Evidence:** A broker-neutral resolution interface allows manual or reconciliation-driven evidence to definitively resolve the state to REJECTED, CANCELLED, LIVE, or FILLED, at which point remaining unused capital reservations are safely released.

## Consequences
- Prevents over-allocation and duplicate execution risk.
- Requires operator or reconciliation-engine intervention (using the durable resolution record) to resolve stuck orders.
- Safer restart behavior since uncertainty records and conservative reservations are persisted.
