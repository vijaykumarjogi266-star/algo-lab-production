"""
OMS Project - Ledger vs Paper Exchange Asset Reconciliation Script
Compares Total Assets held in Broker Ledger (PostgreSQL/SQLite) vs Paper Exchange API.
"""

import sys
from typing import Dict, Any
from oms_project.gateway import BrokerGateway
from oms_project.paper_exchange import PaperExchange


class AssetReconciler:
    def __init__(self, gateway: BrokerGateway, paper_exchange: PaperExchange):
        self.gateway = gateway
        self.paper_exchange = paper_exchange

    def run_reconciliation(self, strategy_id: str = "STRAT_MEAN_REV_001") -> Dict[str, Any]:
        market_prices = self.gateway.reference_market_prices

        # Query Broker Ledger Total Assets
        broker_assets = self.gateway.get_broker_ledger_total_assets(strategy_id=strategy_id)
        broker_cash = self.gateway.strategy_balances.get(strategy_id, 0.0)
        broker_reserved = self.gateway.strategy_reserved.get(strategy_id, 0.0)
        broker_positions = dict(self.gateway.strategy_positions.get(strategy_id, {}))

        # Query Paper Exchange Total Assets
        paper_assets = self.paper_exchange.get_total_assets(market_prices=market_prices)
        paper_cash = self.paper_exchange.cash_balance
        paper_positions = dict(self.paper_exchange.positions)

        variance = abs(broker_assets - paper_assets)

        report = {
            "strategy_id": strategy_id,
            "broker_ledger": {
                "total_assets": round(broker_assets, 2),
                "cash_balance": round(broker_cash, 2),
                "reserved_balance": round(broker_reserved, 2),
                "positions": broker_positions,
            },
            "paper_exchange": {
                "total_assets": round(paper_assets, 2),
                "cash_balance": round(paper_cash, 2),
                "positions": paper_positions,
            },
            "variance": round(variance, 2),
            "status": "MATCH" if round(variance, 4) == 0.0 else "MISMATCH",
        }
        return report


def print_reconciliation_report(report: Dict[str, Any]):
    print("================================================================================")
    print("                 OMS EOD ASSET RECONCILIATION REPORT                            ")
    print("================================================================================")
    print(f" Strategy ID        : {report['strategy_id']}")
    print(f" Broker Ledger Assets: ₹{report['broker_ledger']['total_assets']:,.2f}")
    print(f"   - Cash Balance   : ₹{report['broker_ledger']['cash_balance']:,.2f}")
    print(f"   - Reserved Risk  : ₹{report['broker_ledger']['reserved_balance']:,.2f}")
    print(f"   - Positions      : {report['broker_ledger']['positions']}")
    print("--------------------------------------------------------------------------------")
    print(f" Paper Exchange Assets: ₹{report['paper_exchange']['total_assets']:,.2f}")
    print(f"   - Cash Balance   : ₹{report['paper_exchange']['cash_balance']:,.2f}")
    print(f"   - Positions      : {report['paper_exchange']['positions']}")
    print("================================================================================")
    print(f" ASSET VARIANCE      : ₹{report['variance']:,.2f}")
    print(f" RECONCILIATION STATUS: {'[PASS] VARIANCE = 0' if report['status'] == 'MATCH' else '[FAIL] MISMATCH DETECTED'}")
    print("================================================================================")


if __name__ == "__main__":
    ex = PaperExchange(initial_cash=100000.0)
    gw = BrokerGateway(paper_exchange=ex)
    reconciler = AssetReconciler(gw, ex)
    rep = reconciler.run_reconciliation("STRAT_MEAN_REV_001")
    print_reconciliation_report(rep)
    sys.exit(0 if rep["status"] == "MATCH" else 1)
