"""
Stage 1: Historical Data Integrity and Provenance Test Suite
Asserts that all replay and simulation data is traceable, validated,
cryptographically verified, and strictly fails closed upon corruption or anomaly.
"""

import os
import csv
import time
import pytest
from decimal import Decimal
from oms_project.database import OrderLedgerDB
from oms_project.data_registry import (
    HistoricalDataRegistry, DataValidator, compute_file_sha256,
    ChecksumMismatchError, DataQualityValidationError, DatasetQuarantinedError
)
from oms_project.replay_service import HistoricalReplayEngine


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_data_registry.db")
    db = OrderLedgerDB(db_path=db_file)
    return db


def create_sample_csv(file_path: str, rows: list):
    with open(file_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "price", "volume", "timestamp"])
        writer.writeheader()
        writer.writerows(rows)


def test_valid_dataset_registration_and_provenance(temp_db, tmp_path):
    """Test standard registration of a valid dataset generates verified provenance."""
    csv_file = str(tmp_path / "reliance_valid.csv")
    base_time = 1750000000.0  # arbitrary epoch
    rows = [
        {"symbol": "RELIANCE", "price": 1200.0, "volume": 100, "timestamp": base_time + 1.0},
        {"symbol": "RELIANCE", "price": 1202.5, "volume": 150, "timestamp": base_time + 2.0},
        {"symbol": "RELIANCE", "price": 1201.0, "volume": 200, "timestamp": base_time + 3.0},
    ]
    create_sample_csv(csv_file, rows)

    registry = HistoricalDataRegistry(temp_db)
    meta, report = registry.register_dataset(
        file_path=csv_file,
        name="Reliance 3-Tick Sample",
        source="EXCHANGE_ARCHIVE",
        provider="NSE_OFFICIAL",
        acquisition_date="2026-10-10",
        symbols=["RELIANCE"],
        market="NSE",
        timezone="Asia/Kolkata",
    )

    assert meta.quality_status == "VERIFIED"
    assert meta.record_count == 3
    assert report.is_valid is True
    assert report.error_count == 0
    assert len(meta.sha256_checksum) == 64
    assert meta.sha256_checksum == compute_file_sha256(csv_file)


def test_modified_dataset_checksum_rejected_fails_closed(temp_db, tmp_path):
    """Test that any post-registration file alteration causes checksum rejection and quarantine."""
    csv_file = str(tmp_path / "tamper_test.csv")
    rows = [
        {"symbol": "INFY", "price": 1500.0, "volume": 50, "timestamp": 1000.0},
        {"symbol": "INFY", "price": 1505.0, "volume": 60, "timestamp": 1001.0},
    ]
    create_sample_csv(csv_file, rows)

    registry = HistoricalDataRegistry(temp_db)
    meta, _ = registry.register_dataset(
        file_path=csv_file,
        name="Infosys Clean",
        source="ARCHIVE",
        provider="TEST",
        acquisition_date="2026-10-10",
        symbols=["INFY"],
    )

    # Replay engine loads verified dataset initially
    replay = HistoricalReplayEngine()
    run_id = replay.load_verified_dataset(registry, meta.dataset_id)
    assert run_id.startswith("RUN_")
    assert len(replay.ticks) == 2

    # Now tamper with file on disk (simulate corruption or data drift)
    with open(csv_file, "a", encoding="utf-8") as f:
        f.write("INFY,9999.0,10,1002.0\n")

    # verify_integrity MUST detect mismatch, update status to QUARANTINED, and raise ChecksumMismatchError
    with pytest.raises(ChecksumMismatchError) as exc_info:
        registry.verify_integrity(meta.dataset_id)
    assert "Integrity breach" in str(exc_info.value)

    # Second check: dataset status is now QUARANTINED
    reloaded_meta = registry.get_dataset(meta.dataset_id)
    assert reloaded_meta.quality_status == "QUARANTINED"

    # Replay engine must fail closed
    replay2 = HistoricalReplayEngine()
    with pytest.raises((ChecksumMismatchError, DatasetQuarantinedError)):
        replay2.load_verified_dataset(registry, meta.dataset_id)


def test_duplicate_timestamps_detected_and_rejected(temp_db, tmp_path):
    """Test duplicate timestamps for the same symbol are caught and fail registration."""
    csv_file = str(tmp_path / "dup_ticks.csv")
    rows = [
        {"symbol": "TCS", "price": 3000.0, "volume": 10, "timestamp": 100.0},
        {"symbol": "TCS", "price": 3002.0, "volume": 20, "timestamp": 100.0},  # Duplicate TS
    ]
    create_sample_csv(csv_file, rows)

    registry = HistoricalDataRegistry(temp_db)
    with pytest.raises(DataQualityValidationError) as exc:
        registry.register_dataset(
            file_path=csv_file,
            name="TCS Dup",
            source="ARCHIVE",
            provider="TEST",
            acquisition_date="2026-10-10",
            symbols=["TCS"],
        )
    assert "DUPLICATE_TIMESTAMP" in str(exc.value)


def test_out_of_order_records_and_gaps_detected(temp_db, tmp_path):
    """Test out-of-order timestamps and abnormal gaps are detected in data quality check."""
    csv_file = str(tmp_path / "out_of_order.csv")
    rows = [
        {"symbol": "HDFC", "price": 1600.0, "volume": 10, "timestamp": 200.0},
        {"symbol": "HDFC", "price": 1605.0, "volume": 10, "timestamp": 150.0},  # Out of order
    ]
    create_sample_csv(csv_file, rows)

    registry = HistoricalDataRegistry(temp_db)
    with pytest.raises(DataQualityValidationError) as exc:
        registry.register_dataset(
            file_path=csv_file,
            name="HDFC Out of order",
            source="ARCHIVE",
            provider="TEST",
            acquisition_date="2026-10-10",
            symbols=["HDFC"],
        )
    assert "OUT_OF_ORDER" in str(exc.value)

    # Test abnormal gap detection (generates warning issue)
    csv_gap = str(tmp_path / "gap.csv")
    rows_gap = [
        {"symbol": "HDFC", "price": 1600.0, "volume": 10, "timestamp": 100.0},
        {"symbol": "HDFC", "price": 1605.0, "volume": 10, "timestamp": 600.0},  # 500s gap
    ]
    create_sample_csv(csv_gap, rows_gap)
    is_valid, issues, count, _, _ = DataValidator.validate_csv_file(csv_gap, max_gap_seconds=300.0)
    assert is_valid is True  # Warning does not block validity
    gap_issues = [i for i in issues if i.issue_type == "ABNORMAL_GAP"]
    assert len(gap_issues) == 1
    assert gap_issues[0].severity == "WARNING"


def test_invalid_price_and_volume_rejected(temp_db, tmp_path):
    """Test zero/negative prices and negative volumes are flagged as ERROR."""
    csv_file = str(tmp_path / "bad_data.csv")
    rows = [
        {"symbol": "SBIN", "price": 0.0, "volume": 10, "timestamp": 100.0},
        {"symbol": "SBIN", "price": 500.0, "volume": -5, "timestamp": 101.0},
    ]
    create_sample_csv(csv_file, rows)

    registry = HistoricalDataRegistry(temp_db)
    with pytest.raises(DataQualityValidationError) as exc:
        registry.register_dataset(
            file_path=csv_file,
            name="Bad SBIN",
            source="ARCHIVE",
            provider="TEST",
            acquisition_date="2026-10-10",
            symbols=["SBIN"],
        )
    err_str = str(exc.value)
    assert "INVALID_PRICE" in err_str or "Non-positive price" in err_str
    assert "INVALID_VOLUME" in err_str or "Negative volume" in err_str


def test_timezone_validation(temp_db, tmp_path):
    """Test invalid timezone specification is immediately rejected."""
    csv_file = str(tmp_path / "sample.csv")
    create_sample_csv(csv_file, [{"symbol": "NIFTY", "price": 24000.0, "volume": 1, "timestamp": 1000.0}])

    registry = HistoricalDataRegistry(temp_db)
    with pytest.raises(DataQualityValidationError) as exc:
        registry.register_dataset(
            file_path=csv_file,
            name="Bad TZ",
            source="ARCHIVE",
            provider="TEST",
            acquisition_date="2026-10-10",
            symbols=["NIFTY"],
            timezone="Mars/Olympus_Mons",
        )
    assert "Invalid IANA timezone" in str(exc.value)


def test_provenance_survives_restart(tmp_path):
    """Test dataset registry metadata and provenance survive database connection restart."""
    db_file = str(tmp_path / "persistent_provenance.db")
    csv_file = str(tmp_path / "persistent_dataset.csv")
    rows = [
        {"symbol": "RELIANCE", "price": 1200.0, "volume": 100, "timestamp": 1000.0},
        {"symbol": "RELIANCE", "price": 1201.0, "volume": 100, "timestamp": 1001.0},
    ]
    create_sample_csv(csv_file, rows)

    # 1. Register with instance 1
    db1 = OrderLedgerDB(db_path=db_file)
    reg1 = HistoricalDataRegistry(db1)
    meta, _ = reg1.register_dataset(
        file_path=csv_file,
        name="Persistent Dataset",
        source="ARCHIVE",
        provider="TEST",
        acquisition_date="2026-10-10",
        symbols=["RELIANCE"],
    )
    dataset_id = meta.dataset_id
    expected_checksum = meta.sha256_checksum

    # 2. Close connection
    db1.conn.close()

    # 3. Re-instantiate with instance 2 (simulating restart)
    db2 = OrderLedgerDB(db_path=db_file)
    reg2 = HistoricalDataRegistry(db2)

    meta_reloaded = reg2.get_dataset(dataset_id)
    assert meta_reloaded is not None
    assert meta_reloaded.dataset_id == dataset_id
    assert meta_reloaded.name == "Persistent Dataset"
    assert meta_reloaded.sha256_checksum == expected_checksum
    assert meta_reloaded.quality_status == "VERIFIED"

    # Verify integrity passes cleanly after restart
    verified = reg2.verify_integrity(dataset_id)
    assert verified.quality_status == "VERIFIED"


def test_replay_run_reproducibly_linked_to_dataset_and_config(temp_db, tmp_path):
    """Test replay run records immutable dataset checksum and configuration hash."""
    csv_file = str(tmp_path / "replay_link.csv")
    create_sample_csv(csv_file, [
        {"symbol": "RELIANCE", "price": 1200.0, "volume": 100, "timestamp": 1000.0},
        {"symbol": "RELIANCE", "price": 1205.0, "volume": 100, "timestamp": 1001.0},
    ])

    registry = HistoricalDataRegistry(temp_db)
    meta, _ = registry.register_dataset(
        file_path=csv_file,
        name="Replay Link Test",
        source="ARCHIVE",
        provider="TEST",
        acquisition_date="2026-10-10",
        symbols=["RELIANCE"],
    )

    config = {
        "strategy_id": "STRAT_MEAN_REV_001",
        "slippage_bps": 5.0,
        "parameters": {"lookback": 20, "z_threshold": 2.0},
    }

    replay = HistoricalReplayEngine()
    run_id = replay.load_verified_dataset(registry, meta.dataset_id, configuration=config)

    # Inspect replay run in DB
    cur = temp_db.conn.execute("SELECT * FROM replay_runs WHERE replay_run_id=?", (run_id,))
    row = cur.fetchone()
    assert row is not None
    assert row["dataset_id"] == meta.dataset_id
    assert row["dataset_checksum"] == meta.sha256_checksum
    assert len(row["configuration_hash"]) == 64

    # Complete the run
    registry.complete_replay_run(run_id, status="COMPLETED", metrics={"simulated_trades": 2, "net_pnl": 500.0})
    cur = temp_db.conn.execute("SELECT status, completed_at FROM replay_runs WHERE replay_run_id=?", (run_id,))
    row_done = cur.fetchone()
    assert row_done["status"] == "COMPLETED"
    assert row_done["completed_at"] > 0
