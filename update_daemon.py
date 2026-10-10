import re
import sys

with open("live_market_daemon.py", "r") as f:
    content = f.read()

# 1. Update rename Ed Thorp -> 1% fixed-fractional risk per trade
content = content.replace("Ed Thorp 1% capital risk sizing", "1% fixed-fractional risk per trade")
content = content.replace("Ed Thorp 1% risk sizing", "1% fixed-fractional risk per trade")

# 2. Risk checks on stop distance
risk_code = """
                    # 1% fixed-fractional risk per trade
                    total_equity = self.cash + sum(p.quantity * p.current_price for p in self.positions.values())
                    risk_capital = total_equity * self.risk_per_trade_pct
                    if stop_distance <= 0.0:
                        continue
                    shares_by_risk = int(risk_capital / stop_distance)
                    max_spend = min(self.max_capital_per_position, self.cash - 10000.0)
                    shares_by_cash = int(max_spend / price)
                    qty = max(0, min(shares_by_risk, shares_by_cash))
                    
                    if qty == 0:
                        continue
"""
content = re.sub(r'# 1% fixed-fractional risk per trade.*?qty = max\(1, min\(shares_by_risk, shares_by_cash\)\)', risk_code.strip(), content, flags=re.DOTALL)

with open("live_market_daemon.py", "w") as f:
    f.write(content)
