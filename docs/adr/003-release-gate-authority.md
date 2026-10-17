# ADR-003: Canonical CI/CD Release Gate Authority (`make release-check`)

## Status
- **Status:** Accepted
- **Date:** 2026-10-14
- **Author:** Lead Systems Architect (@vijaykumarjogi266-star)
- **Deciders:** Institutional Quantitative Systems Committee / Lead Systems Architect

## Context
Quantitative simulation, algorithmic risk management, and financial paper-trading systems demand uncompromising operational discipline. In distributed development environments, individual developer verification or disjointed testing scripts create systemic failure modes:
1. **Dependency Drift:** Unpinned or floating package versions lead to non-deterministic execution behavior, conflicting sub-dependencies, or silent numerical drift in numerical libraries (NumPy, Pandas, SciPy).
2. **Security & Credential Vulnerabilities:** Unaudited code contributions may introduce unsafe deserialization, insecure sub-process executions, unmasked API tokens, or hardcoded secrets.
3. **Silent Backup Invalidation:** Backup configurations often suffer from silent entropy where backup archives are generated but cannot be successfully restored during an actual disaster recovery event.
4. **Safety Invariant Regressions:** Accidental edits or refactors might inadvertently relax safety assertions or bypass risk engine import boundaries.

A single, canonical, fail-closed release authority is mandatory to govern code acceptance into the canonical branch and validate deployment artifacts.

## Decision
We designate **`make release-check`** (implemented in [`Makefile`](file:///home/ubuntu/algolab/Makefile#L59)) as the sole authoritative, fail-closed release gate for Algo Lab. No code may be deployed, merged, or certified without a 100% successful execution of this unified command.

### 1. Sequential Multi-Stage Release Verification Pipeline
The `make release-check` target executes eight mandatory, fail-closed verification stages in strict sequence:

```
[1/8] safety-check   --> Validates canonical safety invariants & AST broker isolation
[2/8] lock-check     --> Verifies installed packages against requirements-pinned.txt
[3/8] lint           --> Flake8 AST syntax and critical error detection
[4/8] typecheck      --> Mypy strict static type validation on core systems
[5/8] security-check --> Bandit Static Application Security Testing (SAST)
[6/8] restore-check  --> Automated backup creation and end-to-end restore verification
[7/8] sbom           --> Generates cryptographic SPDX 2.3 JSON Software Bill of Materials
[8/8] test           --> Complete pytest execution with 80%+ test coverage gate
```

### 2. Stage Details & Concrete Tooling
1. **Stage 1: Safety Invariant Audit (`make safety-check`)**
   Executes [`scripts/verify_safety_invariants.py`](file:///home/ubuntu/algolab/scripts/verify_safety_invariants.py) to confirm:
   - `LIVE_TRADING_ENABLED == False` and `REAL_BROKER_EXECUTION_ENABLED == False` in `src/version.py`.
   - Settings validation in `apps/api/core/config.py` enforces fail-closed behavior.
   - Live market daemon invariants and zero live broker order endpoint imports across all modules.
   - Secret scan ensuring zero private tokens or unmasked credentials exist in git tracking.
2. **Stage 2: Pinned Dependency Lock Integrity (`make lock-check`)**
   Executes [`scripts/verify_dependency_lock.py`](file:///home/ubuntu/algolab/scripts/verify_dependency_lock.py) to verify that all 72 production dependencies in the active virtual environment match the exact pinned versions in [`requirements-pinned.txt`](file:///home/ubuntu/algolab/requirements-pinned.txt).
3. **Stage 3: Code Syntax & Critical Lint Analysis (`make lint`)**
   Executes `flake8` against `apps/`, `services/`, `src/`, and `quant/` selecting critical syntax and undefined name errors (`--select=E9,F63,F7,F82`). Must return zero violations.
4. **Stage 4: Static Type Checking (`make typecheck`)**
   Executes `mypy` against core modules to guarantee static type correctness.
5. **Stage 5: Application Security Testing (`make security-check`)**
   Runs `bandit` SAST scanner (`-ll -ii`) recursively scanning all application source code for medium and high-severity security vulnerabilities.
6. **Stage 6: Disaster Recovery & Automated Restore (`make restore-check`)**
   Executes [`scripts/backup_restore.py --test-restore`](file:///home/ubuntu/algolab/scripts/backup_restore.py) which creates an encrypted tar archive of ledger state and database files, decrypts it in an isolated temporary directory, computes SHA-256 hashes, and proves that data can be restored cleanly.
7. **Stage 7: Software Bill of Materials Generation (`make sbom`)**
   Runs [`scripts/generate_sbom.py`](file:///home/ubuntu/algolab/scripts/generate_sbom.py) to compile a formal SPDX 2.3 JSON SBOM ([`data/sbom.spdx.json`](file:///home/ubuntu/algolab/data/sbom.spdx.json)) capturing 140 transitive dependencies, licenses, and checksums.
8. **Stage 8: Test Suite Execution with Coverage Gate (`make test`)**
   Runs `pytest tests/ -q` across all 338 test cases. Enforces the mandatory `80%+` code coverage requirement defined in [`pyproject.toml`](file:///home/ubuntu/algolab/pyproject.toml#L33) (`fail_under = 80`).

### 3. CI/CD Pipeline Mirroring
GitHub Actions workflow ([`.github/workflows/ci.yml`](file:///home/ubuntu/algolab/.github/workflows/ci.yml)) mirrors this pipeline on every pull request, main branch merge, and release tag. Any single stage failure immediately fails the build.

## Non-Negotiable Safety Invariant Compliance
- **Does this decision preserve `LIVE_TRADING_ENABLED = False`?**  
  **Yes.** Stage 1 (`safety-check`) explicitly scans and asserts that `LIVE_TRADING_ENABLED` is `False`. If set to `True`, the entire release gate aborts immediately.
- **Does it maintain independent risk engine authority?**  
  **Yes.** Stage 8 runs boundary tests verifying that strategy modules cannot bypass the risk engine.
- **Does it prevent synthetic data substitution in production paper paths?**  
  **Yes.** Stage 8 executes manifest tests ensuring synthetic data cannot be promoted to validated or experiment pipelines.

## Consequences

### Positive
- **Guaranteed Production Baseline:** No broken builds, security vulnerabilities, unpinned packages, or failing restores can reach canonical branches.
- **Reproducible Verification:** Any engineer or automated CI runner can reproduce identical validation results using a single standard command.
- **Continuous Disaster Recovery Assurance:** Every release test validates that backups can actually be restored, avoiding disaster recovery surprises.
- **Regulatory & Supply Chain Transparency:** Comprehensive SPDX 2.3 SBOM automatically updated with each release certification.

### Negative / Trade-offs
- **Execution Time:** The complete 8-stage gate requires approximately 20–30 seconds to run locally.
- **Zero Tolerance for Warnings/Failures:** Strict lockfile and type checks require immediate remediation whenever new libraries are introduced.

## Compliance & Verification Evidence
- **Link to relevant tests:**
  - [`Makefile`](file:///home/ubuntu/algolab/Makefile#L59)
  - [`.github/workflows/ci.yml`](file:///home/ubuntu/algolab/.github/workflows/ci.yml)
  - [`scripts/verify_safety_invariants.py`](file:///home/ubuntu/algolab/scripts/verify_safety_invariants.py)
  - [`scripts/verify_dependency_lock.py`](file:///home/ubuntu/algolab/scripts/verify_dependency_lock.py)
  - [`scripts/backup_restore.py`](file:///home/ubuntu/algolab/scripts/backup_restore.py)
- **Verification command:**
  ```bash
  make release-check
  ```
