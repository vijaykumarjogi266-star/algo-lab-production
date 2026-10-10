"""
Strategy SDK for Algo Strategy Pods
Provides BaseStrategy, OrderIntent signing, Redis market data feed connection,
and Broker Gateway client submission.
"""

import time
import uuid
import hmac
import hashlib
import json
import urllib.request
import urllib.error
from typing import List, Optional, Dict, Any

from oms_project.schemas import OrderIntent, OrderSide, OrderResult, OrderState


class StrategySDK:
    """SDK helper for Algo Strategy Pods."""

    def __init__(
        self,
        strategy_id: str,
        gateway_url: str = "http://broker_gateway:8000",
        redis_host: str = "redis",
        redis_port: int = 6379,
        pod_secret: str = "pod_secret_mean_reversion_10001",
    ):
        self.strategy_id = strategy_id
        self.gateway_url = gateway_url
        self.redis_host = redis_host
        self.redis_port = redis_port
        self.pod_secret = pod_secret
        self.is_connected_to_redis = False

    def connect_market_data_feed(self) -> bool:
        """Simulates connecting to internal Redis pub/sub market data feed."""
        # Simulated connection success in isolated internal network
        self.is_connected_to_redis = True
        return True

    def create_signed_intent(
        self,
        symbol: str,
        side: OrderSide,
        qty: float,
        price: float,
        request_id: Optional[str] = None,
    ) -> OrderIntent:
        req_id = request_id or f"REQ_{uuid.uuid4().hex[:12]}"
        now = time.time()
        expiry = now + 30.0

        # Sign intent locally in pod
        payload = f"{req_id}:{self.strategy_id}:{symbol}:{side.value}:{qty}:{price}:{now}"
        signature = hmac.new(
            self.pod_secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

        return OrderIntent(
            request_id=req_id,
            strategy_id=self.strategy_id,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            timestamp=now,
            expiry=expiry,
            signature=signature,
        )

    def submit_intent_to_gateway(self, intent: OrderIntent) -> OrderResult:
        """Submits OrderIntent directly to the Broker Gateway HTTP endpoint."""
        url = f"{self.gateway_url}/api/v1/orders"
        data_bytes = json.dumps(intent.model_dump()).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return OrderResult(**res_data)
        except urllib.error.HTTPError as e:
            err_data = json.loads(e.read().decode("utf-8"))
            return OrderResult(
                request_id=intent.request_id,
                order_id=f"REJ_{intent.request_id[:8]}",
                strategy_id=intent.strategy_id,
                symbol=intent.symbol,
                side=intent.side.value,
                qty=intent.qty,
                price=intent.price,
                status=OrderState.REJECTED,
                message=err_data.get("error", "Gateway HTTP Error"),
            )
        except Exception as e:
            # Fallback to local Gateway instance when running local demo loop without HTTP server
            if not hasattr(self, "_fallback_gateway"):
                from oms_project.gateway import BrokerGateway
                self._fallback_gateway = BrokerGateway()
                self._fallback_gateway.strategy_balances[self.strategy_id] = 100000.0
            return self._fallback_gateway.process_order_intent(intent)


class BaseStrategy:
    """Base Class for Quantitative Strategy Implementations."""

    def __init__(
        self,
        strategy_id: str,
        symbol: str,
        sdk: Optional[StrategySDK] = None,
    ):
        self.strategy_id = strategy_id
        self.symbol = symbol
        self.sdk = sdk or StrategySDK(strategy_id=strategy_id)
        self.price_history: List[float] = []
        self.allocated_capital: float = 100000.0
        self.conviction: float = 0.5

    def get_conviction(self) -> float:
        """Returns conviction score between 0.0 and 1.0 representing signal confidence."""
        return max(0.0, min(1.0, float(self.conviction)))

    def on_order_update(self, order_result: Any, allocated_capital: Optional[float] = None) -> None:
        """Update order status and allocated capital from CIO Coordinator."""
        if allocated_capital is not None:
            self.allocated_capital = float(allocated_capital)

    def on_tick(self, price: float, timestamp: float) -> Optional[OrderIntent]:
        """Override in strategy subclass."""
        raise NotImplementedError

