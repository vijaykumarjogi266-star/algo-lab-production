import os
import pytest

@pytest.fixture(scope="session", autouse=True)
def setup_safety_environment():
    """Ensure tests run under a safe simulated configuration by default."""
    os.environ["TRADING_MODE"] = "READ_ONLY"
    os.environ["ORDER_SUBMISSION_ENABLED"] = "false"
    os.environ["ALLOW_LIVE_TRADING"] = "false"
    os.environ["ALLOW_REAL_BROKER_EXECUTION"] = "false"
    os.environ["REAL_MONEY_RISK_PAISE"] = "0"
    os.environ["PAPER_BROKER_ONLY"] = "true"
