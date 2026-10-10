import re

with open("tests/unit/test_adaptive_market_survival_backtest.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip() == 'assert "rsi_7_prev" in df_proc.columns':
        new_lines.append('    assert "rsi_7_prev" in df_proc.columns\n')
    else:
        new_lines.append(line)

with open("tests/unit/test_adaptive_market_survival_backtest.py", "w") as f:
    f.writelines(new_lines)
