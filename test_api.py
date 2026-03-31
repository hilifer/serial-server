#!/usr/bin/env python3
"""
Meter API integration test.

Tests all meter API endpoints against a running server.

Usage:
    # Start server first: python server.py
    # Then run tests:
    python test_api.py
    python test_api.py --host localhost --port 8000
    python test_api.py --parking-only    # Test parking APIs only
    python test_api.py --meter-only      # Test meter APIs only
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from deps import ensure_deps
ensure_deps()

import requests


class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    END = "\033[0m"


def ok(msg):
    print(f"  {C.GREEN}\u2713{C.END} {msg}")

def fail(msg):
    print(f"  {C.RED}\u2717{C.END} {msg}")

def warn(msg):
    print(f"  {C.YELLOW}\u26a0{C.END} {msg}")

def header(msg):
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.END}")
    print(f"{C.BOLD}{C.CYAN}  {msg}{C.END}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.END}")

def subheader(msg):
    print(f"\n  {C.BOLD}{msg}{C.END}")


def test_get(base, path, expect_status=200, expect_keys=None, label=None):
    """Test a GET endpoint. Returns (pass, response_json)."""
    url = f"{base}{path}"
    label = label or f"GET {path}"
    try:
        resp = requests.get(url, timeout=30)
    except requests.ConnectionError:
        fail(f"{label}: connection refused (is server running?)")
        return False, None
    except requests.Timeout:
        fail(f"{label}: timeout")
        return False, None

    if resp.status_code != expect_status:
        fail(f"{label}: status {resp.status_code} (expected {expect_status})")
        try:
            print(f"    {C.DIM}{resp.json()}{C.END}")
        except Exception:
            pass
        return False, None

    try:
        data = resp.json()
    except Exception:
        fail(f"{label}: not valid JSON")
        return False, None

    if expect_keys:
        missing = [k for k in expect_keys if k not in data]
        if missing:
            fail(f"{label}: missing keys {missing}")
            return False, data

    ok(f"{label}: {resp.status_code}")
    return True, data


def test_post(base, path, body, expect_status=200, label=None):
    url = f"{base}{path}"
    label = label or f"POST {path}"
    try:
        resp = requests.post(url, json=body, timeout=30)
    except requests.ConnectionError:
        fail(f"{label}: connection refused")
        return False, None

    if resp.status_code != expect_status:
        fail(f"{label}: status {resp.status_code} (expected {expect_status})")
        return False, None

    try:
        data = resp.json()
    except Exception:
        data = None

    ok(f"{label}: {resp.status_code}")
    return True, data


def test_server_status(base):
    header("Server Status")
    passed, data = test_get(base, "/status", expect_keys=["ports"])
    if not passed:
        return False

    ports = data.get("ports", {})
    for name, info in ports.items():
        status = info.get("status", "?")
        color = C.GREEN if status == "connected" else C.RED
        err = f" ({info.get('last_error', '')})" if info.get("last_error") else ""
        print(f"    {name}: {color}{status}{C.END}{err}")
    return True


def test_meter_apis(base):
    header("Meter APIs")
    passed = 0
    failed = 0

    # GET /meters
    subheader("GET /meters")
    ok_flag, data = test_get(base, "/meters")
    if ok_flag:
        passed += 1
        if isinstance(data, list):
            print(f"    Found {len(data)} meters")
            for m in data[:3]:
                print(f"    [{m.get('address')}] {m.get('name')} ({m.get('model')})")
            if len(data) > 3:
                print(f"    ... and {len(data) - 3} more")
    else:
        failed += 1

    # GET /meter/1/realtime
    subheader("GET /meter/{addr}/realtime")
    for addr in [1, 5]:
        ok_flag, data = test_get(base, f"/meter/{addr}/realtime",
                                  expect_keys=["address", "name", "data"],
                                  label=f"GET /meter/{addr}/realtime")
        if ok_flag:
            passed += 1
            meter_data = data.get("data", {})
            print(f"    {data.get('name')} ({data.get('model')}): {len(meter_data)} params")
            # Show first 3 values
            for name, info in list(meter_data.items())[:3]:
                val = info.get("value")
                unit = info.get("unit", "")
                err = info.get("error", "")
                if err:
                    print(f"    {C.YELLOW}{name}: {err}{C.END}")
                else:
                    print(f"    {name}: {val} {unit}")
        else:
            failed += 1

    # GET /meter/1/daily
    subheader("GET /meter/{addr}/daily")
    ok_flag, data = test_get(base, "/meter/1/daily?days_ago=1",
                              expect_keys=["period", "data"],
                              label="GET /meter/1/daily?days_ago=1")
    if ok_flag:
        passed += 1
        d = data.get("data", {})
        if "energy_active_total_kwh" in d:
            print(f"    Total energy: {d['energy_active_total_kwh']} kWh")
    else:
        failed += 1

    # DJSF daily should return 400
    ok_flag, _ = test_get(base, "/meter/5/daily?days_ago=1", expect_status=400,
                           label="GET /meter/5/daily (expect 400)")
    if ok_flag:
        passed += 1
    else:
        failed += 1

    # GET /meter/1/monthly
    subheader("GET /meter/{addr}/monthly")
    ok_flag, data = test_get(base, "/meter/1/monthly?months_ago=1",
                              expect_keys=["period", "data"],
                              label="GET /meter/1/monthly?months_ago=1")
    if ok_flag:
        passed += 1
    else:
        failed += 1

    # GET /meter/1/yearly
    subheader("GET /meter/{addr}/yearly")
    ok_flag, data = test_get(base, "/meter/1/yearly",
                              expect_keys=["period"],
                              label="GET /meter/1/yearly")
    if ok_flag:
        passed += 1
    else:
        failed += 1

    # Invalid meter
    subheader("Error handling")
    ok_flag, _ = test_get(base, "/meter/99/realtime", expect_status=404,
                           label="GET /meter/99/realtime (expect 404)")
    if ok_flag:
        passed += 1
    else:
        failed += 1

    return passed, failed


def test_parking_apis(base):
    header("Parking APIs")
    passed = 0
    failed = 0

    # GET /parking/spaces
    subheader("GET /parking/spaces")
    ok_flag, data = test_get(base, "/parking/spaces")
    if ok_flag:
        passed += 1
        if isinstance(data, list):
            print(f"    Found {len(data)} spaces")
    else:
        failed += 1

    # GET /parking/status
    subheader("GET /parking/status")
    ok_flag, data = test_get(base, "/parking/status",
                              expect_keys=["total", "occupied", "empty", "spaces"])
    if ok_flag:
        passed += 1
        print(f"    Total: {data.get('total')}, Online: {data.get('online')}, "
              f"Occupied: {data.get('occupied')}, Empty: {data.get('empty')}")
    else:
        failed += 1

    # GET /parking/status?zone=A
    ok_flag, data = test_get(base, "/parking/status?zone=A",
                              label="GET /parking/status?zone=A")
    if ok_flag:
        passed += 1
        spaces = data.get("spaces", [])
        a_spaces = [s for s in spaces if s.get("zone") == "A"]
        print(f"    Zone A: {len(a_spaces)} spaces")
    else:
        failed += 1

    # GET /parking/space/1
    subheader("GET /parking/space/{id}")
    ok_flag, data = test_get(base, "/parking/space/1",
                              expect_keys=["space_id", "data"],
                              label="GET /parking/space/1")
    if ok_flag:
        passed += 1
        regs = data.get("data", {})
        for name, info in regs.items():
            label_str = info.get("label", "")
            val = info.get("value", "?")
            extra = f" ({label_str})" if label_str else ""
            print(f"    {name}: {val}{extra}")
    else:
        failed += 1

    # GET /parking/summary
    subheader("GET /parking/summary")
    ok_flag, data = test_get(base, "/parking/summary",
                              expect_keys=["total_spaces", "occupied", "zones"])
    if ok_flag:
        passed += 1
        print(f"    Total: {data.get('total_spaces')}, "
              f"Occupied: {data.get('occupied')}, Empty: {data.get('empty')}")
        zones = data.get("zones", {})
        for z, info in zones.items():
            print(f"    Zone {z}: occ={info.get('occupied')} "
                  f"empty={info.get('empty')} offline={info.get('offline')}")
    else:
        failed += 1

    # POST /parking/space/1/color
    subheader("POST /parking/space/{id}/color")
    ok_flag, data = test_post(base, "/parking/space/1/color", {"color": 2},
                               label="POST /parking/space/1/color {green}")
    if ok_flag:
        passed += 1
        if data:
            print(f"    Success: {data.get('success')}, Color: {data.get('label')}")
    else:
        failed += 1

    # POST /parking/space/1/display_mode
    subheader("POST /parking/space/{id}/display_mode")
    ok_flag, data = test_post(base, "/parking/space/1/display_mode", {"mode": 0},
                               label="POST /parking/space/1/display_mode {normal}")
    if ok_flag:
        passed += 1
        if data:
            print(f"    Success: {data.get('success')}, Mode: {data.get('label')}")
    else:
        failed += 1

    # Error handling
    subheader("Error handling")
    ok_flag, _ = test_get(base, "/parking/space/99", expect_status=404,
                           label="GET /parking/space/99 (expect 404)")
    if ok_flag:
        passed += 1
    else:
        failed += 1

    ok_flag, _ = test_post(base, "/parking/space/1/color", {"color": 99},
                            expect_status=400,
                            label="POST color=99 (expect 400)")
    if ok_flag:
        passed += 1
    else:
        failed += 1

    return passed, failed


def main():
    parser = argparse.ArgumentParser(description="API integration test")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--meter-only", action="store_true")
    parser.add_argument("--parking-only", action="store_true")
    args = parser.parse_args()

    base = f"http://{args.host}:{args.port}"

    header("API Integration Test")
    print(f"  Server: {base}")

    # Check server is running
    if not test_server_status(base):
        print(f"\n  {C.RED}Server not running. Start with: python server.py{C.END}")
        sys.exit(1)

    total_passed = 0
    total_failed = 0

    if not args.parking_only:
        p, f = test_meter_apis(base)
        total_passed += p
        total_failed += f

    if not args.meter_only:
        p, f = test_parking_apis(base)
        total_passed += p
        total_failed += f

    header("Summary")
    print(f"  Passed: {C.GREEN}{total_passed}{C.END}")
    print(f"  Failed: {C.RED}{total_failed}{C.END}")

    if total_failed == 0:
        print(f"\n  {C.GREEN}{C.BOLD}All API tests passed!{C.END}")
    else:
        print(f"\n  {C.YELLOW}Some tests failed — check serial port connections.{C.END}")

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
