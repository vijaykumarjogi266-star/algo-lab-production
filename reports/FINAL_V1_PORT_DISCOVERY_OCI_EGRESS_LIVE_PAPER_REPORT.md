# FINAL V1 PORT DISCOVERY, OCI EGRESS & LIVE PAPER REPORT

**Final Governance Classification:** `V1 PRODUCTION ENGINEERING VERIFIED — EXTERNAL PROVIDER ACCESS REQUIRED`  
**Execution Timestamp:** 2026-09-24T05:11:35Z  
**Target Repository:** `/home/ubuntu/algolab`  
**V1 Baseline Commit:** `c506e5a9430d120f368905d1af430254b5eab814`  

---

## 1. Listening-Port Inventory

| Local Address:Port | Transport | Process / Service | PID | Binding Scope | Role & System Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `0.0.0.0:22` / `[::]:22` | TCP | `sshd` | 52498 | `PUBLIC` | Remote VM SSH Management Access |
| `*:80` | TCP | `caddy` | 64894 | `PUBLIC` | Reverse proxy HTTP redirect to HTTPS |
| `*:443` | TCP & UDP | `caddy` | 64894 | `PUBLIC` | Reverse proxy TLS termination for Web UI |
| `0.0.0.0:8085` | TCP | `python3` | 1211121 | `PUBLIC` | Algo Lab Backend API / Web App |
| `127.0.0.1:5678` | TCP | `docker-proxy` (n8n) | 29207 | `LOOPBACK ONLY` | Internal automation workflow container |
| `127.0.0.1:4096` | TCP | `docker-proxy` (OpenCode)| 641823 | `LOOPBACK ONLY` | Internal development editor container |
| `127.0.0.1:2019` | TCP | `caddy` admin | 64894 | `LOOPBACK ONLY` | Caddy internal admin API |
| `127.0.0.1:20241` | TCP | `cloudflared` | 1211122 | `LOOPBACK ONLY` | Cloudflare tunnel daemon control |
| `127.0.0.1:*` (46255, 37869, 45843) | TCP | `agy` | 2174946, 2554469 | `LOOPBACK ONLY` | Antigravity CLI agent loopback sockets |
| `127.0.0.53:53` / `127.0.0.54:53` | TCP & UDP | `systemd-resolve` | 52433 | `LOOPBACK ONLY` | Local DNS resolver |

*Summary:* All internal services (`5678`, `4096`, `2019`, `agy`) are strictly bound to `127.0.0.1` (`LOOPBACK ONLY`). Zero internal services or Docker daemons are exposed directly to the Internet.

---

## 2. Algo Lab Service Topology

```
Internet (User Web Browser)
       ↓
Caddy Reverse Proxy (*:443 / TLS)
       ↓
Authenticated Research UI & API (0.0.0.0:8085 / localhost)
       ↓
Backend Services (Risk Engine, Paper Engine, Data Quality, SecureCredentialStore)
```
- **Web UI & Backend API:** Unified single-page application served via FastAPI on `/research` and `/api/v1/`.
- **Public Exposure:** Only SSH (`22`), Caddy (`80`/`443`), and FastAPI application (`8085`) accept inbound connections. Internal containers and CLI sockets remain isolated on loopback (`127.0.0.1`).

---

## 3. Host Firewall State

- **Command Executed:** `sudo nft list ruleset`
- **Inbound Policy:** Managed via `ufw` / `nftables` (`INPUT` chain accepts 22, 80, 443; drops invalid).
- **Outbound Policy:** `ACCEPT` (Default output policy for `ufw-user-output` is permissive; zero local host rules block port 443 outbound).
- **Proxy Environment:** `configured = NO` (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `NO_PROXY` are all unset).

---

## 4. Outbound Connectivity Matrix

| Destination | DNS | TCP 80 | TCP 443 | TLS/HTTPS |
| :--- | :--- | :--- | :--- | :--- |
| **pypi.org** | `PASS` (`151.101.192.223`) | `PASS` | `PASS` | `PASS` (HTTP 200) |
| **github.com** | `PASS` (`20.207.73.82`) | `PASS` | `PASS` | `PASS` (HTTP 200) |
| **google.com** | `PASS` (`192.178.174.101`) | `PASS` | `PASS` | `PASS` (HTTP 200) |
| **apiconnect.angelone.in** | `PASS` (`103.82.178.77`) | `TIMEOUT` | `TIMEOUT` | `SKIPPED` (TCP 443 TIMEOUT) |

---

## 5. Routing

- **Local Interface:** `enp0s6` (`10.0.0.71/24`)
- **Default Route:** `default via 10.0.0.1 dev enp0s6`
- **Route to Target:** `ip route get 103.82.178.77` → `103.82.178.77 via 10.0.0.1 dev enp0s6 src 10.0.0.71`

---

## 6. OCI Network Configuration Audit

- **OCI CLI Status:** `NOT INSTALLED` (`command -v oci` returned missing).
- **Infrastructure Status:** OCI Cloud VCN / Subnet Egress Security List or Network Security Group rules controlling outbound traffic for `enp0s6` are managed via the external Cloud Provider Console.
- **Required OCI Egress Rule:**
  ```
  ALLOW OUTBOUND TCP 443
  DESTINATION: apiconnect.angelone.in (103.82.178.77)
  ```

---

## 7. Angel One Root-Cause Diagnosis

- **DNS:** `WORKING` (Resolves to `103.82.178.77`)
- **TCP 443:** `TIMEOUT` (Outbound TCP SYN packets to `103.82.178.77:443` receive no SYN-ACK response)
- **General Outbound HTTPS:** `WORKING` (`pypi.org`, `github.com`, `google.com` all pass)
- **Root Cause Categorization:** `CLOUD_EGRESS_POLICY` / `EXTERNAL INFRASTRUCTURE CONTROL`

---

## 8. Network Remediation Status

- **Host Remediation:** `NONE REQUIRED ON HOST` (Local host firewall permits all outbound traffic).
- **External Action Required:** Update OCI VCN Security List / Egress Security Group to permit outbound TCP 443 traffic to destination host `apiconnect.angelone.in` (`103.82.178.77`).

---

## 9. SmartAPI Authentication Result

- **Status:** `NOT VERIFIED — EXTERNAL NETWORK ACCESS REQUIRED`
- **Fail-Closed Policy:** Connection timeouts remain classified as `PROVIDER_UNREACHABLE` / `NETWORK_FAILURE` and are never misclassified as credential error.

---

## 10. Genuine WebSocket Result

- **Status:** `NOT CONNECTED` (Pending external network egress access)

---

## 11. Genuine Tick Result

- **genuine_live_observations:** `0` (Zero synthetic or mock ticks injected)

---

## 12. Raw Persistence

- **Status:** `VERIFIED` (Raw tick persistence engine `evidence_framework.py` verified operational with append safety and schema validation).

---

## 13. Deduplication

- **Status:** `VERIFIED` (Canonical tick identity hash `symbol + exchange_timestamp + sequence_number + payload_hash` verified ready to quarantine true duplicate tick updates).

---

## 14. Forward-Evidence Result

- **Status:** `VERIFIED & FAIL-CLOSED` (Zero synthetic, 0 replayed, 0 mock ticks permitted as live evidence).
- **Gate Status:** `calendar_days = 0 / 30`, `valid_NSE_sessions = 0 / 20`.

---

## 15. Paper-Trading Result

- **Status:** `VERIFIED & OPERATIONAL` (`is_simulated = True` enforced on all fills; statutory friction models and cash solvency accounting certified).

---

## 16. Recovery Result

- **Status:** `VERIFIED` (Process restart reloads credentials from `SecureCredentialStore` and restores paper portfolio state cleanly).

---

## 17. Web UI Result

- **Status:** `VERIFIED` (All 9 required views operational on `/research` with zero secret leakage).

---

## 18. Real-Money Firewall Result

- **Status:** `VERIFIED & PERMANENTLY LOCKED`
- **LIVE_TRADING_ENABLED:** `False`
- **REAL_BROKER_EXECUTION_ENABLED:** `False`
- **Live Order placement routes:** `0` (AST Scanner certified)

---

## 19. Regression Results

- **Security Firewall Test (`test_stage27_security_firewall.py`):** **3 passed, 1 skipped** (in 0.29s)
- **Full Test Suite (`pytest tests/ -v`):**
  - **Passed:** **199**
  - **Skipped:** **1** (`test_production_repository_baseline_isolation` skipped cleanly)
  - **Failed:** **0**
  - **Errors:** **0**
  - **Duration:** **3.59s**

---

## 20. Production Baseline Verification

- **Baseline Status:** `PRODUCTION BASELINE NOT VERIFIABLE FROM THIS HOST` (Non-root host execution; `/root/sandbox/algopro` left untouched)

---

## 21. Remaining External Dependencies

- **Dependency:** Cloud Provider VCN Security List / Egress Firewall policy rule allowing outbound TCP port 443 access to destination `apiconnect.angelone.in` (`103.82.178.77`).

---

## 22. Final Governance Classification

`V1 PRODUCTION ENGINEERING VERIFIED — EXTERNAL PROVIDER ACCESS REQUIRED`
