# ALGO LAB — ANGEL ONE EGRESS FINDING VERIFICATION REPORT

**Document Version:** 1.0.0  
**Audit Timestamp (UTC):** 2026-09-29T05:26:30Z  
**Primary Auditor:** Senior Infrastructure & Quantitative-Systems Reliability Auditor  
**Target Repository:** `/home/ubuntu/algolab`  
**Final Status Classification:** `BLOCKED — DESTINATION CONNECTIVITY UNRESOLVED`

---

## 1. EXECUTIVE SUMMARY

A forensic verification was performed to validate the VM's effective public egress IP, establish the exact OCI network routing path, evaluate destination-specific vs. general internet reachability, analyze the relevance of previously cited CIDRs, and define the minimal remediation steps required before making any OCI infrastructure or IP allowlisting changes.

- **Effective Public IPv4 Address:** `152.67.8.10` (Verified via 5 independent HTTPS public IP services).
- **OCI Network Path:** Public Subnet `10.0.0.0/24` $\rightarrow$ OCI Internet Gateway $\rightarrow$ Egress Public IPv4 `152.67.8.10` in OCI Region `ap-mumbai-1` (`AS31898 Oracle Corporation`).
- **Proposed CIDR Relevance:** `140.91.204.0/20` is **NOT** the relevant source range. It was an internal intermediate router hop inside Oracle's network (`140.91.204.31`). The actual source address seen by external servers is `152.67.8.10`.
- **Destination Reachability:**
  - General Internet Egress (`1.1.1.1:443`, `api.ipify.org:443`, `checkip.amazonaws.com:443`): `CONNECTED` (1.46ms – 62.19ms).
  - AWS-hosted Angel One Endpoint (`margincalculator.angelone.in:443` at `13.203.170.26`): `CONNECTED` (3.34ms).
  - Primary Data Center Angel One Endpoints (`apiconnect.angelone.in:443` at `103.82.178.77` and `smartapisocket.angelone.in:443` at `103.82.178.38`): `UNREACHABLE` (`TimeoutError: timed out`).
- **Updated Failure Classification:** `DESTINATION-SPECIFIC TCP/443 UNREACHABILITY`. Without direct confirmation from Angel One API support or packet capture evidence of a specific drop rule, we explicitly do not attribute the failure to a specific WAF or geofencing rule.
- **Safety Invariants:** Hard locked: `ALLOW_LIVE_TRADING = False` and `ALLOW_REAL_BROKER_EXECUTION = False`. Zero live order routes exist.
- **Test Regression Verification:** **252 passed, 1 skipped, 0 failures** in 6.04s.

---

## 2. VERIFIED EFFECTIVE PUBLIC EGRESS IP

Independent HTTPS probes executed from the Algo Lab VM returned the following:

| Service URL | User-Agent | Observed IPv4 Address | Status |
| :--- | :--- | :--- | :--- |
| `https://api.ipify.org` | `curl/7.81.0` | `152.67.8.10` | `SUCCESS` |
| `https://ifconfig.me/ip` | `curl/7.81.0` | `152.67.8.10` | `SUCCESS` |
| `https://icanhazip.com` | `curl/7.81.0` | `152.67.8.10` | `SUCCESS` |
| `https://checkip.amazonaws.com` | `curl/7.81.0` | `152.67.8.10` | `SUCCESS` |
| `https://ipinfo.io/ip` | `curl/7.81.0` | `152.67.8.10` | `SUCCESS` |

**Authoritative Answer:** The actual public IPv4 address that Angel One's servers see is **`152.67.8.10`** (Oracle Cloud Infrastructure, Region `ap-mumbai-1`).

---

## 3. VERIFIED OCI NETWORK PATH

The actual attached OCI network objects for VM `instance-20260909-1733` are:

```
[ VM instance-20260909-1733 ] 
  ├── Private IP: 10.0.0.71/24 (VNIC: ocid1.vnic.oc1.ap-mumbai-1.abrg6ljrkaklt3vex6ciyhup3l3xip3gm4g4ojpj7lfclqgvlgg3p44pspva)
  ├── Subnet: 10.0.0.0/24 (Public Subnet, AP-MUMBAI-1-AD-1)
  ├── Route Table: Default route `0.0.0.0/0 via 10.0.0.1`
  ├── Gateway: OCI Internet Gateway
  └── Public Egress IPv4: 152.67.8.10
```

---

## 4. EVALUATION OF PROPOSED CIDR (`140.91.204.0/20`)

- **Is `140.91.204.0/20` the relevant source range?** `NO`.
- **Derivation & Explanation:** `140.91.204.31` appeared in `tracepath` output as Hop 1. It is an internal intermediate gateway router IP inside Oracle's network infrastructure in Mumbai. It is **NOT** the public source IP used for outbound egress traffic across the Internet.
- **Actionable Correction:** Do NOT submit `140.91.204.0/20` to Angel One for allowlisting. The only relevant single IPv4 address is **`152.67.8.10`**.

---

## 5. DESTINATION COMPARISON MATRIX

Controlled socket probes to multiple destinations yield:

| Destination Description | Host / IP | Port | Latency / Result | Egress Status |
| :--- | :--- | :--- | :--- | :--- |
| **Cloudflare DNS HTTPS** | `1.1.1.1` | 443 | `1.46ms` | `CONNECTED` |
| **Google DNS** | `8.8.8.8` | 53 | `1.93ms` | `CONNECTED` |
| **Ipify Public Service** | `api.ipify.org` (`172.67.74.152`) | 443 | `2.69ms` | `CONNECTED` |
| **AWS CheckIP Service** | `checkip.amazonaws.com` (`18.140.129.83`) | 443 | `62.19ms` | `CONNECTED` |
| **Angel One Margin Calc (AWS India)** | `margincalculator.angelone.in` (`13.203.170.26`)| 443 | `3.34ms` | `CONNECTED` |
| **Angel One REST API** | `apiconnect.angelone.in` (`103.82.178.77`)| 443 | `TimeoutError` | `UNREACHABLE` |
| **Angel One Smart Stream WSS** | `smartapisocket.angelone.in` (`103.82.178.38`)| 443 | `TimeoutError` | `UNREACHABLE` |

**Finding:** General Internet egress is 100% operational. The reachability issue is strictly isolated to Angel One's primary data center endpoints (`103.82.178.0/24`).

---

## 6. CLASSIFICATION & REFINED DIAGNOSIS

In strict accordance with diagnostic guidelines:
- We do not attribute the failure to a specific WAF or geofencing mechanism without direct provider confirmation.
- Refined classification: **`DESTINATION-SPECIFIC TCP/443 UNREACHABILITY`**.

---

## 7. TLS TEST

Because TCP 443 connections to `apiconnect.angelone.in:443` and `smartapisocket.angelone.in:443` timed out, TLS handshake testing was **stopped prior to transmitting credentials**, avoiding unnecessary authentication attempts or secret exposure.

---

## 8. ANGEL ONE SUPPORT INQUIRY PATH

Before modifying OCI networking or provisioning new NAT gateways, contact Angel One API Support with the verified public egress IP:

- **Verified Egress IP:** `152.67.8.10`
- **Inquiry Details:**
  1. Confirm whether SmartAPI (`apiconnect.angelone.in`) and Smart Stream 2.0 (`smartapisocket.angelone.in`) permit traffic from cloud-hosted public IPs (specifically `152.67.8.10` in OCI Mumbai).
  2. Inquire whether source IP allowlisting/registration is required for developer API keys.
  3. Verify whether a static elastic IP (via OCI NAT Gateway) is required for long-term WebSocket connection stability.

---

## 9. NAT GATEWAY RECOMMENDATION DECISION

Provisioning a dedicated OCI NAT Gateway / Reserved Static Public IP is **NOT** recommended immediately.

It should only be considered if Angel One support confirms that:
1. `152.67.8.10` (ephemeral public IP) is rejected due to lack of static assignment, AND
2. Source IP registration is required and supported by Angel One.

---

## 10. SYSTEM CODE & REGRESSION SUITE VERIFICATION

- **Frozen Core Components:** Adapter (`services/market-data/adapters/angel_one.py`), Smart Stream parser, Instrument Master, Market-Data Runner, Multi-Symbol Scanner, Risk Engine, Paper Broker, Accounting Engine, Session Orchestrator, and Provenance Gate remain 100% untouched.
- **Safety Flags:**
  - `ALLOW_LIVE_TRADING: False`
  - `ALLOW_REAL_BROKER_EXECUTION: False`
  - Paper Capital: ₹10,00,000.00
- **Pytest Suite (`/home/ubuntu/algolab/.venv/bin/pytest`):**
  ```
  ================== 252 passed, 1 skipped, 2 warnings in 6.04s ==================
  ```

---

## 11. FINAL CLASSIFICATION

$$\text{BLOCKED — DESTINATION CONNECTIVITY UNRESOLVED}$$

*The Algo Lab codebase and paper-trading infrastructure are 100% complete and validated. Forward market-data collection remains BLOCKED due to destination-specific TCP/443 unreachability at Angel One's primary endpoints (`103.82.178.0/24`). Next step is to submit public egress IP `152.67.8.10` to Angel One API Support.*
