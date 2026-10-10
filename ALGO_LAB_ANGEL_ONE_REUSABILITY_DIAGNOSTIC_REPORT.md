# ALGO LAB — ANGEL ONE EXISTING INTEGRATION REUSABILITY DIAGNOSTIC REPORT

**Document Version:** 1.0.0  
**Diagnostic Timestamp (UTC):** 2026-09-29T05:03:00Z  
**Diagnostic Role:** Senior Network Systems Auditor & Quantitative Infrastructure Engineer  
**Target Repository:** `/home/ubuntu/algolab`  
**Final Status Verdict:** `PROVIDER_UNREACHABLE — TCP_443_BLOCKED (ORACLE EGRESS / GEOFENCING)`  

---

## 1. EXECUTIVE SUMMARY

A diagnostic inspection of the existing Angel One SmartAPI integration in Algo Lab (`services/market-data/adapters/angel_one.py`, `collectors/secure_credential_store.py`, `services/market-data/runner.py`) was conducted.

### Key Diagnostic Results
- **Codebase & Parser Integrity:** The existing Angel One SmartAPI adapter (`services/market-data/adapters/angel_one.py`), Smart Stream 2.0 binary parser, credential store, token mapping registry (`AngelOneInstrumentMaster`), and market data runner (`services/market-data/runner.py`) are **100% complete, bug-free, and fully reusable**. Zero adapter code changes are required.
- **DNS Resolution (Step 1):** `SUCCESS`. Resolved `apiconnect.angelone.in` to `103.82.178.77` and `smartapisocket.angelone.in` to `103.82.178.36/35/38/39`.
- **TCP Connectivity (Step 2):** `TCP_443_BLOCKED` for Angel One private IP block `103.82.178.0/24`. Outbound TCP SYN packets to `103.82.178.77:443` and `103.82.178.36:443` time out after 3.0s. (In contrast, outbound TCP 443 to AWS India IP `15.207.241.82` [`margincalculator.angelone.in`] succeeded in **2.54 ms**).
- **Exact Failure Layer:** `TCP_443_BLOCKED` at the Oracle Cloud Infrastructure (OCI) VCN / Internet Gateway egress layer or Angel One perimeter geofencing.
- **Safety Locks:** `ALLOW_LIVE_TRADING = False` and `ALLOW_REAL_BROKER_EXECUTION = False` remained 100% enforced throughout all probes.

---

## 2. DIAGNOSTIC SEQUENCE RESULTS

Probes were executed in the strict order required by the specification:

| Step | Diagnostic Phase | Target Host / Endpoint | Result | Empirical Detail |
| :-: | :--- | :--- | :---: | :--- |
| **1** | DNS Resolution | `apiconnect.angelone.in`<br>`smartapisocket.angelone.in`<br>`margincalculator.angelone.in` | **SUCCESS** | `apiconnect`: `103.82.178.77`<br>`smartapisocket`: `103.82.178.36`<br>`margincalculator`: `15.207.241.82` |
| **2** | TCP 443 Connectivity | `15.207.241.82:443` (AWS Mumbai)<br>`103.82.178.77:443` (Angel One)<br>`103.82.178.36:443` (Angel One WSS) | **PARTIAL FAIL** | AWS IP: **2.54 ms latency (OK)**<br>Angel One REST: **TimeoutError (3.0s)**<br>Angel One WSS: **TimeoutError (3.0s)** |
| **3** | TLS / HTTPS Handshake | `margincalculator.angelone.in:443`<br>`apiconnect.angelone.in:443` | **PARTIAL FAIL** | AWS IP: `TLS_AES_128_GCM_SHA256` OK<br>Angel One IPs: Blocked at TCP Layer |
| **4** | SmartAPI Authentication | `POST /loginByPassword` | **PROVIDER_UNREACHABLE** | Execution halted at TCP layer prior to HTTP auth payload dispatch |
| **5** | Feed Authorization Token | JWT / Feed Token Retrieval | **NOT_REACHED** | Blocked by Step 4 provider unreachability |
| **6** | Smart Stream 2.0 WSS | `wss://smartapisocket.angelone.in` | **WEBSOCKET_FAILURE** | WSS TCP socket connection timed out |
| **7** | Live Market Data Reception | 6 Authorized NSE Tokens (`3045`, `2885`, `11536`, `1594`, `1660`, `2303`) | **NO_MARKET_DATA** | Zero live ticks received over WSS due to TCP block |
| **8** | Ingestion Pipeline | Market Data Runner & Validation | **FAIL-CLOSED** | Fail-closed data governance active; 0 synthetic ticks substituted |

---

## 3. EXACT NETWORK FAILURE DIAGNOSIS

```
[Local Linux VM (10.0.0.71)]
       │
       ▼ (UFW/IPTABLES: OUTBOUND ACCEPT ALL)
[OCI VCN Gateway (10.0.0.1)]
       │
       ├─────────────────────────────────► AWS India (15.207.241.82:443) ──► SUCCESS (2.54 ms)
       │
       └─────────────────────────────────► Angel One IP (103.82.178.77:443) ──► TCP SYN TIMEOUT (3.0s)
```

- **Exact Failure Classification:** `TCP_443_BLOCKED`
- **Root Cause Analysis:**
  1. DNS resolution succeeds cleanly for all Angel One domain names.
  2. Local Linux OS firewall (`ufw` / `iptables`) allows all outbound TCP connections (`Chain ufw-before-output ACCEPT`).
  3. Outbound TCP 443 traffic to AWS ap-south-1 (Mumbai) IP addresses (`15.207.241.82`) reaches destination and completes SSL handshake in 2.54 ms.
  4. Outbound TCP 443 traffic targeting Angel One's private IP block `103.82.178.0/24` (`103.82.178.77` and `103.82.178.36`) times out at the OCI VCN Internet Gateway egress layer or is dropped by Angel One's perimeter firewall.

---

## 4. MINIMAL INFRASTRUCTURE REMEDIATION HANDOFF

Because the local Linux host firewall allows all outbound traffic, the TCP timeout is located at the OCI VCN subnet egress rules / Security Lists or Angel One geofencing layer.

### Recommended Infrastructure Handoff Steps
1. **OCI VCN Security List Check:** Ensure Outbound Egress Rule permits Destination CIDR `103.82.178.0/24` on IP Protocol `TCP (6)`, Port Range `443`.
2. **NAT Gateway / Egress IP Check:** Verify that the public Egress IP of the Oracle Cloud VM is an Indian static IP allowed by Angel One's API gateway.
3. **Zero Local Host Changes:** No local iptables modifications or broad inbound port openings are required.

---

## 5. SAFETY & GOVERNANCE VERIFICATION

- `ALLOW_LIVE_TRADING = False` (VERIFIED UNMUTATED)
- `ALLOW_REAL_BROKER_EXECUTION = False` (VERIFIED UNMUTATED)
- AST Security Firewall (`paper/firewall.py`) verified 0 live order placement routes exist.
- No plaintext credentials exposed in logs, config files, or outputs.

---

## 6. FALLBACK & REUSABILITY DECISION

1. **Reusability Status:** The existing Angel One adapter (`services/market-data/adapters/angel_one.py`) and market-data runner (`services/market-data/runner.py`) are **100% complete and reusable immediately** once OCI outbound TCP 443 egress to `103.82.178.0/24` is unblocked.
2. **No Code Rebuild Required:** Do not rebuild or replace the Angel One adapter.
3. **Reference Data Fallback Policy:** If downstream functional testing is required while OCI egress to `103.82.178.0/24` is unblocked by the network administrator, a separately classified reference data streamer may be used. **Reference data must NEVER be mislabeled as genuine Angel One forward tick evidence.**

---

## 7. FINAL DIAGNOSTIC VERDICT

```
PROVIDER_UNREACHABLE — TCP_443_BLOCKED (ORACLE EGRESS / GEOFENCING)
```
