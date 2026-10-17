# Contributing to Algo Lab

Thank you for contributing to Algo Lab, an institutional, paper-only quantitative research and forward-simulation platform for Indian equities.

## Non-Negotiable Safety Invariants

Before writing code or opening a pull request, you must agree to and maintain our non-negotiable safety rules:

1. **Paper-Only Execution Policy:** `LIVE_TRADING_ENABLED` and `REAL_BROKER_EXECUTION_ENABLED` must remain `False`. Any attempt to enable live order routing or real broker accounts will fail application startup and CI.
2. **Risk Engine Independence:** The risk engine is strictly independent of strategies, AI models, sentiment/news feeds, and UI commands. Strategies return signals only; only the risk engine can approve or reject orders.
3. **Data Integrity:** Missing, stale, malformed, future-dated, or unverified data must result in `WAIT` / rejection. Synthetic substitution in production paper paths is prohibited.
4. **Zero Secret Logging:** Never write API keys, access tokens, client secrets, passwords, or account identifiers to logs, source code, test outputs, or git commits.
5. **Deterministic & Point-in-Time Safe:** Backtests and forward replays must remain reproducible, point-in-time safe, and versioned.

---

## Development Workflow

### 1. Prerequisites
- Python 3.12+
- Linux (Ubuntu 22.04+ or compatible) or macOS
- SQLite3 and Parquet tools

### 2. Local Setup
```bash
# 1. Clone the repository
git clone https://github.com/vijaykumarjogi266-star/algopro.git algolab
cd algolab

# 2. Set up virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install pinned dependencies
pip install --upgrade pip
pip install -r requirements-pinned.txt
pip install -e .
```

### 3. Pre-Commit Validation Checklist
Before submitting a pull request, ensure all gates pass locally:
```bash
make release-check
```
This runs:
- Safety invariant audit (zero live trading paths)
- Python typecheck (`mypy`)
- Static security audit (`bandit`)
- Secret scanner
- Complete unit and integration test suite (`pytest`)
- Dependency lock verification
- SBOM generation

---

## Pull Request Guidelines

- Branch naming: `feature/<name>`, `fix/<issue>`, `hardening/<scope>`.
- Commit messages: Follow Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`).
- Keep changes focused and logically grouped. Avoid unrelated whitespace or formatting churn.
- Every functional change must include corresponding unit/contract tests.
- Fill out the [Pull Request Template](.github/pull_request_template.md).
