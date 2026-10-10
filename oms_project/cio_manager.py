"""
OMS Project - Chief Investment Officer (CIO) Coordinator Service (cio_manager.py)
Monitors real-time P&L and active positions of all strategy pods,
implements performance-weighted capital allocation, and detects portfolio correlation.
"""

from typing import Dict, List, Optional, Any
from oms_project.gateway import BrokerGateway
from oms_project.strategies.mean_reversion.strategy_sdk import BaseStrategy


class CIOManager:
    """CIO Coordinator Service for Portfolio-Level Coordination & Capital Allocation."""

    def __init__(
        self,
        gateway: BrokerGateway,
        total_portfolio_capital: float = 1000000.0,
        min_pod_floor_pct: float = 0.10,
    ):
        self.gateway = gateway
        self.total_portfolio_capital = total_portfolio_capital
        self.min_pod_floor_pct = min_pod_floor_pct
        self.registered_pods: Dict[str, Optional[BaseStrategy]] = {}
        self.pod_realized_pnl: Dict[str, float] = {}

    def register_pod(self, strategy_id: str, strategy_instance: Optional[BaseStrategy] = None) -> None:
        """Register an active strategy pod with the CIO Manager."""
        self.registered_pods[strategy_id] = strategy_instance
        if strategy_id not in self.pod_realized_pnl:
            self.pod_realized_pnl[strategy_id] = 0.0

    def record_pod_pnl(self, strategy_id: str, pnl_delta: float) -> None:
        """Record trade profit or loss for a strategy pod."""
        self.pod_realized_pnl[strategy_id] = self.pod_realized_pnl.get(strategy_id, 0.0) + pnl_delta

    def compute_allocations(self) -> Dict[str, float]:
        """Performance-Weighted Capital Allocation Algorithm.
        
        Calculates each pod's share of capital based on its % contribution to total portfolio profit,
        ensuring a baseline minimum floor for all registered active pods.
        """
        pods = list(self.registered_pods.keys())
        if not pods:
            return {}

        n_pods = len(pods)
        floor_per_pod = (self.total_portfolio_capital * self.min_pod_floor_pct)
        remaining_pool = self.total_portfolio_capital - (floor_per_pod * n_pods)
        if remaining_pool < 0:
            # Equal floor split if capital pool is smaller than total floor requirements
            equal_share = self.total_portfolio_capital / n_pods
            return {pod: equal_share for pod in pods}

        # Calculate positive P&L contribution
        positive_pnls = {pod: max(0.0, self.pod_realized_pnl.get(pod, 0.0)) for pod in pods}
        total_positive_pnl = sum(positive_pnls.values())

        allocations: Dict[str, float] = {}
        for pod in pods:
            if total_positive_pnl > 0:
                weight = positive_pnls[pod] / total_positive_pnl
            else:
                weight = 1.0 / n_pods  # Equal distribution if no positive P&L accumulated yet

            pod_alloc = floor_per_pod + (weight * remaining_pool)
            allocations[pod] = round(pod_alloc, 2)

        return allocations

    def rebalance_allocations(self) -> Dict[str, float]:
        """Rebalances allocated capital across active pods and updates Gateway & Strategy instances."""
        allocations = self.compute_allocations()
        for strategy_id, allocated_capital in allocations.items():
            # Update Broker Gateway's tracked strategy balance
            self.gateway.strategy_balances[strategy_id] = allocated_capital

            # Notify registered Strategy Instance
            instance = self.registered_pods.get(strategy_id)
            if instance is not None:
                instance.on_order_update(order_result=None, allocated_capital=allocated_capital)

        return allocations

    def detect_portfolio_correlation(self) -> Dict[str, Any]:
        """Scans active pod positions to detect symbol overlap and portfolio correlation risk."""
        symbol_exposures: Dict[str, Dict[str, float]] = {}
        symbol_totals: Dict[str, float] = {}

        for strategy_id, positions in self.gateway.strategy_positions.items():
            for symbol, qty in positions.items():
                if qty != 0:
                    symbol_exposures.setdefault(symbol, {})[strategy_id] = qty
                    symbol_totals[symbol] = symbol_totals.get(symbol, 0.0) + abs(qty)

        correlated_symbols = {
            symbol: pods for symbol, pods in symbol_exposures.items() if len(pods) > 1
        }

        return {
            "symbol_exposures": symbol_exposures,
            "symbol_totals": symbol_totals,
            "correlated_symbols": correlated_symbols,
            "has_correlation_risk": len(correlated_symbols) > 0,
        }
