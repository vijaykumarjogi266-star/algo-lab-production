# Terminix Extraction Candidates

## 1. Safe to Extract (Stateless)
These components are purely mathematical or frontend assets with no risk of mutating system state:
- **Pure Indicators**: `algopro/quant/indicators/*` (EMA, MACD, RSI, etc.)
- **Evaluation/Metrics**: `algopro/services/evaluation_engine/*` (walk-forward tools, metrics)
- **Static UI Assets**: `web_controller/static/*`

## 2. Require Adapter Refactoring
These components have valuable logic but currently attempt to interact with state or brokers directly.
- **Strategies**: `algopro/quant/strategies/*` — Must be refactored to return canonical `OrderIntent` objects rather than executing trades.
- **Web Server Dashboard**: `web_controller/server.py` — Must be refactored into a read-only client of the canonical `OrderLedgerDB`.
- **Market Data Adapters**: Must be rewritten to pipe standard price ticks into the canonical data bus, completely removing order-execution capabilities.

## 3. Never Import Directly
These components violate the core invariants (GAP-06 idempotency, state consolidation, secure credentials) established in the canonical codebase.
- **Direct Broker Scripts**: `algopro/scratch/dhan_debug.py`, `marketfeed.py`
- **Ad-Hoc Session Runners**: `algopro/scratch/run_session_*.py`
- **Credential Handlers**: `paper-engine/adapters/credentials.py` (which loads dotenv secrets locally).
- **Duplicate Paper Engine**: `algopro/services/paper-engine/*` (conflicts with canonical partial-fill and duplicate-execution guardrails).
