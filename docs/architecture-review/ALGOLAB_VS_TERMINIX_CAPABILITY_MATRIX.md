# Capability Matrix: AlgoLab vs Terminix

| Capability | Candidate A (AlgoLab) | Candidate B (Terminix) | Notes |
|---|---|---|---|
| **Execution Idempotency** | PARTIAL | MISSING | AlgoLab implements T08, though 2 idempotency edge-case tests currently fail. Terminix relies on isolated run scripts. |
| **Concurrency-Safe Capital** | PARTIAL | UNSAFE | AlgoLab implements T15 (risk checks exist, tests fail boundary edges). Terminix mutations bypass central state. |
| **Duplicate-fill Handling** | VERIFIED | MISSING | AlgoLab implements `executions_ledger` with unique constraints. |
| **Out-of-order Execution** | VERIFIED | MISSING | AlgoLab implements T09. |
| **Risk Control** | PARTIAL | UNSAFE | AlgoLab has `BrokerGateway` limits. Terminix runs direct API calls. |
| **Paper/Live Guard** | VERIFIED | UNSAFE | AlgoLab gates environments natively. Terminix uses raw WebSockets and API keys directly. |
| **Broker Adapter Isolation** | VERIFIED | UNSAFE | AlgoLab uses unified Gateway. Terminix has direct `place_order` calls in standalone adapters. |
| **Secret Handling** | VERIFIED | UNSAFE | Terminix uses local `dotenv` and plaintext API keys in ad-hoc tests. |
| **Database Ownership** | VERIFIED | UNSAFE | AlgoLab centralizes on `OrderLedgerDB`. Terminix relies on distributed disjoint SQLite files per run session. |
| **Reconciliation** | PARTIAL | PARTIAL | AlgoLab has tests for it (some failing). Terminix has basic manual audit scripts. |
| **P&L Integrity** | PARTIAL | UNKNOWN | AlgoLab P&L snapshots currently fail. Terminix has isolated metrics. |
| **Crash Recovery** | VERIFIED | MISSING | AlgoLab tests `reconstruct_state_from_ledger`. Terminix lacks state resurrection. |
| **Shutdown Safety** | VERIFIED | MISSING | AlgoLab implements safe closure checks. |
| **Test Quality** | VERIFIED | UNSAFE | AlgoLab uses behavior-driven integration tests for boundaries. Terminix has high coverage but is entirely blocked by a broken certification wall. |
| **Documentation** | VERIFIED | PARTIAL | AlgoLab has ADRs and thorough reviews. Terminix has basic READMEs. |
| **Deployment Maturity** | VERIFIED | UNKNOWN | AlgoLab includes established orchestration configs. |
| **Modularity** | VERIFIED | PARTIAL | AlgoLab exposes safe boundaries. Terminix models are deeply coupled to data ingest and broker execution. |
