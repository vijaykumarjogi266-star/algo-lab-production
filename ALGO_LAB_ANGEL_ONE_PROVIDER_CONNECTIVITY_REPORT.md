# ALGO LAB — ANGEL ONE PROVIDER CONNECTIVITY REPORT

**Document Version:** 1.2.0  
**Primary Auditor / Contact:** Senior Infrastructure & Provider Integration Engineer  
**Target Sandbox Repository:** `/home/ubuntu/algolab`  
**Final Status Classification:** `BLOCKED — CONNECTIVITY NOT VERIFIED`

---

## 1. EXECUTIVE SUMMARY & VERIFIED FACTS

Routine diagnostic checks against the Angel One SmartAPI infrastructure indicate a persistent TCP/443 timeout from the deployment host. Broker connectivity has **not been verified**. The system is currently incapable of reaching the provider's production endpoints.

**Confirmed Observations:**
- **Public Egress IPv4:** `152.67.8.10`
- **Outbound General Internet Reachability:** `1.1.1.1:443`, `8.8.8.8:53`, `api.ipify.org:443` are **operational**.
- **Angel One Reachability Comparison (via Safe Diagnostic Script):**
  - `margincalculator.angelone.in:443` (Resolved IP: `3.109.136.106`): `REACHABLE` (TCP/TLS Success, 38ms).
  - `apiconnect.angelone.in:443` (Resolved IP: `103.82.178.77`): `UNREACHABLE` (`TCP_TIMEOUT`, 5000ms+).
  - `smartapisocket.angelone.in:443` (Resolved IP: `103.82.178.39`): `UNREACHABLE` (`TCP_TIMEOUT`, 5000ms+).

**Plausible Unresolved Causes for Timeout:**
- Outbound host firewall (iptables/ufw) or OCI Security Group/NSG restricting traffic to the `103.82.178.0/24` subnet.
- Cloud routing misconfiguration or upstream ISP peering issues between Oracle Cloud Mumbai and the destination AS.
- Proxy or NAT Gateway misconfiguration dropping outbound packets.
- Destination perimeter firewall/WAF implicitly dropping SYN packets from this source IP or ASN.

*Note: The exact cause cannot be definitively determined solely from a local timeout event.*

---

## 2. DIAGNOSTIC PROCEDURES

A safe, non-authenticated diagnostic script (`scripts/safe_connectivity_diagnostic.py`) has been deployed.
- It performs only DNS resolution, TCP SYN checks, and TLS handshakes.
- It **does not** transmit application payloads, credentials, or authenticated API requests.
- This diagnostic can be run safely by operators to poll connectivity status without risk of credential exposure.

**Information Needed for Support (If Local Causes Excluded):**
If a full review of local OCI NSGs, iptables, and route tables proves the traffic is leaving the host unhindered, we will need to ask Angel One Support to check edge logs for dropped SYN packets from `152.67.8.10` directed at `103.82.178.77:443`.

---

## 3. ARCHITECTURAL ISOLATION & NEGATIVE TESTING

- **Paper Trading Independence:** The paper-trading operation operates exclusively in memory and local SQLite ledgers. It requires zero broker network access.
- **Strict Boundaries:** `ALLOW_LIVE_TRADING = False` and `ALLOW_REAL_BROKER_EXECUTION = False` are strictly enforced. 
- **Negative Testing Implemented:** `tests/unit/test_architectural_isolation.py` parses the AST of `live_market_daemon.py` to cryptographically guarantee the absence of `ALLOW_LIVE_TRADING = True` and verifies that mock swing positions close locally without invoking external REST APIs.

---

## 4. CODEBASE & SAFETY SUITE VERIFICATION

- **Mocked vs Live Distinctions:** The Pytest suite (`252 passed`) validates **mocked** logic, local calculations, and schema definitions. It **does not** represent successful integration with the live Angel One broker, which is currently failing at the TCP transport layer.
- **Sanitized Auth Tests:** The `test_angel_one_auth.py` script has been aggressively refactored. It now strictly requires the `--operator-approve-auth` flag to even attempt an authenticated payload transmission, and actively suppresses underlying library logs to prevent accidental credential leakage in stdout.

---

## 5. FINAL CLASSIFICATION

$$\text{BLOCKED — CONNECTIVITY NOT VERIFIED}$$

*The system remains in a safe, paper-only, fail-closed state. Broker connectivity is unverified. Zero authenticated requests or live order submissions will occur.*
