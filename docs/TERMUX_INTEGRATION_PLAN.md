# Termux Integration Plan

This document outlines the phased strategy for integrating permissible components from the Termux repository (`/home/ubuntu/termux-ai-sandbox`) into the Canonical Algo Lab repository (`/home/ubuntu/algolab`), ensuring the hardened core (T06, T08, T09, T15) remains untouched.

## Principles
1. **Never overwrite canonical code automatically.**
2. **Canonical owns state**: `OrderLedgerDB`, `capital_reservations`, `BrokerGateway`, state machine, and risk checks are supreme.
3. **One component per branch.**

## Stage 1: Safe Read-Only Utilities
**Goal**: Import stateless mathematics, analytics, and documentation.
- Actions:
  - Migrate `algopro/quant/indicators/*` to Canonical `/home/ubuntu/algolab/oms_project/research/indicators/`.
  - Migrate `algopro/services/evaluation_engine/metrics.py` to Canonical evaluation path.
  - Transfer non-trading documentation and strategy markdown files.
- Requirement: Zero changes to Canonical OMS logic. Verify with unit tests.

## Stage 2: Health Checks and Dashboards
**Goal**: Integrate the web UI components and monitoring dashboards.
- Actions:
  - Import `web_controller/static/*` assets.
  - Refactor `web_controller/server.py` to serve exclusively as a read-only viewer for `OrderLedgerDB`.
- Requirement: The dashboard may display states but cannot submit order intents without passing through canonical API authentication.

## Stage 3: Refactor Event Receivers
**Goal**: Adapt Termux data adapters to Canonical patterns.
- Actions:
  - Extract the core parsing logic from `algopro/services/market-data/adapters/dhan_adapter.py`.
  - Wrap it so it forwards only normalized market data events into canonical APIs.
  - Implement Canonical interface constraints (no direct `place_order` methods).
- Requirement: All incoming data must go through the canonical normalized bus.

## Stage 4: Reject or Redesign Direct Trading Scripts
**Goal**: Enforce boundary integrity against legacy Termux scripts.
- Actions:
  - Identify all `run_session_*.py` and ad-hoc broker scripts (e.g. `marketfeed.py`, `dhan_debug.py`).
  - Reject their inclusion into the main system.
  - Where a specific trading scenario is valuable, redesign it purely as a canonical test suite that uses `oms_project.schemas.OrderIntent`.
- Requirement: Explicitly mark scripts as `UNSAFE_DIRECT_TRADING_PATH` and archive them externally.

## Stage 5: Isolated Git Branch Testing
**Goal**: Safely deploy imported components.
- Actions:
  - Test one imported component at a time on a separate Git branch.
  - Run the entire hardened test suite (`pytest oms_project/tests/`) to ensure no regressions in T06, T08, T09, or T15.
  - Code review boundary limits.
  - Merge into main once tests pass.
- Requirement: Zero reduction in test coverage or stability.
