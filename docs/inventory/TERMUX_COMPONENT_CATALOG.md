# Termux Algo Lab Component Catalog

This document lists all relevant files from `/home/ubuntu/termux-ai-sandbox`.
_Note: Irrelevant dependencies (.venv, .git, caches, standard libraries) are excluded._

## Catalog Summary
- **Primary Source Code Directory**: `algopro/`
- **Dashboard / UI Component**: `web_controller/`
- **Research / Ad-Hoc Scripts**: `algopro/scratch/`
- **Tests**: `algopro/tests/`
- **Root Scripts**: `start_termux_remote.sh`, `start_setup.sh`, `start_oracle_services.py`

### 1. `algopro/services/`
Contains the core engines of the Termux variant.
- `paper-engine/`: Mock trading and simulation (`runner.py`, `execution.py`, `account.py`, `contracts.py`)
- `paper-engine/adapters/`: Interface configurations (`credentials.py`, `base.py`)
- `evaluation_engine/`: Trading metrics and research simulation (`metrics.py`, `engine.py`, `reporting.py`, `contracts.py`, `walk_forward.py`, `regimes.py`, `sensitivity.py`, `partitioning.py`)
- `execution-engine/`: Placeholders / incomplete definitions.
- `market-data/`: Retrievers and instruments (`registry.py`, `adapters/dhan_adapter.py`, `adapters/yfinance_adapter.py`, `instruments.py`, `calendar.py`, `storage.py`)

### 2. `algopro/quant/`
Contains financial models, strategies, and indicators.
- `indicators/`: Statistical features (`ema.py`, `bollinger.py`, `macd.py`, `rsi.py`, `atr.py`, `vwap.py`, `sma.py`, `adx.py`, etc.)
- `strategies/`: Example strategy algorithms (`orb.py`, `vwap_reversion.py`, `base.py`)
- `portfolio/`, `factors/`: Structural folders for alpha design.

### 3. `web_controller/`
A separate web UI API and dashboard.
- `server.py`: FastAPI or Flask server handling requests and secrets.
- `static/`: Contains `index.html`, `app.js`, `style.css`.
- `.controller_token.key`: Authentication token / secret.

### 4. `algopro/scratch/`
Unstructured test scripts and reports.
- **Audit Scripts**: `audit_003.py`, `audit_006_007.py`, `audit_session_004.py`, `FORENSIC_AUDIT_REPORT.md`
- **Session Runners**: `run_session_002.py` through `run_session_009_forward.py`
- **Broker Tests**: `dhan_debug.py`, `dhan_cert_test.py`, `marketfeed.py`, `dhan_live_test.py`
- **Other utilities**: `check_yf.py`, `check_equity.py`, `inject_opening_cash.py`, `test_ltp.py`
