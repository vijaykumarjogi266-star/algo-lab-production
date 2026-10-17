"""
Comprehensive OMS Strategy Blueprints Backtest Runner
Executes FastTestEngine across multiple liquid symbols (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK)
for all three blueprints:
1. Mean Reversion
2. Trend Following
3. Hybrid Alpha

Extracts:
- Realized Net PnL (₹) & Net PnL (%)
- Total Trades & Win Rate (%)
- Maximum Drawdown (%)
- Statutory Friction Breakdown (Brokerage, STT, Exchange Fee, GST, Slippage)
- Reconciliation Status (PaperExchange vs Ledger)
"""

import os
import sys
import json
from decimal import Decimal
from typing import Dict, Any, List

sys.path.insert(0, "/home/ubuntu/algolab")
import pandas as pd

from oms_project.strategy_factory import FastTestEngine, StrategyFactory
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange
from oms_project.schemas import OrderSide, OrderState
from services.backtest_engine.statutory_cost_model import IndianStatutoryCostModel, OrderLeg, ProductType
from oms_project.scripts.reconciliation import AssetReconciler
from oms_project.strategies.mean_reversion.strategy_sdk import StrategySDK


SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
STRATEGIES = [
    {
        "type": "mean_reversion",
        "name": "Mean Reversion (SMA + BB)",
        "params": {"window": 20, "threshold": 1.5},
        "risk": {"max_qty": 10.0, "stop_loss_pct": 0.02},
    },
    {
        "type": "trend_following",
        "name": "Trend Following (Fast/Slow SMA)",
        "params": {"short_window": 5, "long_window": 20},
        "risk": {"max_qty": 10.0, "stop_loss_pct": 0.02},
    },
    {
        "type": "hybrid",
        "name": "Hybrid Alpha (Regime Switching)",
        "params": {
            "volatility_window": 10,
            "volatility_threshold": 0.01,
            "window": 20,
            "threshold": 1.5,
            "short_window": 5,
            "long_window": 20,
        },
        "risk": {"max_qty": 10.0, "stop_loss_pct": 0.02},
    },
]


def load_symbol_ticks(symbol: str) -> List[Dict[str, Any]]:
    parquet_path = f"/home/ubuntu/algolab/data/cache/{symbol}_NS_5y_1d.parquet"
    if not os.path.exists(parquet_path):
        raise FileNotFoundError(f"Missing cache parquet: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    ticks = []
    for _, row in df.iterrows():
        ts = pd.to_datetime(row["date"]).timestamp()
        ticks.append({
            "symbol": symbol,
            "price": round(float(row["close"]), 2),
            "volume": float(row["volume"]),
            "timestamp": ts,
        })
    return ticks


def compute_win_rate_and_realized_pnl(filled_orders: List[Dict[str, Any]], slippage_bps: float = 1.0):
    """
    Computes exact closed round-trip trades, winning vs losing trades,
    win rate %, and realized net PnL after Indian statutory friction.
    """
    open_buy_lots = []   # list of {"qty": float, "price": float, "friction": float}
    open_sell_lots = []  # list of {"qty": float, "price": float, "friction": float}
    
    closed_trades = []

    for order in filled_orders:
        side = order["side"]
        qty = float(order["qty"])
        price = float(order["price"])
        
        # Calculate single-leg friction
        leg = OrderLeg.BUY if side == "BUY" else OrderLeg.SELL
        friction = IndianStatutoryCostModel.calculate_order_friction(
            leg=leg,
            price=Decimal(str(price)),
            quantity=int(qty),
            product=ProductType.INTRADAY,
            slippage_bps=Decimal(str(slippage_bps)),
        )
        total_order_friction = float(friction.all_in_total_friction)
        friction_per_unit = total_order_friction / qty if qty > 0 else 0.0

        if side == "BUY":
            remaining_qty = qty
            # Match against existing short positions (open_sell_lots)
            while remaining_qty > 0 and open_sell_lots:
                lot = open_sell_lots[0]
                match_qty = min(remaining_qty, lot["qty"])
                gross_pnl = match_qty * (lot["price"] - price)
                matched_friction = (friction_per_unit * match_qty) + (lot["friction_per_unit"] * match_qty)
                net_pnl = gross_pnl - matched_friction
                closed_trades.append({
                    "type": "SHORT",
                    "qty": match_qty,
                    "entry_price": lot["price"],
                    "exit_price": price,
                    "gross_pnl": gross_pnl,
                    "friction": matched_friction,
                    "net_pnl": net_pnl,
                    "is_win": net_pnl > 0,
                })
                lot["qty"] -= match_qty
                remaining_qty -= match_qty
                if lot["qty"] <= 1e-6:
                    open_sell_lots.pop(0)

            if remaining_qty > 0:
                open_buy_lots.append({
                    "qty": remaining_qty,
                    "price": price,
                    "friction_per_unit": friction_per_unit,
                })

        elif side == "SELL":
            remaining_qty = qty
            # Match against existing long positions (open_buy_lots)
            while remaining_qty > 0 and open_buy_lots:
                lot = open_buy_lots[0]
                match_qty = min(remaining_qty, lot["qty"])
                gross_pnl = match_qty * (price - lot["price"])
                matched_friction = (friction_per_unit * match_qty) + (lot["friction_per_unit"] * match_qty)
                net_pnl = gross_pnl - matched_friction
                closed_trades.append({
                    "type": "LONG",
                    "qty": match_qty,
                    "entry_price": lot["price"],
                    "exit_price": price,
                    "gross_pnl": gross_pnl,
                    "friction": matched_friction,
                    "net_pnl": net_pnl,
                    "is_win": net_pnl > 0,
                })
                lot["qty"] -= match_qty
                remaining_qty -= match_qty
                if lot["qty"] <= 1e-6:
                    open_buy_lots.pop(0)

            if remaining_qty > 0:
                open_sell_lots.append({
                    "qty": remaining_qty,
                    "price": price,
                    "friction_per_unit": friction_per_unit,
                })

    num_closed = len(closed_trades)
    winning_trades = [t for t in closed_trades if t["is_win"]]
    losing_trades = [t for t in closed_trades if not t["is_win"]]
    win_rate = (len(winning_trades) / num_closed * 100.0) if num_closed > 0 else 0.0
    total_realized_net_pnl = sum(t["net_pnl"] for t in closed_trades)

    return {
        "closed_trades_count": num_closed,
        "winning_trades": len(winning_trades),
        "losing_trades": len(losing_trades),
        "win_rate_pct": round(win_rate, 2),
        "realized_net_pnl": round(total_realized_net_pnl, 2),
    }


def run_single_backtest(strat_def: Dict[str, Any], symbol: str, ticks: List[Dict[str, Any]], initial_capital: float = 100000.0, slippage_bps: float = 1.0) -> Dict[str, Any]:
    strat_type = strat_def["type"]
    strat_id = f"STRAT_{strat_type.upper()}_{symbol}"
    config = {
        "strategy_id": strat_id,
        "strategy_type": strat_type,
        "symbol": symbol,
        "parameters": strat_def["params"],
        "risk_limits": strat_def["risk"],
    }

    # Setup isolated test environment identical to FastTestEngine
    paper_ex = PaperExchange(initial_cash=initial_capital)
    gateway = BrokerGateway(
        paper_exchange=paper_ex,
        simulation_mode=True,
        slippage_bps=slippage_bps,
    )
    gateway.reset_simulation(initial_cash=initial_capital)
    gateway.strategy_balances[strat_id] = initial_capital
    gateway.strategy_reserved[strat_id] = 0.0
    gateway.strategy_positions[strat_id] = {}
    gateway.strategy_entry_prices[strat_id] = {}
    gateway.simulation_mode = True

    sdk = StrategySDK(strategy_id=strat_id)
    bot = StrategyFactory.instantiate(config, sdk=sdk)

    equity_curve = []
    peak_equity = initial_capital
    max_drawdown_pct = 0.0
    filled_orders = []

    total_brokerage = Decimal("0.0")
    total_stt = Decimal("0.0")
    total_exchange_fee = Decimal("0.0")
    total_sebi_fee = Decimal("0.0")
    total_stamp_duty = Decimal("0.0")
    total_gst = Decimal("0.0")
    total_statutory_friction = Decimal("0.0")
    total_slippage = Decimal("0.0")

    for raw_tick in ticks:
        tick_sym = raw_tick["symbol"]
        tick_px = raw_tick["price"]
        tick_ts = raw_tick["timestamp"]

        gateway.set_market_price(tick_sym, tick_px, tick_ts)
        intent = bot.on_tick(tick_px, timestamp=tick_ts)
        if intent:
            res = gateway.process_order_intent(intent)
            if res.status == OrderState.FILLED:
                filled_orders.append(res.model_dump())

                leg = OrderLeg.BUY if intent.side.value == "BUY" else OrderLeg.SELL
                friction = IndianStatutoryCostModel.calculate_order_friction(
                    leg=leg,
                    price=Decimal(str(tick_px)),
                    quantity=int(intent.qty),
                    product=ProductType.INTRADAY,
                    slippage_bps=Decimal(str(slippage_bps)),
                )

                total_brokerage += friction.brokerage
                total_stt += friction.stt
                total_exchange_fee += friction.exchange_txn_fee
                total_sebi_fee += friction.sebi_turnover_fee
                total_stamp_duty += friction.stamp_duty
                total_gst += friction.gst
                total_statutory_friction += friction.total_statutory_and_brokerage
                total_slippage += friction.slippage_cost_inr

                # Deduct statutory friction
                current_bal = gateway.strategy_balances.get(strat_id, initial_capital)
                friction_inr = float(friction.total_statutory_and_brokerage)
                gateway.strategy_balances[strat_id] = max(0.0, current_bal - friction_inr)
                gateway.paper_exchange.cash_balance = max(0.0, gateway.paper_exchange.cash_balance - friction_inr)

        curr_assets = gateway.get_broker_ledger_total_assets(strat_id)
        if curr_assets > peak_equity:
            peak_equity = curr_assets
        dd = ((peak_equity - curr_assets) / peak_equity) * 100.0 if peak_equity > 0 else 0.0
        if dd > max_drawdown_pct:
            max_drawdown_pct = dd

        equity_curve.append({"timestamp": tick_ts, "price": tick_px, "equity": round(curr_assets, 2)})

    reconciler = AssetReconciler(gateway, gateway.paper_exchange)
    recon_report = reconciler.run_reconciliation(strat_id)

    final_equity = gateway.get_broker_ledger_total_assets(strat_id)
    gross_pnl = final_equity - initial_capital
    net_pnl = gross_pnl - float(total_statutory_friction)
    net_pnl_pct = (net_pnl / initial_capital) * 100.0

    trade_stats = compute_win_rate_and_realized_pnl(filled_orders, slippage_bps=slippage_bps)

    return {
        "strategy_id": strat_id,
        "strategy_type": strat_type,
        "strategy_name": strat_def["name"],
        "symbol": symbol,
        "initial_capital": round(initial_capital, 2),
        "final_equity": round(final_equity, 2),
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
        "net_pnl_pct": round(net_pnl_pct, 2),
        "realized_net_pnl": trade_stats["realized_net_pnl"],
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "total_orders": len(filled_orders),
        "closed_trades": trade_stats["closed_trades_count"],
        "winning_trades": trade_stats["winning_trades"],
        "losing_trades": trade_stats["losing_trades"],
        "win_rate_pct": trade_stats["win_rate_pct"],
        "statutory_friction": {
            "brokerage": float(total_brokerage),
            "stt": float(total_stt),
            "exchange_txn_fee": float(total_exchange_fee),
            "sebi_turnover_fee": float(total_sebi_fee),
            "stamp_duty": float(total_stamp_duty),
            "gst": float(total_gst),
            "slippage": float(total_slippage),
            "total_friction": float(total_statutory_friction + total_slippage),
            "statutory_only": float(total_statutory_friction),
        },
        "reconciliation_variance": round(recon_report["variance"], 8),
        "reconciliation_status": recon_report["status"],
    }


def main():
    print("=" * 100)
    print("       OMS STRATEGY BLUEPRINT COMPREHENSIVE BACKTEST SUITE (FASTTESTENGINE)       ")
    print("=" * 100)

    results = []

    for sym in SYMBOLS:
        print(f"\n[DATA] Loading ticks for {sym}...")
        ticks = load_symbol_ticks(sym)
        print(f" -> Loaded {len(ticks)} ticks ({ticks[0]['price']} to {ticks[-1]['price']})")

        for strat in STRATEGIES:
            res = run_single_backtest(strat, sym, ticks, initial_capital=100000.0, slippage_bps=1.0)
            results.append(res)
            print(f"[{res['strategy_type'].upper():<16} | {sym:<10}] Net PnL: ₹{res['net_pnl']:>9.2f} ({res['net_pnl_pct']:>6.2f}%) | Realized: ₹{res['realized_net_pnl']:>9.2f} | Trades: {res['closed_trades']:>3} (WinRate: {res['win_rate_pct']:>5.1f}%) | MaxDD: {res['max_drawdown_pct']:>5.2f}% | Recon: {res['reconciliation_status']}")

    out_file = "/home/ubuntu/algolab/data/processed/oms_blueprints_backtest_results.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n[SUCCESS] Backtest results saved to {out_file}")


if __name__ == "__main__":
    main()
