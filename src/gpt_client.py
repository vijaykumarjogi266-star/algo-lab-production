#!/usr/bin/env python3
"""
Algo Lab OpenAI ChatGPT & Free Model Integration Module.
Provides high-level programmatic and CLI communication with:
1. OpenAI GPT models (gpt-4o, gpt-4o-mini, etc.)
2. 100% Free Tier Zero-Key Models (GPT-4o / DeepSeek / Mistral) with automatic fallback
for quantitative analysis, code review, portfolio state assessment, and instruction generation.
"""

import os
import sys
import json
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Dict, Any, List, Generator

# Auto-locate project directories
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

INSTITUTIONAL_SYSTEM_PROMPT = """You are an elite Institutional Quantitative Trading and Systems Engineering Advisor embedded in Algo Lab.
Algo Lab operates an automated trading desk for Indian Equities (NSE/BSE) utilizing Delivery/CNC swing trading,
momentum breakout models, and strict risk budgeting (Ed Thorp 1% rule, ATR-based trailing stops, statutory friction models).

When advising:
1. Provide precise, actionable, and mathematically grounded instructions.
2. Consider Indian market specifics: NSE operating hours (09:15 - 15:30 IST), EOD scan at 15:00-15:25 IST,
   statutory taxes (STT 0.1% CNC, DP charges ₹15.93 incl. GST, Stamp duty 0.015%, SEBI fees).
3. Scrutinize all code for data leaks, lookahead bias, race conditions, floating point rounding errors,
   and unhandled broker/API exceptions.
4. Keep advice clear, concise, and production-ready.
"""


def load_openai_api_key(env_path: Optional[Path] = None) -> Optional[str]:
    """
    Retrieves the OpenAI API key with prioritized lookup:
    1. os.environ['OPENAI_API_KEY']
    2. algolab/.env file
    3. ~/.openai/api_key or ~/.config/openai/api_key
    """
    env_key = os.getenv("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    target_env = env_path or ENV_FILE
    if target_env.exists():
        try:
            for line in target_env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key.strip() == "OPENAI_API_KEY":
                    val = val.strip().strip("'\"")
                    if val:
                        os.environ["OPENAI_API_KEY"] = val
                        return val
        except Exception:
            pass

    for fallback_path in [
        Path.home() / ".config" / "openai" / "api_key",
        Path.home() / ".openai" / "api_key",
    ]:
        if fallback_path.exists():
            try:
                val = fallback_path.read_text(encoding="utf-8").strip()
                if val:
                    os.environ["OPENAI_API_KEY"] = val
                    return val
            except Exception:
                pass

    return None


def save_openai_api_key(key: str, env_path: Optional[Path] = None) -> bool:
    """
    Saves or updates OPENAI_API_KEY in the project .env file.
    Preserves existing entries while updating or appending the key.
    """
    target_env = env_path or ENV_FILE
    cleaned_key = key.strip().strip("'\"")
    if not cleaned_key:
        return False

    lines = []
    found = False
    if target_env.exists():
        try:
            lines = target_env.read_text(encoding="utf-8").splitlines()
        except Exception:
            lines = []

    new_lines = []
    for line in lines:
        if line.strip().startswith("OPENAI_API_KEY="):
            new_lines.append(f"OPENAI_API_KEY={cleaned_key}")
            found = True
        else:
            new_lines.append(line)

    if not found:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"OPENAI_API_KEY={cleaned_key}")

    target_env.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.environ["OPENAI_API_KEY"] = cleaned_key
    return True


class ChatGPTClient:
    """
    Institutional ChatGPT client supporting:
    - Official OpenAI API (GPT-4o, GPT-4o-mini, o1)
    - 100% Free Tier Zero-Key Inference (with seamless auto-fallback on quota exhaustion)
    - Streaming responses, code forensic reviews, and live state diagnostics.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        system_prompt: Optional[str] = None,
        provider: str = "auto",  # 'auto', 'openai', or 'free'
    ):
        self.api_key = api_key or load_openai_api_key()
        self.model = model
        self.system_prompt = system_prompt or INSTITUTIONAL_SYSTEM_PROMPT
        self.provider = provider
        self.history: List[Dict[str, str]] = []
        self._client: Any = None

        if self.provider != "free" and self.api_key:
            self._init_openai_client()

    def _init_openai_client(self):
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        except Exception:
            self._client = None

    def is_configured(self) -> bool:
        """Returns True if OpenAI key is present or free provider is active."""
        if self.provider == "free":
            return True
        return bool(self.api_key and self._client)

    def reset_chat(self):
        """Clears conversational memory."""
        self.history.clear()

    def _build_messages(self, prompt: str, custom_system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        sys_p = custom_system_prompt or self.system_prompt
        messages = [{"role": "system", "content": sys_p}]
        messages.extend(self.history)
        messages.append({"role": "user", "content": prompt})
        return messages

    def _stream_free_model(self, messages: List[Dict[str, str]]) -> Generator[str, None, str]:
        """
        Streams from 100% Free Tier zero-key endpoint using Server-Sent Events (SSE).
        Requires zero API key and zero credit balance.
        """
        url = "https://text.pollinations.ai/"
        payload = {
            "messages": messages,
            "model": "openai",
            "stream": True,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "algolab-institutional/1.0",
            },
        )
        if not url.startswith("https://"):
            raise ValueError(f"Insecure scheme in URL: {url}")
        collected = []
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:  # nosec B310
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choices = data.get("choices", [])
                        if choices and "delta" in choices[0]:
                            content = choices[0]["delta"].get("content", "")
                            if content:
                                collected.append(content)
                                yield content
                    except Exception:
                        continue
        except Exception as e:
            # Fallback to direct synchronous POST if streaming stream dropped
            try:
                sync_payload = {"messages": messages, "model": "openai"}
                sync_req = urllib.request.Request(
                    url,
                    data=json.dumps(sync_payload).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "algolab/1.0"},
                )
                with urllib.request.urlopen(sync_req, timeout=30) as sync_resp:  # nosec B310
                    content = sync_resp.read().decode("utf-8", errors="replace")
                    collected.append(content)
                    yield content
            except Exception as e2:
                err = f"\n[Free Model Connection Error]: {e2}\n"
                collected.append(err)
                yield err

        return "".join(collected)

    def stream_prompt(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        remember: bool = True,
    ) -> Generator[str, None, str]:
        """
        Streams response tokens in real-time.
        Automatically uses free model if requested, or falls back to free model if OpenAI quota is exhausted.
        """
        messages = self._build_messages(prompt, custom_system_prompt=system_prompt)
        collected_chunks: List[str] = []

        # 1. Direct Free Mode
        if self.provider == "free" or not self.api_key or not self._client:
            for delta in self._stream_free_model(messages):
                collected_chunks.append(delta)
                yield delta

            full_response = "".join(collected_chunks)
            if remember:
                self.history.append({"role": "user", "content": prompt})
                self.history.append({"role": "assistant", "content": full_response})
            return full_response

        # 2. OpenAI API with Automatic Free Tier Fallback
        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    collected_chunks.append(delta)
                    yield delta
        except Exception as e:
            err_str = str(e)
            if "insufficient_quota" in err_str or "credit_balance_exhausted" in err_str or "429" in err_str:
                notice = "\n\033[93m[Notice: OpenAI credits exhausted (429). Seamlessly switching to Free Tier Model...]\033[0m\n\n"
                yield notice
                collected_chunks.append(notice)
                for delta in self._stream_free_model(messages):
                    collected_chunks.append(delta)
                    yield delta
            else:
                err_msg = f"\n[OpenAI API Error]: {e}"
                yield err_msg
                collected_chunks.append(err_msg)

        full_response = "".join(collected_chunks)
        if remember:
            self.history.append({"role": "user", "content": prompt})
            self.history.append({"role": "assistant", "content": full_response})

        return full_response

    def ask(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        remember: bool = False,
    ) -> str:
        """Synchronous prompt execution."""
        deltas = []
        for d in self.stream_prompt(prompt, system_prompt=system_prompt, remember=remember):
            deltas.append(d)
        return "".join(deltas)

    def review_code(
        self,
        file_path: str | Path,
        focus_area: Optional[str] = None,
        stream: bool = True,
    ) -> Generator[str, None, str] | str:
        """Performs forensic algorithmic code review of a file."""
        p = Path(file_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Target code file not found: {p}")

        code_text = p.read_text(encoding="utf-8", errors="replace")
        focus_clause = f"Focus particularly on: {focus_area}\n" if focus_area else ""

        prompt = (
            f"Please conduct an adversarial code and architecture review of the following file: `{p.name}`.\n"
            f"{focus_clause}\n"
            f"```python\n{code_text}\n```\n\n"
            "Format your feedback with:\n"
            "1. Architectural & Logic Assessment\n"
            "2. Potential Bugs, Edge Cases, or Statutory Flaws\n"
            "3. Concurrency / State Invariant Risks\n"
            "4. Prioritized Actionable Recommendations (P0/P1/P2)\n"
        )

        if stream:
            return self.stream_prompt(prompt, remember=False)
        return self.ask(prompt, remember=False)

    def analyze_portfolio_state(
        self,
        state_file: Optional[Path] = None,
        db_file: Optional[Path] = None,
        stream: bool = True,
    ) -> Generator[str, None, str] | str:
        """Ingests live portfolio state & SQLite ledger and requests risk assessment."""
        target_state = state_file or (BASE_DIR / "data" / "live_portfolio_state.json")
        target_db = db_file or (BASE_DIR / "data" / "swing_portfolio_ledger.db")

        state_data = {}
        if target_state.exists():
            try:
                state_data = json.loads(target_state.read_text(encoding="utf-8"))
            except Exception as e:
                state_data = {"error": f"Failed to parse state file: {e}"}

        recent_trades = []
        if target_db.exists():
            try:
                conn = sqlite3.connect(str(target_db))
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT symbol, direction, quantity, entry_price, exit_price, gross_pnl, net_pnl, "
                    "total_friction, exit_reason, entry_time, exit_time FROM trade_journal "
                    "ORDER BY exit_time DESC LIMIT 10"
                ).fetchall()
                recent_trades = [dict(r) for r in rows]
                conn.close()
            except Exception as e:
                recent_trades = [{"error": f"Failed to read sqlite db: {e}"}]

        prompt = (
            "Here is the current live Algo Lab swing portfolio state and recent trade journal:\n\n"
            f"### Portfolio State:\n```json\n{json.dumps(state_data, indent=2)}\n```\n\n"
            f"### Recent Completed Trades:\n```json\n{json.dumps(recent_trades, indent=2)}\n```\n\n"
            "Please provide an institutional risk assessment and instructions for the upcoming trading session:\n"
            "1. Capital solvency & margin health check\n"
            "2. Sector concentration and exposure risk analysis\n"
            "3. Trailing stop / profit target health for any active positions\n"
            "4. Concrete pre-market instructions for the 15:00 IST EOD scan\n"
        )

        if stream:
            return self.stream_prompt(prompt, remember=False)
        return self.ask(prompt, remember=False)

    def get_trading_instructions(
        self,
        context: str,
        stream: bool = True,
    ) -> Generator[str, None, str] | str:
        """Formulates step-by-step trading desk instructions."""
        prompt = (
            f"User requests trading desk instructions for the following situation:\n\n"
            f"{context}\n\n"
            "Provide step-by-step institutional instructions with clear risk boundaries, "
            "sizing rules, stop-loss mechanisms, and execution timing."
        )

        if stream:
            return self.stream_prompt(prompt, remember=False)
        return self.ask(prompt, remember=False)
