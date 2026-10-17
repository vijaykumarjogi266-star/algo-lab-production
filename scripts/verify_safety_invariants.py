#!/usr/bin/env python3
"""
Algo Lab Safety Invariants Verification Script.
Statically and dynamically asserts that all non-negotiable safety rules are intact:
1. LIVE_TRADING_ENABLED == False
2. REAL_BROKER_EXECUTION_ENABLED == False
3. Any attempt to enable live trading triggers an immediate fail-closed exception.
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def check_version_module():
    from src.version import (
        LIVE_TRADING_ENABLED,
        REAL_BROKER_EXECUTION_ENABLED,
        PAPER_ONLY_EXECUTION_POLICY,
        enforce_canonical_invariants,
    )

    if LIVE_TRADING_ENABLED:
        raise AssertionError("VIOLATION: src.version.LIVE_TRADING_ENABLED must be False!")
    if REAL_BROKER_EXECUTION_ENABLED:
        raise AssertionError("VIOLATION: src.version.REAL_BROKER_EXECUTION_ENABLED must be False!")
    if not PAPER_ONLY_EXECUTION_POLICY:
        raise AssertionError("VIOLATION: src.version.PAPER_ONLY_EXECUTION_POLICY must be True!")

    # Verify enforcement function passes when invariants are intact
    enforce_canonical_invariants()
    print("  ✓ src.version canonical invariants verified (LIVE=False, BROKER=False)")


def check_api_config_invariants():
    from apps.api.core.config import Settings

    # 1. Default config check
    s = Settings()
    if s.ALLOW_LIVE_TRADING or s.ALLOW_REAL_BROKER_EXECUTION:
        raise AssertionError("VIOLATION: apps.api.core.config allows live trading by default!")
    if s.LIVE_TRADING_ENABLED or s.REAL_BROKER_EXECUTION_ENABLED:
        raise AssertionError("VIOLATION: apps.api.core.config allows live trading invariants!")

    # 2. Fail-closed test on attempted override
    try:
        Settings(ALLOW_LIVE_TRADING=True)
        raise AssertionError("VIOLATION: Settings failed to block ALLOW_LIVE_TRADING=True!")
    except ValueError:
        pass

    try:
        Settings(LIVE_TRADING_ENABLED=True)
        raise AssertionError("VIOLATION: Settings failed to block LIVE_TRADING_ENABLED=True!")
    except ValueError:
        pass

    print("  ✓ apps.api.core.config fail-closed validator verified")


def check_live_market_daemon_invariants():
    import live_market_daemon as lmd

    if lmd.ALLOW_LIVE_TRADING:
        raise AssertionError("VIOLATION: live_market_daemon.ALLOW_LIVE_TRADING must be False!")
    if lmd.ALLOW_REAL_BROKER_EXECUTION:
        raise AssertionError("VIOLATION: live_market_daemon.ALLOW_REAL_BROKER_EXECUTION must be False!")

    # Verify enforcement function
    lmd.enforce_safety_invariants()
    print("  ✓ live_market_daemon safety invariants verified")


def check_no_unmasked_secrets():
    """Scans all non-ignored tracked files for potential unmasked API keys or private tokens."""
    suspicious_patterns = [
        "sk-proj-",
        "BEGIN RSA PRIVATE KEY",
        "BEGIN OPENSSH PRIVATE KEY",
    ]
    # Check git tracked files
    import subprocess
    tracked = subprocess.check_output(["git", "ls-files"], cwd=str(BASE_DIR)).decode("utf-8").splitlines()

    flagged = []
    for file_rel in tracked:
        p = BASE_DIR / file_rel
        if not p.is_file() or file_rel.endswith(".parquet") or file_rel.endswith(".db"):
            continue
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            for pattern in suspicious_patterns:
                if pattern in content:
                    flagged.append((file_rel, pattern))
        except Exception:
            pass

    if flagged:
        raise AssertionError(f"VIOLATION: Unmasked secret patterns found in tracked files: {flagged}")
    print("  ✓ Secret scan verified: zero unmasked private credentials in repository")


def main():
    print("=" * 76)
    print("  🛡️  ALGO LAB NON-NEGOTIABLE SAFETY INVARIANTS AUDIT")
    print("=" * 76)

    try:
        check_version_module()
        check_api_config_invariants()
        check_live_market_daemon_invariants()
        check_no_unmasked_secrets()
    except Exception as e:
        print(f"\n❌ SAFETY INVARIANT AUDIT FAILED: {e}")
        sys.exit(1)

    print("\n✅ ALL SAFETY INVARIANTS CERTIFIED: 100% PAPER-ONLY COMPLIANCE.\n")


if __name__ == "__main__":
    main()
