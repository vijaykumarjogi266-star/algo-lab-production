"""
OMS Project - Strategy Factory (Project STRAT-FACTORY)
Provides Parameterized Strategy Blueprints, Config Schema Validation,
High-Speed Fast-Test Replay Engine with Indian Statutory Friction,
and Deployment / Hot-Reload Pipeline.
"""

import os
import json
import time
import asyncio
from decimal import Decimal
from typing import Dict, Any, List, Optional, Type
from pydantic import BaseModel, Field

from oms_project.schemas import OrderIntent, OrderState, NormalizedTick
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.central_data_feed import MarketDataService
from oms_project.replay_service import HistoricalReplayEngine, generate_synthetic_ticks
from oms_project.strategies.mean_reversion.strategy_sdk import BaseStrategy, StrategySDK
from oms_project.strategies.mean_reversion.mean_reversion_strat import MeanReversionStrategy
from oms_project.strategies.trend_following.trend_following_strat import TrendFollowingStrategy
from oms_project.strategies.hybrid.hybrid_alpha_strat import HybridAlphaStrategy
from oms_project.scripts.reconciliation import AssetReconciler

from services.backtest_engine.statutory_cost_model import (
    IndianStatutoryCostModel,
    OrderLeg,
    ProductType,
)


class StrategyConfig(BaseModel):
    strategy_id: str = Field(..., description="Unique strategy identifier (e.g. STRAT_CUSTOM_001)")
    strategy_type: str = Field(..., description="Base blueprint type: mean_reversion, trend_following, or hybrid")
    symbol: str = Field(default="RELIANCE", description="Trading instrument symbol")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Strategy specific indicator parameters")
    risk_limits: Dict[str, Any] = Field(default_factory=dict, description="Risk controls (max_qty, stop_loss_pct)")
    allocation: Dict[str, Any] = Field(default_factory=dict, description="Capital allocation settings")


class StrategyFactory:
    """
    Factory for instantiating and managing parameterized strategy blueprints.
    """

    _blueprints: Dict[str, Type[BaseStrategy]] = {
        "mean_reversion": MeanReversionStrategy,
        "trend_following": TrendFollowingStrategy,
        "hybrid": HybridAlphaStrategy,
        "hybrid_alpha": HybridAlphaStrategy,
    }

    @classmethod
    def register_blueprint(cls, name: str, strategy_cls: Type[BaseStrategy]):
        cls._blueprints[name.lower()] = strategy_cls

    @classmethod
    def get_registered_blueprints(cls) -> Dict[str, Any]:
        return {
            "mean_reversion": {
                "name": "Mean Reversion",
                "description": "Simple Moving Average with Bollinger Band volatility envelope reversion strategy.",
                "parameters_schema": {
                    "window": {"type": "int", "default": 20, "min": 2, "max": 200, "label": "SMA Window Size"},
                    "threshold": {"type": "float", "default": 1.5, "min": 0.1, "max": 5.0, "label": "StdDev Threshold (σ)"},
                },
                "risk_limits_schema": {
                    "max_qty": {"type": "float", "default": 10.0, "min": 1.0, "max": 1000.0, "label": "Order Quantity"},
                    "stop_loss_pct": {"type": "float", "default": 0.02, "min": 0.005, "max": 0.20, "label": "Stop Loss (%)"},
                },
            },
            "trend_following": {
                "name": "Trend Following",
                "description": "Short and Long Moving Average crossover strategy with trailing stop loss.",
                "parameters_schema": {
                    "short_window": {"type": "int", "default": 5, "min": 2, "max": 50, "label": "Short SMA Window"},
                    "long_window": {"type": "int", "default": 20, "min": 10, "max": 200, "label": "Long SMA Window"},
                },
                "risk_limits_schema": {
                    "max_qty": {"type": "float", "default": 10.0, "min": 1.0, "max": 1000.0, "label": "Order Quantity"},
                    "stop_loss_pct": {"type": "float", "default": 0.02, "min": 0.005, "max": 0.20, "label": "Stop Loss (%)"},
                },
            },
            "hybrid": {
                "name": "Hybrid Alpha",
                "description": "Regime-switching strategy combining Mean Reversion and Trend Following based on volatility.",
                "parameters_schema": {
                    "volatility_window": {"type": "int", "default": 10, "min": 5, "max": 50, "label": "Volatility Window"},
                    "volatility_threshold": {"type": "float", "default": 0.01, "min": 0.001, "max": 0.05, "label": "Volatility Threshold"},
                    "window": {"type": "int", "default": 20, "min": 2, "max": 100, "label": "Mean Rev Window"},
                    "short_window": {"type": "int", "default": 5, "min": 2, "max": 50, "label": "Trend Short Window"},
                    "long_window": {"type": "int", "default": 20, "min": 10, "max": 100, "label": "Trend Long Window"},
                },
                "risk_limits_schema": {
                    "max_qty": {"type": "float", "default": 10.0, "min": 1.0, "max": 1000.0, "label": "Order Quantity"},
                    "stop_loss_pct": {"type": "float", "default": 0.02, "min": 0.005, "max": 0.20, "label": "Stop Loss (%)"},
                },
            },
        }

    @classmethod
    def instantiate(cls, config: Dict[str, Any], sdk: Optional[StrategySDK] = None) -> BaseStrategy:
        strat_type = config.get("strategy_type") or config.get("type")
        if not strat_type:
            raise ValueError("Config must specify 'strategy_type' or 'type'")

        strat_type_norm = str(strat_type).lower()
        if strat_type_norm not in cls._blueprints:
            raise ValueError(f"Unknown strategy blueprint '{strat_type}'. Available: {list(cls._blueprints.keys())}")

        strategy_cls = cls._blueprints[strat_type_norm]
        strat_id = config.get("strategy_id", f"STRAT_{strat_type_norm.upper()}_{int(time.time())}")
        symbol = config.get("symbol", "RELIANCE")

        sdk_inst = sdk or StrategySDK(strategy_id=strat_id)
        return strategy_cls(
            strategy_id=strat_id,
            symbol=symbol,
            config=config,
            sdk=sdk_inst,
        )


class FastTestEngine:
    """
    High-Speed Fast-Test Replay Engine with Sim-Lock Security & Statutory Accounting.
    Performs instant deterministic historical replay in the Time Machine.
    """

    MAX_CONCURRENT_FAST_TESTS = 5
    _semaphore = asyncio.Semaphore(MAX_CONCURRENT_FAST_TESTS)

    @classmethod
    def run_fast_test(
        cls,
        config: Dict[str, Any],
        ticks: Optional[List[Dict[str, Any]]] = None,
        initial_capital: float = 100000.0,
        slippage_bps: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Executes a synchronous fast backtest simulation locked strictly to the Time Machine.
        Calculates exact Indian statutory taxes and friction.
        """
        # 1. Sim-Lock Guard Verification
        # Must physically use isolated Simulation Broker Gateway & Paper Exchange
        paper_ex = PaperExchange(initial_cash=initial_capital)
        gateway = BrokerGateway(
            paper_exchange=paper_ex,
            simulation_mode=True,
            slippage_bps=slippage_bps,
        )
        strat_id = config.get("strategy_id", "STRAT_FAST_TEST_001")
        gateway.reset_simulation(initial_cash=initial_capital)
        gateway.strategy_balances[strat_id] = initial_capital
        gateway.strategy_reserved[strat_id] = 0.0
        gateway.strategy_positions[strat_id] = {}
        gateway.strategy_entry_prices[strat_id] = {}
        gateway.simulation_mode = True

        # Ensure live trading environment override is impossible
        if os.getenv("ALLOW_LIVE_TRADING", "False").upper() == "TRUE":
            raise RuntimeError("SIM-LOCK SECURITY VIOLATION: LIVE TRADING ENVAR DETECTED DURING FAST-TEST!")

        # 2. Setup Market Feed and Replay Engine
        feed = MarketDataService()
        replay = HistoricalReplayEngine(market_data_service=feed, playback_speed=0.0)

        tick_data = ticks or generate_synthetic_ticks(
            symbol=config.get("symbol", "RELIANCE"),
            start_price=1200.0,
            count=500,
            seed=42,
        )
        replay.load_ticks(tick_data)

        # 3. Instantiate Strategy via Factory
        sdk = StrategySDK(strategy_id=strat_id)
        bot = StrategyFactory.instantiate(config, sdk=sdk)

        equity_curve: List[Dict[str, Any]] = []
        peak_equity: float = initial_capital
        max_drawdown_pct: float = 0.0
        filled_orders: List[Dict[str, Any]] = []

        total_brokerage = Decimal("0.0")
        total_stt = Decimal("0.0")
        total_exchange_fee = Decimal("0.0")
        total_sebi_fee = Decimal("0.0")
        total_stamp_duty = Decimal("0.0")
        total_gst = Decimal("0.0")
        total_statutory_friction = Decimal("0.0")

        def on_tick_step(tick: NormalizedTick):
            gateway.set_market_price(tick.symbol, tick.price, tick.timestamp)
            intent = bot.on_tick(tick.price, timestamp=tick.timestamp)
            if intent:
                res = gateway.process_order_intent(intent)
                if res.status == OrderState.FILLED:
                    filled_orders.append(res.model_dump())

                    # Calculate statutory friction using IndianStatutoryCostModel
                    leg = OrderLeg.BUY if intent.side.value == "BUY" else OrderLeg.SELL
                    friction = IndianStatutoryCostModel.calculate_order_friction(
                        leg=leg,
                        price=Decimal(str(tick.price)),
                        quantity=int(intent.qty),
                        product=ProductType.INTRADAY,
                        slippage_bps=Decimal(str(slippage_bps)),
                    )
                    nonlocal total_brokerage, total_stt, total_exchange_fee
                    nonlocal total_sebi_fee, total_stamp_duty, total_gst, total_statutory_friction

                    total_brokerage += friction.brokerage
                    total_stt += friction.stt
                    total_exchange_fee += friction.exchange_txn_fee
                    total_sebi_fee += friction.sebi_turnover_fee
                    total_stamp_duty += friction.stamp_duty
                    total_gst += friction.gst
                    total_statutory_friction += friction.total_statutory_and_brokerage

                    # Deduct statutory charges from gateway and paper exchange balances to maintain net financial truth and zero variance
                    current_bal = gateway.strategy_balances.get(strat_id, initial_capital)
                    friction_inr = float(friction.total_statutory_and_brokerage)
                    gateway.strategy_balances[strat_id] = max(0.0, current_bal - friction_inr)
                    gateway.paper_exchange.cash_balance = max(0.0, gateway.paper_exchange.cash_balance - friction_inr)

            curr_assets = gateway.get_broker_ledger_total_assets(strat_id)
            nonlocal peak_equity, max_drawdown_pct
            if curr_assets > peak_equity:
                peak_equity = curr_assets
            dd = ((peak_equity - curr_assets) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
            if dd > max_drawdown_pct:
                max_drawdown_pct = dd

            equity_curve.append({
                "timestamp": tick.timestamp,
                "price": tick.price,
                "equity": round(curr_assets, 2),
            })

        replay.replay_ticks_sync(on_tick_step)

        reconciler = AssetReconciler(gateway, gateway.paper_exchange)
        recon_report = reconciler.run_reconciliation(strat_id)

        final_equity = gateway.get_broker_ledger_total_assets(strat_id)
        gross_pnl = final_equity - initial_capital
        net_pnl = gross_pnl - float(total_statutory_friction)
        net_pnl_pct = (net_pnl / initial_capital) * 100.0

        return {
            "strategy_id": strat_id,
            "strategy_type": config.get("strategy_type") or config.get("type"),
            "initial_capital": round(initial_capital, 2),
            "final_equity": round(final_equity, 2),
            "gross_pnl": round(gross_pnl, 2),
            "net_pnl": round(net_pnl, 2),
            "net_pnl_pct": round(net_pnl_pct, 2),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "total_trades": len(filled_orders),
            "statutory_friction": {
                "brokerage": float(total_brokerage),
                "stt": float(total_stt),
                "exchange_txn_fee": float(total_exchange_fee),
                "sebi_turnover_fee": float(total_sebi_fee),
                "stamp_duty": float(total_stamp_duty),
                "gst": float(total_gst),
                "total_friction": float(total_statutory_friction),
            },
            "reconciliation_variance": round(recon_report["variance"], 8),
            "reconciliation_status": recon_report["status"],
            "equity_curve": equity_curve[:: max(1, len(equity_curve) // 50)],  # Downsample for UI chart
        }
