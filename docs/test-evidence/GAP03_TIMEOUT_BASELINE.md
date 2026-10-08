# GAP-03 Timeout Baseline

Before implementing GAP-03, the system lacked a robust way to handle timeouts during order submission and cancellation:
- Network timeouts often left orders in states that could result in duplicate executions.
- Capital reservations were released prematurely upon timeouts or kept locked forever without an audit trail.
- There was no durable `broker_uncertainty_records` schema to log the state of orders that failed due to network unavailability.

Test files required testing these uncertainty outcomes but they were unimplemented or not covering all scenarios for T05 and T10.
