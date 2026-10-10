# ALGO LAB CLEAN-INSTALL RUNBOOK
**Governing Plan:** *Algo Lab: Quality-First Execution Plan — September 25, 2026 (Phase 8)*  
**Target:** Reproducible clean-environment installation and verification by an independent operator.  

---

## 1. Prerequisites
- Linux OS: Ubuntu 22.04 or 24.04 LTS
- Python 3.12 (`python3.12`, `python3.12-venv`, `python3.12-dev`)
- Git, Build Essentials (`gcc`, `g++`, `make`)

---

## 2. Step-by-Step Installation

```bash
# 1. Clone repository
git clone <repo-url> /home/ubuntu/algolab
cd /home/ubuntu/algolab

# 2. Create isolated Python 3.12 virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip to deterministic baseline
pip install --upgrade pip==26.2.1

# 4. Install pinned dependencies
pip install -r requirements-pinned.txt

# 5. Verify non-negotiable safety locks
python -c "from apps.api.core.config import settings; assert settings.ALLOW_LIVE_TRADING is False; assert settings.ALLOW_REAL_BROKER_EXECUTION is False; print('SAFETY LOCKS VERIFIED')"

# 6. Execute full offline regression test suite
pytest tests/unit/
```

---

## 3. Verifying Safety and Operational Invariants

After installation, the operator must verify:
1. All unit tests pass (`170+ passed, 0 failed`).
2. AST scan confirms zero live broker order placement calls:
   ```bash
   pytest tests/unit/test_stage27_security_firewall.py
   ```
3. Secret redaction test passes:
   ```bash
   pytest tests/unit/test_angel_one_market_data.py -k "test_canary_secret_redaction"
   ```
4. Double-entry ledger invariants pass:
   ```bash
   pytest tests/unit/test_paper_trading_session.py
   ```

---

## 4. Rollback and Disaster Clean-Up

If installation fails or dependencies drift:
```bash
rm -rf .venv
# Re-run from Step 2 with pinned requirements
```
