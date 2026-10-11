"""
OMS Project - Historical Data Registry & Provenance Layer (Stage 1)
Enforces immutable dataset provenance, cryptographic verification,
strict data quality validations, and fail-closed replay controls.
"""

import os
import csv
import json
import time
import hashlib
import sqlite3
import zoneinfo
from typing import Dict, Any, List, Optional, Tuple, Set
from pydantic import BaseModel, Field


class DatasetMetadata(BaseModel):
    """Specification of an immutable historical market dataset."""
    dataset_id: str
    name: str
    source: str
    provider: str
    acquisition_date: str
    symbols: List[str]
    market: str = "NSE"
    timezone: str = "Asia/Kolkata"
    coverage_start: float = 0.0
    coverage_end: float = 0.0
    record_count: int = 0
    schema_version: str = "1.0.0"
    sha256_checksum: str = ""
    quality_status: str = "PENDING"  # PENDING, VERIFIED, QUARANTINED, REJECTED
    owner: str = "AlgoLab Data Governance"
    file_path: str = ""


class DataValidationIssue(BaseModel):
    """Specific data issue detected during validation."""
    issue_type: str  # CHECKSUM_MISMATCH, DUPLICATE_TIMESTAMP, OUT_OF_ORDER, INVALID_PRICE, INVALID_VOLUME, ABNORMAL_GAP, TIMEZONE_ERROR, SESSION_OUT_OF_BOUNDS
    severity: str    # ERROR, WARNING
    symbol: Optional[str] = None
    timestamp: Optional[float] = None
    row_number: Optional[int] = None
    message: str


class DataQualityReport(BaseModel):
    """Comprehensive validation report for a dataset."""
    report_id: str
    dataset_id: str
    validated_at: float
    is_valid: bool
    total_records: int
    error_count: int
    warning_count: int
    issues: List[DataValidationIssue]
    checksum: str


class ChecksumMismatchError(Exception):
    """Raised when on-disk dataset checksum does not match registered checksum."""
    pass


class DataQualityValidationError(Exception):
    """Raised when a dataset fails data quality checks."""
    pass


class DatasetQuarantinedError(Exception):
    """Raised when an attempt is made to replay an unverified or quarantined dataset."""
    pass


def compute_file_sha256(file_path: str) -> str:
    """Computes SHA256 hex digest of file contents."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset file not found: {file_path}")
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class DataValidator:
    """
    Validates tick and bar datasets for historical integrity.
    Detects duplicate timestamps, out-of-order records, gaps,
    invalid prices/volumes, session boundaries, and timezone errors.
    """

    @staticmethod
    def validate_timezone(tz_name: str) -> bool:
        """Confirms timezone string is recognized in the IANA database."""
        try:
            zoneinfo.ZoneInfo(tz_name)
            return True
        except Exception:
            return False

    @staticmethod
    def validate_csv_file(
        file_path: str,
        expected_symbols: Optional[List[str]] = None,
        market_tz: str = "Asia/Kolkata",
        max_gap_seconds: float = 300.0,
        enforce_session_hours: bool = True,
        session_start_hour_min: Tuple[int, int] = (9, 15),
        session_end_hour_min: Tuple[int, int] = (15, 30),
    ) -> Tuple[bool, List[DataValidationIssue], int, float, float]:
        """
        Parses and validates CSV tick data.
        Returns (is_valid, issues, record_count, min_ts, max_ts).
        """
        issues: List[DataValidationIssue] = []

        if not DataValidator.validate_timezone(market_tz):
            issues.append(DataValidationIssue(
                issue_type="TIMEZONE_ERROR",
                severity="ERROR",
                message=f"Invalid IANA timezone specification: '{market_tz}'"
            ))
            return False, issues, 0, 0.0, 0.0

        tz = zoneinfo.ZoneInfo(market_tz)

        if not os.path.exists(file_path):
            issues.append(DataValidationIssue(
                issue_type="FILE_NOT_FOUND",
                severity="ERROR",
                message=f"Dataset file missing at {file_path}"
            ))
            return False, issues, 0, 0.0, 0.0

        record_count = 0
        min_ts = float("inf")
        max_ts = float("-inf")

        seen_timestamps_by_symbol: Dict[str, Set[float]] = {}
        last_timestamp_by_symbol: Dict[str, float] = {}

        allowed_symbols_set = set(expected_symbols) if expected_symbols else None

        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required_cols = {"symbol", "price", "timestamp"}
            if not reader.fieldnames or not required_cols.issubset(set(reader.fieldnames)):
                issues.append(DataValidationIssue(
                    issue_type="SCHEMA_ERROR",
                    severity="ERROR",
                    message=f"CSV must contain headers {required_cols}. Found: {reader.fieldnames}"
                ))
                return False, issues, 0, 0.0, 0.0

            for row_idx, row in enumerate(reader, start=2):
                record_count += 1
                sym = str(row.get("symbol", "")).strip().upper()

                if allowed_symbols_set and sym not in allowed_symbols_set:
                    issues.append(DataValidationIssue(
                        issue_type="UNREGISTERED_SYMBOL",
                        severity="ERROR",
                        symbol=sym,
                        row_number=row_idx,
                        message=f"Symbol '{sym}' is not registered in dataset metadata."
                    ))

                # Parse Price
                try:
                    price = float(row.get("price", 0.0))
                    if price <= 0.0:
                        issues.append(DataValidationIssue(
                            issue_type="INVALID_PRICE",
                            severity="ERROR",
                            symbol=sym,
                            row_number=row_idx,
                            message=f"Non-positive price {price} encountered."
                        ))
                except (ValueError, TypeError):
                    issues.append(DataValidationIssue(
                        issue_type="INVALID_PRICE",
                        severity="ERROR",
                        symbol=sym,
                        row_number=row_idx,
                        message=f"Invalid price value '{row.get('price')}'"
                    ))

                # Parse Volume
                try:
                    vol = float(row.get("volume", 0.0))
                    if vol < 0.0:
                        issues.append(DataValidationIssue(
                            issue_type="INVALID_VOLUME",
                            severity="ERROR",
                            symbol=sym,
                            row_number=row_idx,
                            message=f"Negative volume {vol} encountered."
                        ))
                except (ValueError, TypeError):
                    issues.append(DataValidationIssue(
                        issue_type="INVALID_VOLUME",
                        severity="ERROR",
                        symbol=sym,
                        row_number=row_idx,
                        message=f"Invalid volume value '{row.get('volume')}'"
                    ))

                # Parse Timestamp
                try:
                    ts = float(row.get("timestamp", 0.0))
                except (ValueError, TypeError):
                    issues.append(DataValidationIssue(
                        issue_type="INVALID_TIMESTAMP",
                        severity="ERROR",
                        symbol=sym,
                        row_number=row_idx,
                        message=f"Invalid timestamp value '{row.get('timestamp')}'"
                    ))
                    continue

                if ts < min_ts:
                    min_ts = ts
                if ts > max_ts:
                    max_ts = ts

                # Duplicate Timestamp check
                if sym not in seen_timestamps_by_symbol:
                    seen_timestamps_by_symbol[sym] = set()
                    last_timestamp_by_symbol[sym] = float("-inf")

                if ts in seen_timestamps_by_symbol[sym]:
                    issues.append(DataValidationIssue(
                        issue_type="DUPLICATE_TIMESTAMP",
                        severity="ERROR",
                        symbol=sym,
                        timestamp=ts,
                        row_number=row_idx,
                        message=f"Duplicate timestamp {ts} detected for symbol {sym}."
                    ))
                seen_timestamps_by_symbol[sym].add(ts)

                # Out of Order check
                last_ts = last_timestamp_by_symbol[sym]
                if ts < last_ts:
                    issues.append(DataValidationIssue(
                        issue_type="OUT_OF_ORDER",
                        severity="ERROR",
                        symbol=sym,
                        timestamp=ts,
                        row_number=row_idx,
                        message=f"Out-of-order timestamp {ts} detected after {last_ts} for symbol {sym}."
                    ))
                elif last_ts != float("-inf") and (ts - last_ts) > max_gap_seconds:
                    issues.append(DataValidationIssue(
                        issue_type="ABNORMAL_GAP",
                        severity="WARNING",
                        symbol=sym,
                        timestamp=ts,
                        row_number=row_idx,
                        message=f"Abnormal data gap of {ts - last_ts:.1f}s (> {max_gap_seconds}s) between ticks."
                    ))

                last_timestamp_by_symbol[sym] = max(last_ts, ts)

                # Session Calendar / Trading Hours check
                if enforce_session_hours and ts > 0:
                    import datetime
                    dt = datetime.datetime.fromtimestamp(ts, tz=tz)
                    s_hour, s_min = session_start_hour_min
                    e_hour, e_min = session_end_hour_min
                    
                    # Convert to minutes of day
                    minute_of_day = dt.hour * 60 + dt.minute
                    s_minute = s_hour * 60 + s_min
                    e_minute = e_hour * 60 + e_min

                    if dt.weekday() >= 5:  # Saturday or Sunday
                        issues.append(DataValidationIssue(
                            issue_type="SESSION_OUT_OF_BOUNDS",
                            severity="WARNING",
                            symbol=sym,
                            timestamp=ts,
                            row_number=row_idx,
                            message=f"Tick recorded on weekend ({dt.strftime('%A')}) at {dt.isoformat()}."
                        ))
                    elif minute_of_day < s_minute or minute_of_day > e_minute:
                        issues.append(DataValidationIssue(
                            issue_type="SESSION_OUT_OF_BOUNDS",
                            severity="WARNING",
                            symbol=sym,
                            timestamp=ts,
                            row_number=row_idx,
                            message=f"Tick time {dt.strftime('%H:%M:%S')} outside session window ({s_hour:02d}:{s_min:02d} - {e_hour:02d}:{e_min:02d})."
                        ))

        if record_count == 0:
            issues.append(DataValidationIssue(
                issue_type="EMPTY_DATASET",
                severity="ERROR",
                message="Dataset contains 0 data rows."
            ))

        error_count = sum(1 for i in issues if i.severity == "ERROR")
        is_valid = (error_count == 0)

        if min_ts == float("inf"):
            min_ts = 0.0
        if max_ts == float("-inf"):
            max_ts = 0.0

        return is_valid, issues, record_count, min_ts, max_ts


class HistoricalDataRegistry:
    """
    Manages durable registration, cryptographic verification, and provenance tracking
    for historical datasets in SQLite.
    """

    def __init__(self, db):
        self.db = db

    def register_dataset(
        self,
        file_path: str,
        name: str,
        source: str,
        provider: str,
        acquisition_date: str,
        symbols: List[str],
        market: str = "NSE",
        timezone: str = "Asia/Kolkata",
        schema_version: str = "1.0.0",
        owner: str = "AlgoLab Data Governance",
        validate: bool = True,
        enforce_session_hours: bool = False,
    ) -> Tuple[DatasetMetadata, DataQualityReport]:
        """
        Registers a new dataset, verifies its cryptographic checksum, runs full quality validation,
        and saves immutable provenance record.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Dataset file does not exist: {file_path}")

        # 1. Compute SHA256 checksum
        checksum = compute_file_sha256(file_path)

        # 2. Validate content
        is_valid = True
        issues = []
        rec_count = 0
        min_ts = 0.0
        max_ts = 0.0

        if validate:
            is_valid, issues, rec_count, min_ts, max_ts = DataValidator.validate_csv_file(
                file_path=file_path,
                expected_symbols=symbols,
                market_tz=timezone,
                enforce_session_hours=enforce_session_hours,
            )

        error_count = sum(1 for i in issues if i.severity == "ERROR")
        warning_count = sum(1 for i in issues if i.severity == "WARNING")
        status = "VERIFIED" if is_valid else "QUARANTINED"

        import uuid
        dataset_id = f"DS_{uuid.uuid4().hex[:12].upper()}"
        report_id = f"REP_{uuid.uuid4().hex[:12].upper()}"
        now = time.time()

        metadata = DatasetMetadata(
            dataset_id=dataset_id,
            name=name,
            source=source,
            provider=provider,
            acquisition_date=acquisition_date,
            symbols=symbols,
            market=market,
            timezone=timezone,
            coverage_start=min_ts,
            coverage_end=max_ts,
            record_count=rec_count,
            schema_version=schema_version,
            sha256_checksum=checksum,
            quality_status=status,
            owner=owner,
            file_path=os.path.abspath(file_path),
        )

        quality_report = DataQualityReport(
            report_id=report_id,
            dataset_id=dataset_id,
            validated_at=now,
            is_valid=is_valid,
            total_records=rec_count,
            error_count=error_count,
            warning_count=warning_count,
            issues=issues,
            checksum=checksum,
        )

        # 3. Persist to SQLite
        with self.db.conn:
            self.db.conn.execute(
                """INSERT INTO dataset_registry (
                    dataset_id, name, source, provider, acquisition_date, symbols_json,
                    market, timezone, start_timestamp, end_timestamp, record_count,
                    schema_version, sha256_checksum, quality_status, owner, file_path,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    dataset_id, name, source, provider, acquisition_date, json.dumps(symbols),
                    market, timezone, min_ts, max_ts, rec_count,
                    schema_version, checksum, status, owner, os.path.abspath(file_path),
                    now, now
                )
            )

            self.db.conn.execute(
                """INSERT INTO dataset_quality_reports (
                    report_id, dataset_id, validated_at, is_valid, error_count, warning_count, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    report_id, dataset_id, now, 1 if is_valid else 0,
                    error_count, warning_count, quality_report.model_dump_json()
                )
            )

        if not is_valid:
            err = DataQualityValidationError(
                f"Dataset {dataset_id} failed quality validation with {error_count} errors: {[(i.issue_type, i.message) for i in issues if i.severity == 'ERROR']}"
            )
            err.report = quality_report
            raise err

        return metadata, quality_report

    def get_dataset(self, dataset_id: str) -> Optional[DatasetMetadata]:
        """Retrieves dataset metadata by ID."""
        cur = self.db.conn.execute("SELECT * FROM dataset_registry WHERE dataset_id=?", (dataset_id,))
        row = cur.fetchone()
        if not row:
            return None

        row_dict = dict(row)
        return DatasetMetadata(
            dataset_id=row_dict["dataset_id"],
            name=row_dict["name"],
            source=row_dict["source"],
            provider=row_dict["provider"],
            acquisition_date=row_dict["acquisition_date"],
            symbols=json.loads(row_dict["symbols_json"]),
            market=row_dict["market"],
            timezone=row_dict["timezone"],
            coverage_start=row_dict["start_timestamp"],
            coverage_end=row_dict["end_timestamp"],
            record_count=row_dict["record_count"],
            schema_version=row_dict["schema_version"],
            sha256_checksum=row_dict["sha256_checksum"],
            quality_status=row_dict["quality_status"],
            owner=row_dict["owner"],
            file_path=row_dict["file_path"],
        )

    def verify_integrity(self, dataset_id: str) -> DatasetMetadata:
        """
        Recomputes checksum against live file on disk. Fails closed if file was altered
        or if dataset is quarantined.
        """
        metadata = self.get_dataset(dataset_id)
        if not metadata:
            raise ValueError(f"Dataset {dataset_id} not registered.")

        if not os.path.exists(metadata.file_path):
            with self.db.conn:
                self.db.conn.execute(
                    "UPDATE dataset_registry SET quality_status='QUARANTINED', updated_at=? WHERE dataset_id=?",
                    (time.time(), dataset_id)
                )
            raise FileNotFoundError(f"Dataset file missing on disk: {metadata.file_path}")

        current_checksum = compute_file_sha256(metadata.file_path)

        if current_checksum != metadata.sha256_checksum:
            with self.db.conn:
                self.db.conn.execute(
                    "UPDATE dataset_registry SET quality_status='QUARANTINED', updated_at=? WHERE dataset_id=?",
                    (time.time(), dataset_id)
                )
            raise ChecksumMismatchError(
                f"CRITICAL: Integrity breach for dataset {dataset_id}. Registered SHA256={metadata.sha256_checksum}, actual={current_checksum}. Quarantined."
            )

        if metadata.quality_status != "VERIFIED":
            raise DatasetQuarantinedError(
                f"Dataset {dataset_id} is in status '{metadata.quality_status}'. Replay is blocked."
            )

        return metadata

    def create_replay_run(self, dataset_id: str, configuration: Dict[str, Any]) -> str:
        """
        Binds a backtest/replay run to an exact dataset and configuration hash.
        Fails closed if the dataset cannot be cryptographically verified.
        """
        meta = self.verify_integrity(dataset_id)

        import uuid
        replay_run_id = f"RUN_{uuid.uuid4().hex[:12].upper()}"
        config_serialized = json.dumps(configuration, sort_keys=True)
        config_hash = hashlib.sha256(config_serialized.encode("utf-8")).hexdigest()
        now = time.time()

        with self.db.conn:
            self.db.conn.execute(
                """INSERT INTO replay_runs (
                    replay_run_id, dataset_id, dataset_version, dataset_checksum,
                    configuration_hash, started_at, status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    replay_run_id, dataset_id, meta.schema_version, meta.sha256_checksum,
                    config_hash, now, "INITIALIZED", json.dumps({"config": configuration})
                )
            )

        return replay_run_id

    def complete_replay_run(self, replay_run_id: str, status: str = "COMPLETED", metrics: Optional[Dict[str, Any]] = None):
        """Marks replay run as complete with output metrics."""
        now = time.time()
        with self.db.conn:
            self.db.conn.execute(
                "UPDATE replay_runs SET status=?, completed_at=?, metadata_json=? WHERE replay_run_id=?",
                (status, now, json.dumps(metrics or {}), replay_run_id)
            )
