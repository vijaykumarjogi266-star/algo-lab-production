import re
with open('oms_project/tests/test_concurrent_risk_reservation.py', 'r') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if 'gw.reservation_service...' in line:
        if 'REQ_NL_' in lines[i+3]:
            lines[i] = '        gw.reservation_service.accounts_initial_capital[account_id] = 100.0\n'
        else:
            lines[i] = '        gw.reservation_service.accounts_initial_capital[account_id] = 100000.0\n'
    elif 'gw.strategy_balances...' in line:
        if 'REQ_NL_' in lines[i+2]:
            lines[i] = '        gw.strategy_balances[account_id] = 100.0\n'
        else:
            lines[i] = '        gw.strategy_balances[account_id] = 100000.0\n'
with open('oms_project/tests/test_concurrent_risk_reservation.py', 'w') as f:
    f.writelines(lines)
