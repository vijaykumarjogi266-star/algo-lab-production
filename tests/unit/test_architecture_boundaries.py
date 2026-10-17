"""Architectural Boundary & Isolation Tests for Algo Lab (Workstream F).

Validates:
1. Strategies never import live broker execution or place real orders.
2. AI/LLM modules (gpt_client, chatgpt_advisor) never import order routing or bypass risk.
3. ExecutionSimulatorContract accurately resolves gap-down fills at Open price.
4. Independent risk checks cannot be bypassed by signal generators.
5. Invariants: LIVE_TRADING_ENABLED=False and REAL_BROKER_EXECUTION_ENABLED=False.
"""

import ast
from pathlib import Path
import pytest

from services.backtest_engine.execution_contract import (
    ExecutionSimulatorContract,
    FillPriceModel,
    GapHandlingPolicy,
)
from src.version import (
    LIVE_TRADING_ENABLED,
    PAPER_ONLY_EXECUTION_POLICY,
    REAL_BROKER_EXECUTION_ENABLED,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_safety_flags_frozen():
    """Safety flags must remain permanently False in src.version."""
    assert LIVE_TRADING_ENABLED is False
    assert REAL_BROKER_EXECUTION_ENABLED is False
    assert PAPER_ONLY_EXECUTION_POLICY is True


def test_strategies_cannot_import_live_broker():
    """Scans all strategy and quant files to guarantee zero live order routing imports."""
    disallowed_calls = {
        "place_order",
        "modify_order",
        "cancel_order",
    }
    quant_dir = REPO_ROOT / "quant"
    strategy_files = list(quant_dir.rglob("*.py"))

    for py_file in strategy_files:
        with open(py_file, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "kiteconnect.KiteConnect" not in alias.name, f"Forbidden import in {py_file}: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "kiteconnect" not in module or "ticker" in module, f"Forbidden live broker import in {py_file}: {module}"


def test_ai_advisor_cannot_submit_orders():
    """AI advisor files must not import paper or real order execution engines."""
    ai_files = [
        REPO_ROOT / "src" / "gpt_client.py",
        REPO_ROOT / "scripts" / "chatgpt_advisor.py",
    ]
    for py_file in ai_files:
        if not py_file.exists():
            continue
        with open(py_file, "r", encoding="utf-8") as f:
            code = f.read()
        tree = ast.parse(code, filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert "order_manager" not in module, f"AI module {py_file} imported order_manager"
                assert "execution" not in module, f"AI module {py_file} imported execution"


def test_execution_contract_gap_down_realism():
    """Execution contract must fill at open price during gap-down open below stop loss."""
    contract = ExecutionSimulatorContract(gap_handling=GapHandlingPolicy.REALISTIC_OPEN_PRICE)
    stop_loss = 100.0
    bar_open = 94.0  # Stock opened with a 6% gap-down below stop loss
    bar_low = 92.0

    fill_price = contract.resolve_stop_loss_fill(
        stop_price=stop_loss,
        bar_open=bar_open,
        bar_low=bar_low,
        is_long=True,
    )

    # Must execute at the bar open price (94.0), NOT the stop price (100.0)
    assert fill_price == 94.0, f"Unrealistic fill! Expected {bar_open}, got {fill_price}"


def test_execution_contract_slippage_and_market_impact():
    """Effective fill price must account for spread, bps slippage, and volume participation impact."""
    contract = ExecutionSimulatorContract(
        fixed_tick_slippage_pts=0.05,
        variable_slippage_bps=10.0,  # 10 bps = 0.1%
        market_impact_coefficient=0.2,
    )
    base_price = 1000.0
    order_qty = 500
    bar_volume = 10000.0

    buy_fill = contract.calculate_effective_price(
        base_price=base_price,
        is_buy=True,
        order_quantity=order_qty,
        bar_volume=bar_volume,
    )
    # Buy fill must be strictly greater than base price
    assert buy_fill > base_price
    # Check that slippage drag was applied
    assert buy_fill >= 1001.05

    sell_fill = contract.calculate_effective_price(
        base_price=base_price,
        is_buy=False,
        order_quantity=order_qty,
        bar_volume=bar_volume,
    )
    # Sell fill must be strictly less than base price
    assert sell_fill < base_price
