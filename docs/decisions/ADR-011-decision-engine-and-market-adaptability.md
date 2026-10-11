# ADR-011: Decision Engine, Candidate Intents, and Controlled Market Adaptability

## Context
In previous stages, the Algo Lab OMS established robust reconciliation and safety shutdown (Stage 0), historical data provenance (Stage 1), deterministic replay with market regime classification (Stage 2), and realistic internal paper execution (Stage 3).
Prior to Stage 4, algorithmic strategies lacked a formal separation between raw alpha proposals and actual order generation. Directly dispatching raw orders from strategies introduces systemic risks: lack of regime compatibility filtering, vulnerability to adverse market conditions (e.g. illiquid or high-volatility spikes), and missing auditability for rejected or downsized proposals.

## Decision
We introduce Stage 4: **Decision Engine, Candidate Intent Lifecycle, and Controlled Market Adaptability** (`oms_project/candidate_intent.py`):

1. **Candidate Intent Lifecycle & Immutability**:
   - Strategies never generate or submit direct broker orders. They generate structured `CandidateIntent` models.
   - Formal 4-phase state machine:
     - `CANDIDATE`: Strategy proposal with symbol, intent type, target exposure, time horizon, max slippage, and regime compatibility.
     - `RISK_APPROVED`: Validated through market regime gating and session rules.
     - `SIZED`: Dynamically sized based on market volatility, liquidity caps, and portfolio risk limits.
     - `DISPATCHED`: Converted to cryptographic signed `OrderIntent` and dispatched to `PaperExchange` or `BrokerGateway`.
   - Comprehensive terminal rejection states: `REJECTED_BY_REGIME` and `REJECTED_BY_RISK`.
   - Immutable audit trail recording each state change, timestamp, rationale, and transition metadata.

2. **Market Adaptation Profiles & Anti-Whipsaw Management**:
   - Explicit named profiles: `TRENDING`, `CHOPPY`, `HIGH_VOLATILITY`, `LOW_LIQUIDITY`, `DEGRADED_DATA`, and `NORMAL`.
   - Dynamic profile transitions managed via `ProfileTransitionManager`:
     - **Confirmation Threshold**: Requires consecutive observations (default 3) before transitioning between normal market regimes to prevent whipsawing on transient noise.
     - **Emergency Fail-Closed Escalation**: Immediate, zero-delay escalation into `DEGRADED_DATA` and `HIGH_VOLATILITY`.
     - **Hysteresis Cooldown**: Enforces a strict cooldown window (default 60s) before permitting de-escalation out of adverse/high-risk profiles.

3. **Fail-Closed Safeguards & Adaptive Sizing**:
   - Under `DEGRADED_DATA`: Mandates strict fail-closed behavior (`NO_TRADE` for all new entries; permits only `REDUCE_ONLY` / risk exits).
   - Under `HIGH_VOLATILITY`: Automatically scales down sizing (e.g. 50% scalar) to protect portfolio equity.
   - Under `LOW_LIQUIDITY`: Enforces strict maximum volume participation caps.
   - Under `CHOPPY`: Trend-following strategies are strictly blocked; mean-reversion strategies are permitted.

## Consequences & Verification
- Strict boundary between alpha generation and execution dispatch.
- Zero look-ahead bias and full compatibility with Stage 2 ReplayClock and Stage 3 PaperExchange.
- 11 dedicated tests added in `oms_project/tests/test_stage4_decision_engine.py`.
- Complete test suite expands to 160 passed tests with 0 regressions.
