# ALGO LAB SUPPORT MATRIX & ENVIRONMENT SPECIFICATION
**Version:** 1.0.0 (Quality-First Baseline)  
**Governing Plan:** *Algo Lab: Quality-First Execution Plan — September 25, 2026 (Section 2.1)*  

---

## 1. Operating Boundaries & Supported Environments

| Dimension | Supported Specification | Unsupported (Strictly Excluded) |
| :--- | :--- | :--- |
| **Operating System** | Linux Ubuntu 24.04 LTS (x86_64 / aarch64) | Windows, macOS, unvetted container distros |
| **Python Runtime** | Python 3.12.3 (CPython) | Python <= 3.11, Python >= 3.13, PyPy |
| **Execution Mode** | **Paper Trading Standby & Offline Research Only** | **Live Trading, Real Broker Order Routing** |
| **Safety Flags** | `ALLOW_LIVE_TRADING = False`<br>`ALLOW_REAL_BROKER_EXECUTION = False` | Any flag setting enabling real capital routing |
| **Asset Class** | Indian Cash Equities (NSE Segment 1) | Derivatives (F&O), Commodities, Currencies, Crypto |
| **Execution Order Types** | Long-Only CNC / MIS Simulated Orders | Leverage, Short Selling, Margin Trading Facility (MTF) |
| **Market Data Provider**| Angel One SmartAPI (Smart Stream 2.0 Binary) | Direct exchange co-location, unapproved third-party scrapers |
| **Timezone Standard** | Storage: `UTC`<br>Session & Display: `Asia/Kolkata (IST)` | Naive timestamps, local server time offsets |
| **Accounting Standard** | Double-Entry Statutory Indian Equity (Paise / Decimal) | Unbalanced single-entry ledgers, float-only equity |

---

## 2. Pinned Software Stack

| Component | Pinned Version | Purpose |
| :--- | :--- | :--- |
| **API Framework** | FastAPI `0.141.1`, Uvicorn `0.52.4` | System REST API, health probes, paper trading endpoints |
| **Data Validation** | Pydantic `2.13.5`, Pydantic-Settings `2.15.0` | Schema enforcement, invariant field validation |
| **High-Perf Compute** | Polars `1.44.2`, NumPy `2.5.3`, PyArrow `25.0.1` | Vectorized indicator calculations, point-in-time stores |
| **Persistence** | SQLite 3 (Python stdlib), DuckDB `1.5.5` | Atomic session journals, Parquet analytics |
| **Market Data SDK** | SmartAPI-Python `1.5.5`, WebSocket-Client `1.9.2` | Angel One market data streaming & instrument master |
| **Testing** | Pytest `9.1.1`, Pytest-Asyncio `1.4.0`, Pytest-Cov `7.1.0` | Unit, property, contract, and regression test suites |

---

## 3. Scope Expansion Gate

Per Section 2.1 of the Quality-First Execution Plan:
> *"An unlisted environment is unsupported until tested and approved. Expansion is a scoped change with its own evidence; changing a provider, strategy, market regime, or infrastructure component must not silently inherit acceptance from another configuration."*
