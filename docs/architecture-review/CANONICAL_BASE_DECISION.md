# Canonical Base Decision

## Selected Option
**OPTION 1: RETAIN_ALGOLAB_AS_CANONICAL** (Keep Candidate A as canonical and selectively extract safe modules from Candidate B).

## Confidence Level
**HIGH**

## Rationale
- **Verified Safety Invariants**: Candidate A (AlgoLab) possesses heavily tested guardrails for idempotency, partial fills, and concurrent risk reservation. Candidate B (Terminix) distributes state loosely across isolated SQLite files and runs insecure broker connections.
- **Migration Risk**: Switching to Terminix as the base (Option 2) would erase all the safety hardening achieved in T06, T08, T09, and T15. This is unacceptable for a system bound for live-money trading. Creating a brand new repository (Option 3) wastes effort recreating existing infrastructure.
- **Code Maturity**: While Terminix contains useful quantitative logic, its core execution layer is fundamentally broken (as evidenced by a suite-wide certification block during testing) and highly unsafe.

## Blocking Unknowns
- Resolving the 9 failing boundary tests in the current AlgoLab base (Candidate A) before live deployment.

## Exact First Implementation Task
1. **Fix the 9 failing OMS tests in Candidate A** (AlgoLab). Before we inject new Terminix code, the canonical base must return to a 100% green test suite.
