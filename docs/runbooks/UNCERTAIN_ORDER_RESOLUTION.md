# Runbook: Uncertain Order Resolution

## Context
When the OMS is unable to determine the status of an order via the broker due to a timeout or crash, it will enter either `SUBMISSION_UNKNOWN` or `CANCEL_UNKNOWN` state. The OMS will safely persist the internal order and capital reservation to protect against duplicates. A record is created in `broker_uncertainty_records`.

## Resolution Steps

1. **Investigate on the Broker/Exchange:**
   Check the real broker account (e.g., via their portal or API) to see if the order with the corresponding `request_id` or `idempotency_key` exists.

2. **Determine Status:**
   - **Order Does Not Exist (Submission Timeout):** The broker rejected or never saw the order. The resolution is `REJECTED`.
   - **Order Exists and is Live:** The resolution is `LIVE`.
   - **Order Exists and is Filled:** The resolution is `FILLED`.
   - **Order Cancelled:** The resolution is `CANCELLED`.

3. **Resolve in OMS:**
   Use the `resolve_uncertain_order(order_id, evidence)` API:
   ```python
   gateway.resolve_uncertain_order("ORD_xyz", {"status": "REJECTED", "ref": "manual_check"})
   ```
   This will safely release reserved capital (if applicable) and advance the state machine.

4. **Verify Resolution:**
   - Check that `order_ledger` shows the updated state.
   - Check that `broker_uncertainty_records` marks the case as `RESOLVED`.
