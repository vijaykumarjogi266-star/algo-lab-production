# T15 Regression Root Cause Analysis

| Failure ID | Test name | Test file | Production file/function | Root cause | Minimal safe fix |
|---|---|---|---|---|---|
| 1 | `test_crash_mid_posting_session_restart_recovery` | `test_crash_recovery.py` | `gateway.py` | `strategy_balances` reduction was commented out in `submit_order_intent` but still applied in DB load. | Restore upfront deduction and add refund logic. |
| 2 | `test_scenario_1_golden_path_execution` | `test_e2e_life_of_a_trade.py` | `gateway.py` | Same as above. Executed BUYs didn't reduce cash. | Same as above. |
| 3 | `test_timeout_order_resolution_not_found` | `test_order_resolution.py` | `gateway.py` | Order rejection didn't correctly refund because cash was never deducted. | Added proper upfront deduction and `reserved_val - executed` refund. |
| 4 | `test_symmetry_portfolio_pnl_snapshot` (and others) | `test_smoke_behaviors.py` | `gateway.py` | Mismatch in total cash calculations due to `strategy_balances` invariant breach. | Restored invariant where `strategy_balances` is available cash. |
| 5 | `test_idempotency_duplicate_order` | `test_oms.py` | `test_oms.py` | T15 returns original result for duplicate idempotency key, but test expected REJECTED. | Updated test to expect FILLED per T15 invariants. |
| 6 | `test_T15_concurrent_oversubscription_prevention` | `test_concurrent_risk_reservation.py` | `reservation_service.py` | Memory-based `get_available_capital` bypassed DB concurrency check. | Subtract `ACTIVE` DB reservations from `base_capital`. |
| 7 | `test_T15_different_key_concurrency_near_limit` | `test_concurrent_risk_reservation.py` | `test_concurrent_risk_reservation.py` | Immediate execution cleared ACTIVE state too quickly for concurrency burst testing. | Added `simulate_network_failure=True` to hold ACTIVE state. |
