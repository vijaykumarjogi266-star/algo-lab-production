#!/usr/bin/env python3
"""
Algo Lab — Safe Broker Diagnostic Verifier

Attempts genuine authentication with Angel One SmartAPI using credentials
retrieved from SecureCredentialStore ONLY if explicit operator approval is provided.

Rules:
1. NEVER print, log, or display credentials, passwords, TOTP secret, JWT access token, or refresh token.
2. Require --operator-approve-auth to perform any authenticated call.
3. Supress all underlying library logs to prevent payload leakage.
"""

import sys
import os
import argparse
import logging

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from collectors.secure_credential_store import SecureCredentialStore

# Strictly suppress ALL logs from smartapi or urllib3 to prevent credential leakage
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
logging.getLogger("SmartApi").setLevel(logging.CRITICAL)
logging.getLogger("smartConnect").setLevel(logging.CRITICAL)


def check_and_authenticate(operator_approved: bool):
    print("=" * 60)
    print("SAFE BROKER DIAGNOSTIC VERIFIER")
    print("=" * 60)

    store = SecureCredentialStore()
    creds = store.load_credentials()

    ao_creds = creds.get("ANGEL_ONE", {})
    api_key = ao_creds.get("api_key", "").strip()
    client_code = ao_creds.get("client_code", "").strip()
    password = ao_creds.get("password", "").strip()
    totp_key = ao_creds.get("totp_key", "").strip()

    required_fields = {"api_key": bool(api_key), "client_code": bool(client_code), "password": bool(password), "totp_key": bool(totp_key)}
    all_fields_present = all(required_fields.values())

    print(f"[*] Encrypted Credential Store Status:")
    print(f"    - Store Readable: YES")
    print(f"    - Angel One Record Found: {'YES' if ao_creds else 'NO'}")
    
    if not all_fields_present:
        print("\n[!] STATUS: CREDENTIALS UNAVAILABLE")
        return False, "UNAVAILABLE"

    if not operator_approved:
        print("\n[!] BLOCKED: Authenticated API calls require explicit operator approval.")
        print("    Run with --operator-approve-auth to authorize genuine broker login.")
        return False, "OPERATOR_APPROVAL_REQUIRED"

    print("\n[*] Initiating genuine authentication attempt (OPERATOR APPROVED)...")

    try:
        import pyotp
        from SmartApi import SmartConnect
    except ImportError as e:
        print(f"[!] Required package missing.")
        return False, "MISSING_PACKAGES"

    try:
        totp_code = pyotp.TOTP(totp_key).now()
    except Exception:
        print(f"[!] Failed to generate TOTP code.")
        return False, "INVALID_TOTP_KEY"

    try:
        smart_api = SmartConnect(api_key=api_key)
        data = smart_api.generateSession(client_code, password, totp_code)

        if isinstance(data, dict) and data.get("status") is True:
            print("\n[✓] STATUS: AUTHENTICATION SUCCESSFUL")
            return True, "SUCCESS"
        else:
            print(f"\n[!] STATUS: AUTHENTICATION FAILED (Sanitized)")
            return False, "AUTH_FAILED"

    except Exception:
        print(f"\n[!] STATUS: AUTHENTICATION EXCEPTION (Sanitized)")
        return False, "EXCEPTION"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safe Broker Diagnostic")
    parser.add_argument("--operator-approve-auth", action="store_true", help="Explicitly approve authenticated API calls")
    args = parser.parse_args()
    
    success, status_code = check_and_authenticate(args.operator_approve_auth)
    sys.exit(0 if success else 1)

