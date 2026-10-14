#!/usr/bin/env python3
"""
Algo Lab — Zerodha Kite Connect Session Token Generator

Facilitates generating and refreshing daily Zerodha Kite Connect access tokens:
1. Displays Kite login URL with configured API key.
2. Accepts request_token or full redirected URL.
3. Exchanges request_token + api_secret for daily access_token via KiteConnect SDK.
4. Updates ZERODHA_ACCESS_TOKEN in .env and verifies active connection.
"""

import os
import sys
import re
import argparse
from urllib.parse import urlparse, parse_qs
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

try:
    from dotenv import dotenv_values, set_key
    from kiteconnect import KiteConnect
except ImportError:
    print("[!] Error: Required packages not found. Please run within the virtual environment:")
    print("    source /home/ubuntu/algolab/.venv/bin/activate")
    sys.exit(1)


def mask_secret(val: str, prefix_len: int = 4) -> str:
    """Masks secret values for safe terminal logging."""
    if not val:
        return "<empty>"
    if len(val) <= prefix_len:
        return "*" * len(val)
    return val[:prefix_len] + "*" * (len(val) - prefix_len)


def load_zerodha_creds():
    """Loads Zerodha credentials from .env."""
    if not ENV_PATH.exists():
        print(f"[!] Error: .env file not found at {ENV_PATH}")
        sys.exit(1)

    cfg = dotenv_values(ENV_PATH)
    api_key = cfg.get("ZERODHA_API_KEY", "").strip()
    api_secret = cfg.get("ZERODHA_API_SECRET", "").strip()

    if not api_key:
        print("[!] Error: ZERODHA_API_KEY is missing or empty in .env")
        sys.exit(1)
    if not api_secret:
        print("[!] Error: ZERODHA_API_SECRET is missing or empty in .env")
        sys.exit(1)

    return api_key, api_secret


def extract_request_token(input_val: str) -> str:
    """Extracts request_token whether user provided raw token or full redirected URL."""
    cleaned = input_val.strip()
    if "request_token=" in cleaned:
        parsed = urlparse(cleaned)
        params = parse_qs(parsed.query)
        tokens = params.get("request_token")
        if tokens and len(tokens) > 0:
            return tokens[0].strip()
    return cleaned


def update_env_access_token(new_access_token: str):
    """Updates ZERODHA_ACCESS_TOKEN in .env safely."""
    # Read existing content
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    if re.search(r"^ZERODHA_ACCESS_TOKEN=.*", content, flags=re.MULTILINE):
        content = re.sub(
            r"^ZERODHA_ACCESS_TOKEN=.*",
            f"ZERODHA_ACCESS_TOKEN={new_access_token}",
            content,
            flags=re.MULTILINE,
        )
    else:
        content += f"\nZERODHA_ACCESS_TOKEN={new_access_token}\n"

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def generate_and_save_session(request_token: str, api_key: str, api_secret: str) -> bool:
    """Exchanges request_token for access_token and updates .env."""
    req_token = extract_request_token(request_token)
    if not req_token:
        print("[!] Error: Invalid or empty request_token.")
        return False

    print(f"[*] Exchanging request_token ({mask_secret(req_token, 4)}) with Kite Connect...")
    kite = KiteConnect(api_key=api_key)

    try:
        data = kite.generate_session(req_token, api_secret=api_secret)
    except Exception as e:
        print(f"[!] Session generation failed: {type(e).__name__}: {e}")
        return False

    access_token = data.get("access_token")
    if not access_token:
        print("[!] Error: No access_token returned by Kite Connect.")
        return False

    update_env_access_token(access_token)
    print(f"[✓] Successfully updated ZERODHA_ACCESS_TOKEN in {ENV_PATH}")

    # Verify session profile
    kite.set_access_token(access_token)
    try:
        profile = kite.profile()
        user_id = profile.get("user_id", "N/A")
        user_name = profile.get("user_name", "N/A")
        broker = profile.get("broker", "ZERODHA")
        print("\n" + "=" * 50)
        print(" [✓] ZERODHA KITE SESSION ACTIVE & VERIFIED")
        print("=" * 50)
        print(f" User ID   : {user_id}")
        print(f" User Name : {user_name}")
        print(f" Broker    : {broker}")
        print(f" Token     : {mask_secret(access_token, 4)}")
        print("=" * 50)
        return True
    except Exception as e:
        print(f"[!] Session saved but verification call failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Zerodha Kite Connect Session Token Helper")
    parser.add_argument(
        "--request-token",
        "-t",
        help="The request_token or full redirected URL from browser after login",
    )
    parser.add_argument(
        "--get-url",
        action="store_true",
        help="Only display the Kite login URL and exit",
    )
    args = parser.parse_args()

    api_key, api_secret = load_zerodha_creds()
    login_url = f"https://kite.zerodha.com/connect/login?v=3&api_key={api_key}"

    if args.get_url:
        print(login_url)
        return

    if args.request_token:
        success = generate_and_save_session(args.request_token, api_key, api_secret)
        sys.exit(0 if success else 1)

    # Interactive mode
    print("=" * 60)
    print(" Algo Lab — Zerodha Kite Connect Authentication")
    print("=" * 60)
    print("\n1. Open this URL in your web browser:")
    print(f"   {login_url}\n")
    print("2. Log in with your Zerodha credentials & 2FA (Mobile App Code / TOTP).")
    print("3. After login, your browser will redirect to your configured Redirect URL.")
    print("   Copy either the FULL redirected URL or just the request_token value.\n")

    try:
        user_input = input("Enter request_token or redirected URL: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[*] Operation aborted by user.")
        sys.exit(1)

    if not user_input:
        print("[!] No input provided. Exiting.")
        sys.exit(1)

    success = generate_and_save_session(user_input, api_key, api_secret)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
