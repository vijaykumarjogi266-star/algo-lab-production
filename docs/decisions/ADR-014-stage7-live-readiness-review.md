# ADR-014: Stage 7 Live-Trading Readiness Review & Pre-Flight Attestation Engine

## Context
Following Stage 5 (Independent Live Paper Trading) and Stage 6 (Broker Read-Only Shadow Mode), the OMS project required a formal, objective **Live-Trading Readiness Review & Pre-Flight Attestation Engine** to systematically evaluate algorithmic, financial, and operational safety before authorizing any controlled live pilot (Stage 8).

## Decision
We implement Stage 7: **Live-Trading Readiness Review & Pre-Flight Attestation Engine** (`oms_project/live_readiness_review.py`):

1. **7 Institutional Readiness Gates**:
   - **Gate 1 (Dataset Integrity & Golden Regression)**: Asserts 100% test pass rate across all unit, integration, and golden regression suites.
   - **Gate 2 (Friction & Slippage Stress Sensitivity)**: Validates that strategy profit factor remains $\ge 1.15$ under 1.5x statutory friction and 2x slippage stress.
   - **Gate 3 (Accounting Zero-Leakage Invariant)**: Reconciles ending cash vs starting cash, turnover, and fees; fails closed if discrepancy $\ge 0.01$ INR.
   - **Gate 4 (Natural Forward Evidence Accumulation)**: Enforces minimum 20 authenticated live paper trading sessions (30 calendar days). Fails closed with `INSUFFICIENT_EVIDENCE` if incomplete.
   - **Gate 5 (AST Hard Execution Firewall & Secret Masking)**: Verifies AST hard lockout, zero live broker routing routes, and secret redaction.
   - **Gate 6 (Drawdown Circuit Breakers & Risk Boundaries)**: Verifies that max historical portfolio drawdown does not breach 5% risk tolerance.
   - **Gate 7 (Decision Engine Profile Adaptability & Anti-Whipsaw)**: Verifies hysteresis cooldown, confirmation thresholds, and emergency fail-closed escalations.

2. **Classification Hierarchy**:
   - `DISQUALIFIED`: Any gate failed or security/accounting defect detected.
   - `INSUFFICIENT_EVIDENCE`: Clean algorithmic/security profile, but lacking required natural forward sessions (<20).
   - `CONDITIONALLY_CERTIFIED`: All 7 readiness gates 100% satisfied.
   - `PROMOTED_FOR_PILOT`: Operator sign-off for controlled live pilot.

3. **Cryptographic Attestation**:
   - Generates an immutable, HMAC-SHA256 signed `LiveReadinessAttestation` token.

## Consequences & Verification
- 5 dedicated unit/integration tests added in `oms_project/tests/test_live_readiness_review.py` (5/5 passed).
- Total OMS test suite expands to **175 passed tests** (0 failures).
- Algolab core suite passes **284 tests** (0 regressions).
