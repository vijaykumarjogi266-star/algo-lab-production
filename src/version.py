#!/usr/bin/env python3
"""
Algo Lab Canonical Version & Lifecycle Authority.
Single source of truth for semantic version, revision identifier,
lifecycle state, and non-negotiable paper-only execution policy.
"""

from typing import Final, Literal

__version__: Final[str] = "0.3.0"
__revision__: Final[str] = "git-canonical-rev"
__build_date__: Final[str] = "2026-10-14"

LifecycleState = Literal["prototype", "research", "forward-paper-validation", "release-candidate"]
LIFECYCLE_STATE: Final[LifecycleState] = "forward-paper-validation"

# Non-negotiable safety invariants
PAPER_ONLY_EXECUTION_POLICY: Final[bool] = True
LIVE_TRADING_ENABLED: Final[bool] = False
REAL_BROKER_EXECUTION_ENABLED: Final[bool] = False


def get_version_info() -> dict:
    """Returns canonical project version metadata."""
    return {
        "project": "Algo Lab",
        "version": __version__,
        "revision": __revision__,
        "build_date": __build_date__,
        "lifecycle_state": LIFECYCLE_STATE,
        "paper_only": PAPER_ONLY_EXECUTION_POLICY,
        "live_trading_enabled": LIVE_TRADING_ENABLED,
        "real_broker_execution_enabled": REAL_BROKER_EXECUTION_ENABLED,
    }


def enforce_canonical_invariants() -> None:
    """
    Fails closed immediately if live trading or real broker execution is enabled anywhere.
    Must be called at startup by all services, APIs, and daemons.
    """
    if LIVE_TRADING_ENABLED:
        raise RuntimeError(
            "CRITICAL INVARIANT BREACH: LIVE_TRADING_ENABLED is True. "
            "Algo Lab is strictly a paper-only quantitative research platform."
        )
    if REAL_BROKER_EXECUTION_ENABLED:
        raise RuntimeError(
            "CRITICAL INVARIANT BREACH: REAL_BROKER_EXECUTION_ENABLED is True. "
            "Real broker endpoints and real-money order routing are permanently forbidden."
        )
