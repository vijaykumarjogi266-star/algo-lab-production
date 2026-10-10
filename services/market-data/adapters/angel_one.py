"""
Angel One SmartAPI Market Data Provider Adapter.
Implements MarketDataProvider interface strictly for:
- Market observation
- Historical candlestick retrieval
- Real-time tick parsing (Smart Stream 2.0 binary and JSON)
- Quality gating and timestamp normalization

NON-NEGOTIABLE SAFETY CONSTRAINTS:
- ALLOW_LIVE_TRADING = False
- ALLOW_REAL_BROKER_EXECUTION = False
- Order placement, routing, modification, or cancellation are FORBIDDEN on this adapter.
- Secrets are NEVER logged, printed, or exported in plaintext.
- If upstream network firewall blocks apiconnect.angelone.in, the adapter fails closed
  and reports status BLOCKED with diagnostic root-cause metrics.
"""

import os
import sys
import time
import socket
import struct
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple, Iterator
from zoneinfo import ZoneInfo

from data.schemas.canonical_market_data import (
    CanonicalMarketDataBar,
    CanonicalMarketDataValidator,
)
from data.schemas.contracts import DataQualityStatus
from services.market_data.adapters.base import MarketDataProvider
from services.market_data.adapters.angel_one_instruments import (
    AngelOneInstrumentMaster,
    AngelOneInstrument,
)
from services.market_data.adapters.market_event_schemas import MarketTickEvent

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


class AngelOneMarketDataError(Exception):
    """Base exception for Angel One market data operations."""
    pass


class AngelOneNetworkBlockedError(AngelOneMarketDataError):
    """Raised when upstream network firewall prevents connection to Angel One."""
    pass


class AngelOneMarketDataAdapter(MarketDataProvider):
    """
    Market-data-only adapter for Angel One SmartAPI.
    Decoupled from order routing; real broker execution is strictly forbidden.
    """

    DEFAULT_REST_HOST = "https://apiconnect.angelone.in"
    DEFAULT_WS_HOST = "wss://smartapisocket.angelone.in/smart-stream"
    API_DOMAIN = "apiconnect.angelone.in"

    def __init__(
        self,
        api_key: Optional[str] = None,
        client_code: Optional[str] = None,
        password: Optional[str] = None,
        totp_key: Optional[str] = None,
        mock_mode: bool = False,
        allow_real_time_market_data: bool = False,
    ):
        self._api_key = api_key or os.environ.get("ANGEL_ONE_API_KEY", "")
        self._client_code = client_code or os.environ.get("ANGEL_ONE_CLIENT_CODE", "")
        self._password = password or os.environ.get("ANGEL_ONE_PASSWORD", "")
        self._totp_key = totp_key or os.environ.get("ANGEL_ONE_TOTP_KEY", "")
        
        self.mock_mode = mock_mode
        self.allow_real_time_market_data = allow_real_time_market_data

        # Strict hard invariants
        self.allow_live_trading = False
        self.allow_real_broker_execution = False

        # Session tokens (in-memory only, strictly unlogged)
        self._jwt_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._feed_token: Optional[str] = None
        self._token_issued_at: Optional[datetime] = None
        self._auth_retry_count: int = 0

        # Instrument registry
        self.instrument_master = AngelOneInstrumentMaster()

        # In-memory bar cache for query support
        self._cached_bars: Dict[str, List[CanonicalMarketDataBar]] = {}
        self._sequence_counter: int = 0

    @property
    def provider_name(self) -> str:
        return "angel_one"

    def __repr__(self) -> str:
        key_masked = f"{self._api_key[:2]}****{self._api_key[-4:]}" if len(self._api_key) > 6 else "NOT_CONFIGURED"
        client_masked = f"{self._client_code[:2]}****" if len(self._client_code) > 2 else "NOT_CONFIGURED"
        return (
            f"<AngelOneMarketDataAdapter(provider='{self.provider_name}', "
            f"api_key='{key_masked}', client_code='{client_masked}', "
            f"mock_mode={self.mock_mode}, allow_live_trading=False)>"
        )

    def __str__(self) -> str:
        return self.__repr__()

    # =========================================================================
    # SAFETY GUARDS & STRUCTURAL TRANSPORT FIREWALL
    # =========================================================================

    APPROVED_HOSTS = {
        "apiconnect.angelone.in",
        "smartapisocket.angelone.in",
        "margincalculator.angelone.in",
    }
    APPROVED_HTTP_METHODS = {"GET", "POST"}
    APPROVED_URL_PATHS = {
        "/rest/auth/angelbroking/user/v1/loginByPassword",
        "/rest/auth/angelbroking/jwt/v1/generateTokens",
        "/rest/secure/angelbroking/historical/v1/getCandleData",
        "/rest/secure/angelbroking/market/v1/quote",
        "/rest/secure/angelbroking/user/v1/getProfile",
        "/OpenAPI_File/files/OpenAPIScripMaster.json",
    }
    APPROVED_SUBSCRIPTION_ACTIONS = {0, 1}       # 0 = unsubscribe, 1 = subscribe
    APPROVED_SUBSCRIPTION_MODES = {1, 2, 3}      # 1 = LTP, 2 = Quote, 3 = SnapQuote
    APPROVED_EXCHANGE_SEGMENTS = {1}             # 1 = NSE Cash Market

    FORBIDDEN_PATH_SUBSTRINGS = (
        "order", "trade", "holding", "position", "fund", "gtt", "margin", "portfolio",
        "modify", "cancel", "place", "bracket", "cover", "amo"
    )

    def place_order(self, *args, **kwargs):
        raise PermissionError(
            "CRITICAL GOVERNANCE VIOLATION: AngelOneMarketDataAdapter is strictly market-data-only. "
            "Real broker order routing is completely forbidden in this environment."
        )

    def modify_order(self, *args, **kwargs):
        raise PermissionError("CRITICAL GOVERNANCE VIOLATION: Order modification forbidden.")

    def cancel_order(self, *args, **kwargs):
        raise PermissionError("CRITICAL GOVERNANCE VIOLATION: Order cancellation forbidden.")

    def validate_subscription_operation(
        self,
        action: int,
        mode: int,
        exchange_segment: int,
        tokens: List[str],
    ) -> bool:
        """
        Validates market-data subscription requests against strict structural allowlist:
        - action in {0, 1}
        - mode in {1, 2, 3}
        - exchange_segment in {1} (NSE CM)
        - all tokens present in verified instrument allowlist
        """
        if action not in self.APPROVED_SUBSCRIPTION_ACTIONS:
            raise PermissionError(f"STRUCTURAL TRANSPORT FIREWALL: Subscription action {action} is not permitted.")
        if mode not in self.APPROVED_SUBSCRIPTION_MODES:
            raise PermissionError(f"STRUCTURAL TRANSPORT FIREWALL: Subscription mode {mode} is not permitted.")
        if exchange_segment not in self.APPROVED_EXCHANGE_SEGMENTS:
            raise PermissionError(f"STRUCTURAL TRANSPORT FIREWALL: Exchange segment {exchange_segment} is not permitted.")
        if not tokens:
            raise ValueError("Subscription tokens list cannot be empty.")

        allowlist_tokens = set(self.instrument_master.get_allowlist_tokens())
        for tok in tokens:
            if str(tok).strip() not in allowlist_tokens:
                raise PermissionError(
                    f"STRUCTURAL TRANSPORT FIREWALL: Token '{tok}' is not in verified instrument allowlist."
                )
        return True

    def build_subscription_payload(
        self,
        action: int,
        mode: int,
        tokens: List[str],
        correlation_id: str = "stream_sub_01",
    ) -> Dict[str, Any]:
        """Builds validated, normalized Smart Stream 2.0 JSON subscription packet."""
        self.validate_subscription_operation(action, mode, exchange_segment=1, tokens=tokens)
        return {
            "correlationID": correlation_id,
            "action": action,
            "params": {
                "mode": mode,
                "tokenList": [
                    {
                        "exchangeType": 1,
                        "tokens": [str(t).strip() for t in tokens],
                    }
                ],
            },
        }

    def _execute_safe_market_data_request(
        self,
        method: str,
        path_or_url: str,
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Structural Transport Firewall (Principle 13: Fail-Closed).
        Enforces:
        1. Exact match against approved HTTPS/WSS hosts.
        2. Exact match against approved HTTP methods (GET, POST only).
        3. Exact match against approved market-data endpoint whitelist.
        4. Absolute prohibition of order/trade/holding/fund keywords.
        5. Strict rejection of HTTP redirects to prevent open-redirect routing bypasses.
        """
        import requests
        from urllib.parse import urlparse

        # 1. Method verification
        method_upper = method.upper().strip()
        if method_upper not in self.APPROVED_HTTP_METHODS:
            raise PermissionError(
                f"STRUCTURAL TRANSPORT FIREWALL: Method '{method_upper}' is not an approved HTTP method."
            )

        # 2. Host & Path normalization
        if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
            parsed = urlparse(path_or_url)
            host = parsed.netloc
            clean_path = parsed.path
            if host not in self.APPROVED_HOSTS:
                raise PermissionError(
                    f"STRUCTURAL TRANSPORT FIREWALL: Destination host '{host}' is not in approved hosts: {self.APPROVED_HOSTS}"
                )
            target_url = f"https://{host}{clean_path}"
        else:
            clean_path = path_or_url.split("?")[0].strip()
            # Normalize trailing slashes if present
            if len(clean_path) > 1 and clean_path.endswith("/"):
                clean_path = clean_path.rstrip("/")
            if clean_path == "/OpenAPI_File/files/OpenAPIScripMaster.json":
                target_url = f"https://margincalculator.angelone.in{clean_path}"
            else:
                target_url = f"{self.DEFAULT_REST_HOST}{clean_path}"

        # 3. Path allowlist check
        if clean_path not in self.APPROVED_URL_PATHS:
            raise PermissionError(
                f"STRUCTURAL TRANSPORT FIREWALL: Endpoint '{clean_path}' is not an approved market-data endpoint. Request blocked."
            )

        # 4. Prohibited keywords safeguard
        clean_path_lower = clean_path.lower()
        for forbidden in self.FORBIDDEN_PATH_SUBSTRINGS:
            if forbidden in clean_path_lower:
                raise PermissionError(
                    f"STRUCTURAL TRANSPORT FIREWALL: Forbidden keyword '{forbidden}' detected in path '{clean_path}'. Request blocked."
                )

        # 5. Outbound request with redirect rejection
        try:
            if method_upper == "POST":
                resp = requests.post(target_url, json=payload, headers=headers, timeout=timeout, allow_redirects=False)
            else:
                resp = requests.get(target_url, params=payload, headers=headers, timeout=timeout, allow_redirects=False)

            if resp.status_code in (301, 302, 307, 308):
                raise PermissionError("STRUCTURAL TRANSPORT FIREWALL: Outbound HTTP redirects are strictly forbidden.")

            return resp.json()
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Network transport error to {self.API_DOMAIN}: {type(e).__name__}")

    # =========================================================================
    # AUTHENTICATION & TOKEN LIFECYCLE
    # =========================================================================

    def is_authenticated(self) -> bool:
        if self.mock_mode:
            return True
        if not self._jwt_token or not self._token_issued_at:
            return False
        # Check token age (24 hour max validity)
        age = datetime.now(timezone.utc) - self._token_issued_at
        return age.total_seconds() < 86000

    def authenticate(self) -> Dict[str, Any]:
        """
        Attempts authentication with Angel One SmartAPI.
        Fails safely without raising unhandled crashes on network blocks.
        """
        if self.mock_mode:
            self._jwt_token = "mock_jwt_token_for_offline_simulation"
            self._feed_token = "mock_feed_token_for_offline_simulation"
            self._token_issued_at = datetime.now(timezone.utc)
            return {
                "status": "AUTHENTICATED_MOCK",
                "connected": True,
                "message": "Authenticated in offline deterministic mock mode",
            }

        # Check credentials presence
        if not (self._api_key and self._client_code and self._password and self._totp_key):
            return {
                "status": "CREDENTIALS_UNAVAILABLE",
                "connected": False,
                "message": "Angel One credentials missing or incomplete. Human configuration required.",
            }

        # Check network path before attempting socket call
        net_check = self.diagnose_network_path()
        if not net_check["tcp_connected"]:
            return {
                "status": "BLOCKED_BY_NETWORK_EGRESS",
                "connected": False,
                "message": "Outbound TCP connection to Angel One gateway (apiconnect.angelone.in:443) timed out.",
                "diagnostics": net_check,
            }

        # Genuine authentication call via requests
        try:
            import requests
            import pyotp

            totp_code = pyotp.TOTP(self._totp_key).now()
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-UserType": "USER",
                "X-SourceID": "WEB",
                "X-PrivateKey": self._api_key,
            }
            payload = {
                "clientcode": self._client_code,
                "password": self._password,
                "totp": totp_code,
            }

            data = self._execute_safe_market_data_request(
                "POST",
                "/rest/auth/angelbroking/user/v1/loginByPassword",
                payload=payload,
                headers=headers,
            )

            if data.get("status") is True and "data" in data:
                token_data = data["data"]
                self._jwt_token = token_data.get("jwtToken")
                self._refresh_token = token_data.get("refreshToken")
                self._feed_token = token_data.get("feedToken")
                self._token_issued_at = datetime.now(timezone.utc)
                self._auth_retry_count = 0
                return {
                    "status": "AUTHENTICATED",
                    "connected": True,
                    "message": "Successfully authenticated with Angel One SmartAPI",
                }
            else:
                err_code = data.get("errorcode", "UNKNOWN")
                return {
                    "status": "AUTHENTICATION_FAILED",
                    "connected": False,
                    "error_code": err_code,
                    "message": "Broker authentication rejected credentials or TOTP.",
                }
        except Exception as e:
            return {
                "status": "EXCEPTION",
                "connected": False,
                "message": f"Authentication attempt encountered network exception: {type(e).__name__}",
            }

    def refresh_session_token(self) -> bool:
        """
        Refreshes expired jwtToken using refreshToken.
        Bounded to max 2 retries; transitions to safe failure if refresh fails.
        """
        if self.mock_mode:
            return True
        if not self._refresh_token or self._auth_retry_count >= 2:
            return False

        self._auth_retry_count += 1
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-PrivateKey": self._api_key,
            "Authorization": f"Bearer {self._refresh_token}",
        }
        try:
            data = self._execute_safe_market_data_request(
                "POST",
                "/rest/auth/angelbroking/jwt/v1/generateTokens",
                payload={"refreshToken": self._refresh_token},
                headers=headers,
            )
            if data.get("status") is True and "data" in data:
                self._jwt_token = data["data"].get("jwtToken")
                self._refresh_token = data["data"].get("refreshToken", self._refresh_token)
                self._feed_token = data["data"].get("feedToken", self._feed_token)
                self._token_issued_at = datetime.now(timezone.utc)
                self._auth_retry_count = 0
                return True
        except Exception:
            pass
        return False

    # =========================================================================
    # NETWORK DIAGNOSTIC
    # =========================================================================

    def diagnose_network_path(self, timeout_seconds: float = 2.0) -> Dict[str, Any]:
        """Runs isolated DNS and TCP latency probe to apiconnect.angelone.in."""
        diag = {
            "domain": self.API_DOMAIN,
            "port": 443,
            "dns_resolved": False,
            "ip_address": None,
            "tcp_connected": False,
            "latency_ms": None,
            "error": None,
        }
        try:
            ip = socket.gethostbyname(self.API_DOMAIN)
            diag["dns_resolved"] = True
            diag["ip_address"] = ip
        except Exception as e:
            diag["error"] = f"DNS resolution failed: {e}"
            return diag

        start_t = time.perf_counter()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_seconds)
        try:
            sock.connect((ip, 443))
            diag["tcp_connected"] = True
            diag["latency_ms"] = round((time.perf_counter() - start_t) * 1000.0, 2)
        except Exception as e:
            diag["error"] = f"TCP SYN timeout or connection refused: {type(e).__name__}"
        finally:
            sock.close()

        return diag

    def test_connection(self) -> Dict[str, Any]:
        """
        Tests connectivity and credentials with Angel One.
        Conforms strictly to MarketDataProvider interface contract.
        """
        if self.mock_mode:
            return {
                "status": "CONNECTED_MOCK",
                "message": "Angel One Market Data Provider operating in mock mode",
                "connected": True,
                "latency_ms": 0.5,
                "instrument_count": len(self.instrument_master.list_allowlist_symbols()),
            }

        diag = self.diagnose_network_path()
        if not diag["tcp_connected"]:
            return {
                "status": "BLOCKED_BY_NETWORK_EGRESS",
                "message": (
                    f"Outbound connection to {self.API_DOMAIN}:443 timed out. "
                    "Upstream cloud egress filtering or broker geofencing active."
                ),
                "connected": False,
                "diagnostics": diag,
            }

        auth_res = self.authenticate()
        return auth_res

    # =========================================================================
    # MARKET DATA RETRIEVAL (REST CANDLES & BARS)
    # =========================================================================

    def seed_canonical_bars(self, symbol: str, bars: List[CanonicalMarketDataBar]):
        """Seeds deterministic bars for testing and simulation."""
        sym = symbol.upper().replace(".NS", "")
        self.instrument_master.resolve_token_strict(sym)
        val = CanonicalMarketDataValidator.validate_series(bars)
        if not val.is_valid:
            raise ValueError(f"Seeded bars failed canonical validation: {val.errors}")
        self._cached_bars[sym] = sorted(bars, key=lambda b: b.timestamp)

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> List[CanonicalMarketDataBar]:
        """Retrieves and normalizes market data bars into canonical schema."""
        sym = symbol.upper().replace(".NS", "")
        token = self.instrument_master.resolve_token_strict(sym)

        # Check local cache first (mock or seeded)
        if sym in self._cached_bars:
            bars = self._cached_bars[sym]
            return [b for b in bars if start_time <= b.timestamp <= end_time]

        if self.mock_mode:
            return self._generate_synthetic_bars(sym, timeframe, start_time, end_time)

        # In live mode without network connection, fail closed
        if not self.is_authenticated():
            auth_res = self.authenticate()
            if not auth_res.get("connected"):
                raise AngelOneNetworkBlockedError(f"Market data unavailable: {auth_res.get('message')}")

        # Query Angel One getCandleData endpoint
        return self._fetch_live_candles(sym, token, timeframe, start_time, end_time)

    def get_latest_bar(self, symbol: str) -> Optional[CanonicalMarketDataBar]:
        """Retrieves the latest available canonical bar."""
        sym = symbol.upper().replace(".NS", "")
        self.instrument_master.resolve_token_strict(sym)

        if sym in self._cached_bars and self._cached_bars[sym]:
            return self._cached_bars[sym][-1]

        now = datetime.now(timezone.utc)
        bars = self.get_bars(sym, "1m", now - timedelta(minutes=5), now)
        return bars[-1] if bars else None

    def _generate_synthetic_bars(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CanonicalMarketDataBar]:
        """Generates deterministic mock bars for offline simulation."""
        base_prices = {
            "SBIN": 820.0,
            "RELIANCE": 2950.0,
            "TCS": 4150.0,
            "ITC": 490.0,
            "HAL": 4650.0,
            "INFY": 1880.0,
        }
        base_price = base_prices.get(symbol, 1000.0)
        bars = []
        cur_t = start_time
        step = timedelta(minutes=5 if "5m" in timeframe else 60 if "1h" in timeframe else 1)

        idx = 0
        while cur_t <= end_time:
            # Deterministic wave
            drift = (idx % 10 - 5) * 0.5
            o = round(base_price + drift, 2)
            h = round(o + 2.0, 2)
            l = round(o - 1.5, 2)
            c = round(o + 0.5, 2)
            v = 1500.0 + (idx % 5) * 200.0

            bar = CanonicalMarketDataBar(
                timestamp=cur_t,
                symbol=symbol,
                exchange="NSE",
                timeframe=timeframe,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=v,
                turnover=round(c * v, 2),
                quality_status=DataQualityStatus.VALID,
            )
            bars.append(bar)
            cur_t += step
            idx += 1

        return bars

    def _fetch_live_candles(
        self,
        symbol: str,
        token: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[CanonicalMarketDataBar]:
        """Queries Angel One historical candle REST endpoint and converts to canonical bars."""
        import requests

        tf_map = {
            "1m": "ONE_MINUTE",
            "5m": "FIVE_MINUTE",
            "15m": "FIFTEEN_MINUTE",
            "1h": "ONE_HOUR",
            "1d": "ONE_DAY",
        }
        interval = tf_map.get(timeframe, "FIVE_MINUTE")

        # Format timestamps in IST format expected by Angel One: "YYYY-MM-DD HH:MM"
        from_str = start_time.astimezone(IST).strftime("%Y-%m-%d %H:%M")
        to_str = end_time.astimezone(IST).strftime("%Y-%m-%d %H:%M")

        payload = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": interval,
            "fromdate": from_str,
            "todate": to_str,
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-PrivateKey": self._api_key,
            "Authorization": f"Bearer {self._jwt_token}",
        }

        data = self._execute_safe_market_data_request(
            "POST",
            "/rest/secure/angelbroking/historical/v1/getCandleData",
            payload=payload,
            headers=headers,
        )

        # Handle token expiry AG8001
        if data.get("errorcode") == "AG8001":
            if self.refresh_session_token():
                headers["Authorization"] = f"Bearer {self._jwt_token}"
                data = self._execute_safe_market_data_request(
                    "POST",
                    "/rest/secure/angelbroking/historical/v1/getCandleData",
                    payload=payload,
                    headers=headers,
                )

        if not data.get("status") or "data" not in data or not data["data"]:
            return []

        canonical_bars = []
        for row in data["data"]:
            # Format: [timestamp_str, open, high, low, close, volume]
            dt_raw = row[0]
            # Parse IST timestamp string
            dt_ist = datetime.fromisoformat(dt_raw.replace("Z", "+05:30")) if "T" in dt_raw else datetime.strptime(dt_raw, "%Y-%m-%d %H:%M").replace(tzinfo=IST)
            dt_utc = dt_ist.astimezone(timezone.utc)

            bar = CanonicalMarketDataBar(
                timestamp=dt_utc,
                symbol=symbol,
                exchange="NSE",
                timeframe=timeframe,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                quality_status=DataQualityStatus.VALID,
            )
            canonical_bars.append(bar)

        return canonical_bars

    # =========================================================================
    # REAL-TIME TICK PARSER (SMART STREAM 2.0 PROTOCOL)
    # =========================================================================

    def parse_smart_stream_binary(self, packet: bytes) -> Optional[MarketTickEvent]:
        """
        Parses binary packet emitted by Angel One Smart Stream 2.0 WebSocket.
        
        Binary Structure:
        - Mode 1 (LTP): 8 bytes
        - Mode 2 (Quote): 34 bytes
        - Mode 3 (SnapQuote): 114+ bytes
        
        Prices are scaled in paise (1 INR = 100 paise).
        """
        if len(packet) < 8:
            return None

        # Mode byte
        sub_mode = packet[0]
        # Exchange segment (1 = NSE CM)
        exch_seg = packet[1]
        
        # Token string is at offset 2 (up to 25 bytes null-terminated)
        token_bytes = packet[2:27]
        token_str = token_bytes.split(b"\x00")[0].decode("ascii", errors="ignore").strip()

        inst = self.instrument_master.get_by_token(token_str)
        symbol = inst.symbol if inst else token_str

        receive_time = datetime.now(timezone.utc)
        self._sequence_counter += 1

        # Mode 1: LTP only
        if sub_mode == 1 and len(packet) >= 16:
            # Unpack sequence (int64), timestamp (int64), ltp (int64 in paise)
            ltp_paise = struct.unpack_from("<q", packet, offset=27)[0]
            ltp_inr = round(ltp_paise / 100.0, 2)
            
            return MarketTickEvent(
                provider=self.provider_name,
                symbol=symbol,
                token=token_str,
                exchange="NSE",
                exchange_timestamp=receive_time,
                receive_timestamp=receive_time,
                sequence_id=self._sequence_counter,
                last_traded_price=ltp_inr,
                last_traded_quantity=1,
                cumulative_volume=0,
                subscription_mode=1,
            )

        # Mode 2: Quote (includes LTQ, ATP, Volume)
        if sub_mode == 2 and len(packet) >= 42:
            ltp_paise = struct.unpack_from("<q", packet, offset=27)[0]
            ltq = struct.unpack_from("<q", packet, offset=35)[0]
            atp_paise = struct.unpack_from("<q", packet, offset=43)[0] if len(packet) >= 51 else ltp_paise
            vol = struct.unpack_from("<q", packet, offset=51)[0] if len(packet) >= 59 else 0

            return MarketTickEvent(
                provider=self.provider_name,
                symbol=symbol,
                token=token_str,
                exchange="NSE",
                exchange_timestamp=receive_time,
                receive_timestamp=receive_time,
                sequence_id=self._sequence_counter,
                last_traded_price=round(ltp_paise / 100.0, 2),
                last_traded_quantity=max(1, int(ltq)),
                cumulative_volume=max(0, int(vol)),
                average_traded_price=round(atp_paise / 100.0, 2) if atp_paise > 0 else None,
                subscription_mode=2,
            )

        return None

    def parse_json_tick(self, data: Dict[str, Any]) -> Optional[MarketTickEvent]:
        """Parses JSON format tick payload from websocket or REST quote."""
        token = str(data.get("token") or data.get("symbolToken") or "")
        inst = self.instrument_master.get_by_token(token)
        symbol = inst.symbol if inst else str(data.get("tradingSymbol", "UNKNOWN"))

        ltp = float(data.get("ltp") or data.get("lastPrice") or 0.0)
        if ltp <= 0.0:
            return None

        # Price scaling handling: If price is > 10,000 for SBIN or ITC, it was sent in paise
        if symbol in ["SBIN", "ITC"] and ltp > 10000.0:
            ltp = round(ltp / 100.0, 2)

        receive_time = datetime.now(timezone.utc)
        self._sequence_counter += 1

        return MarketTickEvent(
            provider=self.provider_name,
            symbol=symbol,
            token=token,
            exchange="NSE",
            exchange_timestamp=receive_time,
            receive_timestamp=receive_time,
            sequence_id=self._sequence_counter,
            last_traded_price=ltp,
            last_traded_quantity=int(data.get("ltq", 1)),
            cumulative_volume=int(data.get("volume", 0)),
            average_traded_price=float(data.get("atp")) if data.get("atp") else None,
            total_turnover_inr=float(data.get("turnover")) if data.get("turnover") else None,
            best_bid=float(data.get("best_bid")) if data.get("best_bid") else None,
            best_ask=float(data.get("best_ask")) if data.get("best_ask") else None,
            subscription_mode=int(data.get("mode", 2)),
        )

    def generate_mock_ticks(
        self,
        symbols: List[str],
        count_per_symbol: int = 5,
        start_price: float = 1000.0
    ) -> Iterator[MarketTickEvent]:
        """Emits deterministic ticks for end-to-end pipeline verification."""
        now = datetime.now(timezone.utc)
        for sym in symbols:
            token = self.instrument_master.resolve_token_strict(sym)
            p = start_price
            cum_vol = 10000
            for i in range(count_per_symbol):
                p = round(p + (i % 2 * 2 - 1) * 0.5, 2)
                cum_vol += 50
                self._sequence_counter += 1
                tick_time = now + timedelta(seconds=i)
                yield MarketTickEvent(
                    provider=self.provider_name,
                    symbol=sym,
                    token=token,
                    exchange="NSE",
                    exchange_timestamp=tick_time,
                    receive_timestamp=tick_time,
                    sequence_id=self._sequence_counter,
                    last_traded_price=p,
                    last_traded_quantity=25,
                    cumulative_volume=cum_vol,
                    best_bid=round(p - 0.05, 2),
                    best_ask=round(p + 0.05, 2),
                    subscription_mode=2,
                    quality_status=DataQualityStatus.VALID,
                )
