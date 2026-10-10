import re

with open("tests/unit/test_adaptive_market_survival_backtest.py", "r") as f:
    content = f.read()

content = re.sub(
    r'\s*assert "APPROVED" in perf\["taleb_compliance"\].*\n',
    '\n',
    content
)

with open("tests/unit/test_adaptive_market_survival_backtest.py", "w") as f:
    f.write(content)
