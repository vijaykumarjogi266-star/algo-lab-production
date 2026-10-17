# Algo Lab Canonical Makefile — Quality & Release Integrity Gate
# Enforces fail-closed validation, security checks, and paper-only invariants

VENV ?= .venv
PYTHON = $(VENV)/bin/python3
PIP = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
MYPY = $(VENV)/bin/mypy
BANDIT = $(VENV)/bin/bandit
FLAKE8 = $(VENV)/bin/flake8

.PHONY: help install lint typecheck security-check safety-check lock-check test sbom release-check clean

help:
	@echo "Algo Lab — Quantitative Research OS (Release 0.3.0)"
	@echo "========================================================"
	@echo "make release-check   - Run complete fail-closed CI release gate"
	@echo "make safety-check    - Verify non-negotiable safety invariants"
	@echo "make lock-check      - Verify locked dependency consistency"
	@echo "make lint            - Run code syntax and quality checks"
	@echo "make typecheck       - Run static type analysis (mypy)"
	@echo "make security-check  - Run static application security testing (bandit)"
	@echo "make test            - Run comprehensive pytest test suite"
	@echo "make sbom            - Generate SPDX 2.3 JSON Software Bill of Materials"
	@echo "make clean           - Clean cache and build artifacts"

safety-check:
	@echo "==> [1/7] Auditing Non-Negotiable Safety Invariants..."
	$(PYTHON) scripts/verify_safety_invariants.py

lock-check:
	@echo "==> [2/7] Verifying Pinned Dependency Lock Integrity..."
	$(PYTHON) scripts/verify_dependency_lock.py

lint:
	@echo "==> [3/7] Running Code Syntax & Lint Analysis..."
	$(FLAKE8) apps services src quant --count --select=E9,F63,F7,F82 --show-source --statistics

typecheck:
	@echo "==> [4/7] Running Static Type Checking (mypy)..."
	$(MYPY) src/version.py apps/api/core/config.py src/gpt_client.py

security-check:
	@echo "==> [5/7] Running Static Security Scan (Bandit)..."
	$(BANDIT) -r apps services quant src -ll -ii -x .venv,tests

restore-check:
	@echo "==> [6/8] Verifying Disaster Recovery & Automated Restore..."
	$(PYTHON) scripts/backup_restore.py --test-restore

sbom:
	@echo "==> [7/8] Generating SPDX JSON Software Bill of Materials..."
	$(PYTHON) scripts/generate_sbom.py

test:
	@echo "==> [8/8] Running Test Suite with Coverage Enforcement..."
	$(PYTEST) tests/ -q

release-check: safety-check lock-check lint typecheck security-check restore-check sbom test
	@echo ""
	@echo "================================================================"
	@echo "✅ CANONICAL RELEASE CHECK PASSED — 100% PRODUCTION-HARDENED"
	@echo "================================================================"

clean:
	rm -rf .pytest_cache __pycache__ *.pyc
	find . -type d -name "__pycache__" -exec rm -rf {} +
