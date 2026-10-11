# ADR-012: Stage 5 Independent Live Paper Trading Orchestrator & Autonomous Loop

## Context
Following Stage 4 (Decision Engine, Candidate Intents, and Controlled Market Adaptability), the Algo Lab quantitative execution framework possessed isolated modules for historical replay, simulated exchanges, and regime-adaptive sizing. However, it lacked an integrated, autonomous **Live Paper Trading Loop** able to ingest live market ticks (from providers like NSE India, Yahoo Finance, and Angel One), evaluate candidate intents in real time, execute simulated orders on Zerodha BaseX with accurate Indian statutory frictions, monitor drawdown circuit breakers, and perform deterministic End-of-Day (EOD) financial reconciliation.

## Decision
We introduce Stage 5: **Independent Live Paper Trading Orchestrator & Autonomous Loop** (`oms_project/live_paper_orchestrator.py`):

1. **Autonomous Session Lifecycle**:
   - Explicit session state machine: `INITIALIZED` -> `ACTIVE` -> `PAUSED` -> `CIRCUIT_BREAKER_TRIPPED` -> `CLOSED_EOD`.
   - Continuous Mark-to-Market (MTM) calculation tracking Portfolio Equity = Cash + Positions * LTP.

2. **Hard-Risk Circuit Breakers & Fail-Closed Guards**:
   - `CircuitBreakerConfig` enforcing maximum drawdown limits (e.g. 5%) and maximum daily loss in INR.
   - Immediate fail-closed response: Upon breach, the session unconditionally halts new entry orders (`REJECTED_BY_RISK`).
   - Risk exit / reduce-only orders (`REDUCE_ONLY` / `EXIT_LONG` / `EXIT_SHORT`) are permitted to allow graceful risk unwinding.

3. **Multi-Source Ingestion & Zerodha BaseX Integration**:
   - Ingests streaming normalized `MarketTickEvent` from NSE Live, YFinance, or Angel One.
   - Routes sized `CandidateIntent` objects directly into the `ZerodhaBaseXAdapter` paper execution venue.
   - Deducts realistic Indian friction (Brokerage, STT, Exchange Turnover, SEBI, GST, Stamp Duty).

4. **Deterministic EOD Reconciliation**:
   - Formal audit asserting zero financial leakage:
     $$\text{Cash}_{\text{closing}} = \text{Cash}_{\text{initial}} + \text{Turnover}_{\text{sell}} - \text{Turnover}_{\text{buy}} - \text{Fees}_{\text{total}}$$
   - Any mathematical discrepancy ($\ge 0.01$ INR) fails validation.

## Consequences & Verification
- Stage 5 is completely verified with 4 dedicated unit/integration tests in `oms_project/tests/test_live_paper_orchestrator.py`.
- Full OMS test suite achieves 164 passed tests (0 failures).
- Algolab core suite passes 284 tests (0 failures).
