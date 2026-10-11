# ADR-013: Stage 6 Broker Read-Only Shadow Mode & Cross-Venue Reconciliation Engine

## Context
Following Stage 5 (Independent Live Paper Trading Orchestrator), the Algo Lab platform possessed a complete autonomous paper loop capable of processing streaming ticks and maintaining simulated portfolios.
However, before considering live-trading readiness or governance review (Stage 7), the platform required a dedicated **Broker Read-Only Shadow Mode** to continuously cross-verify internal paper execution against authentic broker account states (e.g. Zerodha Kite, Angel One), while guaranteeing 100% fail-closed isolation from real-money order routing.

## Decision
We implement Stage 6: **Broker Read-Only Shadow Mode & Cross-Venue Reconciliation Engine** (`oms_project/shadow_mode.py`):

1. **Broker Read-Only Shadow Protocol**:
   - Polling broker profile, margins, available cash, open positions, and holdings.
   - Enforcing strict read-only execution: Zero order placement (`placeOrder`, `modifyOrder`, `cancelOrder` are permanently locked at code and AST levels).
   - Generates immutable `BrokerShadowSnapshot` audit records.

2. **Cross-Venue Reconciliation & Drift Detection**:
   - Cross-reconciles internal OMS portfolio against the broker shadow snapshot.
   - Calculates cash delta and position variances across all symbols.
   - Severity classification:
     - `CLEAN`: Zero variance.
     - `WARNING`: Minor cash variance within tolerable threshold ($\le 2\%$).
     - `MATERIAL_DRIFT`: Position mismatch (extra or missing shares) or cash delta exceeding tolerance. Triggers operator alerts.

3. **Fail-Closed Security Assurance**:
   - Asserts `LIVE_TRADING_ENABLED == False` permanently.
   - Any attempt to route orders into real broker APIs raises an unconditional `PermissionError`.

## Consequences & Verification
- 6 dedicated unit/integration tests added in `oms_project/tests/test_shadow_mode.py` (6/6 passed).
- Total OMS test suite expands to **170 passed tests** (0 failures).
- Algolab core suite passes **284 tests** (0 regressions).
