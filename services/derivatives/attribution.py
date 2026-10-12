"""Daily P&L attribution by greek.

Given a book's greeks and the day's market moves, decompose the mark change
into theta, delta, gamma, vega, vanna, volga and an unexplained residual:
    dV ~ theta*dt + delta*dS + 0.5*gamma*dS^2 + vega*dvol
          + vanna*dS*dvol + 0.5*volga*dvol^2 + residual
The residual is computed against the *actual* re-priced mark, so it captures
higher-order and cross terms honestly.
"""

from __future__ import annotations

import numpy as np

__all__ = ["attribute_day", "attribute_path"]


def attribute_day(greeks, dS, dvol, dt, actual_pnl):
    """Attribute one day's P&L. ``greeks`` is a dict; returns a dict."""
    g = {k: float(greeks.get(k, 0.0)) for k in
         ["theta", "delta", "gamma", "vega", "vanna", "volga"]}
    parts = {
        "theta": g["theta"] * dt,
        "delta": g["delta"] * dS,
        "gamma": 0.5 * g["gamma"] * dS ** 2,
        "vega": g["vega"] * dvol,
        "vanna": g["vanna"] * dS * dvol,
        "volga": 0.5 * g["volga"] * dvol ** 2,
    }
    explained = sum(parts.values())
    parts["residual"] = float(actual_pnl) - explained
    parts["total"] = float(actual_pnl)
    return parts


def attribute_path(return_df):
    """Attribution over a whole backtest log.

    ``return_df`` columns: theta, delta, gamma, vega, vanna, volga, dS, dvol,
    dt, actual_pnl (all in local units). Returns a dict of summed columns.
    """
    df = return_df
    g = {k: df[k].to_numpy() for k in
         ["theta", "delta", "gamma", "vega", "vanna", "volga"]}
    dS = df["dS"].to_numpy()
    dvol = df["dvol"].to_numpy()
    dt = df["dt"].to_numpy()
    total = df["actual_pnl"].to_numpy()
    parts = {
        "theta": float((g["theta"] * dt).sum()),
        "delta": float((g["delta"] * dS).sum()),
        "gamma": float((0.5 * g["gamma"] * dS ** 2).sum()),
        "vega": float((g["vega"] * dvol).sum()),
        "vanna": float((g["vanna"] * dS * dvol).sum()),
        "volga": float((0.5 * g["volga"] * dvol ** 2).sum()),
    }
    explained = sum(parts.values())
    parts["residual"] = float(total.sum()) - explained
    parts["total"] = float(total.sum())
    return parts
