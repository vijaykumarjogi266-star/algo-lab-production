# Baseline Test Results

## Exact Commands Run
`PYTHONPATH=. pytest oms_project/tests/ -v`
`PYTHONPATH=. pytest oms_project/tests/test_concurrent_risk_reservation.py -v`

## Environment Notes
- Python 3.12.3
- pytest 9.1.1
- No live broker credentials used. No network calls made.
- Test suites executed against local `test_concurrent.db` or memory database.

## Results
**T15 Suite**:
7 tests passed (T15 suite is verified successful).

**Full OMS Suite**:
60 passed, 9 failed.
Failures introduced due to previous idempotency return value changes and risk exhaustion logic.
Failed tests include:
- `test_scenario_2b_risk_exhaustion_rejection`
- `test_scenario_2d_idempotency_attack`
- `TestOMSArchitecture.test_idempotency_duplicate_order`
- `TestOMSArchitecture.test_risk_exhaustion_balance_limit`
- `test_symmetry_portfolio_pnl_snapshot`
- `test_fast_test_engine_execution_and_statutory_friction`
- `test_factory_telemetry_api_fast_test`
- `test_determinism_proof_8_decimal_precision`
- `test_strategy_optimizer_grid_search`
