============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0
rootdir: /home/ubuntu/algolab
configfile: pyproject.toml
plugins: cov-7.1.0, asyncio-1.4.0, platformdirs-4.12.2, anyio-4.15.1
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 69 items

oms_project/tests/test_alpha_analyst.py ....                             [  5%]
oms_project/tests/test_auto_tuner.py ...                                 [ 10%]
oms_project/tests/test_central_data_feed.py ....                         [ 15%]
oms_project/tests/test_concurrent_risk_reservation.py F.F....            [ 26%]
oms_project/tests/test_crash_recovery.py F                               [ 27%]
oms_project/tests/test_e2e_life_of_a_trade.py F...FF                     [ 36%]
oms_project/tests/test_execution_events.py ..                            [ 39%]
oms_project/tests/test_mean_reversion_strategy.py ...                    [ 43%]
oms_project/tests/test_oms.py .F.F                                       [ 49%]
oms_project/tests/test_order_resolution.py .F                            [ 52%]
oms_project/tests/test_partial_fills.py .                                [ 53%]
oms_project/tests/test_shutdown.py .F                                    [ 56%]
oms_project/tests/test_smoke_behaviors.py ...F                           [ 62%]
oms_project/tests/test_strategy_factory.py ..F..F.                       [ 72%]
oms_project/tests/test_symmetry.py ....                                  [ 78%]
oms_project/tests/test_time_machine.py ...F.FF                           [ 88%]
oms_project/tests/test_war_room.py ........                              [100%]

=================================== FAILURES ===================================
_______________ test_T15_concurrent_oversubscription_prevention ________________
oms_project/tests/test_concurrent_risk_reservation.py:63: in test_T15_concurrent_oversubscription_prevention
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
E   AssertionError: Expected exactly 1 success, got 10
E   assert 10 == 1
E    +  where 10 = len([OrderResult(request_id='REQ_CONC_1', order_id='ORD_REQ_CONC_1', strategy_id='BOT_CONCURRENT', symbol='RELIANCE', side...ed (Qty: 10.0)', timestamp=1791467433.433728, reserved_value=60000.0, execution_tx='v1.signing.f70cdd5b9762881f'), ...])
________________ test_T15_different_key_concurrency_near_limit _________________
oms_project/tests/test_concurrent_risk_reservation.py:145: in test_T15_different_key_concurrency_near_limit
    assert len(successes) == 10 # 10 * 10 = 100
    ^^^^^^^^^^^^^^^^^^^^^^^^^^^
E   AssertionError: assert 20 == 10
E    +  where 20 = len([OrderResult(request_id='REQ_NL_4', order_id='ORD_REQ_NL_4', strategy_id='BOT_NEAR_LIMIT', symbol='NIFTY', side='BUY',...illed (Qty: 1.0)', timestamp=1791467436.4760249, reserved_value=10.0, execution_tx='v1.signing.d241963e5f74f039'), ...])
___ TestGatewayCrashRecovery.test_crash_mid_posting_session_restart_recovery ___
oms_project/tests/test_crash_recovery.py:26: in test_crash_mid_posting_session_restart_recovery
    self.assertEqual(self.gateway.strategy_balances["STRAT_001"], 100000.0 - 12000.0)
E   AssertionError: 100000.0 != 88000.0
____________________ test_scenario_1_golden_path_execution _____________________
oms_project/tests/test_e2e_life_of_a_trade.py:75: in test_scenario_1_golden_path_execution
    assert cash == 88200.0
E   assert 100000.0 == 88200.0
_____________________ test_scenario_2d_idempotency_attack ______________________
oms_project/tests/test_e2e_life_of_a_trade.py:163: in test_scenario_2d_idempotency_attack
    assert gateway.strategy_balances["STRAT_001"] == 88000.0
E   assert 100000.0 == 88000.0
___________________ test_final_reconciliation_zero_variance ____________________
oms_project/tests/test_e2e_life_of_a_trade.py:199: in test_final_reconciliation_zero_variance
    assert report["status"] == "MATCH"
E   AssertionError: assert 'MISMATCH' == 'MATCH'
E     
E     - MATCH
E     + MISMATCH
E     ? +++
_____________ TestOMSArchitecture.test_idempotency_duplicate_order _____________
oms_project/tests/test_oms.py:42: in test_idempotency_duplicate_order
    self.assertEqual(bal_after_first, initial_bal - 12000.0)
E   AssertionError: 100000.0 != 88000.0
____________ TestOMSArchitecture.test_risk_exhaustion_balance_limit ____________
oms_project/tests/test_oms.py:64: in test_risk_exhaustion_balance_limit
    self.assertEqual(self.gateway.strategy_balances["STRAT_001"], 6000.0)
E   AssertionError: 30000.0 != 6000.0
______ TestGatewayOrderResolution.test_timeout_order_resolution_not_found ______
oms_project/tests/test_order_resolution.py:24: in test_timeout_order_resolution_not_found
    self.assertEqual(self.gateway.strategy_balances["STRAT_001"], initial_bal - 12000.0)
E   AssertionError: 100000.0 != 88000.0
_____________ TestGatewayShutdown.test_shutdown_with_unknown_order _____________
oms_project/tests/test_shutdown.py:49: in test_shutdown_with_unknown_order
    self.assertEqual(self.gateway.strategy_balances["STRAT_001"], 100000.0)
E   AssertionError: 112000.0 != 100000.0
_____________________ test_symmetry_portfolio_pnl_snapshot _____________________
oms_project/tests/test_smoke_behaviors.py:162: in test_symmetry_portfolio_pnl_snapshot
    assert res["reconciliation_status"] == "MATCH"
E   AssertionError: assert 'MISMATCH' == 'MATCH'
E     
E     - MATCH
E     + MISMATCH
E     ? +++
____________ test_fast_test_engine_execution_and_statutory_friction ____________
oms_project/tests/test_strategy_factory.py:86: in test_fast_test_engine_execution_and_statutory_friction
    assert res["reconciliation_status"] == "MATCH"
E   AssertionError: assert 'MISMATCH' == 'MATCH'
E     
E     - MATCH
E     + MISMATCH
E     ? +++
_____________________ test_factory_telemetry_api_fast_test _____________________
oms_project/tests/test_strategy_factory.py:121: in test_factory_telemetry_api_fast_test
    assert data["reconciliation_status"] == "MATCH"
E   AssertionError: assert 'MISMATCH' == 'MATCH'
E     
E     - MATCH
E     + MISMATCH
E     ? +++
______________________ test_slippage_engine_buy_and_sell _______________________
oms_project/tests/test_time_machine.py:94: in test_slippage_engine_buy_and_sell
    assert pytest.approx(gw_buy.strategy_balances["STRAT_001"], rel=1e-6) == 89990.0
E   assert 100000.0 ± 0.1 == 89990.0
E     
E     comparison failed
E     Obtained: 89990.0
E     Expected: 100000.0 ± 0.1
__________________ test_determinism_proof_8_decimal_precision __________________
oms_project/tests/test_time_machine.py:158: in test_determinism_proof_8_decimal_precision
    assert res1["reconciliation_variance"] == 0.0
E   assert 286254.4 == 0.0
_____________________ test_strategy_optimizer_grid_search ______________________
oms_project/tests/test_time_machine.py:175: in test_strategy_optimizer_grid_search
    assert best["reconciliation_status"] == "MATCH"
E   AssertionError: assert 'MISMATCH' == 'MATCH'
E     
E     - MATCH
E     + MISMATCH
E     ? +++
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /home/ubuntu/algolab/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

.venv/lib/python3.12/site-packages/starlette/testclient.py:53
  /home/ubuntu/algolab/.venv/lib/python3.12/site-packages/starlette/testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========================== short test summary info ============================
FAILED oms_project/tests/test_concurrent_risk_reservation.py::test_T15_concurrent_oversubscription_prevention
FAILED oms_project/tests/test_concurrent_risk_reservation.py::test_T15_different_key_concurrency_near_limit
FAILED oms_project/tests/test_crash_recovery.py::TestGatewayCrashRecovery::test_crash_mid_posting_session_restart_recovery
FAILED oms_project/tests/test_e2e_life_of_a_trade.py::test_scenario_1_golden_path_execution
FAILED oms_project/tests/test_e2e_life_of_a_trade.py::test_scenario_2d_idempotency_attack
FAILED oms_project/tests/test_e2e_life_of_a_trade.py::test_final_reconciliation_zero_variance
FAILED oms_project/tests/test_oms.py::TestOMSArchitecture::test_idempotency_duplicate_order
FAILED oms_project/tests/test_oms.py::TestOMSArchitecture::test_risk_exhaustion_balance_limit
FAILED oms_project/tests/test_order_resolution.py::TestGatewayOrderResolution::test_timeout_order_resolution_not_found
FAILED oms_project/tests/test_shutdown.py::TestGatewayShutdown::test_shutdown_with_unknown_order
FAILED oms_project/tests/test_smoke_behaviors.py::test_symmetry_portfolio_pnl_snapshot
FAILED oms_project/tests/test_strategy_factory.py::test_fast_test_engine_execution_and_statutory_friction
FAILED oms_project/tests/test_strategy_factory.py::test_factory_telemetry_api_fast_test
FAILED oms_project/tests/test_time_machine.py::test_slippage_engine_buy_and_sell
FAILED oms_project/tests/test_time_machine.py::test_determinism_proof_8_decimal_precision
FAILED oms_project/tests/test_time_machine.py::test_strategy_optimizer_grid_search
================== 16 failed, 53 passed, 2 warnings in 6.50s ===================
