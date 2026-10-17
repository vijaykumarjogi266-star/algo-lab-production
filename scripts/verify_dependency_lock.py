#!/usr/bin/env python3
"""
Algo Lab Dependency Lock Integrity Checker.
Verifies that all locked dependencies in requirements-pinned.txt are installed
with exact version matches in the current Python environment.
"""

import sys
import importlib.metadata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PINNED_FILE = BASE_DIR / "requirements-pinned.txt"


def verify_dependency_locks():
    if not PINNED_FILE.exists():
        print(f"❌ Pinned requirements file missing: {PINNED_FILE}")
        sys.exit(1)

    lines = PINNED_FILE.read_text(encoding="utf-8").splitlines()
    mismatches = []
    checked = 0

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue

        pkg, expected_ver = line.split("==", 1)
        pkg = pkg.strip()
        expected_ver = expected_ver.strip()

        try:
            installed_ver = importlib.metadata.version(pkg)
            checked += 1
            if installed_ver != expected_ver:
                mismatches.append((pkg, expected_ver, installed_ver))
        except importlib.metadata.PackageNotFoundError:
            # Handle normalized names (e.g. underscore vs hyphen)
            norm_pkg = pkg.replace("-", "_")
            try:
                installed_ver = importlib.metadata.version(norm_pkg)
                checked += 1
                if installed_ver != expected_ver:
                    mismatches.append((pkg, expected_ver, installed_ver))
            except importlib.metadata.PackageNotFoundError:
                mismatches.append((pkg, expected_ver, "NOT_INSTALLED"))

    if mismatches:
        print("❌ Dependency Lock Mismatches Detected:")
        for pkg, expected, found in mismatches:
            print(f"  • {pkg}: Expected {expected}, Found {found}")
        sys.exit(1)

    print(f"✅ All {checked} pinned dependencies verified with exact version matches.")


if __name__ == "__main__":
    verify_dependency_locks()
