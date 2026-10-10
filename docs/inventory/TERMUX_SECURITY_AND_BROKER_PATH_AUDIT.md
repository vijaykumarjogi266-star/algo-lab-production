# Termux Security and Broker Path Audit

This document explicitly flags components from the Termux repository that represent **Unsafe Direct Trading Paths**. 

## What is an Unsafe Direct Trading Path?
Any component that attempts to:
- Directly load broker credentials (e.g. `dotenv`, `API key`, `secret`).
- Invoke broker API calls (e.g. `place_order`, `modify_order`, `cancel_order`) outside of the canonical `BrokerGateway`.
- Update position, risk, capital, or execution databases directly outside of canonical mechanisms like `OrderLedgerDB`.

## Identified Unsafe Paths

### 1. `algopro/services/paper-engine/adapters/credentials.py`
- **Classification**: `UNSAFE_DIRECT_TRADING_PATH`
- **Reason**: Loads secrets directly and handles raw database configurations bypassing canonical security models.
- **Remediation**: Do not copy. Canonical `config` and `BrokerGateway` should manage all environment credentials centrally.

### 2. `algopro/services/market-data/adapters/dhan_adapter.py`
- **Classification**: `UNSAFE_DIRECT_TRADING_PATH`
- **Reason**: Implements WebSocket feeds and direct API linkages containing API keys.
- **Remediation**: Data receivers must be refactored to forward normalized ticks into a canonical data bus. Trading actions must route through `BrokerGateway`.

### 3. `algopro/scratch/dhan_debug.py`, `dhan_live_test.py`, `marketfeed.py`, `dhan_cert_test.py`
- **Classification**: `UNSAFE_DIRECT_TRADING_PATH`
- **Reason**: Ad-hoc scripts that initialize `dotenv`, create independent connections, and test order submissions or WebSocket feeds directly.
- **Remediation**: Do not copy. All testing must be conducted via Canonical test runners mocking the `BrokerGateway`.

### 4. `algopro/scratch/run_session_*.py`
- **Classification**: `UNSAFE_DIRECT_TRADING_PATH`
- **Reason**: Workflow scripts manipulating independent SQLite databases to track `execution`, `position`, and `risk` states. This creates race conditions and circumvents idempotency guarantees (GAP-06).
- **Remediation**: Do not copy. Reconstruct scenarios as pytest integration suites acting strictly upon `OrderIntent` objects submitted to the canonical state machine.

### 5. `algopro/services/paper-engine/runner.py` & `execution.py`
- **Classification**: `DUPLICATE_OF_CANONICAL` / `UNSAFE_DIRECT_TRADING_PATH`
- **Reason**: The Termux paper engine contains logic for partial fills, execution, and position management. This conflicts with Canonical `OrderLedgerDB` which has already been hardened (T06, T08, T09).
- **Remediation**: Do not copy. All paper trading must use Canonical `paper_exchange.py` and `BrokerGateway`.
