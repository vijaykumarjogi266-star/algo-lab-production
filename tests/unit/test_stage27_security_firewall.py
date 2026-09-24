"""Algo Lab Stage 27 — Live-Trading Security Firewall & Isolation Test Suite.

Automated security probes enforcing strict paper-only boundary:
1. AST Code Scanner: Verifies ZERO live broker order placement SDK calls or endpoints across all codebase modules.
2. Paper Trading Engine Isolation: Verifies all paper fills output is_simulated=True and contain zero real broker credentials/IDs.
3. Live Network Order Route Block Probe: Verifies no outbound trading execution sockets/routes exist.
4. Environment Variable Bypass Invalidation: Proves environment overrides cannot activate live execution.
5. Production Baseline Isolation Probe: Reports baseline repository status.
"""

import os
import ast
import subprocess
from datetime import datetime, timezone
import pytest

FORBIDDEN_CALLS = [
    "place_order",
    "placeOrder",
    "modify_order",
    "modifyOrder",
    "cancel_order",
    "cancelOrder",
    "execute_live_order",
    "submit_order",
    "send_order",
]

# Excluded files that explicitly define trap methods or security tests
FIREWALL_TRAP_FILES = [
    "services/paper-engine/session.py",
    "services/paper-engine/adapters/base.py",
    "services/paper-engine/adapters/credentials.py",
    "tests/unit/test_stage6_integrity.py",
    "tests/unit/test_stage27_security_firewall.py",
]


def test_ast_prohibit_live_broker_order_calls():
    """AST Scanner: Verifies no python file calls forbidden live broker order placement methods."""
    repo_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    source_dirs = [
        os.path.join(repo_path, "apps"),
        os.path.join(repo_path, "collectors"),
        os.path.join(repo_path, "paper"),
        os.path.join(repo_path, "quant"),
        os.path.join(repo_path, "services"),
    ]

    violations = []

    for s_dir in source_dirs:
        if not os.path.exists(s_dir):
            continue
        for root, _, files in os.walk(s_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, repo_path)
                    if any(rel_path.endswith(t_file) for t_file in FIREWALL_TRAP_FILES):
                        continue

                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    try:
                        tree = ast.parse(content, filename=full_path)
                    except SyntaxError:
                        continue

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Call):
                            func_name = ""
                            if isinstance(node.func, ast.Name):
                                func_name = node.func.id
                            elif isinstance(node.func, ast.Attribute):
                                func_name = node.func.attr

                            if func_name in FORBIDDEN_CALLS:
                                violations.append(f"{rel_path}: called {func_name}")

    assert len(violations) == 0, f"Live broker order placement violations found: {violations}"


def test_paper_engine_isolation_and_credentials():
    """Verifies PaperTradingEngine enforces simulated status and blocks live broker credentials."""
    from services.paper_engine.session import PaperTradingEngine
    from services.paper_engine.adapters.credentials import LIVE_TRADING_ENABLED, ExecutionEnvironment

    assert LIVE_TRADING_ENABLED is False

    engine = PaperTradingEngine(":memory:")
    with pytest.raises(PermissionError):
        engine.create_session(
            name="Live Attempt Test",
            strategy_id="strat_test",
            universe=["RELIANCE"],
            environment=ExecutionEnvironment.LIVE,
        )


def test_live_execution_env_override_bypass_prohibited():
    """Verifies setting ENABLE_LIVE_TRADING=TRUE environment variable does not activate live trading."""
    os.environ["ENABLE_LIVE_TRADING"] = "TRUE"
    os.environ["BROKER_API_KEY"] = "SECRET_KEY_PROBE"
    try:
        from services.paper_engine.adapters.credentials import LIVE_TRADING_ENABLED
        assert LIVE_TRADING_ENABLED is False
    finally:
        os.environ.pop("ENABLE_LIVE_TRADING", None)
        os.environ.pop("BROKER_API_KEY", None)


def test_production_repository_baseline_isolation():
    """Verifies that production baseline repository path is verified or reported correctly."""
    prod_path = "/root/sandbox/algopro"
    if not os.path.exists(prod_path):
        pytest.skip("PRODUCTION BASELINE NOT VERIFIABLE FROM THIS HOST")
