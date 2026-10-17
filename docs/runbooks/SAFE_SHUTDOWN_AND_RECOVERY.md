# Safe Shutdown and Recovery

1. **Initiation**: Triggered via `initiate_shutdown` or host `SIGTERM` / `Ctrl+C`.
2. **Blocked**: All new order intent without `reduce_only=True`.
3. **Late Fills**: Accepted correctly via webhook async logic.
4. **Restart**: The `BrokerGateway` reloads the active `shutdown_session_id`.
5. **Emergency Halt & Forensic Quarantine**: For comprehensive step-by-step procedures on emergency halting, process termination via `systemctl`, forensic snapshotting, and transaction rollback, see [`OPERATIONAL_HANDOVER_AND_PROCEDURES.md`](OPERATIONAL_HANDOVER_AND_PROCEDURES.md#5-paper-engine-emergency-halt--quarantine-protocol).

