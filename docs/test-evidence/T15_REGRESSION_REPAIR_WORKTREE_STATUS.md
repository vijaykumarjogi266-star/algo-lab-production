On branch fix/t15-full-suite-regressions
Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   apps/api/core/config.py
	modified:   apps/api/main.py
	modified:   apps/api/routes/system.py
	modified:   apps/api/schemas/health.py
	modified:   apps/web/next.config.mjs
	modified:   apps/web/package-lock.json
	modified:   apps/web/src/app/backtests/page.tsx
	modified:   apps/web/src/app/layout.tsx
	modified:   apps/web/src/app/risk/page.tsx
	modified:   apps/web/src/components/Navigation.tsx
	modified:   collectors/secure_credential_store.py
	modified:   quant/strategies/base.py
	modified:   services/backtest-engine/cost_models.py
	modified:   services/market-data/__init__.py
	modified:   services/market-data/adapters/__init__.py
	modified:   tests/integration/test_data_api.py
	modified:   tests/integration/test_experiment_api.py
	modified:   tests/integration/test_stage6_api.py
	modified:   tests/unit/test_experiment_comparison.py
	modified:   tests/unit/test_experiment_provenance_audit.py
	modified:   tests/unit/test_stage5_integrity.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	ALGO_LAB_ANGEL_ONE_EGRESS_REMEDIATION_REPORT.md
	ALGO_LAB_ANGEL_ONE_EGRESS_VERIFICATION_REPORT.md
	ALGO_LAB_ANGEL_ONE_PROVIDER_CONNECTIVITY_REPORT.md
	ALGO_LAB_ANGEL_ONE_REUSABILITY_DIAGNOSTIC_REPORT.md
	ALGO_LAB_CURRENT_STATUS_CAPABILITY_AUDIT.md
	ALGO_LAB_FORWARD_SESSION_001_REPORT.md
	ALGO_LAB_FORWARD_SESSION_PREFLIGHT_REPORT.md
	ALGO_LAB_REALTIME_EQUITY_BUILD_REPORT.md
	ALGO_LAB_REALTIME_EQUITY_INDEPENDENT_VALIDATION_REPORT.md
	ALGO_LAB_STRATEGIES_COMPARISON.md
	ARCHITECTURE.md
	CHANGELOG.md
	CLEAN_INSTALL_RUNBOOK.md
	PROJECT_STATUS.md
	STAGE27_V1_ANGEL_ONE_CONFIGURATION_REPORT.md
	STAGE27_V1_BASELINE_REPORT.md
	STAGE27_V1_DAY1_OPERATIONAL_REPORT.md
	STAGE27_V1_EOD_COMPLETION_REPORT.md
	STAGE27_V1_FIRST_FORWARD_SESSION_REPORT.md
	SUPPORT_MATRIX.md
	apps/api/core/security.py
	apps/api/routers/
	apps/api/routes/dashboard.py
	apps/web/src/app/dashboard/
	apps/web/src/components/KiteHeader.tsx
	audit/
	config/
	daily_institutional_harvester.py
	data/cache/
	data/instruments/
	data/live_portfolio_state.json
	data/paper/
	data/youtube_algo_strategies.csv
	data/youtube_deep_strategy_database.csv
	docs/CONSOLIDATION_PLAN.md
	docs/TERMUX_INTEGRATION_PLAN.md
	docs/architecture-review/
	docs/decisions/
	docs/inventory/
	docs/market_data/
	docs/test-evidence/
	extract_strategy_links.py
	fix_dashboard.py
	fix_engine.py
	fix_final_tests.py
	fix_final_tests_2.py
	fix_final_tests_3.py
	fix_final_tests_4.py
	fix_final_tests_5.py
	fix_indent.py
	fix_remaining_blockers.py
	fix_risk.py
	fix_test_baseline_2.py
	fix_test_baseline_3.py
	fix_tests.py
	live_market_daemon.py
	oms_project/
	options_harvester.py
	patch_ingest.py
	patch_live_daemon_imports.py
	patch_lock.py
	quant-os.service
	refactor.py
	reports/
	requirements-pinned.txt
	scripts/
	services/backtest-engine/adaptive_market_engine.py
	services/backtest-engine/statutory_cost_model.py
	services/common/
	services/market-data/adapters/angel_one.py
	services/market-data/adapters/angel_one_instruments.py
	services/market-data/adapters/market_event_schemas.py
	services/market-data/adapters/market_pipeline.py
	services/market-data/runner.py
	services/orchestrator/
	services/reconciliation/
	services/scanner/
	simulate_daemon.py
	src/
	test_logic.py
	tests/conftest.py
	tests/integration/test_adversarial_failure_scenarios.py
	tests/integration/test_end_to_end_realtime_paper_system.py
	tests/unit/test_adaptive_market_survival_backtest.py
	tests/unit/test_angel_one_market_data.py
	tests/unit/test_api_security.py
	tests/unit/test_architectural_isolation.py
	tests/unit/test_dashboard_router.py
	tests/unit/test_eod_reconciliation.py
	tests/unit/test_financial_truth_and_statutory_costs.py
	tests/unit/test_live_market_daemon.py
	tests/unit/test_market_data_runner.py
	tests/unit/test_multi_symbol_scanner.py
	tests/unit/test_notification_engine.py
	tests/unit/test_persistence_and_recovery.py
	tests/unit/test_session_orchestrator.py
	tests/unit/test_single_slice_gated_paper_path.py
	update_daemon.py
	update_dashboard.py
	web_ui/
	youtube_deep_harvester.py
	youtube_strategy_harvester.py

no changes added to commit (use "git add" and/or "git commit -a")
