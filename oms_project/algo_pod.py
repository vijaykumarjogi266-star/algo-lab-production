"""
OMS Project - Algo Strategy Pod Client
Generates signed OrderIntent requests and sends them strictly to the Broker Gateway.
Has NO exchange API keys and NO egress network access to external brokers.
"""

import time
import uuid
import hmac
import hashlib
from oms_project.schemas import OrderIntent, OrderSide, OrderResult


class AlgoStrategyPod:
    def __init__(self, strategy_id: str, pod_secret: str = "pod_secret_123"):
        self.strategy_id = strategy_id
        self.pod_secret = pod_secret

    def create_order_intent(
        self,
        symbol: str,
        side: OrderSide,
        qty: float,
        price: float,
        request_id: str = None,
    ) -> OrderIntent:
        req_id = request_id or str(uuid.uuid4())
        now = time.time()
        expiry = now + 30.0

        # Sign the intent payload locally inside the Algo Pod
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
