#!/usr/bin/env python3
"""
Algo Lab Stage 27 — Network & Connectivity Diagnostic Helper

Checks DNS, TCP (443), HTTPS TLS handshake, and Cloud Egress policy for apiconnect.angelone.in.
Does NOT send or print credentials.
"""

import socket
import ssl
import sys
import urllib.request
import urllib.error

HOST = "apiconnect.angelone.in"
PORT = 443
TIMEOUT = 4.0


def check_dns():
    print("--- 1. DNS RESOLUTION ---")
    try:
        ip_list = socket.gethostbyname_ex(HOST)[2]
        print(f"DNS Resolution: SUCCESS")
        print(f"Resolved IP Count: {len(ip_list)}")
        return "SUCCESS", ip_list
    except Exception as e:
        print(f"DNS Resolution: FAILED ({e})")
        print("Resolved IP Count: 0")
        return "FAILED", []


def check_tcp(ips):
    print("\n--- 2. TCP CONNECTIVITY (Port 443) ---")
    if not ips:
        print("TCP Status: DNS_FAILURE")
        return "DNS_FAILURE"

    target_ip = ips[0]
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        res = s.connect_ex((target_ip, PORT))
        s.close()
        if res == 0:
            print("TCP Status: TCP_REACHABLE")
            return "TCP_REACHABLE"
        else:
            print(f"TCP Status: TCP_TIMEOUT (connect_ex returned code {res})")
            return "TCP_TIMEOUT"
    except socket.timeout:
        print("TCP Status: TCP_TIMEOUT")
        return "TCP_TIMEOUT"
    except Exception as e:
        print(f"TCP Status: TCP_BLOCKED ({type(e).__name__}: {e})")
        return "TCP_BLOCKED"


def check_https():
    print("\n--- 3. HTTPS CONNECTIVITY ---")
    url = f"https://{HOST}/"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as response:
            print(f"HTTPS Status: HTTPS_REACHABLE (HTTP {response.status})")
            return "HTTPS_REACHABLE"
    except urllib.error.HTTPError as e:
        # HTTP errors like 404/403 mean the HTTPS connection succeeded
        print(f"HTTPS Status: HTTPS_REACHABLE (HTTP Error {e.code})")
        return "HTTPS_REACHABLE"
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            print("HTTPS Status: HTTPS_TIMEOUT")
            return "HTTPS_TIMEOUT"
        elif isinstance(e.reason, ssl.SSLError):
            print(f"HTTPS Status: TLS_ERROR ({e.reason})")
            return "TLS_ERROR"
        else:
            print(f"HTTPS Status: HTTPS_BLOCKED ({e.reason})")
            return "HTTPS_BLOCKED"
    except Exception as e:
        print(f"HTTPS Status: HTTPS_TIMEOUT ({type(e).__name__}: {e})")
        return "HTTPS_TIMEOUT"


def check_egress():
    print("\n--- 4. CLOUD EGRESS POLICY ---")
    # Test standard global endpoints to see if outbound access is generally allowed or restricted to specific domains/IP ranges
    test_hosts = [
        ("pypi.org", 443),
        ("github.com", 443),
        ("apiconnect.angelone.in", 443),
    ]
    results = {}
    for h, p in test_hosts:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.5)
            r = s.connect_ex((h, p))
            s.close()
            results[h] = "REACHABLE" if r == 0 else "TIMEOUT"
        except Exception:
            results[h] = "BLOCKED"

    print("Egress probe results:")
    for h, status in results.items():
        print(f"  - {h}:{PORT} => {status}")

    if results.get("apiconnect.angelone.in") == "REACHABLE":
        print("Overall Egress Policy: ALLOWED")
        return "ALLOWED"
    elif any(v == "REACHABLE" for v in results.values()):
        print("Overall Egress Policy: RESTRICTED (General internet allowed, financial broker IP domain blocked by cloud egress rules/firewall)")
        return "RESTRICTED"
    else:
        print("Overall Egress Policy: BLOCKED")
        return "BLOCKED"


def main():
    dns_status, ips = check_dns()
    tcp_status = check_tcp(ips)
    https_status = check_https()
    egress_status = check_egress()

    print("\n" + "=" * 50)
    print("DIAGNOSTIC SUMMARY:")
    print(f"DNS          = {dns_status}")
    print(f"TCP_443      = {tcp_status}")
    print(f"HTTPS        = {https_status}")
    print(f"egress_policy= {egress_status}")
    print("=" * 50)


if __name__ == "__main__":
    main()
