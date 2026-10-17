"""Comprehensive Unit Tests for Workstream E: Data Governance & Research Reproducibility."""

from datetime import date, datetime, time, timedelta, timezone
import pytest
from pydantic import ValidationError

from services.data_governance.manifest import (
    DataLineageStage,
    DatasetManifest,
    DatasetQualityMetrics,
    ExperimentManifest,
    LicenseClassification,
)
from services.data_governance.calendar_provider import (
    SpecialSession,
    VersionedMarketCalendarProvider,
)


def test_dataset_manifest_valid_creation():
    """Valid dataset manifest with complete lineage and checksum verifies cleanly."""
    valid_hash = "a" * 64
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    metrics = DatasetQualityMetrics(
        total_records=5000,
        duplicate_timestamps_rejected=0,
        invalid_ohlc_bars_rejected=0,
        finite_price_ratio=1.0,
        ohlc_consistency_ratio=1.0,
    )
    manifest = DatasetManifest(
        dataset_id="NSE_NIFTY50_DAILY",
        version="2026.10.14",
        provider="NSE_OFFICIAL_BHAVCOPY",
        license_classification=LicenseClassification.COMMERCIAL_LICENSED,
        lineage_stage=DataLineageStage.VALIDATED,
        ingestion_timestamp=now,
        data_availability_timestamp=now,
        checksum_sha256=valid_hash,
        storage_uri="data/cache/nifty50_daily_2026.parquet",
        quality_metrics=metrics,
        is_synthetic=False,
    )
    assert manifest.dataset_id == "NSE_NIFTY50_DAILY"
    assert manifest.lineage_stage == DataLineageStage.VALIDATED
    assert manifest.is_synthetic is False


def test_dataset_manifest_synthetic_substitution_rejection():
    """Synthetic data cannot be promoted to VALIDATED or EXPERIMENT_INPUT in production paths."""
    valid_hash = "b" * 64
    now = datetime.now(timezone.utc) - timedelta(hours=1)
    metrics = DatasetQualityMetrics(total_records=100)

    # Synthetic data marked as VALIDATED must raise ValidationError
    with pytest.raises(ValidationError, match="Synthetic data cannot be promoted"):
        DatasetManifest(
            dataset_id="SYNTHETIC_TEST",
            version="1.0.0",
            provider="SIMULATOR",
            license_classification=LicenseClassification.PUBLIC_OPEN,
            lineage_stage=DataLineageStage.VALIDATED,
            ingestion_timestamp=now,
            data_availability_timestamp=now,
            checksum_sha256=valid_hash,
            storage_uri="data/test.parquet",
            quality_metrics=metrics,
            is_synthetic=True,  # Invariant violation!
        )


def test_dataset_manifest_future_data_rejection():
    """Data with availability timestamp in the future must fail validation."""
    valid_hash = "c" * 64
    future_time = datetime.now(timezone.utc) + timedelta(days=2)
    metrics = DatasetQualityMetrics(total_records=100)

    with pytest.raises(ValidationError, match="Future-dated data availability detected"):
        DatasetManifest(
            dataset_id="FUTURE_DATA",
            version="1.0.0",
            provider="NSE",
            license_classification=LicenseClassification.COMMERCIAL_LICENSED,
            lineage_stage=DataLineageStage.RAW,
            ingestion_timestamp=datetime.now(timezone.utc),
            data_availability_timestamp=future_time,
            checksum_sha256=valid_hash,
            storage_uri="data/future.parquet",
            quality_metrics=metrics,
        )


def test_experiment_manifest_deterministic_fingerprint():
    """ExperimentManifest must generate deterministic SHA-256 fingerprints across identical runs."""
    start = datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)
    end = datetime(2026, 6, 30, 15, 30, tzinfo=timezone.utc)

    exp1 = ExperimentManifest(
        strategy_name="AlgoLab_Super_Adaptive",
        strategy_source_hash="1" * 64,
        parameters={"atr_multiplier": 3.5, "fast_ema": 8, "slow_ema": 20},
        data_manifest_ids=["MANIFEST_NSE_2026"],
        dependency_lock_hash="2" * 64,
        start_timestamp=start,
        end_timestamp=end,
        metrics={"cagr": 0.28, "max_drawdown": 0.08},
        output_artifacts={"results.json": "3" * 64},
    )

    exp2 = ExperimentManifest(
        strategy_name="AlgoLab_Super_Adaptive",
        strategy_source_hash="1" * 64,
        parameters={"atr_multiplier": 3.5, "fast_ema": 8, "slow_ema": 20},
        data_manifest_ids=["MANIFEST_NSE_2026"],
        dependency_lock_hash="2" * 64,
        start_timestamp=start,
        end_timestamp=end,
        metrics={"cagr": 0.28, "max_drawdown": 0.08},
        output_artifacts={"results.json": "3" * 64},
    )

    fp1 = exp1.compute_experiment_fingerprint()
    fp2 = exp2.compute_experiment_fingerprint()

    # Determinism
    assert fp1 == fp2
    assert len(fp1) == 64

    # Parameter mutation alters fingerprint
    exp_mutated = ExperimentManifest(
        strategy_name="AlgoLab_Super_Adaptive",
        strategy_source_hash="1" * 64,
        parameters={"atr_multiplier": 4.0, "fast_ema": 8, "slow_ema": 20},
        data_manifest_ids=["MANIFEST_NSE_2026"],
        dependency_lock_hash="2" * 64,
        start_timestamp=start,
        end_timestamp=end,
        metrics={"cagr": 0.25, "max_drawdown": 0.10},
        output_artifacts={"results.json": "3" * 64},
    )
    assert exp_mutated.compute_experiment_fingerprint() != fp1


def test_versioned_calendar_special_session_muhurat():
    """VersionedMarketCalendarProvider accurately handles special Diwali Muhurat sessions."""
    cal = VersionedMarketCalendarProvider()
    muhurat_date = date(2026, 11, 8)

    # Muhurat date is a trading day despite being Sunday/Diwali holiday
    assert cal.is_special_session(muhurat_date) is True
    assert cal.is_trading_day(muhurat_date) is True

    # Special session boundaries: 18:15 to 19:15 IST
    open_t, close_t = cal.get_session_bounds(muhurat_date)
    assert open_t == time(18, 15)
    assert close_t == time(19, 15)

    # Regular daytime 10:00 IST is not within Muhurat trading hours
    tz_ist = cal.DEFAULT_OPEN
    daytime_ist = datetime.combine(muhurat_date, time(10, 0), tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert cal.is_regular_trading_session(daytime_ist) is False

    # Evening 18:30 IST is active Muhurat trading
    evening_ist = datetime.combine(muhurat_date, time(18, 30), tzinfo=timezone(timedelta(hours=5, minutes=30)))
    assert cal.is_regular_trading_session(evening_ist) is True


def test_versioned_calendar_next_trading_day():
    """Accurately skips weekends and holidays when calculating next trading day."""
    cal = VersionedMarketCalendarProvider()
    # Friday 2026-01-23 -> Monday 2026-01-26 is Republic Day holiday -> Next trading day is Tuesday 2026-01-27
    friday = date(2026, 1, 23)
    next_day = cal.get_next_trading_day(friday)
    assert next_day == date(2026, 1, 27)
