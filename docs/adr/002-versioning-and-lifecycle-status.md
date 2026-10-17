# ADR-002: Semantic Versioning & Canonical Lifecycle Status Authority

## Status
- **Status:** Accepted
- **Date:** 2026-10-14
- **Author:** Lead Systems Architect (@vijaykumarjogi266-star)
- **Deciders:** Institutional Quantitative Systems Committee / Lead Systems Architect

## Context
Prior to Phase 0 standardization, the Algo Lab repository experienced fragmented versioning and divergent lifecycle definitions across multiple subsystems:
1. **Version Drift:** Independent components (`pyproject.toml`, `apps/web/package.json`, Docker build manifests, and FastAPI endpoints) specified disparate or hardcoded version strings (`0.1.0`, `0.2.0`, `1.0.0-rc`).
2. **Ambiguous Lifecycle Maturity:** The absence of a formal lifecycle classification led to uncertainty regarding whether specific pipelines were prototypes, speculative research sandboxes, or hardened forward-paper validation runtimes.
3. **Audit Imprecision:** Release evidence reports, SBOMs, and experiment tracking manifests could not guarantee exact traceability without a single canonical version authority.

To establish institutional credibility, reproducible experiment tracking, and unambiguous deployment monitoring, the platform required a single source of truth for semantic versioning and lifecycle state.

## Decision
We adopt **Semantic Versioning 2.0.0 (`MAJOR.MINOR.PATCH`)** at version **`0.3.0`** and designate [`src/version.py`](file:///home/ubuntu/algolab/src/version.py) as the sole authoritative single source of truth across all platform components.

### 1. Canonical Definition in `src/version.py`
All version, revision, build date, and lifecycle state constants are centrally declared in [`src/version.py`](file:///home/ubuntu/algolab/src/version.py):
```python
from typing import Final, Literal

__version__: Final[str] = "0.3.0"
__revision__: Final[str] = "git-canonical-rev"
__build_date__: Final[str] = "2026-10-14"

LifecycleState = Literal["prototype", "research", "forward-paper-validation", "release-candidate"]
LIFECYCLE_STATE: Final[LifecycleState] = "forward-paper-validation"
```

### 2. Standardized Lifecycle States Taxonomy
The platform formalizes four distinct, strictly typed lifecycle states:
- **`prototype`:** Exploratory scripts, scratch models, and non-validated mathematical formulations.
- **`research`:** Offline historical backtests, feature engineering pipelines, and regime evaluation.
- **`forward-paper-validation`:** Current platform baseline (0.3.0). Real-time Indian equity paper simulation, risk engine gating, deterministic replay, hardened container orchestration, and fail-closed safety.
- **`release-candidate`:** Future milestone designated for multi-month stable forward paper validation before formal institutional release freeze.

### 3. Synchronization Across All Subsystems
All platform surfaces are synchronized to import or reflect [`src/version.py`](file:///home/ubuntu/algolab/src/version.py):
1. **Python Packaging:** [`pyproject.toml`](file:///home/ubuntu/algolab/pyproject.toml#L7) sets `version = "0.3.0"`.
2. **REST API Endpoints:** FastAPI backend ([`apps/api/main.py`](file:///home/ubuntu/algolab/apps/api/main.py)) exposes `get_version_info()` at root `/` and `/health`, broadcasting `version`, `lifecycle_state`, and `paper_only` flags.
3. **Web Dashboard:** [`apps/web/package.json`](file:///home/ubuntu/algolab/apps/web/package.json) sets `"version": "0.3.0"`.
4. **Container Manifests:** [`docker/Dockerfile.api`](file:///home/ubuntu/algolab/docker/Dockerfile.api) stamps Open Containers Initiative (OCI) image labels:
   - `org.opencontainers.image.version="0.3.0"`
   - `org.opencontainers.image.lifecycle="forward-paper-validation"`
   - `org.opencontainers.image.paper_only="true"`
5. **Data & Experiment Governance:** [`services/data_governance/manifest.py`](file:///home/ubuntu/algolab/services/data_governance/manifest.py) records `execution_model_version = "0.3.0"` in all immutable experiment manifests.
6. **Documentation & Release Evidence:** Canonical status recorded across [`docs/governance/platform_status.md`](file:///home/ubuntu/algolab/docs/governance/platform_status.md), [`README.md`](file:///home/ubuntu/algolab/README.md), and [`RELEASE_EVIDENCE.md`](file:///home/ubuntu/algolab/RELEASE_EVIDENCE.md).

## Non-Negotiable Safety Invariant Compliance
- **Does this decision preserve `LIVE_TRADING_ENABLED = False`?**  
  **Yes.** [`src/version.py`](file:///home/ubuntu/algolab/src/version.py#L19) co-locates the lifecycle state with immutable safety flags `LIVE_TRADING_ENABLED = False` and `REAL_BROKER_EXECUTION_ENABLED = False`.
- **Does it maintain independent risk engine authority?**  
  **Yes.** Version metadata exposed across API and UI states explicitly that all order proposals must pass independent risk validation before entering paper execution.
- **Does it prevent synthetic data substitution in production paper paths?**  
  **Yes.** When `LIFECYCLE_STATE = "forward-paper-validation"`, data governance manifests reject datasets flagged with `is_synthetic = True` for production execution.

## Consequences

### Positive
- **Zero Version Ambiguity:** Every log, API response, UI dashboard header, Docker image, and experiment manifest reflects identical versioning.
- **Auditable Experiment Lineage:** Backtest and forward-paper runs are tagged with the exact execution engine version (`0.3.0`) for deterministic provenance.
- **Automated Consistency Verification:** Automated contract tests verify that packaging, API health, and source constants never diverge.

### Negative / Trade-offs
- **Synchronized Release Bumping:** Bumping version numbers requires updating `src/version.py` and downstream manifests in unison; automated release tooling is required to streamline increments.

## Compliance & Verification Evidence
- **Link to relevant tests:**
  - [`tests/unit/test_health.py`](file:///home/ubuntu/algolab/tests/unit/test_health.py) (validates `/health` returns version `0.3.0` and lifecycle `forward-paper-validation`)
  - [`tests/contracts/test_contracts.py`](file:///home/ubuntu/algolab/tests/contracts/test_contracts.py)
  - [`src/version.py`](file:///home/ubuntu/algolab/src/version.py)
- **Verification command:**
  ```bash
  .venv/bin/python3 -c "from src.version import get_version_info; print(get_version_info())"
  # and
  .venv/bin/pytest tests/unit/test_health.py -q
  ```
