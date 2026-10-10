"""
Angel One SmartAPI Instrument Master & Token Mapping Registry.
Maintains authoritative mappings between canonical equity symbols and Angel One numeric tokens.
Versioned with deterministic SHA-256 cryptographic digests.
"""

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Dict, Optional, List, Any


@dataclass(frozen=True)
class AngelOneInstrument:
    symbol: str             # Canonical symbol: "SBIN"
    trading_symbol: str     # Angel One broker symbol: "SBIN-EQ"
    token: str              # Angel One numeric token: "3045"
    exchange: str           # "NSE"
    series: str             # "EQ"
    tick_size: float        # 0.05
    lot_size: int           # 1
    isin: str               # International Securities Identification Number


class AngelOneInstrumentMaster:
    """
    Versioned registry for Angel One SmartAPI equity instruments.
    Rejects unresolved or ambiguous instruments.
    """

    VERSION = "2026-09-25.v1"
    
    # Authoritative allowlist for core NSE cash equities
    _CORE_REGISTRY: Dict[str, AngelOneInstrument] = {
        "SBIN": AngelOneInstrument(
            symbol="SBIN",
            trading_symbol="SBIN-EQ",
            token="3045",
            exchange="NSE",
            series="EQ",
            tick_size=0.10,
            lot_size=1,
            isin="INE062A01020",
        ),
        "RELIANCE": AngelOneInstrument(
            symbol="RELIANCE",
            trading_symbol="RELIANCE-EQ",
            token="2885",
            exchange="NSE",
            series="EQ",
            tick_size=0.10,
            lot_size=1,
            isin="INE002A01018",
        ),
        "TCS": AngelOneInstrument(
            symbol="TCS",
            trading_symbol="TCS-EQ",
            token="11536",
            exchange="NSE",
            series="EQ",
            tick_size=0.10,
            lot_size=1,
            isin="INE467B01029",
        ),
        "ITC": AngelOneInstrument(
            symbol="ITC",
            trading_symbol="ITC-EQ",
            token="1660",
            exchange="NSE",
            series="EQ",
            tick_size=0.05,
            lot_size=1,
            isin="INE154A01025",
        ),
        "HAL": AngelOneInstrument(
            symbol="HAL",
            trading_symbol="HAL-EQ",
            token="2303",
            exchange="NSE",
            series="EQ",
            tick_size=0.10,
            lot_size=1,
            isin="INE066F01012",
        ),
        "INFY": AngelOneInstrument(
            symbol="INFY",
            trading_symbol="INFY-EQ",
            token="1594",
            exchange="NSE",
            series="EQ",
            tick_size=0.10,
            lot_size=1,
            isin="INE009A01021",
        ),
    }

    def __init__(self):
        self._by_symbol: Dict[str, AngelOneInstrument] = dict(self._CORE_REGISTRY)
        self._by_token: Dict[str, AngelOneInstrument] = {inst.token: inst for inst in self._CORE_REGISTRY.values()}
        self._by_trading_symbol: Dict[str, AngelOneInstrument] = {inst.trading_symbol: inst for inst in self._CORE_REGISTRY.values()}

    @property
    def version(self) -> str:
        return self.VERSION

    @property
    def sha256_checksum(self) -> str:
        """Deterministic digest of registered instruments."""
        payload = json.dumps([asdict(self._by_symbol[k]) for k in sorted(self._by_symbol.keys())], sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_by_symbol(self, symbol: str) -> Optional[AngelOneInstrument]:
        """Resolves by canonical symbol e.g. 'SBIN' or 'SBIN.NS'."""
        clean = symbol.upper().replace(".NS", "").strip()
        return self._by_symbol.get(clean)

    def get_by_token(self, token: str) -> Optional[AngelOneInstrument]:
        """Resolves by Angel One numeric token string e.g. '3045'."""
        return self._by_token.get(str(token).strip())

    def get_by_trading_symbol(self, trading_symbol: str) -> Optional[AngelOneInstrument]:
        """Resolves by broker symbol e.g. 'SBIN-EQ'."""
        return self._by_trading_symbol.get(trading_symbol.upper().strip())

    def resolve_token_strict(self, symbol: str) -> str:
        """Resolves symbol to numeric token or raises ValueError."""
        inst = self.get_by_symbol(symbol)
        if not inst:
            raise ValueError(f"Unresolved or unmapped instrument '{symbol}'. Not in Angel One allowlist.")
        return inst.token

    def resolve_symbol_strict(self, token: str) -> str:
        """Resolves token to canonical symbol or raises ValueError."""
        inst = self.get_by_token(token)
        if not inst:
            raise ValueError(f"Unresolved or unmapped token '{token}'. Not in Angel One allowlist.")
        return inst.symbol

    def list_allowlist_symbols(self) -> List[str]:
        return sorted(list(self._by_symbol.keys()))

    def get_allowlist_tokens(self) -> List[str]:
        """Returns sorted list of all approved numeric instrument tokens."""
        return sorted(list(self._by_token.keys()))

    def list_all_instruments(self) -> List[Dict[str, Any]]:
        return [asdict(inst) for inst in self._CORE_REGISTRY.values()]
