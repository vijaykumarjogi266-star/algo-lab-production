# Safe Shutdown and Recovery

1. **Initiation**: Triggered via `initiate_shutdown`.
2. **Blocked**: All new order intent without `reduce_only=True`.
3. **Late Fills**: Accepted correctly via webhook async logic.
4. **Restart**: The `BrokerGateway` reloads the active `shutdown_session_id`.
