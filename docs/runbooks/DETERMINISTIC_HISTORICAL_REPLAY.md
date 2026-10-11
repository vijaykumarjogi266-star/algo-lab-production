# Runbook: Deterministic Historical Replay and Market-Regime Evaluation

## 1. Overview
The deterministic historical replay engine allows reproducible backtesting and simulation across verified historical datasets while guaranteeing zero future-data leakage (strict look-ahead bias prevention).

## 2. Replay Execution Steps

### 2.1 Verify Dataset Registration
Before replay, ensure the dataset is registered and verified in `HistoricalDataRegistry`:
```python
from oms_project.database import OrderLedgerDB
from oms_project.data_registry import HistoricalDataRegistry

db = OrderLedgerDB("data/ledger.db")
registry = HistoricalDataRegistry(db)
meta = registry.verify_integrity("DS_NSE_RELIANCE_2026")
```

### 2.2 Configure and Launch Replay
```python
from oms_project.deterministic_replay import ReplayExecutionEngine, MarketRegime
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy

engine = ReplayExecutionEngine(
    db_path="data/ledger.db",
    initial_cash=100000.0,
    slippage_bps=5.0,
    fee_rate_bps=2.0,
    enforce_session_hours=True,
)

report = engine.run_replay(
    dataset_id="DS_NSE_RELIANCE_2026",
    registry=registry,
    strategy_class=MeanReversionStrategy,
    strategy_params={"window_size": 10, "std_dev_threshold": 1.2, "order_qty": 10.0},
    symbol="RELIANCE",
    allowed_regimes=[MarketRegime.RANGE_BOUND, MarketRegime.LOW_VOLATILITY],
)
```

### 2.3 Inspect Durable Replay Execution Report
Reports are durably stored in SQLite table `replay_execution_reports`:
```sql
SELECT report_id, replay_run_id, net_pnl, max_drawdown_pct, turnover, total_fees, reconciliation_status
FROM replay_execution_reports
WHERE replay_run_id = 'REP_RUN_...';
```

## 3. Look-Ahead Bias Error Handling
- If any component attempts to query ticks or prices ahead of the virtual simulation clock, the system immediately raises:
  `LookAheadBiasError`
- Action: Inspect the strategy or indicator window query and ensure `end <= clock.current_time`.

## 4. Tampered Dataset Handling
- If on-disk dataset bytes change after registration:
  - `ChecksumMismatchError` is raised.
  - Dataset status is updated to `QUARANTINED`.
  - Replay is blocked fail-closed.
