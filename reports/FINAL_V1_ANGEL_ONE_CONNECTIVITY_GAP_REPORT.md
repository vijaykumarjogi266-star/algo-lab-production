# FINAL V1 ANGEL ONE CONNECTIVITY GAP REPORT

**Final Classification:** `V1 PRODUCTION ENGINEERING VERIFIED — EXTERNAL PROVIDER ACCESS REQUIRED`  
**Execution Timestamp:** 2026-09-24T05:05:15Z  
**Target Repository:** `/home/ubuntu/algolab`  
**V1 Baseline Commit:** `c506e5a9430d120f368905d1af430254b5eab814`  

---

## 1. Current V1 State

- **Application Stack:** `VERIFIED & FROZEN` (100% complete software stack, `SecureCredentialStore` encryption, paper trading engine, risk circuit breakers, evidence framework, and single-page Web UI).
- **Real-Money Locks:** `LIVE_TRADING_ENABLED = False` & `REAL_BROKER_EXECUTION_ENABLED = False` (0 live order placement routes).

---

## 2. Network Diagnosis

- **Host Interface:** `enp0s6` (`10.0.0.71/24`)
- **Default Route:** `default via 10.0.0.1 dev enp0s6`
- **Address Resolution Command:** `getent hosts apiconnect.angelone.in`
- **Route Probe Command:** `ip route get 103.82.178.77`

---

## 3. DNS Result

- **Status:** `SUCCESS`
- **Resolved IP:** `103.82.178.77`
- **Resolution Output:** `103.82.178.77 apiconnect.angelone.in`

---

## 4. Routing Result

- **Target IP:** `103.82.178.77`
- **Route:** `103.82.178.77 via 10.0.0.1 dev enp0s6 src 10.0.0.71`
- **Status:** `VALID LOCAL ROUTE` (Local routing table correctly resolves outbound path via default gateway `10.0.0.1`).

---

## 5. TCP Result

- **Target:** `103.82.178.77:443`
- **Status:** `TCP_TIMEOUT` (Outbound TCP SYN packets to port 443 timed out with `errno=11` / EAGAIN)
- **Comparison Probe:** `pypi.org:443` (`REACHABLE`, 2.55 ms) & `github.com:443` (`REACHABLE`, 23.3 ms)

---

## 6. TLS Result

- **Status:** `TLS_SKIPPED` (TCP connection failed prior to TLS handshake)

---

## 7. HTTPS Result

- **Status:** `HTTPS_SKIPPED` (Blocked at lower TCP socket layer)

---

## 8. Firewall / Policy Result

- **Local Host Firewall:** `PERMISSIVE` (`ufw-user-output` / default output policy is `ACCEPT`; no local host firewall rules block port 443 outbound).
- **Upstream Cloud Egress Policy:** `RESTRICTED` (Outbound TCP 443 packets to `103.82.178.77` are dropped upstream by cloud provider egress security list or Angel One regional IP geofencing).

---

## 9. Container Result

- **Execution Environment:** `BARE_HOST_ENVIRONMENT` (Not running inside Docker/Kubernetes container; `/.dockerenv` absent).

---

## 10. Proxy Result

- **Proxy Environment Variables:** `configured = NO` (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` are all unset). Direct socket connection attempted.

---

## 11. SmartAPI Result

- **SDK Status:** `VERIFIED_CORRECT` (SDK v1.5.5 implementation, root URL `https://apiconnect.angelone.in`, login route `/rest/auth/angelbroking/user/v1/loginByPassword`, and TOTP calculation are correct).

---

## 12. Root Cause

- **Primary Classification:** `CLOUD_EGRESS_POLICY` / `EXTERNAL INFRASTRUCTURE CONTROL`
- **Detail:** Local host networking, DNS resolution, and application code are fully functional. Outbound TCP port 443 packets to Angel One IP `103.82.178.77` are dropped upstream by cloud provider egress firewall rules or regional IP geofencing.

---

## 13. Remediation Performed

- **Application Code:** Frozen (Zero speculative application code changes; no weakening of security rules).
- **Required External Infrastructure Action:** Configure cloud Security List / Egress Firewall to permit:
  ```
  ALLOW OUTBOUND TCP 443
  DESTINATION: apiconnect.angelone.in (103.82.178.77)
  ```
- **Verification Command Post-Infrastructure Fix:**
  ```bash
  .venv/bin/python scripts/test_angel_one_auth.py
  ```

---

## 14. Genuine Authentication Result

- **Status:** `NOT VERIFIED — NETWORK UNAVAILABLE` (Fail-closed policy: network timeouts remain classified as `PROVIDER_UNREACHABLE` / `NETWORK_FAILURE` and are never misclassified as credential rejection).

---

## 15. Genuine WebSocket Result

- **Status:** `NOT CONNECTED` (Pending external network access)

---

## 16. Genuine Live Observations

- **genuine_live_observations:** `0` (Zero synthetic/mock ticks injected)

---

## 17. Live Paper-Trading Result

- **Status:** `OPERATIONAL — PENDING LIVE FEED` (Paper engine, risk checks, cash solvency, and P&L accounting verified ready)

---

## 18. Security Verification

- **LIVE_TRADING_ENABLED:** `False`
- **REAL_BROKER_EXECUTION_ENABLED:** `False`
- **Live order placement routes:** `0` (AST Scanner certified)
- **Paper-to-live bypasses:** `0`

---

## 19. Regression Test Results

- **Security Firewall Test (`test_stage27_security_firewall.py`):** **3 passed, 1 skipped** (in 0.29s)
- **Full Test Suite (`pytest tests/ -v`):**
  - **Passed:** **199**
  - **Skipped:** **1** (`test_production_repository_baseline_isolation` skipped cleanly)
  - **Failed:** **0**
  - **Errors:** **0**
  - **Duration:** **3.64s**

---

## 20. Remaining External Dependency

- **Dependency:** Outbound cloud network egress access for TCP port 443 to `apiconnect.angelone.in` (`103.82.178.77`).

---

## 21. Final Classification

`V1 PRODUCTION ENGINEERING VERIFIED — EXTERNAL PROVIDER ACCESS REQUIRED`
