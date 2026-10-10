#!/usr/bin/env python3
"""
Algo Lab Stage 27 — Root-Cause Angel One Connectivity Diagnostic

Detailed Python networking diagnostic for apiconnect.angelone.in.
Checks:
- socket.getaddrinfo (IPv4 vs IPv6 resolution & addresses)
- TCP 443 socket connection per IP / address family with latency measurement
- Raw TLS handshake using python 'ssl' (SNI, cert validation)
- HTTP/HTTPS GET request
- Proxy environment inspection
- Container vs Host environment detection
- Known HTTPS comparison targets (pypi.org, github.com)
"""

import socket
import ssl
import sys
import os
import time
import urllib.request
import urllib.error

TARGET_HOST = "apiconnect.angelone.in"
TARGET_PORT = 443
TIMEOUT = 3.5

KNOWN_TARGETS = [("pypi.org", 443), ("github.com", 443)]


def step1_dns_and_tcp():
    print("=" * 60)
    print("STEP 1 & 2: DNS & ADDRESS FAMILY (IPv4 vs IPv6) TCP DIAGNOSTICS")
    print("=" * 60)

    try:
        addr_info = socket.getaddrinfo(TARGET_HOST, TARGET_PORT, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except Exception as e:
        print(f"[!] DNS Lookup Failed: {e}")
        return [], {}

    print(f"[✓] getaddrinfo returned {len(addr_info)} entry/entries for {TARGET_HOST}:")

    results = []

    for i, res in enumerate(addr_info):
        af, socktype, proto, canonname, sa = res
        ip = sa[0]
        family_name = "IPv4" if af == socket.AF_INET else ("IPv6" if af == socket.AF_INET6 else str(af))
        print(f"\n  Entry #{i+1}: Family={family_name}, IP={ip}, Port={sa[1]}")

        # Test TCP connection
        start_t = time.perf_counter()
        tcp_res = "FAILED"
        err_detail = "None"
        latency_ms = None

        try:
            s = socket.socket(af, socktype, proto)
            s.settimeout(TIMEOUT)
            conn_res = s.connect_ex((ip, TARGET_PORT))
            end_t = time.perf_counter()
            latency_ms = round((end_t - start_t) * 1000, 2)

            if conn_res == 0:
                tcp_res = "REACHABLE"
                print(f"    -> TCP Result: REACHABLE (Latency: {latency_ms} ms)")
            else:
                tcp_res = "TIMEOUT"
                err_detail = f"connect_ex errno={conn_res}"
                print(f"    -> TCP Result: TIMEOUT (errno={conn_res})")
            s.close()
        except socket.timeout:
            tcp_res = "TIMEOUT"
            err_detail = "socket.timeout"
            print(f"    -> TCP Result: TIMEOUT (socket.timeout)")
        except Exception as e:
            tcp_res = "BLOCKED"
            err_detail = f"{type(e).__name__}: {e}"
            print(f"    -> TCP Result: BLOCKED ({err_detail})")

        results.append({
            "ip": ip,
            "family": family_name,
            "tcp_result": tcp_res,
            "latency_ms": latency_ms,
            "err_detail": err_detail,
        })

    return addr_info, results


def step3_tls_handshake(addr_info, tcp_results):
    print("\n" + "=" * 60)
    print("STEP 3: RAW TLS HANDSHAKE WITHOUT CREDENTIALS")
    print("=" * 60)

    reachable_entries = [r for r in tcp_results if r["tcp_result"] == "REACHABLE"]
    if not reachable_entries:
        print("[!] Skipped: No TCP reachable addresses found for Angel One.")
        return "TCP_FAILURE"

    target = reachable_entries[0]
    print(f"[*] Attempting TLS handshake to {target['ip']} ({target['family']})...")

    ctx = ssl.create_default_context()
    # Ensure SNI and certificate validation are enabled
    try:
        s = socket.socket(socket.AF_INET if target['family'] == 'IPv4' else socket.AF_INET6, socket.SOCK_STREAM)
        s.settimeout(TIMEOUT)
        s.connect((target['ip'], TARGET_PORT))

        ssl_sock = ctx.wrap_socket(s, server_hostname=TARGET_HOST)
        cipher = ssl_sock.cipher()
        tls_ver = ssl_sock.version()
        cert = ssl_sock.getpeercert()

        print(f"[✓] TLS Handshake Successful!")
        print(f"    - TLS Version: {tls_ver}")
        print(f"    - Cipher: {cipher[0]} ({cipher[1]})")
        print(f"    - Subject CN: {dict(x[0] for x in cert.get('subject', []))}")
        ssl_sock.close()
        return "TLS_SUCCESS"
    except ssl.SSLError as e:
        print(f"[!] TLS Failure: {e}")
        return "TLS_FAILURE"
    except Exception as e:
        print(f"[!] TLS Connection Error: {e}")
        return "TLS_FAILURE"


def step4_https_request(tls_status):
    print("\n" + "=" * 60)
    print("STEP 4: HTTPS CONNECTIVITY WITHOUT CREDENTIALS")
    print("=" * 60)

    if tls_status != "TLS_SUCCESS":
        print("[!] Skipped: TLS handshake did not succeed.")
        return "HTTPS_SKIPPED"

    url = f"https://{TARGET_HOST}/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            print(f"[✓] HTTPS Response Status: HTTP {resp.status}")
            return "HTTPS_SUCCESS"
    except urllib.error.HTTPError as e:
        print(f"[✓] HTTPS Response Status: HTTP Error {e.code} (Reachable)")
        return "HTTPS_SUCCESS"
    except Exception as e:
        print(f"[!] HTTPS Request Failed: {e}")
        return "HTTPS_FAILURE"


def step5_proxy_inspection():
    print("\n" + "=" * 60)
    print("STEP 5: PROXY CONFIGURATION INSPECTION")
    print("=" * 60)

    proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"]
    found_proxies = {}

    for var in proxy_vars:
        val = os.environ.get(var)
        if val:
            # Mask credentials if present in proxy URL
            sanitized = val
            if "@" in val:
                proto, rest = val.split("://", 1) if "://" in val else ("", val)
                creds_part, host_part = rest.rsplit("@", 1)
                sanitized = f"{proto}://••••:••••@{host_part}" if proto else f"••••:••••@{host_part}"
            found_proxies[var] = sanitized

    if found_proxies:
        print("[*] Proxy Environment Variables Detected:")
        for k, v in found_proxies.items():
            print(f"    - {k} = {v}")

        # Check urllib proxy handler default
        proxies = urllib.request.getproxies()
        print(f"[*] Python urllib default proxies: {list(proxies.keys())}")
        return "CONFIGURED_YES", found_proxies
    else:
        print("[✓] No Proxy Environment Variables configured (configured = NO)")
        print("[✓] Python process is connecting directly without HTTP proxies.")
        return "CONFIGURED_NO", {}


def step6_container_detection():
    print("\n" + "=" * 60)
    print("STEP 6: HOST VS CONTAINER ENVIRONMENT DETECTION")
    print("=" * 60)

    is_container = False
    details = []

    if os.path.exists("/.dockerenv"):
        is_container = True
        details.append("/.dockerenv present")

    if os.path.exists("/proc/1/cgroup"):
        try:
            with open("/proc/1/cgroup", "r") as f:
                cgroup_content = f.read()
                if "docker" in cgroup_content or "kubepods" in cgroup_content or "containerd" in cgroup_content:
                    is_container = True
                    details.append("cgroup contains docker/containerd signatures")
        except Exception:
            pass

    if is_container:
        print(f"[*] Execution Environment: CONTAINERIZED ({', '.join(details)})")
        return "CONTAINER", details
    else:
        print("[*] Execution Environment: BARE HOST / VM (Not running inside Docker/Kubernetes container)")
        return "HOST", details


def step8_known_targets():
    print("\n" + "=" * 60)
    print("STEP 8: COMPARISON WITH KNOWN HTTPS TARGETS")
    print("=" * 60)

    results = {}
    for host, port in KNOWN_TARGETS:
        start_t = time.perf_counter()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(TIMEOUT)
            res = s.connect_ex((host, port))
            end_t = time.perf_counter()
            s.close()
            latency = round((end_t - start_t) * 1000, 2)
            if res == 0:
                print(f"[✓] {host}:{port} -> TCP REACHABLE ({latency} ms)")
                results[host] = f"REACHABLE ({latency} ms)"
            else:
                print(f"[!] {host}:{port} -> TCP TIMEOUT (errno={res})")
                results[host] = "TIMEOUT"
        except Exception as e:
            print(f"[!] {host}:{port} -> FAILED ({e})")
            results[host] = f"FAILED ({e})"

    return results


def main():
    addr_info, tcp_results = step1_dns_and_tcp()
    tls_status = step3_tls_handshake(addr_info, tcp_results)
    https_status = step4_https_request(tls_status)
    proxy_status, proxy_details = step5_proxy_inspection()
    env_type, env_details = step6_container_detection()
    known_target_results = step8_known_targets()

    print("\n" + "=" * 60)
    print("ROOT CAUSE SUMMARY")
    print("=" * 60)

    ipv4_tcp = [r for r in tcp_results if r["family"] == "IPv4"]
    ipv6_tcp = [r for r in tcp_results if r["family"] == "IPv6"]

    print(f"DNS Resolution    : {'SUCCESS' if addr_info else 'FAILED'}")
    print(f"IPv4 TCP 443      : {ipv4_tcp[0]['tcp_result'] if ipv4_tcp else 'N/A'}")
    print(f"IPv6 TCP 443      : {ipv6_tcp[0]['tcp_result'] if ipv6_tcp else 'NONE_RESOLVED'}")
    print(f"TLS Status        : {tls_status}")
    print(f"HTTPS Status      : {https_status}")
    print(f"Proxy Configured  : {proxy_status}")
    print(f"Execution Env     : {env_type}")
    print(f"Known Targets     : {known_target_results}")


if __name__ == "__main__":
    main()
