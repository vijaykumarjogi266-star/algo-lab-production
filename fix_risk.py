import re
import math

with open("live_market_daemon.py", "r") as f:
    content = f.read()

risk_old = """                    # 1% fixed-fractional risk per trade
                    total_equity = self.cash + sum(p.quantity * p.current_price for p in self.positions.values())
                    risk_capital = total_equity * self.risk_per_trade_pct
                    if stop_distance <= 0.0:
                        continue
                    shares_by_risk = int(risk_capital / stop_distance)
                    max_spend = min(self.max_capital_per_position, self.cash - 10000.0)
                    shares_by_cash = int(max_spend / price)
                    qty = max(0, min(shares_by_risk, shares_by_cash))"""

risk_new = """                    import math
                    if not (math.isfinite(price) and math.isfinite(atr14) and math.isfinite(stop_distance)):
                        continue
                    if price <= 0 or stop_distance <= 0.0 or atr14 <= 0:
                        continue

                    # 1% fixed-fractional risk per trade
                    total_equity = self.cash + sum(p.quantity * p.current_price for p in self.positions.values())
                    if not math.isfinite(total_equity) or total_equity <= 0:
                        continue
                        
                    risk_capital = total_equity * self.risk_per_trade_pct
                    shares_by_risk = int(risk_capital / stop_distance)
                    
                    # Respect cash limits: preserve a configurable minimum cash reserve
                    min_cash_reserve = getattr(self, "min_cash_reserve", 10000.0)
                    max_spend = min(self.max_capital_per_position, max(0.0, self.cash - min_cash_reserve))
                    shares_by_cash = int(max_spend / price)
                    
                    qty = max(0, min(shares_by_risk, shares_by_cash))"""

content = content.replace(risk_old, risk_new)
with open("live_market_daemon.py", "w") as f:
    f.write(content)
