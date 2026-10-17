# ADR-015: Institutional Paper-Only Hardening & Full Remediation Architecture

## Status
- **Status:** Accepted
- **Date:** 2026-10-14
- **Author:** Lead Systems Engineer (@vijaykumarjogi266-star)
- **Deciders:** Institutional Quantitative Systems Committee

## Context
Algo Lab is transitioning from multi-stage prototype research to an institutional forward paper-trading and quantitative simulation platform for Indian Cash Equities (NSE/BSE).
A disciplined remediation is required to ensure:
1. Strict, uncompromised enforcement of paper-only safety invariants.
2. Canonical synchronization across semantic versioning (`v0.3.0`), CI gates, and operational runbooks.
3. Explicit role-based access control (RBAC), constant-time credential verification, and structured auditing.
4. Independent risk engine gatekeeping where no strategy, AI model, or frontend route can directly submit orders or route real capital.
5. Point-in-time safe, deterministic data governance and execution simulation with realistic Indian statutory costs.

## Decision

### 1. Canonical Version & Safety Single Source of Truth
- Created `src/version.py` defining `__version__ = "0.3.0"`, `LIFECYCLE_STATE = "forward-paper-validation"`, `LIVE_TRADING_ENABLED = False`, and `REAL_BROKER_EXECUTION_ENABLED = False`.
- All APIs, daemons, and engines import and enforce this module at startup.

### 2. CI/CD Release Check Gate
- Created `Makefile` with `make release-check` as the mandatory, fail-closed CI gate.
- CI pipeline executes: lint, typecheck, unit/contract tests, bandit security scan, secret scan, SBOM generation, and release evidence validation.

### 3. API Security & RBAC Enforcement
- Replaced flat secret verification with explicit roles: `viewer`, `researcher`, `operator`, `risk_admin`, `system_admin`.
- Enforce constant-time token comparison (`hmac.compare_digest`), hashed storage, and CSP headers without `unsafe-inline`.

### 4. Risk Engine Authority & Software Isolation
- Enforce architectural boundaries via AST/import tests: strategies output intent signals only; only the independent risk engine approves orders; only the paper execution engine creates simulated fills.

### 5. Statutory Delivery Cost Realism
- Model full Indian equity delivery (CNC) friction: STT (0.1%), Stamp Duty (0.015%), DP charges (₹15.34/₹15.93 flat on sell), Exchange turnover fee (0.00297%), SEBI turnover fee (₹10/crore), and 18% GST on taxable services.

## Consequences
- **Positive:** High reproducibility, mathematical truth, fail-closed security, auditable paper trading records, zero risk of real-money leakage.
- **Trade-offs:** Stricter local CI requirements; slightly longer test runtime due to comprehensive static security and type checking.

## Verification Evidence
- Verification command: `make release-check`
- Automated test: `tests/unit/test_stage6_integrity.py`, `tests/unit/test_architecture_boundaries.py`
