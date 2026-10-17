# Runbook: Algo Lab Backup, Restore, and Disaster Recovery

## 1. Objectives & SLA Guarantees

| Metric | Target SLA | Description |
|---|---|---|
| **RPO (Recovery Point Objective)** | **< 1 hour / EOD Snapshot** | Maximum acceptable data loss window for swing and intraday simulated portfolios. EOD snapshots occur at 15:35 IST daily. |
| **RTO (Recovery Time Objective)** | **< 5 minutes** | Time required to verify, decrypt, unpack, and re-mount portfolio ledgers and experiment registries on a fresh VM or container. |
| **Integrity Assurance** | **100% SHA-256 Validated** | Zero unverified archives restored; fail-closed verification on any checksum mismatch. |
| **Confidentiality** | **Encrypted at Rest** | AES/Stream encryption keyed via `BACKUP_ENCRYPTION_KEY`; zero credentials or plaintext tokens in metadata. |

---

## 2. Backup Architecture & Manifest Format

Algo Lab creates atomic, encrypted tarball archives containing:
1. `data/swing_portfolio_ledger.db` — SQLite double-entry transactional ledger.
2. `data/live_portfolio_state.json` — Point-in-time runtime daemon state.
3. `data/manifests/*.json` — Point-in-time dataset and experiment manifests.

Each backup produces a sidecar JSON manifest (`algolab_backup_<TIMESTAMP>.manifest.json`) containing:
```json
{
  "backup_version": "1.0.0",
  "created_at_utc": "2026-10-14T15:39:22Z",
  "lifecycle_state": "forward-paper-validation",
  "files": {
    "swing_portfolio_ledger.db": {
      "original_size": 28672,
      "sha256": "4a7b..."
    }
  },
  "archive_sha256": "8f2c...",
  "archive_size_bytes": 14210
}
```

---

## 3. Operational Procedures

### Creating an Encrypted Backup
```bash
python3 scripts/backup_restore.py --create --retention-days 30
```
This writes the encrypted archive to `backups/algolab_backup_<TIMESTAMP>.tar.enc` and deletes backups older than 30 days.

### Verifying Backup Integrity
```bash
python3 scripts/backup_restore.py --verify backups/algolab_backup_<TIMESTAMP>.tar.enc
```
Exits with code `0` if archive checksum and all inner file digests match; exits with code `1` and fails closed if corrupted.

### Restoring a Backup
```bash
python3 scripts/backup_restore.py --restore backups/algolab_backup_<TIMESTAMP>.tar.enc --target-dir data/
```

### Automated CI & Staging Smoke Test
```bash
python3 scripts/backup_restore.py --test-restore
```
Creates a temporary sandbox, generates an encrypted backup, verifies checksums, restores, and validates file contents.

---

## 4. Emergency Incident Recovery Runbook

1. **Stop active services:**
   ```bash
   sudo systemctl stop quant-os.service
   ```
2. **Inspect and identify the most recent valid backup:**
   ```bash
   python3 scripts/backup_restore.py --verify $(ls -t backups/*.tar.enc | head -n 1)
   ```
3. **Execute restore:**
   ```bash
   python3 scripts/backup_restore.py --restore $(ls -t backups/*.tar.enc | head -n 1) --target-dir data/
   ```
4. **Run release safety check:**
   ```bash
   make safety-check
   ```
5. **Restart daemon:**
   ```bash
   sudo systemctl start quant-os.service
   ```

---

## 5. Related Operational Runbooks
- **Deployment Rollback & Fast RTO Restore**: See [`OPERATIONAL_HANDOVER_AND_PROCEDURES.md`](OPERATIONAL_HANDOVER_AND_PROCEDURES.md#6-deployment-rollback-procedure).
- **Incident Response & SRE Alerts**: See [`INCIDENT_RESPONSE_AND_ALERTS.md`](INCIDENT_RESPONSE_AND_ALERTS.md).

