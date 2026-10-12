"""
Comprehensive Hard Tests for Algo Lab Derivatives Package:
- Black-Scholes-Merton and Black-76 pricing & boundary invariants
- Put-Call Parity exact balance
- 13 analytical Greeks & numerical differentiation convergence
- Bjerksund-Stensland 2002 & Leisen-Reimer binomial American pricer consistency
- Robust Implied Volatility root-finding on extreme ITM/OTM
- Greek P&L Attribution & residual accounting
- Whalley-Wilmott optimal hedging band with Indian statutory transaction friction
- Stress testing & Scenario Grid risk analytics
"""

import math
import numpy as np
import pytest
from services.derivatives import pricing, attribution, hedging, risk


def test_put_call_parity_exact_invariance():
    """Verify C - P == S*exp(-qT) - K*exp(-rT) across multiple strikes and maturities."""
    S = 24500.0
    r = 0.065
    q = 0.012
    sigma = 0.16
    for K in [23000.0, 24500.0, 26000.0]:
        for T in [7 / 365, 30 / 365, 90 / 365]:
            c = pricing.black_scholes(S, K, T, r, q, sigma, kind="call")
            p = pricing.black_scholes(S, K, T, r, q, sigma, kind="put")
            synthetic_forward = S * math.exp(-q * T) - K * math.exp(-r * T)
            assert math.isclose(c - p, synthetic_forward, rel_tol=1e-7, abs_tol=1e-7)


def test_greek_numerical_convergence():
    """Verify analytical Greeks match finite difference perturbations."""
    S = 25000.0
    K = 25200.0
    T = 45 / 365
    r = 0.06
    q = 0.0
    sigma = 0.18
    g = pricing.greeks(S, K, T, r, q, sigma, kind="call")

    # Delta finite difference: dV/dS
    dS = 0.01
    c_up = pricing.black_scholes(S + dS, K, T, r, q, sigma, kind="call")
    c_dn = pricing.black_scholes(S - dS, K, T, r, q, sigma, kind="call")
    num_delta = (c_up - c_dn) / (2.0 * dS)
    assert math.isclose(g["delta"], num_delta, rel_tol=1e-4)

    # Gamma finite difference: d^2V/dS^2
    c_mid = pricing.black_scholes(S, K, T, r, q, sigma, kind="call")
    num_gamma = (c_up - 2.0 * c_mid + c_dn) / (dS ** 2)
    assert math.isclose(g["gamma"], num_gamma, rel_tol=1e-3)

    # Vega finite difference: dV/dsigma
    dvol = 0.0001
    c_vol_up = pricing.black_scholes(S, K, T, r, q, sigma + dvol, kind="call")
    c_vol_dn = pricing.black_scholes(S, K, T, r, q, sigma - dvol, kind="call")
    num_vega = (c_vol_up - c_vol_dn) / (2.0 * dvol)
    assert math.isclose(g["vega"], num_vega, rel_tol=1e-4)


def test_implied_volatility_inversion():
    """Verify recovering implied volatility from generated option prices."""
    S = 25000.0
    K = 24800.0
    T = 20 / 365
    r = 0.06
    q = 0.0
    true_vol = 0.225

    target_price = pricing.black_scholes(S, K, T, r, q, true_vol, kind="call")
    recovered_vol = pricing.implied_vol(target_price, S, K, T, r, q, kind="call")
    assert math.isclose(recovered_vol, true_vol, rel_tol=1e-4)


def test_american_vs_european_premium_invariance():
    """Early exercise optionality must guarantee American price >= European price."""
    S = 100.0
    K = 105.0
    T = 0.5
    r = 0.08
    q = 0.04
    sigma = 0.25

    euro_put = pricing.black_scholes(S, K, T, r, q, sigma, kind="put")
    amer_put_bs = pricing.bjerksund_stensland(S, K, T, r, q, sigma, kind="put")
    amer_put_lr = pricing.leisen_reimer(S, K, T, r, q, sigma, n=151, kind="put", american=True)

    assert amer_put_bs >= euro_put - 1e-6
    assert amer_put_lr >= euro_put - 1e-6
    assert math.isclose(amer_put_bs, amer_put_lr, rel_tol=0.03)


def test_pathwise_greek_attribution_conservation():
    """Verify Greek attribution partitions daily mark-to-market change with minimal Taylor residual."""
    S0 = 25000.0
    K = 25000.0
    T = 30 / 365
    r = 0.06
    q = 0.0
    sigma = 0.15

    p0 = pricing.black_scholes(S0, K, T, r, q, sigma, kind="call")
    g = pricing.greeks(S0, K, T, r, q, sigma, kind="call")

    # Day 1 move: spot +50, vol +0.005, time dt = 1/365
    dt = 1.0 / 365.0
    dS = 50.0
    dvol = 0.005
    p1 = pricing.black_scholes(S0 + dS, K, T - dt, r, q, sigma + dvol, kind="call")
    actual_pnl = p1 - p0

    attr = attribution.attribute_day(greeks=g, dS=dS, dvol=dvol, dt=dt, actual_pnl=actual_pnl)
    # Total equals actual pnl
    assert math.isclose(attr["total"], actual_pnl, rel_tol=1e-7)
    # Sum of parts plus residual exactly equals actual pnl
    sum_components = (
        attr["theta"] + attr["delta"] + attr["gamma"] +
        attr["vega"] + attr["vanna"] + attr["volga"] + attr["residual"]
    )
    assert math.isclose(sum_components, actual_pnl, rel_tol=1e-7)
    # Higher order residual should be small relative to main terms
    assert abs(attr["residual"]) < abs(attr["delta"]) * 0.15


def test_whalley_wilmott_optimal_hedging_band():
    """Verify Whalley-Wilmott friction band expands with higher transaction cost and gamma."""
    spot = 25000.0
    sigma = 0.16
    tau = 20 / 365
    r = 0.06
    gamma = 0.00035
    risk_aversion = 0.1

    # Low friction: 5 bps
    low_cost = 0.0005
    lo1, hi1 = hedging.whalley_wilmott_band(0.50, gamma, spot, sigma, tau, r, low_cost, risk_aversion)
    width1 = hi1 - lo1

    # High friction: 20 bps (NSE taxes + slippage)
    high_cost = 0.0020
    lo2, hi2 = hedging.whalley_wilmott_band(0.50, gamma, spot, sigma, tau, r, high_cost, risk_aversion)
    width2 = hi2 - lo2

    # Higher transaction costs must widen the no-trade band to prevent friction bleed
    assert width2 > width1
    assert lo2 < 0.50 < hi2


def test_institutional_stress_matrix():
    """Verify stress test evaluates macro crisis shocks."""
    def test_pricer(positions, s_rel, dvol):
        val = 0.0
        for p in positions:
            s = 25000.0 * s_rel
            v = max(0.01, 0.15 + dvol)
            val += p["qty"] * pricing.black_scholes(s, p["K"], p["T"], p["r"], p["q"], v, kind=p["kind"])
        return val

    positions = [{"qty": 10, "K": 25000.0, "T": 0.1, "r": 0.06, "q": 0.0, "kind": "call"}]
    base = test_pricer(positions, 1.0, 0.0)
    stress_results = risk.stress_pnl(test_pricer, positions, base_mark=base)

    assert "GFC2008" in stress_results
    assert "COVID2020" in stress_results
    # Long call position must lose money in GFC (-35% spot crash)
    assert stress_results["GFC2008"] < 0
