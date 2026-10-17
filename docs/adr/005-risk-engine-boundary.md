# ADR-005: Independent Risk Engine Boundary & Architectural Isolation

## Status
- **Status:** Accepted
- **Date:** 2026-10-14
- **Author:** Lead Systems Architect (@vijaykumarjogi266-star)
- **Deciders:** Institutional Quantitative Systems Committee / Lead Systems Architect

## Context
In automated quantitative architecture, a pervasive failure pattern is the conflation of alpha generation (strategy logic) with risk management and execution routing. When strategies, generative AI advisory modules, or web interfaces possess direct authority to submit orders or size trades, severe vulnerabilities emerge:
1. **Uncontrolled Position Sizing:** A misconfigured alpha strategy or rogue calculation loop can size orders disproportionately, causing massive portfolio concentration or capital exhaustion.
2. **Race Conditions in Multi-Strategy Capital Reservation:** Multiple concurrently executing strategies can simultaneously evaluate available cash and both submit maximum-allocation orders, leading to over-leverage or settlement default.
3. **Regime Ignorance:** Individual strategies lack global visibility into macroeconomic market regimes (e.g., exchange circuit breakers, high-volatility spikes, degraded data feeds), continuing to generate entry signals when platform safety mandates cash preservation.
4. **AI Hallucination Execution:** LLM-based assistants or external advisors could output erratic trade instructions that would execute directly if not constrained behind strict mathematical risk filters.

A hardened, independent risk engine is required to serve as an un-bypassable gatekeeper between intent creation and paper order execution.

## Decision
We enforce the complete architectural decoupling of the Risk Engine ([`services/risk-engine/`](file:///home/ubuntu/algolab/services/risk-engine/)) from all alpha strategies, machine learning models, AI advisors, and web user interfaces through strict lifecycle state transitions and AST import barriers.

### 1. The Candidate Intent Lifecycle
No strategy or AI model is permitted to generate or execute orders directly. Instead, strategy components emit pure, non-binding **Candidate Intents**:

```
[Strategy / AI Advisor]
        │
        ▼ (Generates Candidate Intent only)
   [ CANDIDATE ]
        │
        ▼
[Independent Risk Engine] ─── (Evaluates Global Exposure, Regimes & Capital Locks)
        │
   ┌────┴───────────────────────────┐
   ▼                                ▼
[ RISK_APPROVED ]              [ REJECTED ] (Persisted with rationale)
   │
   ▼
[ Dynamic Sizing & Cap Gate ]
   │
   ▼
[ DISPATCHED to Paper Execution Engine ]
```

1. **`CANDIDATE`:** Proposed trade signal containing symbol, proposed side, entry trigger, stop-loss price, and rationale.
2. **Risk Engine Validation:** The independent risk engine evaluates:
   - System-wide leverage and portfolio cash solvency.
   - Single-asset concentration limits (e.g., maximum 10% of portfolio value per ISIN).
   - Portfolio-level daily maximum drawdown stop (e.g., 2% daily loss lock).
   - Market regime gating (e.g., blocking entries during `DEGRADED_DATA` or `HIGH_VOLATILITY`).
   - Double-entry capital reservation locks to prevent concurrent race condition over-allocation.
3. **`RISK_APPROVED` or `REJECTED`:** The intent is either authorized or rejected with an immutable audit rationale.
4. **`SIZED` & `DISPATCHED`:** Only after risk clearance is the intent dynamically sized and routed strictly to the internal paper exchange simulator.

### 2. Architectural Import Barriers & AST Static Analysis
To guarantee that this separation is physically impossible to circumvent in code, automated boundary tests in [`tests/unit/test_architecture_boundaries.py`](file:///home/ubuntu/algolab/tests/unit/test_architecture_boundaries.py) enforce AST import isolation:
1. **Strategy Module Isolation:** All files in [`quant/`](file:///home/ubuntu/algolab/quant/) are scanned via Python AST. Any import of broker execution classes, order dispatchers, or raw trading endpoints causes immediate test failure.
2. **AI Advisor Isolation:** AI advisory modules ([`src/gpt_client.py`](file:///home/ubuntu/algolab/src/gpt_client.py), [`scripts/chatgpt_advisor.py`](file:///home/ubuntu/algolab/scripts/chatgpt_advisor.py)) are statically analyzed to ensure they never import `order_manager`, `execution`, or risk engine overrides. AI outputs are treated as advisory context, never execution directives.
3. **Web UI Isolation:** FastAPI dashboard endpoints cannot trigger paper execution directly; they can only query state or post candidate intents to the queue.

## Non-Negotiable Safety Invariant Compliance
- **Does this decision preserve `LIVE_TRADING_ENABLED = False`?**  
  **Yes.** The risk engine strictly validates that order dispatching routes exclusively to the paper execution engine and fails closed if live trading flags are true.
- **Does it maintain independent risk engine authority?**  
  **Yes.** This ADR establishes the absolute independence and primacy of the risk engine over all strategies, AI advisors, and UI controllers.
- **Does it prevent synthetic data substitution in production paper paths?**  
  **Yes.** The risk engine evaluates market liquidity and volatility using only validated real market snapshots, refusing to clear orders when feeds are degraded or unvalidated.

## Consequences

### Positive
- **Architectural Immunity to Strategy Bugs:** A defective or runaway alpha algorithm cannot bankrupt virtual accounts or cause cascading liquidation; the risk engine enforces absolute limits.
- **Safe AI Integration:** Generative AI and LLM agents can be freely explored for research insights without any possibility of hallucinated market orders.
- **Zero Double-Allocation Race Conditions:** Atomic capital reservations prevent multiple parallel strategies from claiming the same capital buffer.
- **Comprehensive Audit Trail:** Every rejected and approved trade intent is persisted with its complete risk assessment metadata.

### Negative / Trade-offs
- **Execution Overhead:** Strategy signals must traverse the asynchronous candidate intent queue and risk verification stages before reaching simulation matching.
- **Strict AST Linter Restrictions:** Strategy developers cannot use convenience shortcuts or directly invoke execution helpers.

## Compliance & Verification Evidence
- **Link to relevant tests:**
  - [`tests/unit/test_architecture_boundaries.py`](file:///home/ubuntu/algolab/tests/unit/test_architecture_boundaries.py) (`test_strategies_cannot_import_live_broker`, `test_ai_advisor_cannot_submit_orders`)
  - [`tests/unit/test_architectural_isolation.py`](file:///home/ubuntu/algolab/tests/unit/test_architectural_isolation.py)
  - [`tests/unit/test_stage27_security_firewall.py`](file:///home/ubuntu/algolab/tests/unit/test_stage27_security_firewall.py)
- **Verification command:**
  ```bash
  .venv/bin/pytest tests/unit/test_architecture_boundaries.py tests/unit/test_architectural_isolation.py -q
  ```
