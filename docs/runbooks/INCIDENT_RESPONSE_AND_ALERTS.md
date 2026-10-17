# Algo Lab Incident Response, Observability & Alerting Runbook

## Document Control

| Attribute | Details |
|---|---|
| **Document ID** | `RUNBOOK-SRE-005` |
| **Title** | Production Incident Response & Alert Triage Runbook |
| **Owner** | Site Reliability & Observability Engineering (SRE) / Quantitative Operations |
| **System Version** | `0.3.0` |
| **Lifecycle State** | `forward-paper-validation` (Strictly Paper-Only) |
| **Last Reviewed** | 2026-10-14 |
| **Classification** | Internal Production Operations Manual |
| **Companion Runbook** | [`RUNBOOK-OPS-001` (Operational Handover & Procedures)](OPERATIONAL_HANDOVER_AND_PROCEDURES.md) |


---

## 1. Objectives & Operational Principles

Algo Lab is an institutional quantitative research and algorithmic trading platform designed for autonomous intraday scanning, decision evaluation, and simulated paper execution under real Indian market (NSE) conditions. 

When anomalous conditions occur, the system and operating engineers must adhere to four non-negotiable operational principles:

1. **Fail-Closed by Design**: If system state, data freshness, or network connectivity is ambiguous, trading decisions must immediately halt or default to cash (`HOLD` / `WAIT`). Never force a trade.
2. **Capital Preservation First**: Risk limits, circuit breakers, and drawdowns supersede strategy profit goals. Circuit breakers trigger immediate, irrevocable trading pauses.
3. **Strict Paper-Only Invariant**: Production live broker capital execution is strictly prohibited (`ALLOW_LIVE_TRADING=False`, `REAL_BROKER_EXECUTION_ENABLED=False`). Any attempt or drift towards live order routing constitutes an emergency P0 security and compliance incident.
4. **Zero Unverified State**: All portfolio ledgers, backups, and metrics must be cryptographically verified (SHA-256) and traceable through immutable audit logs.

---

## 2. Incident Severity Classification Framework

Incidents are classified into four severity tiers based on operational impact, invariant integrity, and capital safety:

| Severity | Priority | Definition & Threshold Criteria | Response SLA | Mitigation SLA | Escalation Target |
|---|---|---|---|---|---|
| **Critical** | **P0** | **Invariant Breach or Circuit Breaker Trip**: Direct threat to platform integrity, live trading violation attempt (`algolab_live_trading_enabled == 1`), circuit breaker activation (`algolab_circuit_breaker_active == 1`), database corruption, or double-entry ledger imbalance. | **< 2 min** | **< 5 min** (Emergency Halt) | Primary On-Call SRE, Lead Quant Engineer, Chief Risk Officer (CRO) |
| **High** | **P1** | **Operational Blackout During Market Hours**: Autonomous market daemon heartbeat lost between 09:15-15:30 IST (`algolab_daemon_heartbeat_timestamp > 300s`), core REST API liveness failure (`/health` unreachable > 1m), primary data feed severed, or active authorization brute-force / token leakage spike. | **< 5 min** | **< 15 min** | Primary On-Call SRE, Senior Quantitative Systems Developer |
| **Medium** | **P2** | **Degraded Telemetry or Risk Rejection Spike**: Stale market data rejections exceeding 10 in 5 minutes, independent risk engine rejections exceeding 20 in 5 minutes, automated disaster recovery backup drill failure, or rate limiter threshold warnings. | **< 15 min** | **< 2 hours** | Secondary SRE, Infrastructure Engineer |
| **Low** | **P3** | **Non-Critical Telemetry Degradation**: Minor metric scrape timeouts, non-blocking disk capacity warnings (>80%), background task retry events, or cosmetic dashboard display anomalies. | **< 1 hour** | **Next Business Day** | SRE General Backlog |

---

## 3. Incident Escalation Path & Communication Procedures

### 3.1 On-Call Roster & Escalation Matrix

```
[Prometheus Alertmanager / Sentry Probe]
                 │
                 ▼
       ┌──────────────────┐
       │  On-Call SRE     │  <-- Acknowledges within SLA (P0: 2m, P1: 5m)
       └─────────┬────────┘
                 │ (Unacknowledged after 5m OR P0 Invariant Breach)
                 ▼
       ┌──────────────────┐
       │ Lead Quant Eng   │  <-- Assumes Incident Commander (IC) Role
       └─────────┬────────┘
                 │ (P0 Circuit Breaker / Capital Safety / Security)
                 ▼
       ┌──────────────────┐
       │ Chief Risk Off.  │  <-- Final Authority on Trading Resumption
       └──────────────────┘
```

| Escalation Level | Role | Notification Channel | Failover Trigger |
|---|---|---|---|
| **Level 1** | Primary On-Call SRE | PagerDuty / Telegram (`@algolab_ops_bot`) / SMS | 3 minutes without acknowledgement |
| **Level 2** | Lead Quantitative Systems Engineer | Dedicated Incident War Room / Direct Call | 7 minutes without mitigation |
| **Level 3** | Chief Risk Officer (CRO) & Engineering Lead | Direct Urgent Phone Call / Encrypted Channel | Mandatory for any P0 incident |

### 3.2 War Room & Incident Protocol

1. **War Room Activation**: For any P0 or P1 incident, the on-call engineer immediately opens the `#incident-war-room` channel on Slack/Telegram and initiates a voice bridge.
2. **Designate Incident Commander (IC)**: The highest-ranking engineer on the call becomes the IC, managing communication and assigning triage tasks.
3. **Status Broadcasting Cadence**:
   - **P0**: Broadcast status updates to `#engineering-alerts` every **15 minutes**.
   - **P1**: Broadcast status updates every **30 minutes**.
4. **Standard Broadcast Format**:
   ```text
   🚨 [INCIDENT UPDATE] - [P0/P1] - [Alert Name]
   Status: INVESTIGATING | IDENTIFIED | MITIGATING | RESOLVED
   Impact: [Brief summary of affected services and portfolio impact]
   Incident Commander: @username
   Current Actions: [Key operational steps underway]
   Next Update: [Timestamp, e.g., 10:15 UTC]
   ```

---

## 4. Emergency System Halt Command & Quarantine Protocol

When an invariant breach, rogue process, or uncontained circuit breaker trip is detected, the on-call engineer **must immediately execute the emergency system halt sequence**. Do not hesitate or attempt code edits before halting runtime execution.

### 4.1 The Emergency System Halt Sequence

Execute the following commands sequentially on the host:

```bash
# ==============================================================================
# STEP 1: IMMEDIATELY HALT AUTONOMOUS TRADING DAEMON
# ==============================================================================
sudo systemctl stop quant-os.service

# Verify daemon process is completely dead:
pgrep -f "live_market_daemon.py" || echo "✅ Daemon halted successfully."

# ==============================================================================
# STEP 2: HALT API GATEWAY & PREVENT EXTERNAL MUTATIONS
# ==============================================================================
cd /home/ubuntu/algolab
docker compose stop api proxy

# ==============================================================================
# STEP 3: AUDIT NON-NEGOTIABLE SAFETY INVARIANTS (FAIL-CLOSED VERIFICATION)
# ==============================================================================
make safety-check

# Expected Output:
# ==> [1/7] Auditing Non-Negotiable Safety Invariants...
# ✅ ALL SAFETY INVARIANTS CERTIFIED: 100% PAPER-ONLY COMPLIANCE.
```

### 4.2 Quarantine & Forensic State Preservation

If an invariant violation or live execution attempt was detected:
1. **Preserve Runtime State**: Do NOT delete log files or databases. Copy runtime state immediately:
   ```bash
   mkdir -p /home/ubuntu/incident_forensics_$(date +%Y%m%d_%H%M%S)
   cp -r /home/ubuntu/algolab/data /home/ubuntu/incident_forensics_$(date +%Y%m%d_%H%M%S)/
   cp -r /home/ubuntu/algolab/logs /home/ubuntu/incident_forensics_$(date +%Y%m%d_%H%M%S)/
   ```
2. **Inspect Process List**:
   ```bash
   ps aux | grep -E "python3|algolab" | grep -v grep
   ```
3. **Hold State until CRO Approval**: The system must remain quarantined until root cause is identified and written approval from the CRO is documented.

---

## 5. Step-by-Step Triage and Mitigation Procedures

### 5.1 `ApiLivenessFailure`

- **Severity**: P1 (High)
- **PromQL**: `up{job="algolab-api"} == 0`
- **Trigger**: The `/health` endpoint has been unreachable or returning non-200 responses for > 1 minute.
- **Impact**: Clients, automated scanners, health probes, and the Web UI cannot communicate with the platform backend.

#### Triage Steps
1. **Check Docker Container State**:
   ```bash
   docker ps -a --filter "name=algolab-api"
   ```
2. **Inspect API Logs**:
   ```bash
   docker logs --tail 100 algolab-api
   ```
   *Look for: Python exceptions, OOM-killer terminations, or database connection errors.*
3. **Probe Direct Loopback Liveness**:
   ```bash
   curl -iv http://127.0.0.1:8000/health
   ```
4. **Check PostgreSQL Health**:
   ```bash
   docker exec -it algolab-postgres pg_isready -U algolab -d algolab
   ```
5. **Inspect Host Memory & OOM Logs**:
   ```bash
   dmesg -T | grep -i -E "oom|killed process" | tail -n 20
   ```

#### Mitigation & Resolution
1. **If Container Crashed / Stalled**:
   ```bash
   docker compose restart api
   ```
2. **If PostgreSQL is Unreachable**:
   ```bash
   docker compose restart postgres
   # Wait for postgres healthcheck to pass, then restart api:
   docker compose restart api
   ```
3. **If Out-of-Memory (OOM)**:
   - Temporarily increase container memory limit in `docker-compose.yml` (e.g. from 2048M to 3072M).
   - Reload containers: `docker compose up -d`
4. **Verification**:
   ```bash
   curl -s http://127.0.0.1:8000/health | jq .
   # Expected: {"status":"healthy","version":"0.3.0",...}
   ```

---

### 5.2 `DaemonHeartbeatLost`

- **Severity**: P1 (High)
- **PromQL**:
  ```promql
  (time() - algolab_daemon_heartbeat_timestamp > 300)
    and on() (
      (hour() == 3 and minute() >= 45)
      or (hour() > 3 and hour() < 10)
      or (hour() == 10 and minute() <= 0)
    )
    and on() (day_of_week() >= 1 and day_of_week() <= 5)
  ```
- **Trigger**: `algolab_daemon_heartbeat_timestamp` is older than 5 minutes during active Indian market hours (09:15-15:30 IST, Monday-Friday).
- **Impact**: Intraday market scanner, regime classifier, and trailing stop loss engines are halted. Risk management exits may fail to execute.

#### Triage Steps
1. **Check Systemd Service Status**:
   ```bash
   sudo systemctl status quant-os.service
   ```
2. **Inspect Service Logs**:
   ```bash
   journalctl -u quant-os.service -n 100 --no-pager
   ```
3. **Check Daemon Log File**:
   ```bash
   tail -n 100 /home/ubuntu/algolab/logs/daemon.log
   ```
4. **Check for Stale Process Lock**:
   ```bash
   ls -la /tmp/algolab_daemon.lock
   cat /tmp/algolab_daemon.lock
   ```
5. **Verify Outbound Broker / Market Data Connectivity**:
   ```bash
   python3 /home/ubuntu/algolab/scripts/diagnose_network.py
   ```

#### Mitigation & Resolution
1. **If Service Stopped or Failed**:
   ```bash
   sudo systemctl restart quant-os.service
   ```
2. **If Lockfile Stale (Process Crashed Without Cleanup)**:
   ```bash
   # Confirm no zombie daemon is running:
   ps aux | grep live_market_daemon.py
   # If no process exists, remove stale lock:
   sudo rm -f /tmp/algolab_daemon.lock
   sudo systemctl start quant-os.service
   ```
3. **If Process Hung on Socket Timeout**:
   - Check if Angel One / Yahoo Finance endpoints are experiencing throttling or DNS failures.
   - Force restart:
     ```bash
     sudo systemctl kill -s SIGKILL quant-os.service
     sudo systemctl start quant-os.service
     ```
4. **Verification**:
   ```bash
   curl -s http://127.0.0.1:8000/metrics | grep algolab_daemon_heartbeat_timestamp
   # Confirm epoch timestamp is within < 30 seconds of current time: date +%s
   ```

---

### 5.3 `CircuitBreakerTripped`

- **Severity**: P0 (Critical)
- **PromQL**: `algolab_circuit_breaker_active == 1`
- **Trigger**: Global portfolio risk engine has activated the circuit breaker.
- **Impact**: All order generation and strategy executions are immediately halted. System is locked in safe mode.

#### Triage Steps
1. **Inspect Active Circuit Breaker Trigger Reason**:
   ```bash
   cat /home/ubuntu/algolab/data/live_portfolio_state.json | jq .circuit_breaker
   ```
2. **Check Current Portfolio Drawdown & P&L**:
   ```bash
   cat /home/ubuntu/algolab/data/live_portfolio_state.json | jq '{drawdown: .current_drawdown_pct, max_loss: .daily_loss, pnl: .realized_pnl}'
   ```
3. **Review Audit Logs for Triggering Trade**:
   ```bash
   tail -n 100 /home/ubuntu/algolab/logs/risk_engine.log
   ```
4. **Check Market-Wide Index Volatility**:
   - Verify if NIFTY 50 / BANKNIFTY hit an exchange lower/upper circuit band.

#### Mitigation & Resolution
1. **DO NOT blindly reset the circuit breaker**.
2. **Review Open Paper Positions**:
   ```bash
   python3 -c "
   import sqlite3, json
   conn = sqlite3.connect('/home/ubuntu/algolab/data/swing_portfolio_ledger.db')
   print(conn.execute('SELECT symbol, quantity, entry_price, current_price, unrealized_pnl FROM positions WHERE status=\"OPEN\"').fetchall())
   "
   ```
3. **Evaluate Invalidation Condition**:
   - If circuit breaker was triggered by a legitimate risk limit breach (e.g. 5% daily drawdown reached), **the system must remain halted for the remainder of the trading day**.
   - If triggered by erroneous market data tick (bad spike), verify historical tick register:
     ```bash
     python3 scripts/diagnose_network.py
     ```
4. **Controlled System Reset (Requires CRO Approval)**:
   ```bash
   # Only after documented RCA and sign-off:
   python3 -c "
   import json
   with open('data/live_portfolio_state.json', 'r+') as f:
       d = json.load(f)
       d['circuit_breaker_active'] = False
       f.seek(0)
       json.dump(d, f, indent=2)
       f.truncate()
   print('Circuit breaker reset recorded.')
   "
   make safety-check
   sudo systemctl restart quant-os.service
   ```
5. **Verification**:
   ```bash
   curl -s http://127.0.0.1:8000/metrics | grep algolab_circuit_breaker_active
   # Must return: algolab_circuit_breaker_active 0
   ```

---

### 5.4 `PaperOnlyViolationAttempt`

- **Severity**: P0 (Critical - Invariant Breach)
- **PromQL**: `algolab_live_trading_enabled == 1`
- **Trigger**: System detected that live trading configuration flag has been set to true (`algolab_live_trading_enabled == 1`).
- **Impact**: Immediate regulatory and capital safety violation. Potential for unauthorized real broker order placement.

#### Triage Steps
1. **IMMEDIATELY EXECUTE EMERGENCY HALT**:
   ```bash
   sudo systemctl stop quant-os.service
   docker compose stop api
   ```
2. **Audit Environment Variables**:
   ```bash
   env | grep -E "LIVE_TRADING|ALLOW_LIVE|REAL_BROKER"
   grep -E "ALLOW_LIVE_TRADING|REAL_BROKER" /home/ubuntu/algolab/.env
   ```
3. **Inspect Systemd Unit Environment**:
   ```bash
   grep -E "ALLOW_LIVE_TRADING" /home/ubuntu/algolab/quant-os.service
   ```
4. **Inspect Git Revision Log for Unauthorized Modifications**:
   ```bash
   git status
   git log -n 5 --stat
   ```

#### Mitigation & Resolution
1. **Force Environment Settings to False**:
   ```bash
   sed -i 's/ALLOW_LIVE_TRADING=.*/ALLOW_LIVE_TRADING=False/g' /home/ubuntu/algolab/.env
   sed -i 's/REAL_BROKER_EXECUTION_ENABLED=.*/REAL_BROKER_EXECUTION_ENABLED=False/g' /home/ubuntu/algolab/.env
   sed -i 's/LIVE_TRADING_ENABLED=.*/LIVE_TRADING_ENABLED=false/g' /home/ubuntu/algolab/docker-compose.yml
   ```
2. **Run Safety Invariant Test Suite**:
   ```bash
   make safety-check
   ```
   *If `make safety-check` fails with non-zero exit code, do not start any services.*
3. **Audit Broker API Keys**:
   - Check if real credentials exist in `.env`. Replace any live credentials with dummy paper keys.
4. **Verification**:
   ```bash
   docker compose up -d api proxy
   curl -s http://127.0.0.1:8000/metrics | grep algolab_live_trading_enabled
   # Must return: algolab_live_trading_enabled 0
   ```

---

### 5.5 `DataStalenessSpike`

- **Severity**: P2 (Medium)
- **PromQL**: `increase(algolab_stale_data_rejections_total[5m]) > 10`
- **Trigger**: Market data quality engine rejected more than 10 ticks/bars in 5 minutes due to stale timestamps.
- **Impact**: The decision engine will reject signal evaluation and default to cash (`WAIT`), resulting in missed trading setups.

#### Triage Steps
1. **Check System Host Time Synchronization (NTP)**:
   ```bash
   timedatectl status
   # Check 'NTP service: active' and 'System clock synchronized: yes'
   ```
2. **Test Upstream Provider Latency**:
   ```bash
   python3 scripts/diagnose_network.py
   ```
3. **Inspect Market Data Quality Logs**:
   ```bash
   tail -n 100 /home/ubuntu/algolab/logs/market_data.log | grep -i "stale"
   ```
4. **Check Broker WebSocket Feed Status**:
   - Verify if Angel One / provider WebSocket is dropping frames or buffering.

#### Mitigation & Resolution
1. **If Host Clock Drift Detected**:
   ```bash
   sudo systemctl restart systemd-timesyncd
   timedatectl timesync-status
   ```
2. **If Upstream Data Provider Lagging**:
   - Verify whether issue is symbol-specific or market-wide.
   - Switch market data adapter to secondary fallback:
     ```bash
     # Inspect services/market-data/adapters/
     # Verify Yahoo Finance / Basex secondary ingestion
     python3 scripts/bounded_market_data_smoke_test.py
     ```
3. **Verification**:
   ```bash
   # Monitor rate of increase:
   watch -n 10 "curl -s http://127.0.0.1:8000/metrics | grep algolab_stale_data_rejections_total"
   # Counter should stop incrementing.
   ```

---

### 5.6 `RiskRejectionSpike`

- **Severity**: P2 (Medium)
- **PromQL**: `increase(algolab_risk_rejections_total[5m]) > 20`
- **Trigger**: Independent risk engine rejected more than 20 candidate trade signals within 5 minutes.
- **Impact**: Indicates a rogue strategy generating unviable orders, excessive sizing, or market parameters drifting outside acceptable risk envelopes.

#### Triage Steps
1. **Inspect Risk Engine Rejection Reasons**:
   ```bash
   tail -n 100 /home/ubuntu/algolab/logs/risk_engine.log | grep -i "reject"
   ```
   *Common triggers:*
   - `EXCESSIVE_LEVERAGE`: Requested position exceeds account margin limits.
   - `SECTOR_CONCENTRATION_BREACH`: Over-allocation in single industry sector.
   - `ORDER_RATE_LIMIT`: Strategy generating > 10 orders per minute.
   - `SPREAD_TOO_WIDE`: Bid-ask spread exceeds 0.5% threshold.
2. **Identify Offending Strategy**:
   - Check which strategy runner is submitting signals (`STRATEGY_SUPER_ADAPTIVE`, `STRATEGY_RSI_SWING`, etc.).

#### Mitigation & Resolution
1. **If Runaway Signal Generation Loop**:
   - Pause the offending strategy via configuration or restart the daemon with the conservative baseline:
     ```bash
     sudo systemctl stop quant-os.service
     # Edit /home/ubuntu/algolab/quant-os.service:
     # Environment="DAEMON_STRATEGY=STRATEGY_BASELINE_SAFE"
     sudo systemctl daemon-reload
     sudo systemctl start quant-os.service
     ```
2. **If Spread / Volatility Widening Due to Market Open/Close**:
   - Normal widening occurs at 09:15-09:20 IST. Verify if alert clears after initial market liquidity settles.
3. **Verification**:
   ```bash
   curl -s http://127.0.0.1:8000/metrics | grep algolab_risk_rejections_total
   ```

---

### 5.7 `BackupFailure`

- **Severity**: P2 (Medium)
- **PromQL**: `algolab_backup_restore_drill_status == 0 or increase(algolab_backup_restore_drill_failures_total[1h]) > 0`
- **Trigger**: Automated disaster recovery backup creation, checksum verification, or sandbox restore drill failed.
- **Impact**: RPO / RTO SLA guarantees compromised. Loss of validated disaster recovery capability.

#### Triage Steps
1. **Run Manual Sandbox Restore Test Drill**:
   ```bash
   python3 /home/ubuntu/algolab/scripts/backup_restore.py --test-restore
   ```
2. **Check Available Disk Space**:
   ```bash
   df -h /home/ubuntu/algolab
   ```
3. **Inspect Backup Directory & Permissions**:
   ```bash
   ls -la /home/ubuntu/algolab/backups/
   ```
4. **Verify Ledger Database Integrity**:
   ```bash
   sqlite3 /home/ubuntu/algolab/data/swing_portfolio_ledger.db "PRAGMA integrity_check;"
   # Expected output: ok
   ```

#### Mitigation & Resolution
1. **If Disk Space Full**:
   - Clean old logs and cache:
     ```bash
     make clean
     find /home/ubuntu/algolab/logs -name "*.log.*" -mtime +7 -delete
     ```
2. **If Database Locked by Zombie Process**:
   ```bash
   fuser /home/ubuntu/algolab/data/swing_portfolio_ledger.db
   ```
3. **Create New Verified Encrypted Backup**:
   ```bash
   python3 /home/ubuntu/algolab/scripts/backup_restore.py --create --retention-days 30
   ```
4. **Verify Integrity of the Fresh Archive**:
   ```bash
   LATEST_BACKUP=$(ls -t /home/ubuntu/algolab/backups/*.tar.enc | head -n 1)
   python3 /home/ubuntu/algolab/scripts/backup_restore.py --verify "$LATEST_BACKUP"
   ```
5. **Verification**:
   ```bash
   python3 /home/ubuntu/algolab/scripts/backup_restore.py --test-restore
   # Expected output: ✅ [Automated Restore Test PASSED] 2 files restored and validated.
   ```

---

### 5.8 `AuthorizationFailureSpike`

- **Severity**: P1 (High)
- **PromQL**: `increase(algolab_http_auth_failures_total[5m]) > 10 or rate(http_requests_total{status=~"401|403"}[5m]) > 0.5`
- **Trigger**: Elevated rate of HTTP 401 Unauthorized or 403 Forbidden responses over a 5-minute window.
- **Impact**: Potential credential stuffing attack, brute-force key probe, or stale client API key configuration causing system degradation.

#### Triage Steps
1. **Inspect Nginx Access Log for Attack Vectors**:
   ```bash
   tail -n 200 /var/log/nginx/access.log | grep -E '"status":(401|403)'
   ```
2. **Extract Top Offending Client IP Addresses**:
   ```bash
   tail -n 1000 /var/log/nginx/access.log | awk -F'"client_ip":"' '{print $2}' | awk -F'"' '{print $1}' | sort | uniq -c | sort -nr | head -n 10
   ```
3. **Check Targeted URI Endpoints**:
   ```bash
   tail -n 500 /var/log/nginx/access.log | grep -E '"status":(401|403)' | awk -F'"uri":"' '{print $2}' | awk -F'"' '{print $1}' | sort | uniq -c | sort -nr
   ```
4. **Verify Internal Key Expiration**:
   - Check if internal automation services are using expired or revoked API keys:
     ```bash
     grep -rn "X-API-Key" /home/ubuntu/algolab/scripts/
     ```

#### Mitigation & Resolution
1. **If Malicious External IP Identified**:
   - Immediately block offending IP using Linux `iptables`:
     ```bash
     sudo iptables -I INPUT -s <OFFENDING_IP> -j DROP
     ```
2. **If Internal API Key Compromised or Leaked**:
   - Rotate the secret key in `.env`:
     ```bash
     NEW_KEY="algolab_sec_$(openssl rand -hex 16)"
     sed -i "s/INTERNAL_API_SECRET=.*/INTERNAL_API_SECRET=$NEW_KEY/g" /home/ubuntu/algolab/.env
     docker compose restart api
     ```
3. **If Internal Service Out of Sync**:
   - Update client scripts with rotated key from `.env`.
4. **Verification**:
   ```bash
   # Verify error rate drops to zero:
   curl -s http://127.0.0.1:8000/metrics | grep algolab_http_auth_failures_total
   ```

---

## 6. Disaster Recovery & Emergency Rollback Playbook

When catastrophic failure occurs (e.g. data volume corruption, failed database migration, unrecoverable state drift), execute the full disaster recovery procedure:

```bash
# 1. STOP ALL RUNNING SERVICES
sudo systemctl stop quant-os.service
cd /home/ubuntu/algolab
docker compose down

# 2. IDENTIFY AND VERIFY LATEST KNOWN GOOD BACKUP
LATEST_BACKUP=$(ls -t backups/*.tar.enc | head -n 1)
echo "Inspecting backup: $LATEST_BACKUP"
python3 scripts/backup_restore.py --verify "$LATEST_BACKUP"

# 3. RESTORE DATA FILES INTO PRODUCTION DIRECTORY
python3 scripts/backup_restore.py --restore "$LATEST_BACKUP" --target-dir /home/ubuntu/algolab/data/

# 4. RUN SYSTEM INTEGRITY & SAFETY CERTIFICATION
make safety-check
make test

# 5. RESTART DOCKER INFRASTRUCTURE & AUTONOMOUS DAEMON
docker compose up -d
sleep 5
sudo systemctl start quant-os.service

# 6. VERIFY SYSTEM HEALTH PROBES
curl -s http://127.0.0.1:8000/health/ready | jq .
```

---

## 7. Post-Mortem Policy & Root Cause Analysis (RCA) Protocol

### 7.1 Blameless Culture & Guiding Principles
Algo Lab enforces a strictly blameless post-mortem culture. Incidents are treated as systematic learning opportunities to harden architectural guardrails, improve automated testing, and refine operational observability. Retrospective inquiries focus on system design vulnerabilities, human-in-the-loop UX failures, and tooling gaps rather than individual mistake allocation.

### 7.2 Mandatory Trigger Criteria
A formal Root Cause Analysis (RCA) document is mandatory for:
- Any **P0** incident (Circuit Breaker trip, Live Trading Invariant violation attempt, Ledger corruption).
- Any **P1** incident lasting longer than 15 minutes.
- Any unexpected loss of market state or unexplained simulation order divergence.

### 7.3 Timeline & SLA Requirements
1. **Initial Notification**: Within 30 minutes of incident resolution.
2. **Draft RCA Document**: Produced within **24 hours**.
3. **Review Meeting**: Conducted with SRE, Quant Lead, and Risk Officer within **48 hours**.
4. **Action Item Completion**: High-priority remediation tasks completed within **7 business days**.

---

## 8. Root Cause Analysis (RCA) Template

All incident post-mortems must be drafted using the following markdown template and archived in `docs/post-mortems/YYYY-MM-DD-incident-title.md`:

```markdown
# Incident Post-Mortem: [INCIDENT TITLE]

## 1. Executive Summary
- **Incident Date**: YYYY-MM-DD
- **Severity**: P0 / P1 / P2
- **Duration**: [e.g., 23 minutes]
- **Incident Commander**: [Name/Handle]
- **Participating Engineers**: [Names]
- **Service Affected**: [e.g., live_market_daemon, api, postgres]
- **Business Impact**: [Describe trading simulation impact, skipped cycles, or invariant risk]

## 2. Incident Timeline (UTC & IST)
| UTC Time | IST Time | Event / Action Taken | Actor |
|---|---|---|---|
| 03:45:00 | 09:15:00 | Initial anomalous state occurred | System |
| 03:47:12 | 09:17:12 | Prometheus alert fired: DaemonHeartbeatLost | Prometheus |
| 03:48:30 | 09:18:30 | On-call SRE paged and acknowledged | @sre_lead |
| 03:52:00 | 09:22:00 | System halted using emergency sequence | @sre_lead |
| 04:05:00 | 09:35:00 | Root cause identified; patch applied | @quant_eng |
| 04:08:00 | 09:38:00 | System verified and restored to service | @sre_lead |

## 3. Root Cause Analysis (The 5 Whys)
1. **Why did the alert fire?**
   - The daemon heartbeat was not updated for > 5 minutes during market hours.
2. **Why was the heartbeat not updated?**
   - The main daemon execution loop was blocked on an HTTP request.
3. **Why was the HTTP request blocked?**
   - The market data provider endpoint timed out without triggering a socket timeout.
4. **Why did it not trigger a socket timeout?**
   - The HTTP client connection timeout was unset (defaulted to infinite).
5. **Why was the timeout unset?**
   - A recent refactoring omitted explicit `timeout=5.0` parameter in the adapter call.

## 4. What Worked / What Failed
### What Went Well
- Prometheus alert fired promptly within 2 minutes of condition onset.
- Emergency halt command cleanly stopped the daemon without state corruption.
- Team assembled in `#incident-war-room` within 3 minutes.

### What Went Wrong
- Alert annotations lacked direct link to socket diagnostic script.
- Stale lockfile required manual removal rather than automated PID verification.

### Where We Got Lucky
- Occurrence happened outside peak volatility window; zero simulated positions were open.

## 5. Preventative & Corrective Action Items
| ID | Action Item | Type | Owner | Target Date | Ticket / PR |
|---|---|---|---|---|---|
| ACT-01 | Enforce default timeout on all HTTP/WebSocket client sessions | Preventative | @quant_dev | YYYY-MM-DD | #1234 |
| ACT-02 | Add automated PID liveness check to acquire_lock utility | Hardening | @sre_eng | YYYY-MM-DD | #1235 |
| ACT-03 | Add synthetic network timeout unit test to test suite | Testing | @qa_eng | YYYY-MM-DD | #1236 |

## 6. Approvals & Sign-Off
- **Lead SRE**: ___________________________ Date: ___________
- **Lead Quant Engineer**: _________________ Date: ___________
- **Chief Risk Officer**: __________________ Date: ___________
```
