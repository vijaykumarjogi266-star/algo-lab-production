#!/usr/bin/env python3
"""
Algo Lab Stage 27 — Secure Credential Update CLI Helper

Allows updating Angel One (or FYERS) credentials in the encrypted SecureCredentialStore
without echoing secrets to terminal or logs.

Usage:
  Interactive (hidden prompt via getpass):
    python scripts/update_credentials.py --provider ANGEL_ONE

  Environment-based (non-interactive):
    ANGEL_ONE_API_KEY="..." ANGEL_ONE_CLIENT_CODE="..." ANGEL_ONE_PASSWORD="..." ANGEL_ONE_TOTP_KEY="..." \
      python scripts/update_credentials.py --provider ANGEL_ONE --env
"""

import sys
import os
import argparse
import getpass
from typing import Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from collectors.secure_credential_store import SecureCredentialStore, BACKUP_STORE_PATH, DEFAULT_STORE_DIR


def update_angel_one(from_env: bool = False) -> bool:
    print("[*] Secure Credential Update — Angel One SmartAPI")

    if from_env:
        api_key = os.environ.get("ANGEL_ONE_API_KEY", "").strip()
        client_code = os.environ.get("ANGEL_ONE_CLIENT_CODE", "").strip()
        password = os.environ.get("ANGEL_ONE_PASSWORD", "").strip()
        totp_key = os.environ.get("ANGEL_ONE_TOTP_KEY", "").strip()
    else:
        print("[+] Please enter credentials (inputs will be hidden / non-echoed):")
        api_key = getpass.getpass("    Angel One API Key: ").strip()
        client_code = getpass.getpass("    Angel One Client Code: ").strip()
        password = getpass.getpass("    Angel One Password/PIN: ").strip()
        totp_key = getpass.getpass("    Angel One TOTP Secret: ").strip()

    if not api_key or not client_code or not password or not totp_key:
        print("[!] Error: All 4 fields (api_key, client_code, password, totp_key) must be non-empty.")
        return False

    store = SecureCredentialStore()
    existing_data = store.load_credentials()

    existing_data["ANGEL_ONE"] = {
        "api_key": api_key,
        "client_code": client_code,
        "password": password,
        "totp_key": totp_key,
    }

    # Save to primary store path
    store.save_credentials(existing_data)
    print(f"[+] Credentials successfully encrypted and saved to primary store.")

    # Also save to backup store path if accessible
    try:
        if os.path.exists(os.path.dirname(BACKUP_STORE_PATH)):
            backup_store = SecureCredentialStore(store_path=BACKUP_STORE_PATH)
            backup_store.save_credentials(existing_data)
            print(f"[+] Credentials successfully backed up to store at {BACKUP_STORE_PATH}.")
    except Exception as e:
        print(f"[*] Note: Backup store update skipped: {e}")

    # Verify persistence without revealing plaintext
    reloaded = store.load_credentials()
    ao = reloaded.get("ANGEL_ONE", {})
    verified = all(len(str(ao.get(k, ""))) > 0 for k in ["api_key", "client_code", "password", "totp_key"])

    if verified:
        print("[✓] Verification successful: All 4 fields present and non-empty in encrypted store.")
        return True
    else:
        print("[!] Verification failed: Encrypted payload incomplete.")
        return False

def update_dhan(from_env: bool = False) -> bool:
    print("[*] Secure Credential Update — DhanHQ API")

    if from_env:
        client_id = os.environ.get("DHAN_CLIENT_ID", "").strip()
        access_token = os.environ.get("DHAN_ACCESS_TOKEN", "").strip()
    else:
        print("[+] Please enter credentials (inputs will be hidden / non-echoed):")
        client_id = getpass.getpass("    Dhan Client ID: ").strip()
        access_token = getpass.getpass("    Dhan Access Token: ").strip()

    if not client_id or not access_token:
        print("[!] Error: Both fields (client_id, access_token) must be non-empty.")
        return False

    store = SecureCredentialStore()
    existing_data = store.load_credentials()

    existing_data["DHAN"] = {
        "client_id": client_id,
        "access_token": access_token,
    }

    # Save to primary store path
    store.save_credentials(existing_data)
    print(f"[+] Credentials successfully encrypted and saved to primary store.")

    # Also save to backup store path if accessible
    try:
        if os.path.exists(os.path.dirname(BACKUP_STORE_PATH)):
            backup_store = SecureCredentialStore(store_path=BACKUP_STORE_PATH)
            backup_store.save_credentials(existing_data)
            print(f"[+] Credentials successfully backed up to store at {BACKUP_STORE_PATH}.")
    except Exception as e:
        print(f"[*] Note: Backup store update skipped: {e}")

    reloaded = store.load_credentials()
    dh = reloaded.get("DHAN", {})
    verified = all(len(str(dh.get(k, ""))) > 0 for k in ["client_id", "access_token"])

    if verified:
        print("[✓] Verification successful: Client ID and Access Token securely stored.")
        return True
    else:
        print("[!] Verification failed: Encrypted payload incomplete.")
        return False

def main():
    parser = argparse.ArgumentParser(description="Secure Credential Store Update Utility")
    parser.add_argument("--provider", choices=["ANGEL_ONE", "FYERS", "DHAN"], default="ANGEL_ONE", help="Target provider")
    parser.add_argument("--env", action="store_true", help="Read credentials from environment variables instead of getpass prompt")
    args = parser.parse_args()

    if args.provider == "ANGEL_ONE":
        success = update_angel_one(from_env=args.env)
        sys.exit(0 if success else 1)
    elif args.provider == "DHAN":
        success = update_dhan(from_env=args.env)
        sys.exit(0 if success else 1)
    else:
        print(f"[!] Provider {args.provider} update not implemented in this script.")
        sys.exit(1)


if __name__ == "__main__":
    main()
