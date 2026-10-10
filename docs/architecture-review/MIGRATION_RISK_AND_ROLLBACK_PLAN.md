# Migration Risk and Rollback Plan

## Data/Schema Compatibility Risk
- **Database Conflict**: Terminix frequently runs its paper-engine and tests via isolated, dynamically created SQLite instances. AlgoLab utilizes a unified `OrderLedgerDB` schema with strict primary/idempotency keys (T08, T15).
- **Behavior Collision**: If Terminix execution or paper-engine models were ported entirely, it would immediately overwrite and lose the hardened T06 (partial fills), T08 (duplicate execution), T09 (out of order execution), and T15 (concurrent reservation) safety controls.

## Recommended Migration Strategy (Selective Extraction)
To minimize risk, we will adopt a **selective import** strategy rather than a wholesale repository switch.

### Reversible Migration Plan
1. **Branching**: All work happens on isolated feature branches in the canonical AlgoLab repository (e.g., `feat/import-indicators-terminix`).
2. **Tagging**: Create an annotated Git tag in `/home/ubuntu/algolab` right before any extraction begins (`git tag -a base-pre-terminix-extraction -m "Pre-migration baseline"`).
3. **One Component at a Time**:
    - Import stateless mathematics first (Indicators).
    - Ensure all tests in `pytest oms_project/tests/` still yield exactly 60 passes and 9 failures (or improved).
    - Commit and merge.
4. **Rollback**: If a port compromises the `BrokerGateway` or `OrderLedgerDB`, immediately execute `git checkout base-pre-terminix-extraction` or revert the PR. No external broker state is affected because all testing uses local paper constraints.
