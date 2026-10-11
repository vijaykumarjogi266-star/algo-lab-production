# Runbook: Historical Data Registration and Provenance Verification

## Overview
This runbook guides operators and quantitative researchers in registering, auditing, and replaying historical datasets under the Algo Lab Stage 1 governance framework.

## 1. Registering a Dataset
```python
from oms_project.database import OrderLedgerDB
from oms_project.data_registry import HistoricalDataRegistry

db = OrderLedgerDB("path/to/ledger.db")
registry = HistoricalDataRegistry(db)

metadata, report = registry.register_dataset(
    file_path="data/historical/reliance_2026.csv",
    name="Reliance Q3 2026 Ticks",
    source="NSE_ARCHIVE",
    provider="EXCHANGE_DIRECT",
    acquisition_date="2026-10-10",
    symbols=["RELIANCE"],
    market="NSE",
    timezone="Asia/Kolkata",
)
print(f"Registered {metadata.dataset_id} with status: {metadata.quality_status}")
```

## 2. Integrity and Quarantine Procedures
If a dataset is altered on disk after registration:
1. `registry.verify_integrity(dataset_id)` automatically detects the hash difference.
2. The dataset status is set to `QUARANTINED` in the database.
3. A `ChecksumMismatchError` is raised.
4. All replay runs referencing this dataset are immediately halted.

To resolve a quarantine:
1. Identify whether corruption, unauthorized editing, or disk failure occurred.
2. If legitimate clean data was provided, re-register as a new dataset version with an incremented `schema_version` and documented reason.
3. Never manually alter database checksums to match corrupted files.

## 3. Replay Run Binding
When initializing a replay engine:
```python
from oms_project.replay_service import HistoricalReplayEngine

replay = HistoricalReplayEngine()
run_id = replay.load_verified_dataset(
    registry=registry,
    dataset_id=metadata.dataset_id,
    configuration={"strategy": "STRAT_001", "slippage_bps": 5.0}
)
```
The run is permanently logged in `replay_runs` with the dataset ID, version, checksum, and configuration hash.
