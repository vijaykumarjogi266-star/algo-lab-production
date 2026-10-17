# Algo Lab Known Limitations & System Boundaries

**Project Version:** `0.3.0`  
**Lifecycle State:** `forward-paper-validation`  
**Certification Date:** 2026-10-14  
**Scope:** Architectural, Operational, and Computational Boundaries

---

## 1. Paper-Only Simulation Boundary

Algo Lab is engineered exclusively as a **quantitative investment research and forward-simulation operating system**. Real-money trading, automated order placement, and live capital routing are strictly out of scope:

1. **Permanent Invariant Locks:**
   - Both `LIVE_TRADING_ENABLED` and `REAL_BROKER_EXECUTION_ENABLED` are permanently set to `False` in [`src/version.py`](file:///home/ubuntu/algolab/src/version.py).
   - Any attempt to toggle these flags via environment variables, configuration files, or CLI arguments causes the system to fail-closed immediately at startup (exit code 1).
2. **AST Static Firewall:**
   - Static analysis tools inspect all codebase modules to prohibit invocation of real broker order placement APIs (`place_order`, `modify_order`, `cancel_order`).
3. **Execution Sandbox:**
   - All virtual orders are routed to the internal simulated matching engine (`services/paper-engine/`) and accounted for in the local virtual portfolio ledger (`data/swing_portfolio_ledger.db`).

---

## 2. Market Data Granularity Boundaries (EOD & 5-Minute Bars)

The platform is designed and calibrated for multi-day swing and intermediate intraday quantitative strategies:

1. **Supported Bar Granularities:**
   - **End-of-Day (EOD):** Official exchange bhavcopies and daily adjusted bars (09:15 to 15:30 IST).
   - **5-Minute Bars:** Deterministically constructed 5-minute OHLCV bars for intraday regime analysis and signal generation.
2. **Unsupported High-Frequency Granularities:**
   - Sub-minute bars (1-second, 5-second, 10-second) and tick-level high-frequency trading (HFT) / latency-arbitrage workflows are intentionally not supported.
3. **Session Windows & Auto-Square-Off:**
   - Market session boundaries strictly adhere to the National Stock Exchange of India (NSE) calendar.
   - Intraday paper positions are subject to a mandatory 15:15 IST auto-square-off schedule to prevent simulated overnight gap risk on MIS orders.

---

## 3. Historical Tick Bandwidth & Storage Constraints

1. **Tick Buffer Caps & Bandwidth Limitations:**
   - Streaming live market data adapters ingest Level-1 (LTP) and Level-2 (Top of Book) feeds from broker market data APIs.
   - Due to network bandwidth and local disk storage bounds, historical Level-3 full market depth (order book ladder) is not retained indefinitely in raw format.
2. **Storage Architecture:**
   - Real-time tick streams are aggregated into 5-minute bars and written to partitioned Parquet files (`data/cache/intraday_5m/`) and DuckDB point-in-time tables.
   - If websocket buffers experience saturation during high-volatility spikes, ticks are safely dropped with an explicit warning rather than stalling the synchronous execution loop.

---

## 4. Indian Statutory Tax & Cost Model Assumptions

Simulated execution prices and net P&L calculations incorporate double-entry statutory friction models based on 2026 Indian regulatory rules:

1. **Statutory Schedule Applied:**
   - **Securities Transaction Tax (STT):**
     - Delivery (CNC) Equities: 0.1% on buy and 0.1% on sell notional.
     - Intraday (MIS) Equities: 0.025% on sell notional only.
     - Equity Options: 0.0625% on sell premium notional (or 0.125% upon exercise).
   - **Stamp Duty:** 0.015% on delivery buy notional (Indian Stamp Act rate).
   - **Exchange Turnover Charges:** 0.00297% of traded value (NSE cash segment rate).
   - **SEBI Turnover Charges:** ₹10 per crore (0.0001% of traded value).
   - **Depository Participant (DP) Charges:** ₹15.34 flat per sell transaction ISIN (CDSL depository fee).
   - **Goods and Services Tax (GST):** 18% applied to brokerage, exchange turnover fees, and DP charges.
2. **Model Assumptions & Exclusions:**
   - Standard broker flat rate (₹20 per executed order or 0.03%, whichever is lower) is assumed by default; bilateral client-negotiated commission schedules are not modeled.
   - Tax jurisdiction is assumed to be Indian domestic resident; Foreign Portfolio Investor (FPI) tax treaties, surcharge brackets, and Double Tax Avoidance Agreements (DTAA) are not evaluated.
   - Physical settlement of derivatives at expiry is not modeled; option contracts are assumed cash-settled against final settlement price.

---

## 5. Storage Scalability & Concurrency Limits

1. **Single-Node SQLite Ledger:**
   - Virtual paper portfolios use SQLite with `BEGIN EXCLUSIVE` transaction locking to guarantee atomic double-entry accounting without race conditions.
   - This design is robust for single-node workloads but will experience lock contention if parallel execution threads attempt hundreds of write operations per second against the same file.
2. **Memory Footprint:**
   - Multi-symbol 5-year 5-minute bar backtests require approximately 4GB–8GB of RAM for vector calculations across the Nifty 50 / Nifty 100 universe.
