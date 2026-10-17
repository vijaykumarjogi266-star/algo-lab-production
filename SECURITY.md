# Security Policy — Algo Lab

## Institutional Safety Invariants

Algo Lab is designed strictly as a **paper-only quantitative investment research and forward-simulation operating system**.
Under no circumstances does this repository facilitate real-money trading, live broker execution, or automated capital routing.

### Core Safety Locks
- `LIVE_TRADING_ENABLED = False` (Hardcoded fail-closed invariant)
- `REAL_BROKER_EXECUTION_ENABLED = False` (Hardcoded fail-closed invariant)
- AST-level static security firewalls inspect and prohibit any invocation of real broker order endpoints (`placeOrder`, `modifyOrder`, `cancelOrder`).
- Any environment or configuration setting that attempts to enable live execution fails application startup immediately with code 1.

---

## Supported Versions

| Version | Status | Security Support |
| :---: | :---: | :---: |
| 0.3.x | Active (Paper Validation) | ✅ Supported |
| < 0.3.0 | Legacy Baselines | ❌ Discontinued |

---

## Reporting a Vulnerability

If you discover a security flaw, unauthorized live trading path, secret exposure, or data leak vulnerability:

1. **Do NOT open a public GitHub issue.**
2. Send a confidential report to the security maintainers with:
   - Vulnerability description
   - Steps to reproduce
   - Potential impact
   - Proposed patch (if available)
3. You will receive an initial response within 24 hours and regular status updates until remediation is deployed.

---

## Secret Handling & Data Redaction

- All Zerodha (`pl5u************`), Angel One, OpenAI, Discord, and Telegram credentials must remain strictly masked in logs, shell outputs, and state files.
- Secrets must only be injected via environment variables (`.env` ignored by Git) or secure secret stores.
- Automated secret scanning is enforced in CI via `make release-check`.
