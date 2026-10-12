# Project Status — Algo Lab Production Baseline

- **Proposed Canonical Root**: `/home/ubuntu/algolab` (authoritative repository)
- **Production Remote**: `https://github.com/vijaykumarjogi266-star/algo-lab-production` (Private)
- **Verified Test Suite Result**: **`201 passed, 2 warnings, 0 failures`** (175 OMS/Decision tests + 26 Unit/Scanner/Stress/Backtest tests)
- **Verified Components**: 
  - T05 / T10 Timeout & Broker Uncertainty Resolution
  - T06 / T08 / T09 / T15 Concurrent Risk & Capital Reservation
  - T18 / T19 / T20 Safe Shutdown & Ingestion Preserving Semantics
  - GAP-07 / T28 / T30 Deterministic Double-Entry Reconciliation
  - Stage 1 Cryptographic Data Integrity & Provenance
  - Stage 2 Monotonic Deterministic Replay & Look-Ahead Protection
  - Stage 3 Internal Paper Exchange Realism, Slippage & Queuing Mechanics
  - Stage 4 Candidate Intent Lifecycle & Multi-Regime Decision Adaptation
  - Stage 5-7 Deep Multi-Interval Technical Scanner & Autonomous EOD Swing Engine
  - Dynamic Ratchet Trailing Stop Engine with Injected Clock Isolation (`ClockProtocol`)
  - Statutory Indian Delivery Tax & Friction Model (STT, Stamp Duty, DP charges, GST)
- **Shutdown & Risk Semantics**:
  - Shutdown blocks new entries while cleanly preserving execution ingestion.
  - Restart restores durable SQLite state and continues blocking entries until all material breaks are reconciled.
- **Operating Modes & Safety Locks**:
  `TRADING_MODE=READ_ONLY`
  `ORDER_SUBMISSION_ENABLED=false`
  `ALLOW_LIVE_TRADING=false`
  `ALLOW_REAL_BROKER_EXECUTION=false`
- **Broker Safety & Execution Firewall**:
  - Live real-broker execution is strictly blocked by AST static analysis firewall.
  - No unsimulated broker order API endpoints (`placeOrder`, `modifyOrder`, `cancelOrder`) are reachable.
- **EOD Session Ledger (October 12, 2026)**:
  - Canonical Forward Swing Account: ₹100,000.00 (100% Cash Solvency, ₹0.00 drawdown, zero overnight risk exposure).
  - Intraday Paper Session (`sess_e22e8042bc25`): Successfully squared off via mandatory 15:15 IST trigger; session status `COMPLETED`.

## Safety Rules
1. All engineering work must occur exclusively within the canonical repository (`/home/ubuntu/algolab`).
2. Before modifying code, inspect existing implementations, contracts, and regression test suites.
3. Do not create auxiliary Algo Lab roots.
4. Overwriting entire files without line-by-line inspection is prohibited.
5. Merging external modules requires documented architectural comparison, test verification, git branch isolation, and rollback plans.
6. Every production update must update `CHANGELOG.md`, `PROJECT_STATUS.md`, `ARCHITECTURE.md`, and passing test evidence.
