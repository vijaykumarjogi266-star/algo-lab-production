#!/home/ubuntu/algolab/.venv/bin/python3
"""
Algo Lab Full Project Review Generator & ChatGPT Pipeline.
Extracts the authoritative system architecture, strategy mechanics, risk invariants,
and statutory tax models, and submits them to ChatGPT for an institutional review.
"""

import sys
import os
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.gpt_client import ChatGPTClient, load_openai_api_key

PROJECT_REVIEW_PROMPT = """You are an Institutional Quantitative Hedge Fund Chief Risk Officer and Lead Systems Architect.
Perform an adversarial, comprehensive review of Algo Lab, an automated algorithmic trading platform built for Indian Cash Equities (NSE) running on an Oracle Cloud Ubuntu Linux VM.

### PROJECT ARCHITECTURE & DESIGN OVERVIEW:
1. Operational Paradigm:
   - End-of-Day (EOD) Swing Trading (Delivery / CNC).
   - Intraday 15:15 mandatory liquidation is strictly ELIMINATED for swing trades; positions are held overnight to capture multi-day momentum.
   - Operating Window: 15:00 IST (wakeup/ingestion) -> 15:15 IST (execution) -> 15:25 IST (persistence) -> 15:30 IST (session completion).
   - Daemon Loop: `live_market_daemon.py --loop-daily` running under `quant-os.service` with systemd auto-restart.

2. Selected Core Strategy (STRATEGY_SUPER_ADAPTIVE):
   - Universe: 50 Nifty Constituents (dynamically ingested with sector concentration guard: max 1 open position per sector).
   - Entry Trigger: Price > 200 SMA, 50 SMA > 200 SMA, Price >= 50-day Donchian High, Volume >= 1.05x 20-day Volume SMA, ADX(14) >= 15.0, plus fundamental filter (ROE >= 15%, Revenue Growth > 0).
   - Exit Mechanisms: 3.0x ATR(14) trailing stop loss; 5.0x Risk profit target; Asymmetric profit ratchets at +1.5R (ratchet to breakeven + 0.5% buffer) and +3.0R (lock in +1.5R minimum); 20-day Donchian low breach exit.
   - Position Sizing: Ed Thorp 1.0% capital risk rule (`risk_capital = total_equity * 0.01 / stop_distance`), capped at 3 concurrent positions (₹30,000 max capital per slot, preserving ₹10,000 minimum cash reserve).

3. Indian Statutory Cost Model:
   - STT: 0.1% on Buy and Sell legs (CNC Delivery).
   - Stamp Duty: 0.015% on Buy leg only.
   - DP Charges: Flat ₹13.50 base + 18% GST = ₹15.93 applied strictly on Sell leg.
   - Exchange Txn Fee: 0.00297% on turnover.
   - SEBI Turnover Fee: ₹10 per crore (0.0001%).
   - GST: 18% applied to Exchange fee, SEBI fee, and DP base charge (STT and Stamp duty excluded from taxable base).
   - Buy friction deducted directly from cash upon entry; Sell friction deducted from gross sell proceeds upon exit.

4. State Persistence & Safety Invariants:
   - Fail-closed runtime flags: `ALLOW_LIVE_TRADING = False` and `ALLOW_REAL_BROKER_EXECUTION = False`.
   - Dual-layer persistence: Atomic JSON writes via tempfile + `os.replace` to prevent corrupted state on VM crash.
   - SQLite Overnight Ledger (`swing_portfolio_ledger.db`): ACID transactions across `portfolio_state`, `open_positions`, `trade_journal`, and `overnight_snapshots`.
   - Timezone resiliency: Native Python 3.12 `zoneinfo.ZoneInfo("Asia/Kolkata")` with official `exchange_calendars` (`XNSE`) holiday checks.

Please provide your rigorous institutional critique:
1. Architecture & Concurrency: Are there any residual state amnesia, race conditions, or unhandled edge cases?
2. Strategy Robustness & Alpha Decay: Will the 50d Donchian breakout with fundamental gating hold positive expectancy in choppy / sideways regimes?
3. Friction & Sizing: Is the 1% Thorp risk model and ₹15.93 DP charge drag sufficiently mitigated by the 3 concurrent slots and 13 trades/year turnover?
4. Oracle Cloud 24/7 Operations: What monitoring, telemetry, or watchdog guards should be prioritized for uninterrupted multi-month live paper execution?
5. Final Production Clearance: Grade the system (A/B/C/F) and list any remaining P0/P1 recommendations before real capital allocation.
"""


def main():
    use_free = "--free" in sys.argv
    print("=" * 80)
    print("  🧠  ALGO LAB INSTITUTIONAL PROJECT REVIEW WITH CHATGPT")
    print("=" * 80)

    key = load_openai_api_key()
    provider = "free" if (use_free or not key) else "auto"
    client = ChatGPTClient(api_key=key, provider=provider)

    model_label = "Free Tier AI Model" if provider == "free" else "ChatGPT / Free Fallback"
    print(f"Connecting to {model_label} to review the Algo Lab project...")
    print("-" * 80 + "\n")

    try:
        for chunk in client.stream_prompt(PROJECT_REVIEW_PROMPT, remember=False):
            print(chunk, end="", flush=True)
        print("\n" + "=" * 80)
    except Exception as e:
        print(f"\n[OpenAI API Response]: {e}")
        print("\n" + "-" * 80)
        print("💡 NOTE: If you received a 429 'insufficient_quota' error, your API key is authentic,")
        print("but your OpenAI account requires prepaid credits ($5-$10) at:")
        print("👉 https://platform.openai.com/settings/organization/billing/\n")
        print("You can also copy the review prompt below directly into ChatGPT Web (https://chatgpt.com):\n")
        print("=" * 80)
        print(PROJECT_REVIEW_PROMPT)
        print("=" * 80)


if __name__ == "__main__":
    main()
