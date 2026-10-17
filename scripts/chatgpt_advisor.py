#!/home/ubuntu/algolab/.venv/bin/python3
"""
Algo Lab ChatGPT CLI & Advisor.
Provides a direct terminal interface to communicate with OpenAI GPT models:
- Single-shot queries & piped inputs (e.g., git diff | chatgpt "review this diff")
- Interactive multi-turn chat sessions
- Code forensics & architectural audits
- Live portfolio risk analysis & EOD instructions
- Easy API key management
"""

import sys
import os
import argparse
from pathlib import Path

# Auto-configure environment and project paths
BASE_DIR = Path(__file__).resolve().parent.parent
venv_python = BASE_DIR / ".venv" / "bin" / "python3"
if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve() and "-c" not in sys.argv:
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.gpt_client import (
    ChatGPTClient,
    load_openai_api_key,
    save_openai_api_key,
    DEFAULT_MODEL,
)

# Terminal Styling ANSI codes
C_CYAN = "\033[96m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_RED = "\033[91m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RESET = "\033[0m"


def print_banner():
    print(f"{C_BOLD}{C_CYAN}=" * 76)
    print(f"  🧠  ALGO LAB CHATGPT QUANTITATIVE & CODE ADVISOR (OpenAI)")
    print(f"=" * 76 + f"{C_RESET}")


def prompt_set_key_interactive():
    print_banner()
    print(f"{C_YELLOW}[!] OPENAI_API_KEY is not currently configured.{C_RESET}\n")
    print("To use ChatGPT, please provide your OpenAI API Key (starts with 'sk-...').")
    print("Your key will be securely saved into `/home/ubuntu/algolab/.env`.\n")

    try:
        key = input(f"{C_BOLD}Enter OpenAI API Key: {C_RESET}").strip()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(1)

    if not key:
        print(f"{C_RED}Error: Empty key provided.{C_RESET}")
        sys.exit(1)

    if save_openai_api_key(key):
        print(f"{C_GREEN}✓ Key successfully saved to {BASE_DIR}/.env!{C_RESET}\n")
    else:
        print(f"{C_RED}Failed to save key.{C_RESET}")
        sys.exit(1)


def run_interactive_chat(client: ChatGPTClient):
    print_banner()
    print(f"Model: {C_GREEN}{client.model}{C_RESET} | Active Workspace: {C_CYAN}{BASE_DIR}{C_RESET}")
    print(f"Commands: Type {C_YELLOW}exit{C_RESET} or {C_YELLOW}quit{C_RESET} to exit, {C_YELLOW}clear{C_RESET} to reset chat context.\n")

    while True:
        try:
            user_input = input(f"{C_BOLD}{C_GREEN}You > {C_RESET}").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting chat session.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            print("Session ended.")
            break

        if user_input.lower() in ("clear", "reset"):
            client.reset_chat()
            print(f"{C_DIM}[Chat history reset.]{C_RESET}\n")
            continue

        print(f"\n{C_BOLD}{C_CYAN}ChatGPT > {C_RESET}", end="", flush=True)
        try:
            for chunk in client.stream_prompt(user_input, remember=True):
                print(chunk, end="", flush=True)
            print("\n")
        except Exception as e:
            print(f"\n{C_RED}[Error]: {e}{C_RESET}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Algo Lab ChatGPT Quantitative & Systems Advisor CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  chatgpt "How should I manage gap risk on Nifty swing delivery?"
  chatgpt --review live_market_daemon.py
  chatgpt --state
  chatgpt --instructions "What are the pre-market checklist steps for 09:15 IST?"
  chatgpt -i
  git diff | chatgpt "Review these changes for bugs"
  chatgpt --set-key sk-...
        """,
    )

    parser.add_argument("prompt", nargs="*", help="Direct prompt to ChatGPT (optional)")
    parser.add_argument("-i", "--interactive", action="store_true", help="Launch interactive multi-turn chat session")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"OpenAI Model (default: {DEFAULT_MODEL})")
    parser.add_argument("--review", metavar="FILE", help="Perform forensic code and logic review on specified file")
    parser.add_argument("--focus", help="Optional focus area for code review (e.g., 'slippage', 'state consistency')")
    parser.add_argument("--state", action="store_true", help="Inspect live Algo Lab portfolio state and ask GPT for risk instructions")
    parser.add_argument("--free", action="store_true", help="Use 100%% free zero-key model (no OpenAI credits needed)")
    parser.add_argument("--instructions", metavar="CONTEXT", help="Generate actionable institutional instructions for given context")
    parser.add_argument("--set-key", metavar="KEY", help="Save or update OpenAI API key into .env")
    parser.add_argument("--status", action="store_true", help="Check OpenAI API key and connectivity status")
    parser.add_argument("--no-stream", action="store_true", help="Disable token streaming output")

    args = parser.parse_args()

    # 1. Handle key setting
    if args.set_key:
        if save_openai_api_key(args.set_key):
            masked = args.set_key[:7] + "..." + args.set_key[-4:] if len(args.set_key) > 12 else "***"
            print(f"{C_GREEN}✓ Successfully saved OPENAI_API_KEY ({masked}) to {BASE_DIR}/.env{C_RESET}")
        else:
            print(f"{C_RED}Failed to save key.{C_RESET}")
        return

    # 2. Check key existence
    key = load_openai_api_key()

    if args.status:
        print_banner()
        print(f"Free Zero-Key Model:  {C_GREEN}ONLINE & READY (100% Free Forever){C_RESET}")
        if key:
            masked = key[:7] + "..." + key[-4:] if len(key) > 12 else "***"
            print(f"OpenAI API Key:       {C_GREEN}CONFIGURED{C_RESET} ({masked})")
            print(f"Default Model:        {args.model}")
            print("Testing OpenAI API status...")
            try:
                client = ChatGPTClient(api_key=key, model=args.model, provider="openai")
                res = client.ask("Respond with 'OK' if you can read this.", remember=False)
                print(f"OpenAI Response:      {C_GREEN}{res.strip()}{C_RESET}")
                print(f"{C_GREEN}✓ OpenAI API is operational!{C_RESET}")
            except Exception as e:
                print(f"{C_YELLOW}⚠ OpenAI returned: {e}{C_RESET}")
                print(f"{C_CYAN}ℹ Free model is automatically active as fallback (or use --free){C_RESET}")
        else:
            print(f"OpenAI API Key:       {C_YELLOW}NOT CONFIGURED{C_RESET}")
            print(f"{C_CYAN}ℹ Free model is active by default (use --free){C_RESET}")
        return

    provider = "free" if args.free else ("auto" if key else "free")
    client = ChatGPTClient(api_key=key, model=args.model, provider=provider)

    # 3. Check for piped stdin input (e.g. `cat file.py | chatgpt "prompt"`)
    piped_input = ""
    if not sys.stdin.isatty():
        try:
            piped_input = sys.stdin.read().strip()
        except Exception:
            piped_input = ""

    # 4. Handle Code Review Mode
    if args.review:
        target_file = Path(args.review)
        print_banner()
        print(f"Auditing File: {C_CYAN}{target_file}{C_RESET}")
        if args.focus:
            print(f"Focus Area:    {C_YELLOW}{args.focus}{C_RESET}")
        print(f"Model:         {C_GREEN}{client.model}{C_RESET}\n" + "-" * 76 + "\n")

        try:
            if args.no_stream:
                print(client.review_code(target_file, focus_area=args.focus, stream=False))
            else:
                for chunk in client.review_code(target_file, focus_area=args.focus, stream=True):
                    print(chunk, end="", flush=True)
                print()
        except Exception as e:
            print(f"{C_RED}[Error during review]: {e}{C_RESET}")
        return

    # 5. Handle Live Portfolio State Mode
    if args.state:
        print_banner()
        print(f"Analyzing Live Portfolio State & SQLite Ledger...")
        print(f"Model: {C_GREEN}{client.model}{C_RESET}\n" + "-" * 76 + "\n")

        try:
            if args.no_stream:
                print(client.analyze_portfolio_state(stream=False))
            else:
                for chunk in client.analyze_portfolio_state(stream=True):
                    print(chunk, end="", flush=True)
                print()
        except Exception as e:
            print(f"{C_RED}[Error analyzing state]: {e}{C_RESET}")
        return

    # 6. Handle Instructions Mode
    if args.instructions:
        print_banner()
        print(f"Generating Trading Instructions...")
        print(f"Model: {C_GREEN}{client.model}{C_RESET}\n" + "-" * 76 + "\n")

        try:
            if args.no_stream:
                print(client.get_trading_instructions(args.instructions, stream=False))
            else:
                for chunk in client.get_trading_instructions(args.instructions, stream=True):
                    print(chunk, end="", flush=True)
                print()
        except Exception as e:
            print(f"{C_RED}[Error generating instructions]: {e}{C_RESET}")
        return

    # 7. Handle Direct Prompt (or Piped Input)
    joined_prompt = " ".join(args.prompt).strip()
    if piped_input and joined_prompt:
        final_prompt = f"{joined_prompt}\n\nContext Data:\n```\n{piped_input}\n```"
    elif piped_input:
        final_prompt = piped_input
    else:
        final_prompt = joined_prompt

    if final_prompt:
        try:
            if args.no_stream:
                print(client.ask(final_prompt, remember=False))
            else:
                for chunk in client.stream_prompt(final_prompt, remember=False):
                    print(chunk, end="", flush=True)
                print()
        except Exception as e:
            print(f"{C_RED}[Error]: {e}{C_RESET}")
        return

    # 8. Interactive mode if requested or no arguments supplied
    run_interactive_chat(client)


if __name__ == "__main__":
    main()
