"""Hedging: delta-hedging schedules (fixed / band / gamma-scaled /
Whalley-Wilmott / Zakamouline), hedge-to-band-edge, path-wise P&L
decomposition, and a multi-greek hedge-basket solver.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "fixed_schedule", "band_hedge", "gamma_scaled_band", "whalley_wilmott_band",
    "zakamouline_band", "hedge_to_band_edge", "pnl_decomposition",
    "hedge_basket_solve",
]


def fixed_schedule(delta_target, n_steps):
    """Deterministic rebalancing times (fractions of the horizon)."""
    return np.linspace(0.0, 1.0, n_steps + 1)


def band_hedge(delta_now, delta_model, band):
    """Trade only when |delta_now - delta_model| > band."""
    diff = delta_now - delta_model
    if abs(diff) > band:
        return diff  # trade amount to restore model delta
    return 0.0


def gamma_scaled_band(base_band, gamma, spot, notional):
    """Widen the band when gamma is small relative to the position."""
    scale = 1.0 / max(abs(gamma) * spot * notional, 1e-9)
    return base_band * min(max(scale, 1.0), 5.0)


def whalley_wilmott_band(delta, gamma, spot, sigma, tau, r, lambda_, risk_aversion):
    """Whalley-Wilmott no-transaction region around the BSM delta.

    Returns (delta_low, delta_high).  ``lambda_`` = proportional tx cost,
    ``risk_aversion`` = risk aversion coefficient (utility).
    """
    half_width = ((3.0 / 2.0) * np.exp(-r * tau) * gamma ** 2
                  * lambda_ * spot / risk_aversion) ** (1.0 / 3.0)
    return delta - half_width, delta + half_width


def zakamouline_band(delta, gamma, spot, sigma, tau, r, lambda_, risk_aversion,
                     K=5.0):
    """Zakamouline-style band (simplified): WW band with a kink near the BSM
    delta and cost-adjusted trade-to points."""
    lo, hi = whalley_wilmott_band(delta, gamma, spot, sigma, tau, r,
                                  lambda_, risk_aversion)
    kink = K * lambda_ * abs(gamma)
    return lo - kink, delta, hi + kink, delta


def hedge_to_band_edge(delta_now, delta_model, band):
    """When the band is breached, trade only to the nearest band edge instead
    of fully back to the model delta (cost-optimal)."""
    diff = delta_now - delta_model
    if abs(diff) <= band:
        return 0.0
    if diff > 0:
        return diff - band  # sell down to upper edge
    return diff + band      # buy up to lower edge


def pnl_decomposition(path, dt, hedges, option_theta_path, gamma_path,
                      sigma_imp_path, sigma_real_path):
    """Path-wise P&L decomposition.

    Gamma P&L ≈ sum_t 0.5*Gamma*S^2*(sigma_real^2 - sigma_imp^2)*dt,
    plus theta carry, hedge slippage (tracking error), and residual.
    """
    S = np.asarray(path)
    dS = np.diff(S)
    # all derivative paths are length n-1, aligned with dS / S[:-1]
    gamma_pnl = 0.5 * np.sum(gamma_path * S[:-1] ** 2
                             * (sigma_real_path ** 2 - sigma_imp_path ** 2) * dt)
    theta_pnl = np.sum(option_theta_path * dt)
    hedge_pnl = -np.sum(hedges * dS)
    total = gamma_pnl + theta_pnl + hedge_pnl
    return {"gamma_pnl": float(gamma_pnl), "theta_pnl": float(theta_pnl),
            "hedge_pnl": float(hedge_pnl), "total": float(total)}


def hedge_basket_solve(target_greeks, hedge_instruments):
    """Solve trade quantities in ``hedge_instruments`` to neutralize
    ``target_greeks`` (least squares; instruments carry per-unit greek
    vectors)."""
    names = list(target_greeks)
    A = np.array([[inst["greeks"][g] for inst in hedge_instruments]
                  for g in names])
    b = -np.array([target_greeks[g] for g in names], dtype=float)
    q, *_ = np.linalg.lstsq(A, b, rcond=None)
    residual = A @ q - b
    return dict(zip([inst["name"] for inst in hedge_instruments], q)), residual
