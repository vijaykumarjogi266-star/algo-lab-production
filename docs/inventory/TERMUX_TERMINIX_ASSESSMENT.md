# Termux / Terminix Assessment

## Overview
`/home/ubuntu/termux-ai-sandbox`

- **Reusable Tested Components**: May contain lightweight execution scripts or mobile-friendly notification adapters.
- **Overlap with Active OMS**: High risk of overlapping logic in standalone Python scripts bypassing the formal `BrokerGateway`.
- **Version Conflicts**: Unlikely to contain the hardened T15 concurrent risk reservations or T06 partial fill patches.
- **Migration Risks**: Directly merging scripts could reintroduce non-idempotent execution paths or live Zerodha tokens.
- **Recommended Extraction Sequence**:
  1. Audit for unique data adapters or notification webhooks.
  2. Port logic via PRs against the canonical `algolab` architecture, wrapping them in `BrokerGateway` protections.
  3. Archive the sandbox.
