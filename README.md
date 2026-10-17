# Algo Lab — Institutional Paper-Trading Quantitative Research OS

[![Algo Lab CI](https://github.com/vijaykumarjogi266-star/algopro/actions/workflows/ci.yml/badge.svg)](https://github.com/vijaykumarjogi266-star/algopro/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/version-0.3.0-blue.svg)](src/version.py)
[![Lifecycle](https://img.shields.io/badge/lifecycle-forward--paper--validation-green.svg)](src/version.py)
[![Policy](https://img.shields.io/badge/policy-paper--only-red.svg)](SECURITY.md)
[![License](https://img.shields.io/badge/license-Proprietary-lightgrey.svg)](LICENSE)

> **Algo Lab** is an institutional quantitative investment research, backtesting, and forward paper-simulation platform engineered specifically for Indian Cash Equities (NSE/BSE).
>
> **Algo Lab is strictly a paper-only simulation system.** It does NOT execute real-money trades, does NOT manage external client capital, and does NOT route orders to live broker trading accounts.

---

## 1. Scope and Explicit Non-Goals

### In-Scope Capabilities
- Point-in-time safe historical backtesting across 5-year multi-regime Nifty 50 constituent datasets.
- Forward paper-trading simulation utilizing near-close (15:00–15:30 IST) daily bars.
- Statutory Indian Equity cost modeling: Securities Transaction Tax (STT 0.1% CNC), Stamp Duty (0.015%), Depository Participant (DP) charges (₹15.34 flat on sell), Exchange fees, SEBI turnover fees, and 18% GST.
- Crash-resilient overnight state persistence using ACID-compliant SQLite ledgers and atomic JSON file replacement.
- Independent, hard-coded Risk Engine enforcing capital reservation, sector concentration limits, and maximum drawdown gates.
- Built-in AI Quantitative Advisor CLI with seamless free model fallback.

### Explicit Non-Goals
- **Zero Real-Money Trading:** No real order routing, no capital placement, no live broker execution.
- **No Financial / Investment Advice:** Algo Lab does not provide recommendations, tip services, or financial advisory.
- **No Direct Strategy-to-Broker Execution:** Strategies cannot submit orders directly; only the independent risk engine can approve candidate intents.
- **No Synthetic Data Fallback:** Missing or corrupted data results in `WAIT` / rejection; synthetic data substitution in production paper paths is strictly forbidden.

---

## 2. Paper-Only and Non-Investment-Advice Notice

> [!CAUTION]
> **IMPORTANT REGULATORY & SAFETY NOTICE**  
> All simulated trades, metrics, P&L calculations, and strategy signals produced by Algo Lab are purely hypothetical, generated within isolated forward paper simulations or historical backtests. Past performance in simulation is no guarantee of future returns. This software is provided solely for quantitative research and software verification.

---

## 3. Non-Negotiable Safety Invariants

Algo Lab operates under strict, fail-closed runtime boundaries:

1. `LIVE_TRADING_ENABLED` must remain `False`.
2. `REAL_BROKER_EXECUTION_ENABLED` must remain `False`.
3. Any configuration or environment variable attempting to enable live broker execution causes immediate application termination and CI failure.
4. The Risk Engine is strictly decoupled and independent from all strategies, AI advisors, and UI controllers.
5. No strategy, AI model, or API endpoint may bypass risk checks or directly submit orders.
6. Missing, stale, future-dated, or malformed data results in `WAIT` or rejection, never synthetic substitution.
7. Backtests and forward paper simulations must remain reproducible, point-in-time safe, and deterministic.
8. No network action may route real orders or transmit unredacted secrets.
9. Secrets, API keys, tokens, and credentials must never be written to logs, artifacts, or version control.
10. Backward compatibility must be preserved across schema migrations, with all intentional breaks documented.

---

## 4. Architecture Overview

```
algo-lab/
├── apps/
│   ├── api/                    # FastAPI Institutional Backend (RBAC, Audit, Endpoints)
│   └── web/                    # Next.js 14 TypeScript Research UI Shell
├── services/
│   ├── risk-engine/            # Independent Risk Gate & Capital Reservation
│   ├── backtest-engine/        # Multi-regime simulation & Indian statutory tax models
│   ├── paper-engine/           # Simulated broker exchange & trailing stop ratchets
│   ├── scanner/                # Nifty 50 constituent universe & sector mapping
│   ├── data-quality/           # Anomaly detection & point-in-time data validation
│   └── market-data/            # Daily & intraday historical bar ingestion
├── oms_project/                # Order Management System, decision engine, & state machine
├── quant/                      # Technical indicators, Donchian channels, ADX, ATR models
├── src/
│   ├── version.py              # Canonical version (0.3.0) & safety invariant authority
│   ├── gpt_client.py           # Institutional AI Advisor client (OpenAI & Free Models)
│   └── notification_engine.py  # Discord & Telegram EOD webhook alert engine
├── data/
│   ├── cache/                  # Clean 5-year Parquet daily historical bars (50 Nifty tickers)
│   ├── live_portfolio_state.json # Atomic paper portfolio state
│   └── swing_portfolio_ledger.db # Authoritative SQLite overnight double-entry ledger
├── scripts/                    # Backtests, stress tests, CLI advisors, & backup tooling
├── tests/                      # Over 320 unit, contract, regression, and security tests
├── Makefile                    # Canonical CI release check gate (`make release-check`)
└── pyproject.toml              # Build specification & tool configurations
```

---

## 5. Local Setup & Quickstart

### Prerequisites
- Linux (Ubuntu 22.04+ or Oracle Linux) or macOS
- Python 3.12+
- SQLite 3.35+

### Installation
```bash
# 1. Clone repository
git clone https://github.com/vijaykumarjogi266-star/algopro.git algolab
cd algolab

# 2. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install pinned dependencies
pip install --upgrade pip
pip install -r requirements-pinned.txt
pip install -e .

# 4. Verify local installation & safety invariants
make release-check
```

---

## 6. Fixture-Based Demo

Run an offline 5-year institutional backtest on the cached Nifty 50 dataset:
```bash
python scripts/run_adaptive_market_survival_backtest.py --strategy STRATEGY_SUPER_ADAPTIVE --universe nifty50
```

Run a single-tick smoke test of the autonomous EOD swing trading daemon:
```bash
python live_market_daemon.py --once
```

---

## 7. Data Governance & Research Reproducibility

- **Data Provenance:** Historical bars are verified using SHA-256 cryptographic checksums.
- **Strict Timezone Integrity:** All market time calculations strictly utilize `Asia/Kolkata` (`ZoneInfo`) with official `exchange_calendars` (`XNSE`) holiday schedules.
- **Lookahead & Anomaly Filters:** Any candle with future-dated timestamps, negative prices, or volume anomalies is rejected.

---

## 8. Forward Paper-Simulation Workflow

The forward paper trading engine operates autonomously during the near-close market window:
1. **15:00–15:15 IST (Candle Ingestion):** Ingests near-close 1d bars for all 50 Nifty tickers, computing ATR(14), Donchian channels, and momentum signals.
2. **15:15–15:25 IST (Trade Execution):** Evaluates trailing stops (3.0x ATR) and executes candidate entries adhering to the Ed Thorp 1% capital risk rule.
3. **15:25–15:30 IST (Overnight Persistence):** Commits open positions and cash balances to the SQLite ledger (`swing_portfolio_ledger.db`) and atomic JSON file.
4. **15:30+ IST (Session Completion):** Dispatches EOD summary reports to Discord/Telegram webhooks and sleeps until the next official NSE session.

---

## 9. 24/7 Deployment on Oracle Cloud

### Running via systemd (Recommended)
```bash
# Copy and enable the hardened systemd unit file
sudo cp quant-os.service /etc/systemd/system/quant-os.service
sudo systemctl daemon-reload
sudo systemctl enable quant-os.service
sudo systemctl start quant-os.service

# Check live daemon logs
journalctl -u quant-os.service -f
```

---

## 10. Incident Response & Safe Shutdown

- **Emergency Stop:** Press `Ctrl+C` or run `sudo systemctl stop quant-os.service`. The daemon intercepts `SIGINT`/`SIGTERM`, safely commits current positions to SQLite, and exits with code 0.
- **Manual State Recovery:** Run `python scripts/backup_restore.py --verify` to inspect database and state file integrity.
- **Operational Procedures & Handover:** Complete step-by-step standard operating procedures, including Circuit-Breaker Recovery, Credential Rotation, Data Provider Failover, Emergency Quarantine, and RBAC matrix are documented in [`docs/runbooks/OPERATIONAL_HANDOVER_AND_PROCEDURES.md`](docs/runbooks/OPERATIONAL_HANDOVER_AND_PROCEDURES.md).
- **Incident Response & SRE Alerts:** Triage matrices, alert definitions, and war room protocols are documented in [`docs/runbooks/INCIDENT_RESPONSE_AND_ALERTS.md`](docs/runbooks/INCIDENT_RESPONSE_AND_ALERTS.md).
- **Disaster Recovery & Restore:** Backup encryption, verification, and restore procedures are documented in [`docs/runbooks/BACKUP_AND_RESTORE.md`](docs/runbooks/BACKUP_AND_RESTORE.md).

---

## 11. Contributing & Security Reporting

- Review [CONTRIBUTING.md](CONTRIBUTING.md) for pull request guidelines and code style.
- Review [SECURITY.md](SECURITY.md) for vulnerability disclosure and secret masking standards.
- View architectural decisions in [docs/adr/](docs/adr/).
