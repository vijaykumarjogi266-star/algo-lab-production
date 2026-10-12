"""Risk: portfolio greeks, scenario grids, stress tests, joint spot-vol
Monte-Carlo VaR, Kelly & vol-target sizing, SPAN-lite margin, and
hard/soft pre-trade limits with cooldown-then-re-arm logic (README finding #6).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "portfolio_greeks", "scenario_grid", "STRESS_TESTS", "stress_pnl",
    "monte_carlo_var", "kelly_fraction", "vol_target_size", "size_by_risk",
    "span_lite_margin", "LimitManager",
]


def portfolio_greeks(positions):
    """Aggregate greeks across a list of position dicts.

    Each position dict carries ``qty`` and a ``greeks`` dict (or individual
    greek fields).
    """
    keys = ["delta", "gamma", "theta", "vega", "rho", "vanna", "volga"]
    agg = {k: 0.0 for k in keys}
    for pos in positions:
        qty = pos.get("qty", 0.0)
        g = pos.get("greeks", pos)
        for k in keys:
            agg[k] += qty * float(g.get(k, 0.0))
    return agg


def scenario_grid(pricer, positions, spots, vols):
    """Reprice a book across a spot x vol grid. ``pricer(positions, S, sigma)``
    must return the portfolio mark for a given spot and flat vol shift."""
    out = np.zeros((len(vols), len(spots)))
    for i, sv in enumerate(vols):
        for j, s in enumerate(spots):
            out[i, j] = pricer(positions, s, sv)
    return out


STRESS_TESTS = {
    "GFC2008": dict(dS=-0.35, dvol=0.30),
    "COVID2020": dict(dS=-0.25, dvol=0.25),
    "vol_spike": dict(dS=-0.05, dvol=0.20),
    "rate_shock": dict(dS=0.0, dvol=0.05),
    "gap_down": dict(dS=-0.10, dvol=0.10),
}


def stress_pnl(pricer, positions, base_mark, tests=None):
    """Return P&L under named stress scenarios."""
    tests = tests or STRESS_TESTS
    rows = {}
    for name, spec in tests.items():
        rows[name] = pricer(positions, 1.0 + spec["dS"], spec["dvol"]) - base_mark
    return pd.Series(rows, name="pnl")


def monte_carlo_var(pricer, positions, S0, sigma0, n_sims=20000, horizon=10.0,
                    rho=-0.7, vol_of_vol=0.5, seed=0, alpha=0.99):
    """Joint spot-vol Monte-Carlo VaR for a mark-to-model book.

    Spot follows GBM; vol follows a correlated log-normal increment. Returns
    the (1-alpha) percentile loss (positive number = loss).
    """
    rng = np.random.default_rng(seed)
    z1 = rng.standard_normal(n_sims)
    z2 = rho * z1 + np.sqrt(1.0 - rho ** 2) * rng.standard_normal(n_sims)
    dt = horizon / 252.0
    dS = S0 * (np.exp(0.5 * sigma0 ** 2 * dt + sigma0 * np.sqrt(dt) * z1) - 1.0)
    dvol = sigma0 * vol_of_vol * np.sqrt(dt) * z2
    pnl = np.empty(n_sims)
    for i in range(n_sims):
        pnl[i] = pricer(positions, S0 + dS[i], sigma0 + dvol[i]) - \
                 pricer(positions, S0, sigma0)
    loss = -pnl
    var = float(np.quantile(loss, alpha))
    return {"var": var, "cvar": float(loss[loss >= var].mean()),
            "alpha": alpha, "n_sims": n_sims}


def kelly_fraction(edge, win_prob, loss_frac=1.0, win_frac=1.0):
    """Full Kelly fraction for a binary bet. ``edge`` = expected return per
    unit staked; conservative: return half-Kelly by default via caller."""
    b = win_frac / max(loss_frac, 1e-12)  # net odds
    f = (b * win_prob - (1.0 - win_prob)) / max(b, 1e-12)
    return float(f)


def vol_target_size(portfolio_vol, target_vol, capital):
    """Scale capital deployed so portfolio vol hits the target."""
    if portfolio_vol <= 0:
        return capital
    return float(capital * min(target_vol / portfolio_vol, 1.0))


def size_by_risk(stress_loss_per_unit, capital, max_loss_frac=0.02):
    """Stress-based position sizing: size so a defined stress scenario loses
    no more than ``max_loss_frac`` of capital.  ``stress_loss_per_unit`` is the
    absolute loss of one unit under the stress scenario."""
    budget = capital * max_loss_frac
    if stress_loss_per_unit <= 0:
        return 0.0
    return float(budget / stress_loss_per_unit)


def span_lite_margin(S, K, T, r, q, sigma, premium, kind, lot=1.0,
                     margin_frac=0.03, vol_buffer=0.05):
    """SPAN-lite margin: premium + a fraction of notional adverse move.

    margin = |premium| + max(0, intrinsic_loss_from_adverse_move) + buffer
    This is a deliberately simplified scan-risk stand-in.
    """
    adverse = (S * (sigma + vol_buffer) * np.sqrt(T)) * margin_frac
    return float((abs(premium) + adverse) * lot)


class LimitManager:
    """Hard vs soft pre-trade limits with cooldown-then-re-arm.

    - A *soft* breach reduces allowed size; a *hard* breach halts trading.
    - A drawdown kill-switch arms only after ``cooldown`` days (README #6).
    """

    def __init__(self, hard_max_dd=0.20, soft_max_dd=0.10, cooldown_days=5,
                 max_consecutive_loss_days=7):
        self.hard_max_dd = hard_max_dd
        self.soft_max_dd = soft_max_dd
        self.cooldown_days = cooldown_days
        self.max_consecutive_loss_days = max_consecutive_loss_days
        self.halted = False
        self.reduced = False
        self._dd_days = 0
        self._consec_losses = 0

    def update(self, pnl_today, equity, peak_equity):
        """Feed the day's P&L and equity; returns (halted, reduced).

        Hard breach halts; after ``cooldown_days`` with the drawdown back
        inside the hard limit, the book re-arms at reduced size. A soft breach
        (or a run of down days) only reduces size — it never halts (README #6).
        """
        dd = 1.0 - equity / peak_equity if peak_equity > 0 else 0.0
        if pnl_today < 0:
            self._consec_losses += 1
        else:
            self._consec_losses = 0
        if dd >= self.hard_max_dd:
            self.halted = True
            self._dd_days = 0
        elif self.halted:
            self._dd_days += 1
            if self._dd_days >= self.cooldown_days:
                self.halted = False
                self.reduced = True
                self._dd_days = 0
        if dd >= self.soft_max_dd:
            self.reduced = True
            self._dd_days = 0
        else:
            self._dd_days += 1
            if self._dd_days >= self.cooldown_days and dd < self.soft_max_dd * 0.5:
                self.reduced = False
        if self._consec_losses >= self.max_consecutive_loss_days:
            self.reduced = True
        return self.halted, self.reduced

    def allow_size(self, requested):
        """Clip a requested size when a soft breach is active."""
        if self.halted:
            return 0.0
        return requested * 0.5 if self.reduced else requested
