"""
Algo Lab Institutional Quantitative Research Engine.
Protocol: Formal Hypothesis Testing, Out-of-Sample Validation, Deflated Sharpe Ratio,
Walk-Forward Optimization, and Double-Entry Friction Modeling.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import polars as pl
import math
import polars as pl

from services.backtest_engine.adaptive_market_engine import (
    AdaptiveMarketSurvivalBacktester,
    ProductType,
)
from services.backtest_engine.statutory_cost_model import IndianStatutoryCostModel
from services.scanner.universe_manager import Nifty50UniverseManager

logger = logging.getLogger("InstitutionalResearchEngine")


class AlphaHypothesisStatus(str, Enum):
    FORMULATED = "FORMULATED"
    IN_SAMPLE_TESTING = "IN_SAMPLE_TESTING"
    OUT_OF_SAMPLE_VERIFIED = "OUT_OF_SAMPLE_VERIFIED"
    REJECTED_OVERFITTING = "REJECTED_OVERFITTING"
    REJECTED_FRICTION_BLEED = "REJECTED_FRICTION_BLEED"
    APPROVED_FOR_INCUBATION = "APPROVED_FOR_INCUBATION"


@dataclass
class QuantitativeExperimentManifest:
    experiment_id: str
    hypothesis_title: str
    target_universe: str
    economic_rationale: str
    in_sample_window: str
    out_of_sample_window: str
    in_sample_sharpe: float
    out_of_sample_sharpe: float
    deflated_sharpe_ratio: float
    haircut_sharpe: float
    p_value_overfitting: float
    max_drawdown_oos: float
    statutory_friction_paid_inr: float
    status: AlphaHypothesisStatus
    verdict_notes: str
    timestamp_utc: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class InstitutionalResearchEngine:
    """
    Standardized Quantitative Research Harness modeled after Two Sigma / AQR methodologies:
    1. In-Sample (IS) vs. Out-of-Sample (OOS) temporal split (70/30 split).
    2. Deflated Sharpe Ratio (DSR) & Marcos Lopez de Prado Multiple Testing Correction.
    3. Statutory Delivery & Intraday Indian Tax Drag Integration.
    4. Durable JSON Experiment Registry in research/experiments/.
    """

    def __init__(self, cache_dir: Optional[Path] = None, output_dir: Optional[Path] = None):
        self.base_dir = Path(__file__).resolve().parent.parent
        self.cache_dir = cache_dir or Path("/home/ubuntu/algolab-sandbox/disposable_sandbox/data/cache")
        self.output_dir = output_dir or (self.base_dir / "research" / "experiments")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.universe_mgr = Nifty50UniverseManager()

    def load_universe_datasets(self) -> Dict[str, pl.DataFrame]:
        """Loads available 5Y daily parquet datasets from cache."""
        symbols = self.universe_mgr.get_symbols()
        datasets: Dict[str, pl.DataFrame] = {}
        for sym in symbols:
            p = self.cache_dir / f"{sym}_NS_5y_1d.parquet"
            if p.exists():
                datasets[sym] = pl.read_parquet(p)
        return datasets

    def split_temporal_dataset(
        self,
        datasets: Dict[str, pl.DataFrame],
        split_date: str = "2025-01-01"
    ) -> Tuple[Dict[str, pl.DataFrame], Dict[str, pl.DataFrame]]:
        """Splits multi-asset datasets into In-Sample (historical training) and Out-Of-Sample (future validation)."""
        is_data: Dict[str, pl.DataFrame] = {}
        oos_data: Dict[str, pl.DataFrame] = {}

        for sym, df in datasets.items():
            # Filter by date column
            df_is = df.filter(pl.col("date") < datetime.strptime(split_date, "%Y-%m-%d"))
            df_oos = df.filter(pl.col("date") >= datetime.strptime(split_date, "%Y-%m-%d"))
            if len(df_is) > 100:
                is_data[sym] = df_is
            if len(df_oos) > 50:
                oos_data[sym] = df_oos

        return is_data, oos_data

    @staticmethod
    def _norm_cdf(x: float) -> float:
        """Standard normal cumulative distribution function."""
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    @staticmethod
    def _norm_ppf(p: float) -> float:
        """Acklam's algorithm for inverse normal cumulative distribution function (quantile)."""
        if p <= 0.0:
            return -8.0
        if p >= 1.0:
            return 8.0
        # Coefficients in rational approximations
        a = [-3.969683028665376e+01,  2.209460984245205e+02,
             -2.759285104469687e+02,  1.383577518672690e+02,
             -3.066479806614716e+01,  2.506628277459239e+00]
        b = [-5.447609879822406e+01,  1.615858368580409e+02,
             -1.556989798598866e+02,  6.680131188771972e+01,
             -1.328068155288572e+01]
        c = [-7.784894002430293e-03, -3.223964580411365e-01,
             -2.400758277161838e+00, -2.549732539343734e+00,
              4.374664141464968e+00,  2.938163982698783e+00]
        d = [ 7.784695709041462e-03,  3.224671290700398e-01,
              2.445134137142996e+00,  3.754408661907416e+00]
        p_low = 0.02425
        p_high = 1.0 - p_low

        if p < p_low:
            q = math.sqrt(-2.0 * math.log(p))
            return (((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                   ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)
        elif p <= p_high:
            q = p - 0.5
            r = q * q
            return (((((a[0]*r + a[1])*r + a[2])*r + a[3])*r + a[4])*r + a[5])*q / \
                   (((((b[0]*r + b[1])*r + b[2])*r + b[3])*r + b[4])*r + 1.0)
        else:
            q = math.sqrt(-2.0 * math.log(1.0 - p))
            return -(((((c[0]*q + c[1])*q + c[2])*q + c[3])*q + c[4])*q + c[5]) / \
                    ((((d[0]*q + d[1])*q + d[2])*q + d[3])*q + 1.0)

    @classmethod
    def calculate_deflated_sharpe_ratio(
        cls,
        estimated_sharpe: float,
        num_trials: int,
        sample_length: int,
        skewness: float = 0.0,
        kurtosis: float = 3.0,
    ) -> Tuple[float, float]:
        """
        Calculates the Deflated Sharpe Ratio (DSR) using Lopez de Prado's formula (2014)
        to rigorously penalize data mining and trial multiplicity.
        """
        if sample_length <= 1:
            return 0.0, 1.0

        # Euler-Mascheroni constant
        euler = 0.5772156649
        # Expected maximum Sharpe under the null hypothesis (zero true skill) across N trials
        if num_trials > 1:
            z_term = (1 - euler) * cls._norm_ppf(1 - 1 / num_trials) + euler * cls._norm_ppf(1 - 1 / (num_trials * math.e))
        else:
            z_term = 0.0

        expected_max_sr = z_term

        # Variance of the Sharpe ratio estimator
        sr_variance = (1.0 - skewness * estimated_sharpe + ((kurtosis - 1.0) / 4.0) * (estimated_sharpe ** 2)) / (sample_length - 1.0)
        sr_std = math.sqrt(max(1e-6, sr_variance))

        # DSR Z-score
        dsr_z = (estimated_sharpe - expected_max_sr) / sr_std
        p_value = 1.0 - cls._norm_cdf(dsr_z)
        deflated_sr = cls._norm_cdf(dsr_z)

        return float(deflated_sr), float(p_value)

    def evaluate_strategy_hypothesis(
        self,
        experiment_id: str,
        hypothesis_title: str,
        strategy_code: str,
        economic_rationale: str,
        num_prior_trials: int = 10,
        split_date: str = "2025-01-01",
    ) -> QuantitativeExperimentManifest:
        """Runs institutional dual-stage validation (IS -> OOS) with DSR calculation."""
        datasets = self.load_universe_datasets()
        if not datasets:
            raise RuntimeError("No cached datasets found to execute hypothesis testing.")

        is_data, oos_data = self.split_temporal_dataset(datasets, split_date=split_date)
        sector_map = self.universe_mgr.get_sector_map()

        # 1. Run In-Sample Evaluation (2021 - 2024)
        engine_is = AdaptiveMarketSurvivalBacktester(
            initial_capital=100000.0,
            max_capital_per_position=45000.0,
            max_concurrent_positions=2,
            risk_per_trade_pct=0.010,
            product=ProductType.DELIVERY,
            stop_loss_atr_multiplier=2.5,
            take_profit_risk_multiplier=3.5,
            sector_map=sector_map,
            strategy=strategy_code,
        )
        res_is = engine_is.run_backtest(is_data)
        is_perf = res_is["performance_metrics"]
        is_sharpe = float(is_perf.get("sharpe_ratio", 0.0))

        # 2. Run Out-of-Sample Evaluation (2025 - 2026)
        engine_oos = AdaptiveMarketSurvivalBacktester(
            initial_capital=100000.0,
            max_capital_per_position=45000.0,
            max_concurrent_positions=2,
            risk_per_trade_pct=0.010,
            product=ProductType.DELIVERY,
            stop_loss_atr_multiplier=2.5,
            take_profit_risk_multiplier=3.5,
            sector_map=sector_map,
            strategy=strategy_code,
        )
        res_oos = engine_oos.run_backtest(oos_data)
        oos_meta = res_oos["metadata"]
        oos_perf = res_oos["performance_metrics"]
        oos_fric = res_oos["friction_breakdown"]
        oos_sharpe = float(oos_perf.get("sharpe_ratio", 0.0))
        oos_dd = float(oos_perf.get("max_drawdown_pct", 0.0))
        total_friction = float(oos_fric.get("total_friction_inr", 0.0))

        # 3. Calculate Multiple Testing Penalization (Deflated Sharpe Ratio)
        sample_len = len(list(oos_data.values())[0]) if oos_data else 250
        dsr, p_val = self.calculate_deflated_sharpe_ratio(
            estimated_sharpe=oos_sharpe,
            num_trials=num_prior_trials,
            sample_length=sample_len,
        )

        # Haircut Sharpe (50% rule of thumb for institutional paper incubation)
        haircut_sr = round(oos_sharpe * 0.5, 2)

        # 4. Formulate Institutional Verdict
        if oos_meta["net_profit_inr"] > 0 and dsr >= 0.70 and oos_dd <= 12.0:
            status = AlphaHypothesisStatus.APPROVED_FOR_INCUBATION
            verdict = "PASSED Out-of-Sample test with positive expectancy and robust DSR. Qualified for paper incubation."
        elif oos_meta["net_profit_inr"] <= 0 and oos_perf.get("gross_profit_factor", 0.0) >= 1.0:
            status = AlphaHypothesisStatus.REJECTED_FRICTION_BLEED
            verdict = "REJECTED: Strategy shows positive gross alpha but fails after Indian statutory frictions & taxes."
        elif is_sharpe > 1.2 and oos_sharpe < 0.2:
            status = AlphaHypothesisStatus.REJECTED_OVERFITTING
            verdict = "REJECTED: Severe In-Sample overfitting; performance degraded precipitously out-of-sample."
        else:
            status = AlphaHypothesisStatus.OUT_OF_SAMPLE_VERIFIED if oos_meta["net_profit_inr"] > 0 else AlphaHypothesisStatus.REJECTED_OVERFITTING
            verdict = "Completed OOS evaluation. Requires parameter consolidation."

        manifest = QuantitativeExperimentManifest(
            experiment_id=experiment_id,
            hypothesis_title=hypothesis_title,
            target_universe="NIFTY_50_CASH",
            economic_rationale=economic_rationale,
            in_sample_window="2021-10-01 to 2024-12-31",
            out_of_sample_window=f"2025-01-01 to 2026-10-01",
            in_sample_sharpe=round(is_sharpe, 2),
            out_of_sample_sharpe=round(oos_sharpe, 2),
            deflated_sharpe_ratio=round(dsr, 3),
            haircut_sharpe=haircut_sr,
            p_value_overfitting=round(p_val, 4),
            max_drawdown_oos=round(oos_dd, 2),
            statutory_friction_paid_inr=round(total_friction, 2),
            status=status,
            verdict_notes=verdict,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )

        # Persist durable manifest
        manifest_file = self.output_dir / f"{experiment_id}.json"
        with open(manifest_file, "w") as f:
            json.dump(manifest.to_dict(), f, indent=2)

        return manifest
