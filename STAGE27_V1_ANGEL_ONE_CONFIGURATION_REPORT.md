# STAGE 27 V1 ANGEL ONE CONFIGURATION REPORT

**Final Classification:** `ANGEL ONE NETWORK PATH BLOCKED`  
**Execution Timestamp:** 2026-09-24T03:35:30Z  
**Target Repository:** `/home/ubuntu/algolab`  
**V1 Baseline Commit:** `c506e5a9430d120f368905d1af430254b5eab814`  

---

## 1. Root-Cause Connectivity Analysis

- **DNS:** `SUCCESS` (Resolved `apiconnect.angelone.in` to `103.82.178.77`)
- **IPv4:** `TCP_TIMEOUT` (Outbound TCP SYN to `103.82.178.77:443` timed out with `errno=11` / EAGAIN)
- **IPv6:** `NONE_RESOLVED` (No IPv6 AAAA record exists for `apiconnect.angelone.in`)
- **TCP:** `TCP_FAILURE` (Connection to port 443 timed out)
- **TLS:** `TLS_SKIPPED` (TCP connection failed before TLS handshake)
- **HTTPS:** `HTTPS_SKIPPED` (Blocked at TCP socket layer)
- **Proxy:** `configured = NO` (No proxy environment variables set; direct socket connection)
- **Host:** Bare Host / VM (`enp0s6` interface, default gateway `10.0.0.1`)
- **Container:** `NOT_CONTAINERIZED` (Process running directly on bare host/VM)
- **Known HTTPS target:** 
  - `pypi.org:443` -> `REACHABLE` (2.55 ms latency)
  - `github.com:443` -> `REACHABLE` (23.3 ms latency)
- **SmartAPI code review:** `VERIFIED_CORRECT`
  - Root URL: `https://apiconnect.angelone.in` (Current production endpoint)
  - Login Route: `/rest/auth/angelbroking/user/v1/loginByPassword`
  - URL Construction & Headers: Correct per official SmartAPI SDK v1.5.5
  - Network Exception Handling: Correct (`urllib3`/`requests` timeouts correctly caught)
- **Root cause:** `UPSTREAM_NETWORK_FIREWALL_BLOCK` (Outbound TCP port 443 traffic to Angel One IP `103.82.178.77` is dropped upstream by cloud egress filtering or Angel One's regional IP geofencing).

---

## 2. Credential Store Verification

- **encrypted_persistence:** `VERIFIED` (`PBKDF2-HMAC-SHA256` + `HMAC-SHA256 AES-256`)
- **credential_reload:** `VERIFIED` (Reloaded cleanly from `SecureCredentialStore`)
- **required_fields:** `PRESENT` (`['api_key', 'client_code', 'password', 'totp_key']`)
- **Redaction & Leak Prevention:** `VERIFIED` (Zero credentials, passwords, TOTP secrets, or tokens printed or stored)

---

## 3. SmartAPI Authentication

- **Authentication Call Result:** `NETWORK_FAILURE` (Connection to `apiconnect.angelone.in:443` timed out; credentials are NOT classified as invalid)

---

## 4. WebSocket Status

- **WebSocket:** `NOT CONNECTED`
- **genuine_observations:** `0`

---

## 5. Forward Gate Status

- **calendar_days:** `0 / 30`
- **valid_NSE_sessions:** `0 / 20`
- **invalid_sessions:** `0`
- **excluded_sessions:** `0`
- **duplicate_sessions:** `0`
- **gate_status:** `INCOMPLETE`

---

## 6. Trading Security & Real-Money Locks

- **LIVE_TRADING_ENABLED:** `False`
- **REAL_BROKER_EXECUTION_ENABLED:** `False`
- **Live Order placement routes:** `0` (AST Scanner certified)
- **Paper-to-live bypasses:** `0`

---

## 7. Regression Test Results

- **Command Executed:** `PYTHONPATH=. .venv/bin/pytest tests/ -v`
- **Passed:** **199**
- **Skipped:** **1** (`test_production_repository_baseline_isolation` skipped cleanly when `/root/sandbox/algopro` is absent)
- **Failed:** **0**
- **Errors:** **0**
- **Duration:** **3.56s**
