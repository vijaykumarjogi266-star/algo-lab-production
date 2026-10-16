#!/bin/bash
# Runner for AlgoLab Intraday Survival & Hybrid Engine
# Segment: INTRADAY ONLY (10k Base + 5x Leverage = 50k Buying Power)

VENV_PY="/home/ubuntu/algolab/.venv/bin/python3"
SCRIPT="/home/ubuntu/algolab/services/intraday_survival_daemon.py"
INSPECTOR="/home/ubuntu/algolab/scripts/get_intraday_pnl.py"

case "$1" in
  start)
    echo "Starting Intraday Survival Daemon in background..."
    nohup $VENV_PY $SCRIPT > /home/ubuntu/algolab/logs/intraday_daemon_run.log 2>&1 &
    echo "Started with PID $!"
    ;;
  status)
    $VENV_PY $INSPECTOR
    ;;
  eod)
    echo "Triggering EOD Review & Ledger Audit Generation..."
    $VENV_PY $SCRIPT --eod-review
    LATEST_MD=$(ls -t /home/ubuntu/algolab/data/reports/EOD_INTRADAY_REVIEW_*.md 2>/dev/null | head -1)
    if [ -f "$LATEST_MD" ]; then
      echo ""
      cat "$LATEST_MD"
    fi
    ;;
  openclaw-review)
    echo "Triggering OpenClaw Daily Review & Recommendations..."
    $VENV_PY $SCRIPT --openclaw-review
    ;;
  emergency-kill)
    echo "🚨 EXECUTING EMERGENCY PANIC BUTTON (100% FLATTEN)..."
    $VENV_PY /home/ubuntu/algolab/scripts/emergency_kill.py
    ;;
  reconcile)
    echo "Auditing broker positions against ledger..."
    $VENV_PY $SCRIPT --reconcile
    ;;
  tx)
    echo "--- RECENT INTRADAY TRANSACTIONS & CAPITAL AUDIT ---"
    $VENV_PY -c "
import sqlite3
conn = sqlite3.connect('/home/ubuntu/algolab/data/intraday_ledger.db')
c = conn.cursor()
c.execute('SELECT timestamp_ist, tx_type, symbol, quantity, price, turnover, allocated_margin, cash_after, buying_power_utilized_pct, notes FROM intraday_transaction_log ORDER BY timestamp_utc DESC LIMIT 20;')
rows = c.fetchall()
if not rows:
    print('No transactions logged yet.')
else:
    for r in rows:
        print(f'{r[0]} | {r[1]:<18} | {r[2]:<10} | Qty: {r[3]:>3} @ ₹{r[4]:>7.2f} | Turn: ₹{r[5]:>9,.2f} | Cash: ₹{r[7]:>8,.2f} ({r[8]:>4.1f}% util) | {r[9]}')
"
    ;;
  run)
    $VENV_PY $SCRIPT
    ;;
  *)
    echo "AlgoLab Intraday Controller"
    echo "Usage: $0 {status|eod|openclaw-review|emergency-kill|reconcile|tx|start|run}"
    ;;
esac
