#!/usr/bin/env python3
"""
One-click parking space sensor test.

Tests 54 parking sensors across COM31 (zone A) and COM32 (zone B):
  - COM31: addresses 1-27 -> spaces 1-27
  - COM32: addresses 1-27 -> spaces 28-54

Usage:
    python test_parking_live.py
    python test_parking_live.py --zone A          # Test zone A only (COM31)
    python test_parking_live.py --zone B          # Test zone B only (COM32)
    python test_parking_live.py --space 1,2,28    # Test specific spaces
    python test_parking_live.py --detail          # Read all registers (not just status)
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def ensure_deps():
    try:
        import serial  # noqa
    except ImportError:
        print("Installing missing dependency: pyserial ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyserial", "-q"],
            stdout=subprocess.DEVNULL,
        )


ensure_deps()

import serial

sys.path.insert(0, str(Path(__file__).parent))

from meter import build_read_request, parse_read_response
from parking import (
    PARKING_SPACES, PARKING_BY_ID, PARKING_REGISTERS,
    build_parking_status_request, build_parking_all_request,
    parse_parking_status, parse_parking_all,
)


# ---------------------------------------------------------------------------
# Color output
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Serial helpers
# ---------------------------------------------------------------------------

def send_recv(ser, request, timeout=0.5):
    ser.reset_input_buffer()
    ser.write(request)
    time.sleep(0.05)

    response = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = ser.in_waiting
        if n > 0:
            response += ser.read(n)
            time.sleep(0.02)
        elif response:
            break
        else:
            time.sleep(0.01)
    return response if response else None


def open_port(port, baudrate, timeout):
    try:
        ser = serial.Serial(port=port, baudrate=baudrate, bytesize=8,
                            parity="N", stopbits=1, timeout=timeout)
        ok(f"Serial port {port} opened")
        return ser
    except serial.SerialException as e:
        fail(f"Cannot open {port}: {e}")
        return None


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------

def test_space_status(ser, space, timeout):
    """Quick status test for one space."""
    req = build_parking_status_request(space.slave_addr)
    resp = send_recv(ser, req, timeout)

    if resp is None:
        return None, "no response"

    data = parse_read_response(resp)
    if data is None:
        return None, f"parse error (RX: {resp.hex()})"

    val = parse_parking_status(data)
    if val is None:
        return None, "invalid data"

    return int(val), None


def test_space_detail(ser, space, timeout):
    """Full register read for one space."""
    req = build_parking_all_request(space.slave_addr)
    resp = send_recv(ser, req, timeout)

    if resp is None:
        return None, "no response"

    data = parse_read_response(resp)
    if data is None:
        return None, f"parse error (RX: {resp.hex()})"

    result = parse_parking_all(data)
    if result is None:
        return None, "invalid data"

    return result, None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Parking space sensor test")
    parser.add_argument("--com31", default="COM31", help="COM port for zone A")
    parser.add_argument("--com32", default="COM32", help="COM port for zone B")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--zone", type=str, help="Test zone A or B only")
    parser.add_argument("--space", type=str, help="Comma-separated space IDs (1-54)")
    parser.add_argument("--detail", action="store_true",
                        help="Read all registers (not just status)")
    args = parser.parse_args()

    header("Parking Space Sensor Test")
    print(f"  COM31 (Zone A): {args.com31}")
    print(f"  COM32 (Zone B): {args.com32}")
    print(f"  Baud: {args.baudrate}, Timeout: {args.timeout}s")

    # Determine which spaces to test
    if args.space:
        space_ids = [int(x.strip()) for x in args.space.split(",")]
        spaces = [PARKING_BY_ID[i] for i in space_ids if i in PARKING_BY_ID]
    elif args.zone:
        zone = args.zone.upper()
        spaces = [s for s in PARKING_SPACES if s.zone == zone]
    else:
        spaces = PARKING_SPACES

    print(f"  Testing {len(spaces)} spaces")

    # Open serial ports
    ports_needed = set(s.com_port for s in spaces)
    serial_conns = {}

    for port_name in ports_needed:
        actual_port = args.com31 if port_name == "COM31" else args.com32
        subheader(f"Opening {port_name} ({actual_port})")
        ser = open_port(actual_port, args.baudrate, args.timeout)
        if ser:
            serial_conns[port_name] = ser

    # Test each space
    total_ok = 0
    total_fail = 0
    occupied = 0
    empty = 0

    for port_name in ["COM31", "COM32"]:
        port_spaces = [s for s in spaces if s.com_port == port_name]
        if not port_spaces:
            continue

        zone = port_spaces[0].zone
        header(f"Zone {zone} ({port_name}) - {len(port_spaces)} spaces")

        ser = serial_conns.get(port_name)
        if ser is None:
            fail(f"{port_name} not available, skipping {len(port_spaces)} spaces")
            total_fail += len(port_spaces)
            continue

        for space in port_spaces:
            if args.detail:
                result, err = test_space_detail(ser, space, args.timeout)
                if err:
                    fail(f"Space {space.space_id:>2d} (addr {space.slave_addr:>2d}): {err}")
                    total_fail += 1
                else:
                    status_info = result.get("vehicle_status", {})
                    label = status_info.get("label", "?")
                    battery = result.get("battery_level", {}).get("value", "?")
                    temp = result.get("temperature", {}).get("value", "?")
                    fault = result.get("fault_code", {}).get("value", 0)
                    count = result.get("detection_count", {}).get("value", "?")

                    color = C.RED if label == "occupied" else C.GREEN
                    fault_str = f" {C.RED}FAULT={int(fault)}{C.END}" if fault else ""
                    ok(f"Space {space.space_id:>2d}: {color}{label:<8s}{C.END} "
                       f"bat={battery}% temp={temp}°C count={count}{fault_str}")
                    total_ok += 1
                    if label == "occupied":
                        occupied += 1
                    else:
                        empty += 1
            else:
                val, err = test_space_status(ser, space, args.timeout)
                if err:
                    fail(f"Space {space.space_id:>2d} (addr {space.slave_addr:>2d}): {err}")
                    total_fail += 1
                else:
                    label = "occupied" if val else "empty"
                    color = C.RED if val else C.GREEN
                    ok(f"Space {space.space_id:>2d}: {color}{label}{C.END}")
                    total_ok += 1
                    if val:
                        occupied += 1
                    else:
                        empty += 1

            time.sleep(0.03)  # inter-frame delay

    # Close ports
    for ser in serial_conns.values():
        ser.close()

    # Summary
    header("Summary")
    print(f"  Online:   {C.GREEN}{total_ok}{C.END}")
    print(f"  Offline:  {C.RED}{total_fail}{C.END}")
    print(f"  Occupied: {C.YELLOW}{occupied}{C.END}")
    print(f"  Empty:    {C.GREEN}{empty}{C.END}")

    if total_fail == 0:
        print(f"\n  {C.GREEN}{C.BOLD}All sensors responding!{C.END}")
    elif total_ok == 0:
        print(f"\n  {C.RED}{C.BOLD}No sensors responding. Check wiring and addresses.{C.END}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
