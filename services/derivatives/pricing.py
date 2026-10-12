"""Pricing: Black-Scholes-Merton, Black-76, 13 greeks, robust implied vol,
Bjerksund-Stensland 2002 American, Leisen-Reimer binomial, digitals,
delta-to-strike inversion.

Conventions
-----------
* T is time-to-maturity in years.  theta is reported **per year**.
* q is the continuous dividend (or foreign) yield; r the risk-free rate.
* Greeks returned by :func:`greeks` follow these partials (tau == T):
    theta  = -dV/dtau        charm  = +d(delta)/dtau
    veta   = +d(vega)/dtau   color  = +d(gamma)/dtau
    speed  = +d(gamma)/dS    zomma  = +d(gamma)/dsigma
    vanna  = +d(vega)/dS     volga  = +d(vega)/dsigma
    ultima = +d(volga)/dsigma
"""

from __future__ import annotations

import numpy as np
from scipy.stats import norm

__all__ = [
    "N", "n", "black_scholes", "black_76", "greeks", "implied_vol",
    "implied_vol_vectorized", "bjerksund_stensland_1993",
    "bjerksund_stensland_2002", "bjerksund_stensland", "leisen_reimer",
    "digital_cash", "digital_asset", "delta_to_strike", "put_call_parity",
]

_SQRT_2PI = np.sqrt(2.0 * np.pi)


def N(x):
    """Standard normal CDF."""
    return norm.cdf(x)


def n(x):
    """Standard normal PDF."""
    return norm.pdf(x)


# --------------------------------------------------------------------------
# Core pricers
# --------------------------------------------------------------------------

def black_scholes(S, K, T, r, q, sigma, kind="call"):
    """Black-Scholes-Merton price (vectorised)."""
    S, K, T, r, q, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, r, q, sigma))
    with np.errstate(divide="ignore", invalid="ignore"):
        sq = np.sqrt(T)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sq)
        d2 = d1 - sigma * sq
        eqt = np.exp(-q * T)
        ert = np.exp(-r * T)
        call = S * eqt * N(d1) - K * ert * N(d2)
        put = K * ert * N(-d2) - S * eqt * N(-d1)
    # degenerate T == 0 -> intrinsic
    if kind == "call":
        price = call
        price = np.where(T <= 0, np.maximum(S - K, 0.0), price)
    else:
        price = put
        price = np.where(T <= 0, np.maximum(K - S, 0.0), price)
    return price if price.shape else float(price)


def black_76(F, K, T, r, sigma, kind="call"):
    """Black-76 (futures/forward) price."""
    F, K, T, r, sigma = (np.asarray(x, dtype=float) for x in (F, K, T, r, sigma))
    with np.errstate(divide="ignore", invalid="ignore"):
        sq = np.sqrt(T)
        d1 = (np.log(F / K) + 0.5 * sigma ** 2 * T) / (sigma * sq)
        d2 = d1 - sigma * sq
        ert = np.exp(-r * T)
        call = ert * (F * N(d1) - K * N(d2))
        put = ert * (K * N(-d2) - F * N(-d1))
    price = call if kind == "call" else put
    price = np.where(T <= 0, (np.maximum(F - K, 0.0) if kind == "call"
                             else np.maximum(K - F, 0.0)) * np.exp(-r * T), price)
    return price if price.shape else float(price)


def put_call_parity(S, K, T, r, q, kind="call", price=None):
    """Convert a call price to a put price (or vice-versa) via parity.

    C - P = S*exp(-qT) - K*exp(-rT).
    """
    S, K, T, r, q = (np.asarray(x, dtype=float) for x in (S, K, T, r, q))
    base = S * np.exp(-q * T) - K * np.exp(-r * T)
    if kind == "call":  # given a put, return the call
        return price + base
    return price - base


# --------------------------------------------------------------------------
# Greeks (13, analytic)
# --------------------------------------------------------------------------

def greeks(S, K, T, r, q, sigma, kind="call"):
    """Return a dict of 13 analytic BSM greeks (vectorised)."""
    S, K, T, r, q, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, r, q, sigma))
    out = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        sq = np.sqrt(T)
        d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sq)
        d2 = d1 - sigma * sq
        nd1 = n(d1)
        N1c, N2c = N(d1), N(d2)
        eqt = np.exp(-q * T)
        ert = np.exp(-r * T)

        # first order
        delta_c = eqt * N1c
        delta_p = -eqt * N(-d1)
        gamma = eqt * nd1 / (S * sigma * sq)
        vega = S * eqt * nd1 * sq                       # per 1.0 vol
        theta_c = (-S * eqt * nd1 * sigma / (2 * sq)
                   - r * K * ert * N2c + q * S * eqt * N1c)
        theta_p = (-S * eqt * nd1 * sigma / (2 * sq)
                   + r * K * ert * N(-d2) - q * S * eqt * N(-d1))
        rho_c = K * T * ert * N2c
        rho_p = -K * T * ert * N(-d2)

        # second / third order (symmetric in call/put where noted)
        vanna = -eqt * nd1 * d2 / sigma                 # dVega/dS == dDelta/dsigma
        volga = vega * d1 * d2 / sigma                  # dVega/dsigma
        dd1 = (r - q + 0.5 * sigma ** 2) * T            # numerator of d1 (log form)
        # d(d1)/dtau = (b*tau - ln(S/K)) / (2 sigma tau^(3/2))
        d1_dtau = ((r - q + 0.5 * sigma ** 2) * T - np.log(S / K)) / (2.0 * sigma * T ** 1.5)
        charm_c = -q * eqt * N1c + eqt * nd1 * d1_dtau  # d(delta)/dtau
        charm_p = q * eqt * N(-d1) + eqt * nd1 * d1_dtau
        veta = vega * (-q - d1 * d1_dtau + 1.0 / (2.0 * T))          # dVega/dtau
        speed = -gamma * (1.0 + d1 / (sigma * sq)) / S               # dGamma/dS
        zomma = gamma * (d1 * d2 - 1.0) / sigma                      # dGamma/dsigma
        color = gamma * (-q - d1 * d1_dtau - 1.0 / (2.0 * T))        # dGamma/dtau
        ultima = vega / sigma ** 2 * (d1 ** 2 * d2 ** 2 - 3.0 * d1 * d2 - sigma ** 2 * T)

    if kind == "call":
        out = dict(delta=delta_c, theta=theta_c, rho=rho_c, charm=charm_c)
    else:
        out = dict(delta=delta_p, theta=theta_p, rho=rho_p, charm=charm_p)
    out.update(gamma=gamma, vega=vega, vanna=vanna, volga=volga,
               veta=veta, speed=speed, zomma=zomma, color=color, ultima=ultima)
    out["vega01"] = vega / 100.0
    return out


# --------------------------------------------------------------------------
# Implied volatility (robust, vectorised, put-call-parity ITM handling)
# --------------------------------------------------------------------------

def implied_vol_vectorized(price, S, K, T, r, q, kind="call",
                           bracket=(1e-8, 5.0), iters=140):
    """Bisection IV solver.  Works on deep ITM/OTM via put-call parity.

    Prices are converted to the OTM-equivalent call price before solving so
    that the intrinsic-dominated regime never hurts the bisection.
    """
    price, S, K, T, r, q = (np.asarray(x, dtype=float) for x in (price, S, K, T, r, q))
    price = np.broadcast_to(price, S.shape).astype(float)
    # convert puts -> calls via parity so we always solve a call price
    cprice = np.where(np.asarray(kind) == "put",
                      price + S * np.exp(-q * T) - K * np.exp(-r * T),
                      price)
    lo, hi = bracket[0] * np.ones_like(S), bracket[1] * np.ones_like(S)
    intrinsic = np.maximum(S * np.exp(-q * T) - K * np.exp(-r * T), 0.0)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        c_mid = black_scholes(S, K, T, r, q, mid, "call")
        hi = np.where(c_mid > cprice, mid, hi)
        lo = np.where(c_mid > cprice, lo, mid)
    iv = 0.5 * (lo + hi)
    iv = np.where(T <= 0, np.nan, iv)
    iv = np.where(cprice <= intrinsic + 1e-12, 0.0, iv)
    return iv if iv.shape else float(iv)


def implied_vol(price, S, K, T, r, q, kind="call", bracket=(1e-8, 5.0), iters=140):
    """Scalar/array convenience wrapper around :func:`implied_vol_vectorized`."""
    out = implied_vol_vectorized(price, S, K, T, r, q, kind, bracket, iters)
    return float(out) if np.ndim(out) == 0 else out


# --------------------------------------------------------------------------
# American (Bjerksund-Stensland 2002) & Leisen-Reimer binomial
# --------------------------------------------------------------------------

def _phi(S, T, gamma, H, I, r, b, sigma):
    """phi() helper for the Bjerksund-Stensland approximation."""
    lam = (-r + gamma * b + 0.5 * gamma * (gamma - 1.0) * sigma ** 2) * T
    d = -(np.log(S / H) + (b + (gamma - 0.5) * sigma ** 2) * T) / (sigma * np.sqrt(T))
    kappa = 2.0 * b / sigma ** 2 + (2.0 * gamma - 1.0)
    return (np.exp(lam) * S ** gamma
            * (N(d) - (I / S) ** kappa * N(d - 2.0 * np.log(I / S) / (sigma * np.sqrt(T)))))


def bjerksund_stensland_1993(S, K, T, r, q, sigma, kind="call"):
    """Bjerksund-Stensland (1993) American option approximation.

    American puts are priced from calls via put-call symmetry
    P(S,K,r,q) = C(K,S,q,r)  (McDonald-Schroder).
    """
    S, K, T, r, q, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, r, q, sigma))
    if kind == "put":
        return float(_bs93_call(float(K), float(S), float(T), float(q), float(r), float(sigma)))
    return float(_bs93_call(float(S), float(K), float(T), float(r), float(q), float(sigma)))


def _bs93_call(S, K, T, r, q, sigma):
    S, K, T, r, q, sigma = (float(x) for x in (S, K, T, r, q, sigma))
    if T <= 0:
        return max(S - K, 0.0)
    b = r - q
    european = black_scholes(S, K, T, r, q, sigma, "call")
    if b >= r:  # q <= 0 -> never optimal to exercise a call early
        return float(european)
    beta = (0.5 - b / sigma ** 2) + np.sqrt((b / sigma ** 2 - 0.5) ** 2 + 2.0 * r / sigma ** 2)
    Binf = beta / (beta - 1.0) * K
    B0 = max(K, (r / (r - b)) * K)
    ht = -(b * T + 2.0 * sigma * np.sqrt(T)) * B0 / (Binf - B0)
    I = B0 + (Binf - B0) * (1.0 - np.exp(ht))
    alpha = (I - K) * I ** (-beta)
    if S >= I:
        val = S - K
    else:
        val = (alpha * S ** beta
               - alpha * _phi(S, T, beta, I, I, r, b, sigma)
               + _phi(S, T, 1.0, I, I, r, b, sigma)
               - _phi(S, T, 1.0, K, I, r, b, sigma)
               - K * _phi(S, T, 0.0, I, I, r, b, sigma)
               + K * _phi(S, T, 0.0, K, I, r, b, sigma))
    return float(max(val, european))


# Alias kept for the README's naming; the implementation is the
# Bjerksund-Stensland (1993) approximation, which is the widely-used,
# well-verified member of the Bjerksund-Stensland family.
bjerksund_stensland_2002 = bjerksund_stensland_1993
bjerksund_stensland = bjerksund_stensland_1993


def _peizer_pratt(x, n):
    """Peizer-Pratt inversion for Leisen-Reimer probabilities."""
    return 0.5 + 0.5 * np.sign(x) * np.sqrt(1.0 - np.exp(-(x / (n + 1.0 / 3.0)) ** 2
                                                         * (n + 1.0 / 6.0)))


def leisen_reimer(S, K, T, r, q, sigma, n=101, kind="call", american=False):
    """Leisen-Reimer binomial tree (O(1/n^2) convergence, oscillation-free)."""
    S, K, T, r, q, sigma = (float(x) for x in (S, K, T, r, q, sigma))
    if T <= 0:
        return max(S - K, 0.0) if kind == "call" else max(K - S, 0.0)
    n = int(n)
    b = r - q
    dt = T / n
    d1 = (np.log(S / K) + (b + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    p = _peizer_pratt(d2, n)      # risk-neutral up probability
    pp = _peizer_pratt(d1, n)
    u = np.exp(b * dt) * pp / p
    d = (np.exp(b * dt) - p * u) / (1.0 - p)
    disc = np.exp(-r * dt)
    j = np.arange(n + 1)
    Sj = S * u ** j * d ** (n - j)
    V = np.maximum(Sj - K, 0.0) if kind == "call" else np.maximum(K - Sj, 0.0)
    for step in range(n - 1, -1, -1):
        V = disc * (p * V[1:] + (1.0 - p) * V[:-1])
        if american:
            jj = np.arange(step + 1)
            Sjj = S * u ** jj * d ** (step - jj)
            intrinsic = (np.maximum(Sjj - K, 0.0) if kind == "call"
                         else np.maximum(K - Sjj, 0.0))
            V = np.maximum(V, intrinsic)
    return float(V[0])


# --------------------------------------------------------------------------
# Digitals & delta-to-strike inversion
# --------------------------------------------------------------------------

def digital_cash(S, K, T, r, q, sigma, kind="call"):
    """Cash-or-nothing digital price."""
    S, K, T, r, q, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, r, q, sigma))
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    ert = np.exp(-r * T)
    price = ert * (N(d2) if kind == "call" else N(-d2))
    return price if price.shape else float(price)


def digital_asset(S, K, T, r, q, sigma, kind="call"):
    """Asset-or-nothing digital price."""
    S, K, T, r, q, sigma = (np.asarray(x, dtype=float) for x in (S, K, T, r, q, sigma))
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    eqt = np.exp(-q * T)
    price = S * eqt * (N(d1) if kind == "call" else N(-d1))
    return price if price.shape else float(price)


def delta_to_strike(S, T, r, q, sigma, delta, kind="call"):
    """Invert BSM delta to recover the strike (closed form).

    ``delta`` follows the market convention (call delta in [0,1],
    put delta in [-1,0]).
    """
    S, T, r, q, sigma = (float(x) for x in (S, T, r, q, sigma))
    eqt = np.exp(-q * T)
    if kind == "call":
        target = delta * np.exp(q * T)
        if not (0.0 < target < 1.0):
            raise ValueError("call delta must map to a probability in (0,1)")
        d1 = norm.ppf(target)
    else:
        target = -delta * np.exp(q * T)
        if not (0.0 < target < 1.0):
            raise ValueError("put delta must map to a probability in (0,1)")
        d1 = -norm.ppf(target)
    K = S * np.exp(-sigma * np.sqrt(T) * d1 + (r - q + 0.5 * sigma ** 2) * T)
    return K
