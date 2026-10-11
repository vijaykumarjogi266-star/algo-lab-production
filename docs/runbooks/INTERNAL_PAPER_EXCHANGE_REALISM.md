# Runbook: Internal Paper Exchange Realism & Adverse Profile Testing

## 1. Scope & Objective
This runbook guides operators and developers in running, configuring, and verifying the enhanced internal paper exchange in Algo Lab.
The paper exchange serves as an execution simulation engine providing microstructural realism without connecting to any external network or live broker.

## 2. Configuration & Profiles
Execution realism is parameterized by `AdverseExecutionProfile` in `oms_project/paper_exchange.py`:

```python
from decimal import Decimal
from oms_project.paper_exchange import PaperExchange, AdverseExecutionProfile

# Example: Stress profile with partial fills and high slippage
profile = AdverseExecutionProfile(
    name="HIGH_VOL_STRESS",
    base_spread_bps=Decimal("10.0"),
    linear_slippage_factor=Decimal("0.0005"),
    fee_bps=Decimal("3.0"),
    fixed_fee_per_order=Decimal("20.0"),
    fill_mode="PARTIAL",
    partial_fill_ratio=Decimal("0.5"),
    max_participation_rate=Decimal("0.10"),
    reject_unfunded_reduce_only=True
)

exchange = PaperExchange(profile=profile)
```

### Supported Fill Modes
- `IMMEDIATE`: Full fill if limits/spread permit.
- `PARTIAL`: Deterministic partial fill based on `partial_fill_ratio`.
- `NO_FILL`: Execution drops/rejection simulating illiquidity.

### Order Book & Queue Mechanics
- `LIMIT` orders rest in the exchange book (`bid_book` / `ask_book`) until marketable against incoming tick updates.
- FIFO priority is maintained across price buckets.

## 3. Session End Auto-Cancellation (EOD Close)
To simulate intraday exchange behavior:
```python
exchange.on_session_close()
```
All open limit orders are cancelled, and any reserved risk capital in the gateway is released cleanly.

## 4. Sensitivity Matrix Generation
To evaluate strategies against adverse execution matrices:
```python
results = exchange.generate_sensitivity_matrix(
    spread_range=[Decimal("1.0"), Decimal("5.0"), Decimal("10.0")],
    slippage_factors=[Decimal("0.0"), Decimal("0.0001"), Decimal("0.0005")],
    base_price=Decimal("100.0"),
    qty=Decimal("100"),
    order_type="MARKET",
    side="BUY"
)
```

## 5. Verification Commands
To execute the comprehensive realism test suite:
```bash
PYTHONPATH=. .venv/bin/pytest oms_project/tests/test_paper_exchange_realism.py -q
```
Verify zero regressions across all modules:
```bash
PYTHONPATH=. .venv/bin/pytest oms_project/tests/ -q
```
