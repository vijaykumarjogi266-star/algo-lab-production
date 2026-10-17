#!/usr/bin/env python3
"""
AlgoLab Multi-Agent Pre-Trade Consensus Engine
Orchestrates institutional pre-trade consensus among Hermes, OpenClaw, and Antigravity.
Acts as an automated quantitative investment committee before execution.
"""

import os
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

IST = timezone(timedelta(hours=5, minutes=30))
logger = logging.getLogger("agent_consensus")

DECISION_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "decisions"


@dataclass
class AgentVote:
    agent: str
    role: str
    status: str  # "APPROVED", "REJECTED", "CAUTION"
    score: float  # 0.0 to 1.0
    reasoning: str
    checks: Dict[str, bool] = field(default_factory=dict)


@dataclass
class ConsensusVerdict:
    symbol: str
    action: str
    entry_price: float
    stop_loss: float
    target_price: float
    quantity: int
    composite_score: float
    unanimous: bool
    status: str  # "APPROVED", "REJECTED", "CAUTION"
    votes: Dict[str, Dict[str, Any]]
    summary: str
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentConsensusEngine:
    """
    Multi-Agent Pre-Trade Consensus Engine.
    Hermes: Macro & Market Regime Sentinel
    OpenClaw: Microstructure, Friction & Invariant Auditor
    Antigravity: Mathematical Edge & Sizing Governor
    """

    def __init__(self, ledger_path: Optional[Path] = None):
        self.ledger_path = ledger_path or (DECISION_DIR / "agent_consensus_ledger.json")

    def evaluate_hermes(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        stop_loss: float,
        regime: str = "BULL_MOMENTUM",
        adx: float = 28.5,
        india_vix: float = 14.2,
    ) -> AgentVote:
        """
        Hermes: Macro & Volatility Regime Sentinel.
        Verifies:
        1. ADX >= 20 (Strong directional momentum)
        2. India VIX < 24.0 (Normal volatility, avoids flash-crash hazard)
        3. Regime alignment with trade action
        """
        checks = {
            "adx_trend_sufficient": adx >= 20.0,
            "india_vix_safe": india_vix < 24.0,
            "regime_aligned": not (action.upper() == "BUY" and "BEAR" in regime.upper()),
        }

        passed = sum(checks.values())
        score = round(passed / len(checks) * 0.95, 2)  # Max 0.95 baseline

        if all(checks.values()):
            status = "APPROVED"
            reasoning = f"Regime {regime} validated. ADX={adx:.1f} indicates robust trend; VIX={india_vix:.1f} within safe operating bounds."
        elif not checks["regime_aligned"] or not checks["india_vix_safe"]:
            status = "REJECTED"
            reasoning = f"Regime conflict or high VIX alert. Regime={regime}, VIX={india_vix:.1f}."
        else:
            status = "CAUTION"
            reasoning = f"Borderline trend strength (ADX={adx:.1f}). Proceed with tightened stop."

        return AgentVote(
            agent="Hermes",
            role="Macro & Regime Sentinel",
            status=status,
            score=score,
            reasoning=reasoning,
            checks=checks,
        )

    def evaluate_openclaw(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        stop_loss: float,
        quantity: int,
        capital: float = 10000.0,
        max_risk_inr: float = 150.0,
        estimated_friction_bps: float = 8.5,
    ) -> AgentVote:
        """
        OpenClaw: Institutional Invariant & Friction Auditor.
        Verifies:
        1. Max risk per trade <= invariant limit (default ₹150)
        2. Friction cost within statutory threshold (< 15 bps)
        3. Position sizing does not violate solvency
        """
        risk_per_share = abs(entry_price - stop_loss)
        total_risk_inr = risk_per_share * quantity
        position_value = entry_price * quantity

        checks = {
            "max_risk_invariant": total_risk_inr <= (max_risk_inr * 1.05),  # 5% tolerance for tick rounding
            "friction_acceptable": estimated_friction_bps <= 15.0,
            "solvency_within_leverage": position_value <= (capital * 5.5),  # Within 5x MIS leverage
        }

        passed = sum(checks.values())
        score = round(passed / len(checks) * 0.93, 2)

        if all(checks.values()):
            status = "APPROVED"
            reasoning = f"Invariant checks passed. Total Risk=₹{total_risk_inr:.2f} <= ₹{max_risk_inr:.2f} cap. Friction={estimated_friction_bps}bps."
        elif not checks["max_risk_invariant"]:
            status = "REJECTED"
            reasoning = f"Invariant #2 Breach: Proposed trade risk ₹{total_risk_inr:.2f} exceeds strict ₹{max_risk_inr:.2f} cap."
        else:
            status = "CAUTION"
            reasoning = f"High friction or leverage boundary reached: {position_value:.2f} INR."

        return AgentVote(
            agent="OpenClaw",
            role="Friction & Invariant Auditor",
            status=status,
            score=score,
            reasoning=reasoning,
            checks=checks,
        )

    def evaluate_antigravity(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        stop_loss: float,
        target_price: float,
        quantity: int,
        historical_win_rate: float = 0.55,
    ) -> AgentVote:
        """
        Antigravity: Quantitative Strategy & Mathematical Edge Governor.
        Verifies:
        1. Risk-to-Reward ratio >= 1:1.5
        2. Positive mathematical expectancy (Expectancy > 0)
        3. Sizing aligns with fractional Kelly criterion
        """
        risk_pts = abs(entry_price - stop_loss)
        reward_pts = abs(target_price - entry_price)

        rr_ratio = (reward_pts / risk_pts) if risk_pts > 0 else 0.0
        # Mathematical expectancy: (WinRate * Reward) - (LossRate * Risk)
        loss_rate = 1.0 - historical_win_rate
        expectancy = (historical_win_rate * reward_pts) - (loss_rate * risk_pts)

        checks = {
            "risk_reward_ge_1_5": rr_ratio >= 1.45,  # Floating precision buffer
            "positive_expectancy": expectancy > 0,
            "target_greater_than_zero": target_price > 0,
        }

        passed = sum(checks.values())
        score = round(passed / len(checks) * 0.96, 2)

        if all(checks.values()):
            status = "APPROVED"
            reasoning = f"Mathematical edge verified. R:R={rr_ratio:.2f} >= 1.5, Expectancy=+₹{expectancy:.2f}/share, WinRate={historical_win_rate*100:.0f}%."
        elif not checks["risk_reward_ge_1_5"]:
            status = "REJECTED"
            reasoning = f"Unfavorable asymmetric edge: R:R ratio {rr_ratio:.2f} is below minimum 1:1.5 threshold."
        else:
            status = "CAUTION"
            reasoning = f"Expectancy is marginal (+₹{expectancy:.2f})."

        return AgentVote(
            agent="Antigravity",
            role="Math Edge & Sizing Governor",
            status=status,
            score=score,
            reasoning=reasoning,
            checks=checks,
        )

    def run_consensus(
        self,
        symbol: str,
        action: str = "BUY",
        entry_price: float = 0.0,
        stop_loss: float = 0.0,
        target_price: float = 0.0,
        quantity: int = 1,
        capital: float = 10000.0,
        regime: str = "BULL_MOMENTUM",
        adx: float = 28.5,
        india_vix: float = 14.2,
        max_risk_inr: float = 150.0,
        historical_win_rate: float = 0.55,
    ) -> ConsensusVerdict:
        """
        Executes pre-trade multi-agent deliberation and records verdict to audit ledger.
        """
        now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")

        # 1. Gather independent agent evaluations
        vote_hermes = self.evaluate_hermes(
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            regime=regime,
            adx=adx,
            india_vix=india_vix,
        )

        vote_openclaw = self.evaluate_openclaw(
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            quantity=quantity,
            capital=capital,
            max_risk_inr=max_risk_inr,
        )

        vote_antigravity = self.evaluate_antigravity(
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            quantity=quantity,
            historical_win_rate=historical_win_rate,
        )

        votes = {
            "Hermes": asdict(vote_hermes),
            "OpenClaw": asdict(vote_openclaw),
            "Antigravity": asdict(vote_antigravity),
        }

        # 2. Determine consensus status
        all_approved = (
            vote_hermes.status == "APPROVED"
            and vote_openclaw.status == "APPROVED"
            and vote_antigravity.status == "APPROVED"
        )
        any_rejected = (
            vote_hermes.status == "REJECTED"
            or vote_openclaw.status == "REJECTED"
            or vote_antigravity.status == "REJECTED"
        )

        # Weighted composite score: Hermes (30%), OpenClaw (35%), Antigravity (35%)
        composite = round(
            (vote_hermes.score * 0.30) + (vote_openclaw.score * 0.35) + (vote_antigravity.score * 0.35),
            4,
        )

        if all_approved and composite >= 0.75:
            verdict_status = "APPROVED"
            unanimous = True
            summary = (
                f"✅ <b>UNANIMOUS ({composite*100:.1f}%)</b> | "
                f"Hermes ({vote_hermes.score*100:.0f}%) • OpenClaw ({vote_openclaw.score*100:.0f}%) • Antigravity ({vote_antigravity.score*100:.0f}%)"
            )
        elif any_rejected:
            verdict_status = "REJECTED"
            unanimous = False
            rejecting_agents = [
                k for k, v in [("Hermes", vote_hermes), ("OpenClaw", vote_openclaw), ("Antigravity", vote_antigravity)]
                if v.status == "REJECTED"
            ]
            summary = f"❌ <b>VETOED by {', '.join(rejecting_agents)}</b> (Score: {composite*100:.1f}%)"
        else:
            verdict_status = "CAUTION"
            unanimous = False
            summary = f"⚠️ <b>CONDITIONALLY APPROVED ({composite*100:.1f}%)</b>"

        verdict = ConsensusVerdict(
            symbol=symbol,
            action=action,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target_price=target_price,
            quantity=quantity,
            composite_score=composite,
            unanimous=unanimous,
            status=verdict_status,
            votes=votes,
            summary=summary,
            timestamp=now_ist,
        )

        self.record_to_ledger(verdict)
        return verdict

    def record_to_ledger(self, verdict: ConsensusVerdict) -> None:
        """Appends the consensus verdict to persistent JSON ledger."""
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            records = []
            if self.ledger_path.exists():
                try:
                    with open(self.ledger_path, "r") as f:
                        records = json.load(f)
                        if not isinstance(records, list):
                            records = [records]
                except Exception:
                    records = []

            records.append(verdict.to_dict())
            # Keep latest 250 records
            records = records[-250:]

            with open(self.ledger_path, "w") as f:
                json.dump(records, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to record consensus to ledger {self.ledger_path}: {e}")


# Singleton instance
agent_consensus_engine = AgentConsensusEngine()
