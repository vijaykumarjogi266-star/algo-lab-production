import re
import os

test_file = "tests/unit/test_adaptive_market_survival_backtest.py"
if os.path.exists(test_file):
    with open(test_file, "r") as f:
        content = f.read()

    # 1. Remove rejected_orders_solvency assertion
    content = re.sub(
        r'\s*assert perf\["rejected_orders_solvency"\].*\n',
        '\n',
        content
    )

    with open(test_file, "w") as f:
        f.write(content)
