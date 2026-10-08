# T15 Regression Repair Results

## Baseline Failures
The full OMS suite initially had 16 failing assertions linked to T15 regressions, including:
- `test_scenario_1_golden_path_execution`
- `test_crash_mid_posting_session_restart_recovery`
- `test_T15_concurrent_oversubscription_prevention`
- `test_T15_different_key_concurrency_near_limit`
- `test_idempotency_duplicate_order`

## Root Causes & Source Changes
1. **Broken Cash Invariant**: `submit_order_intent` previously commented out the upfront cash deduction for reservations, breaking the `strategy_balances = Available Cash` invariant and causing executed BUYs to magically "restore" the spent cash.
   *Fix*: Restored upfront cash deduction in `gateway.py` and added exact refund logic in `process_execution_report` for partial fills/rejections.
2. **Concurrency Hole**: `reservation_service.py` bypassed the `ACTIVE` DB reservation sum when `get_available_capital` was provided by the memory gateway.
   *Fix*: Always subtract DB `ACTIVE` reservations from `base_capital` in `reservation_service.py`. Passed `strategy_balances + strategy_reserved` from `gateway.py` to form the correct base capital.
3. **Idempotency Assertions**: T15 returns the original order for a duplicate key, but tests expected `REJECTED`.
   *Fix*: Updated `test_idempotency_duplicate_order` to expect `FILLED`.
4. **Test Burst Constraint**: Concurrency tests used `simulation_mode=False` which instantly `CONSUMED` reservations, clearing the `ACTIVE` state before the concurrent burst could trip the limit.
   *Fix*: Added `simulate_network_failure=True` to hold the reservations in `ACTIVE` status.

## Test Commands and Results
- `PYTHONPATH=. pytest oms_project/tests/ -q` -> 69 passed (100% green)
- `PYTHONPATH=. pytest oms_project/tests/test_concurrent_risk_reservation.py -q` -> 7 passed
- `for i in {1..20}; do PYTHONPATH=. pytest oms_project/tests/test_concurrent_risk_reservation.py -q || exit 1; done` -> All 20 iterations passed successfully.

## Remaining Limitations
None. All required safety controls and OMS assertions have been successfully restored and verified.
Commit: c6c48782bfd39ba053bc94c2132bc9b79ca2b8d4
