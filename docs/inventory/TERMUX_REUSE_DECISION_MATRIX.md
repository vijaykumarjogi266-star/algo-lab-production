# Termux Reuse Decision Matrix

This document maps Termux files against the Canonical Algo Lab architecture and classifies their safety for reuse.

## Classification Categories
- **SAFE_REUSE_CANDIDATE**: Pure mathematical functions or read-only utilities with no side effects.
- **REUSE_AFTER_ADAPTER_REFACTOR**: Useful models that must be wrapped so they do not directly alter system state.
- **REFERENCE_ONLY**: Files used only to inspire design; code should not be copied.
- **UNSAFE_DIRECT_TRADING_PATH**: Files that attempt to place orders, execute database transactions independently, or bypass `OrderLedgerDB` and `BrokerGateway`.
- **DATA_OR_ARCHIVE_ONLY**: Markdown docs, old configs, CSV files.
- **DUPLICATE_OF_CANONICAL**: Subsystems already completed in the canonical repository.
- **UNKNOWN_REQUIRES_TESTS**: Utility files lacking tests to confirm their exact behavior.

## Matrix

| Component/Path | Classification | Notes |
|---|---|---|
| `algopro/quant/indicators/*` (e.g. `ema.py`, `macd.py`, `rsi.py`, `vwap.py`) | **SAFE_REUSE_CANDIDATE** | Pure functions processing data arrays. Do not handle state or orders. Useful for strategy research. |
| `algopro/services/evaluation_engine/*` (e.g. `metrics.py`, `walk_forward.py`) | **SAFE_REUSE_CANDIDATE** | Mathematical and statistical evaluation tools. Useful for backtesting metrics. No trading state modified. |
| `algopro/quant/strategies/*` | **REUSE_AFTER_ADAPTER_REFACTOR** | Strategy logic is useful, but it must be refactored to return an `OrderIntent` instead of submitting orders directly. |
| `algopro/services/market-data/adapters/yfinance_adapter.py` | **SAFE_REUSE_CANDIDATE** | Pure data retrieval, read-only. Useful for historic backtesting. |
| `web_controller/static/*` | **SAFE_REUSE_CANDIDATE** | Frontend files. Safe for UI dashboard implementation. |
| `web_controller/server.py` | **REUSE_AFTER_ADAPTER_REFACTOR** | Can provide dashboard endpoints, but must route all OMS calls through canonical interfaces. |
| `algopro/services/market-data/adapters/dhan_adapter.py` | **UNSAFE_DIRECT_TRADING_PATH** | Contains broker-specific websocket/credentials handling. Should be integrated via Canonical `BrokerGateway`. |
| `algopro/services/paper-engine/*` | **DUPLICATE_OF_CANONICAL** | Simulators and runners that overlap with Canonical OMS and order ledger logic. Do not import. |
| `algopro/scratch/dhan_debug.py`, `dhan_live_test.py`, `marketfeed.py` | **UNSAFE_DIRECT_TRADING_PATH** | Direct test scripts making live connections with API keys. Unsafe. |
| `algopro/scratch/run_session_*.py`, `audit_*.py` | **REFERENCE_ONLY** | Manual test workflows tracking independent SQLite states. |
| `start_termux_remote.sh`, `start_oracle_services.py` | **REFERENCE_ONLY** | Deployment scripts specific to Termux ecosystem. |
| `algopro/scratch/PAPER_SESSION_*_REPORT.md` | **DATA_OR_ARCHIVE_ONLY** | Test evidence reports. |

## Documentation of Safe Candidates

**`algopro/quant/indicators/*`**
- **Exact Purpose**: Calculate statistical points (RSI, MACD, Bollinger Bands, etc.) from price series.
- **Why it is useful**: Standardizes research metrics, eliminating the need to write them from scratch.
- **Dependencies**: Pandas, NumPy.
- **Conflict Risk**: Low. Completely stateless.
- **Target Location**: `/home/ubuntu/algolab/oms_project/research/indicators/`
- **Required Boundary**: Must only accept DataFrames and output DataFrames/Series.
- **Tests Required**: Verification against known standard market data.
- **Handles Secrets**: No.
- **State Updates**: No.
