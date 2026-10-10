#!/usr/bin/env python3
"""
Algo Lab — Safe Non-Authenticated Connectivity Diagnostic

Performs a strict TCP and TLS handshake to verify basic network egress
and host reachability without transmitting any application-layer payload.
"""

import sys
import socket
import ssl
import time
import json
from datetime import datetime, timezone

def test_endpoint(hostname: str, port: int, timeout_sec: float = 5.0) -> dict:
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": hostname,
        "port": port,
        "dns_resolution": None,
        "tcp_success": False,
        "tls_success": False,
        "failure_category": None,
        "duration_ms": 0,
        "cert_info": None
    }
    
    start_time = time.perf_counter()
    
    # 1. DNS Resolution
    try:
        ip = socket.gethostbyname(hostname)
        result["dns_resolution"] = f"SUCCESS ({ip})"
    except socket.gaierror:
        result["dns_resolution"] = "FAILED"
        result["failure_category"] = "DNS_RESOLUTION_FAILED"
        result["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
        return result
        
    # 2. TCP Connection
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout_sec)
    
    try:
        sock.connect((hostname, port))
        result["tcp_success"] = True
    except socket.timeout:
        result["failure_category"] = "TCP_TIMEOUT"
        result["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
        sock.close()
        return result
    except ConnectionRefusedError:
        result["failure_category"] = "TCP_CONNECTION_REFUSED"
        result["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
        sock.close()
        return result
    except Exception as e:
        result["failure_category"] = f"TCP_ERROR_{type(e).__name__}"
        result["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
        sock.close()
        return result
        
    # 3. TLS Handshake (if port 443)
    if port == 443:
        context = ssl.create_default_context()
        try:
            ssock = context.wrap_socket(sock, server_hostname=hostname)
            result["tls_success"] = True
            cert = ssock.getpeercert()
            
            # Extract basic non-sensitive cert info
            cert_summary = {}
            for item in cert.get("subject", []):
                for k, v in item:
                    if k in ("commonName", "organizationName"):
                        cert_summary[k] = v
                        
            result["cert_info"] = cert_summary
            ssock.close()
        except ssl.SSLError:
            result["failure_category"] = "TLS_HANDSHAKE_FAILED"
        except socket.timeout:
            result["failure_category"] = "TLS_TIMEOUT"
        except Exception as e:
            result["failure_category"] = f"TLS_ERROR_{type(e).__name__}"
            
    if not result["failure_category"]:
        result["failure_category"] = "NONE"
        
    result["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
    return result

def main():
    endpoints = [
        ("apiconnect.angelone.in", 443),
        ("smartapisocket.angelone.in", 443),
        ("margincalculator.angelone.in", 443)
    ]
    
    print("=" * 60)
    print("SAFE BROKER NETWORK DIAGNOSTIC (UNAUTHENTICATED)")
    print("=" * 60)
    
    results = []
    for host, port in endpoints:
        res = test_endpoint(host, port)
        results.append(res)
        
        print(f"\n[Target] {host}:{port}")
        print(f"  - Timestamp (UTC) : {res['timestamp_utc']}")
        print(f"  - DNS Resolution  : {res['dns_resolution']}")
        print(f"  - TCP Connection  : {'SUCCESS' if res['tcp_success'] else 'FAILED'}")
        if port == 443 and res['tcp_success']:
            print(f"  - TLS Handshake   : {'SUCCESS' if res['tls_success'] else 'FAILED'}")
        if res['cert_info']:
            print(f"  - Cert Subject    : {res['cert_info']}")
        print(f"  - Diagnostics     : {res['failure_category']} ({res['duration_ms']} ms)")
        
    with open("safe_network_diagnostic.json", "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    main()
