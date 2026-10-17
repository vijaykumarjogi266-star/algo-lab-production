# ADR-004: Data & Experiment Provenance, Lineage Tiers & Synthetic Fallback Prohibition

## Status
- **Status:** Accepted
- **Date:** 2026-10-14
- **Author:** Lead Systems Architect (@vijaykumarjogi266-star)
- **Deciders:** Institutional Quantitative Systems Committee / Lead Systems Architect

## Context
In quantitative finance, the validity of backtesting, regime evaluation, and forward paper trading is bounded by the integrity, timeliness, and provenance of input market data. Flawed data governance introduces systemic failure modes:
1. **Look-Ahead Bias & Survivorship Bias:** Data feeds incorporating future corporate actions or unrecorded survivorship filters inflate backtest performance, leading to catastrophic strategy collapse in forward paper validation.
2. **Silent Data Tampering:** Manually edited or corrupted historical CSV/Parquet records invalidate experiment reproducibility and lead to unreproducible alpha claims.
3. **Synthetic Substitution Contamination:** In testing environments, fallbacks that substitute synthetic random-walk or interpolated data when upstream feeds fail can quietly leak into forward-paper sessions, producing hallucinated paper fills and fictitious P&L.
4. **Unrecorded Experiment Lineage:** Backtest runs frequently omit the precise strategy code commit, hyperparameter dictionary, and dataset revisions that produced a result, preventing independent verification.

A cryptographically verified, typed data governance architecture is required to guarantee mathematical truth and auditability.

## Decision
We implement a typed, cryptographic data governance framework codified in [`services/data_governance/manifest.py`](file:///home/ubuntu/algolab/services/data_governance/manifest.py), enforcing 5 strict lineage tiers, SHA-256 integrity checksums, point-in-time availability validation, and zero synthetic data substitution in production paths.

### 1. Five-Tier Data Lineage Hierarchy
Every market dataset registered in the system transitions through a formal, unidirectional five-tier lineage pipeline:

```
[1] RAW              --> Unmodified ingested data directly from upstream provider/exchange
[2] VALIDATED        --> Monotonic timestamps, duplicate-free, finite prices, valid OHLC boundaries
[3] ADJUSTED         --> Adjusted for corporate actions (splits, bonuses, dividends) with explicit provenance
[4] FEATURE          --> Deterministic technical indicators computed strictly point-in-time
[5] EXPERIMENT_INPUT --> Immutable, fingerprinted input dataset locked for backtest/paper replay
```

### 2. Typed Dataset Manifests & SHA-256 Integrity
Every dataset is accompanied by a strongly typed [`DatasetManifest`](file:///home/ubuntu/algolab/services/data_governance/manifest.py#L46) storing:
- `dataset_id`, `version`, `provider`, and `license_classification`.
- `lineage_stage`: Current lineage tier (`DataLineageStage`).
- `ingestion_timestamp` and `data_availability_timestamp` (enforcing point-in-time validation).
- `checksum_sha256`: 64-character hexadecimal SHA-256 digest calculated over the data file bytes.
- `quality_metrics`: Total records, duplicate count, OHLC consistency ratio, finite price ratio.

Before any dataset can be ingested into a backtest engine or replay clock, its SHA-256 digest is re-computed. Any checksum mismatch triggers automatic quarantine (`QUARANTINED`) and raises a `ChecksumMismatchError`.

### 3. Absolute Prohibition of Synthetic Data Fallback
To ensure forward-paper reality matches actual Indian exchange dynamics, synthetic data substitution is prohibited in all production pipelines:
- In [`DatasetManifest`](file:///home/ubuntu/algolab/services/data_governance/manifest.py#L77-L84), a model validator raises an immediate error if `is_synthetic = True` for datasets in `VALIDATED` or `EXPERIMENT_INPUT` stages:
```python
if self.is_synthetic and self.lineage_stage in (DataLineageStage.VALIDATED, DataLineageStage.EXPERIMENT_INPUT):
    raise ValueError(
        "Non-negotiable invariant violation: Synthetic data cannot be promoted to VALIDATED or EXPERIMENT_INPUT."
    )
```
- In forward-paper trading sessions, if an external data provider feed drops or yields stale quotes, the execution daemon halts or transitions to a `WAIT` state; it **never** generates artificial ticks or interpolated synthetic bars.

### 4. Immutable Experiment Manifests & Reproducibility Fingerprints
Every backtest or forward simulation generates an [`ExperimentManifest`](file:///home/ubuntu/algolab/services/data_governance/manifest.py#L100) capturing:
- Strategy source code SHA-256 hash (`strategy_source_hash`).
- Strategy parameters dictionary.
- Associated dataset manifest IDs and dependency lock hash.
- Execution model version (`0.3.0`).
- Deterministic experiment fingerprint computed via SHA-256 over canonicalized configuration JSON.

## Non-Negotiable Safety Invariant Compliance
- **Does this decision preserve `LIVE_TRADING_ENABLED = False`?**  
  **Yes.** Data governance operates purely at the data storage and ingestion boundary. It contains zero trading or routing capabilities.
- **Does it maintain independent risk engine authority?**  
  **Yes.** Market data validated under this framework feeds into the risk engine for independent volatility and liquidity assessment without allowing strategies to alter price feeds.
- **Does it prevent synthetic data substitution in production paper paths?**  
  **Yes.** This is the core mandate of ADR-004. Synthetic datasets are forbidden from entering `VALIDATED` or `EXPERIMENT_INPUT` stages, and missing data forces execution waiting rather than synthetic interpolation.

## Consequences

### Positive
- **Guaranteed Reproducibility:** Any experiment can be reconstructed bit-for-bit from its manifest, source hash, and dataset checksum.
- **Mathematical Integrity:** Eliminates look-ahead bias and future-dated price leakage.
- **Zero Hallucinated Fills:** Prohibits artificial synthetic data from creating fictitious trading profits in paper sessions.
- **Automated Quarantine:** Corrupted or modified historical data files are intercepted before entering simulation.

### Negative / Trade-offs
- **Storage & Metadata Overhead:** Each dataset requires an accompanying JSON manifest and SHA-256 computation cycle during registration.
- **Strict Pipeline Ingestion:** Unvalidated CSV files cannot be directly read by the backtest engine without passing through the data registry.

## Compliance & Verification Evidence
- **Link to relevant tests:**
  - [`tests/unit/test_data_governance_manifest.py`](file:///home/ubuntu/algolab/tests/unit/test_data_governance_manifest.py) (6/6 tests passing)
  - [`tests/unit/test_dataset_registry.py`](file:///home/ubuntu/algolab/tests/unit/test_dataset_registry.py)
  - [`tests/unit/test_experiment_provenance_audit.py`](file:///home/ubuntu/algolab/tests/unit/test_experiment_provenance_audit.py)
- **Verification command:**
  ```bash
  .venv/bin/pytest tests/unit/test_data_governance_manifest.py tests/unit/test_experiment_provenance_audit.py -q
  ```
