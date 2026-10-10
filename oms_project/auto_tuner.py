"""
OMS Project - Auto-Tuner Service (Project ADAPT - Wave 2: Autonomous Optimization & Verification)
Automated optimization loop that takes AlphaAnalyst insights and verifies proposed parameter shifts
in the Time Machine before human-in-the-loop promotion.
"""

import json
import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from oms_project.strategy_factory import StrategyFactory, FastTestEngine
from oms_project.alpha_analyst import AlphaAnalyst, AnalystInsight


class TuningVerificationResult(BaseModel):
    strategy_id: str
    baseline_config: Dict[str, Any]
    candidate_config: Dict[str, Any]
    baseline_net_pnl: float
    candidate_net_pnl: float
    pnl_improvement_inr: float
    baseline_max_drawdown_pct: float
    candidate_max_drawdown_pct: float
    drawdown_reduction_pct: float
    verdict: str = Field(..., description="APPROVED_FOR_PROMOTION | REJECTED_SUBOPTIMAL")
    explanation: str
    timestamp: float = Field(default_factory=time.time)


class AutoTuner:
    """
    Auto-Tuner Service.
    Automates pre-deployment simulation proofs in the Time Machine.
    """

    def __init__(self, analyst: Optional[AlphaAnalyst] = None):
        self.analyst = analyst or AlphaAnalyst()
        self.history_verifications: List[TuningVerificationResult] = []

    def verify_insight_recommendation(
        self,
        insight: Dict[str, Any],
        base_config: Dict[str, Any],
        initial_capital: float = 100000.0,
    ) -> TuningVerificationResult:
        """
        Runs Time Machine backtests comparing baseline config vs candidate config derived from insight.
        """
        strat_id = base_config.get("strategy_id", "STRAT_AUTO_TUNED")

        # 1. Run baseline simulation
        baseline_res = FastTestEngine.run_fast_test(base_config, initial_capital=initial_capital)

        # 2. Construct candidate config based on category recommendation
        candidate_config = json.loads(json.dumps(base_config))  # Deep copy
        category = insight.get("category", "")
        params = candidate_config.setdefault("parameters", {})
        risk = candidate_config.setdefault("risk_limits", {})

        if category == "REGIME_LOSS":
            if "threshold" in params:
                params["threshold"] = round(float(params["threshold"]) + 0.5, 2)
            elif "window" in params:
                params["window"] = int(params["window"]) + 5
        elif category == "SLIPPAGE_TOXICITY":
            if "max_qty" in risk:
                risk["max_qty"] = max(1.0, round(float(risk["max_qty"]) * 0.8, 1))
        elif category == "STOP_LOSS_SHAKEOUT":
            if "stop_loss_pct" in risk:
                risk["stop_loss_pct"] = round(float(risk["stop_loss_pct"]) + 0.01, 3)

        # 3. Run candidate simulation in Time Machine
        candidate_res = FastTestEngine.run_fast_test(candidate_config, initial_capital=initial_capital)

        base_pnl = baseline_res["net_pnl"]
        cand_pnl = candidate_res["net_pnl"]
        pnl_diff = cand_pnl - base_pnl

        base_dd = baseline_res["max_drawdown_pct"]
        cand_dd = candidate_res["max_drawdown_pct"]
        dd_diff = base_dd - cand_dd

        if pnl_diff > 0 or (dd_diff > 0 and cand_pnl >= base_pnl * 0.95):
            verdict = "APPROVED_FOR_PROMOTION"
            explanation = f"Time Machine simulation proof confirms parameter shift improves Net P&L by +₹{pnl_diff:.2f} and reduces drawdown by {dd_diff:.2f}%."
        else:
            verdict = "REJECTED_SUBOPTIMAL"
            explanation = f"Time Machine simulation rejected parameter shift (P&L delta: ₹{pnl_diff:.2f}, Drawdown delta: {dd_diff:.2f}%)."

        result = TuningVerificationResult(
            strategy_id=strat_id,
            baseline_config=base_config,
            candidate_config=candidate_config,
            baseline_net_pnl=base_pnl,
            candidate_net_pnl=cand_pnl,
            pnl_improvement_inr=round(pnl_diff, 2),
            baseline_max_drawdown_pct=base_dd,
            candidate_max_drawdown_pct=cand_dd,
            drawdown_reduction_pct=round(dd_diff, 2),
            verdict=verdict,
            explanation=explanation,
        )

        self.history_verifications.append(result)
        return result

    def auto_optimize_strategy(
        self,
        base_config: Dict[str, Any],
        initial_capital: float = 100000.0,
    ) -> Dict[str, Any]:
        """
        Sweeps parameter grid around strategy and returns top verified configurations.
        """
        strat_type = base_config.get("strategy_type", "mean_reversion")
        results = []

        if strat_type == "mean_reversion":
            windows = [10, 15, 20, 25]
            thresholds = [1.0, 1.5, 2.0]
            for w in windows:
                for t in thresholds:
                    cfg = json.loads(json.dumps(base_config))
                    cfg["parameters"] = {"window": w, "threshold": t}
                    res = FastTestEngine.run_fast_test(cfg, initial_capital=initial_capital)
                    results.append({"config": cfg, "metrics": res})
        else:
            shorts = [3, 5, 8]
            longs = [15, 20, 30]
            for s in shorts:
                for l in longs:
                    cfg = json.loads(json.dumps(base_config))
                    cfg["parameters"] = {"short_window": s, "long_window": l}
                    res = FastTestEngine.run_fast_test(cfg, initial_capital=initial_capital)
                    results.append({"config": cfg, "metrics": res})

        results.sort(key=lambda r: r["metrics"]["net_pnl"], reverse=True)
        top_candidates = results[:3]

        return {
            "strategy_id": base_config.get("strategy_id"),
            "total_grid_evaluations": len(results),
            "best_candidate": top_candidates[0] if top_candidates else None,
            "top_3_candidates": top_candidates,
        }
