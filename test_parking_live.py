#!/usr/bin/env python3
"""
One-click parking detector test (custom RS485 protocol).

Tests 54 detectors: COM31 zone A (addr 1-27), COM32 zone B (addr 1-27).

Usage:
    python test_parking_live.py
    python test_parking_live.py --zone A
    python test_parking_live.py --space 1,2,28
    python test_parking_live.py --detail            # Read all 8 registers
    python test_parking_live.py --set-color 1 green  # Set space 1 LED to green
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
        print("Installing pyserial ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pyserial", "-q"],
            stdout=subprocess.DEVNULL,
        )


ensure_deps()

import serial

sys.path.insert(0, str(Path(__file__).parent))

from parking import (
    PARKING_SPACES, PARKING_BY_ID,
    build_read_all, build_read_status, build_set_display_mode, build_set_color,
    parse_response, parse_detector_registers, expected_frame_len,
    STATUS_NAMES, DISPLAY_MODE_NAMES, COLOR_NAMES,
)


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

def header(msg):
    print(f"\n{C.BOLD}{C.CYAN}{'=' * 60}{C.END}")
    print(f"{C.BOLD}{C.CYAN}  {msg}{C.END}")
    print(f"{C.BOLD}{C.CYAN}{'=' * 60}{C.END}")


def send_recv(ser, request, timeout=0.5):
    ser.reset_input_buffer()
    ser.write(request)
    time.sleep(0.05)

    response = b""
    exp_len = None
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = ser.in_waiting
        if n > 0:
            response += ser.read(n)
            if exp_len is None and len(response) >= 5:
                exp_len = expected_frame_len(response)
            if exp_len and len(response) >= exp_len:
                return response[:exp_len]
            time.sleep(0.01)
        elif response:
            if exp_len and len(response) < exp_len:
                time.sleep(0.01)
                continue
            break
        else:
            time.sleep(0.01)
    return response if response else None


def open_port(port, baudrate, timeout):
    try:
        ser = serial.Serial(port=port, baudrate=baudrate, bytesize=8,
                            parity="N", stopbits=1, timeout=timeout)
        ok(f"{port} opened")
        return ser
    except serial.SerialException as e:
        fail(f"Cannot open {port}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Parking detector test")
    parser.add_argument("--com31", default="COM31")
    parser.add_argument("--com32", default="COM32")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--zone", type=str, help="A or B")
    parser.add_argument("--space", type=str, help="Space IDs: 1,2,28")
    parser.add_argument("--detail", action="store_true", help="Read all registers")
    parser.add_argument("--set-color", nargs=2, metavar=("SPACE_ID", "COLOR"),
                        help="Set LED color: 1 green")
    parser.add_argument("--set-mode", nargs=2, metavar=("SPACE_ID", "MODE"),
                        help="Set display mode: 1 vip")
    args = parser.parse_args()

    header("Parking Detector Test (Custom RS485 Protocol)")

    # Handle set-color / set-mode commands
    if args.set_color or args.set_mode:
        if args.set_color:
            sid, val_str = int(args.set_color[0]), args.set_color[1].lower()
            color_map = {v.lower(): k for k, v in COLOR_NAMES.items()}
            color_map.update({str(k): k for k in COLOR_NAMES})
            if val_str not in color_map:
                fail(f"Unknown color: {val_str}. Valid: {COLOR_NAMES}")
                sys.exit(1)
            color_val = color_map[val_str]
        else:
            sid, val_str = int(args.set_mode[0]), args.set_mode[1].lower()

        space = PARKING_BY_ID.get(sid)
        if not space:
            fail(f"Space {sid} not found")
            sys.exit(1)

        port = args.com31 if space.com_port == "COM31" else args.com32
        ser = open_port(port, args.baudrate, args.timeout)
        if not ser:
            sys.exit(1)

        if args.set_color:
            req = build_set_color(space.slave_addr, color_val)
            print(f"  Setting space {sid} color to {COLOR_NAMES[color_val]}...")
        else:
            mode_map = {v.lower(): k for k, v in DISPLAY_MODE_NAMES.items()}
            mode_map.update({str(k): k for k in DISPLAY_MODE_NAMES})
            if val_str not in mode_map:
                fail(f"Unknown mode: {val_str}. Valid: {DISPLAY_MODE_NAMES}")
                sys.exit(1)
            mode_val = mode_map[val_str]
            req = build_set_display_mode(space.slave_addr, mode_val)
            print(f"  Setting space {sid} mode to {DISPLAY_MODE_NAMES[mode_val]}...")

        print(f"  TX: {req.hex()}")
        resp = send_recv(ser, req, args.timeout)
        if resp:
            print(f"  RX: {resp.hex()}")
            parsed = parse_response(resp)
            if parsed and parsed["opcode"] == 0x81:
                ok("Write confirmed")
            else:
                fail("Write not confirmed")
        else:
            fail("No response")
        ser.close()
        return

    # Determine spaces to test
    if args.space:
        space_ids = [int(x.strip()) for x in args.space.split(",")]
        spaces = [PARKING_BY_ID[i] for i in space_ids if i in PARKING_BY_ID]
    elif args.zone:
        spaces = [s for s in PARKING_SPACES if s.zone == args.zone.upper()]
    else:
        spaces = PARKING_SPACES

    print(f"  Testing {len(spaces)} detectors\n")

    # Open ports
    ports_needed = set(s.com_port for s in spaces)
    serial_conns = {}
    for pn in ports_needed:
        actual = args.com31 if pn == "COM31" else args.com32
        ser = open_port(actual, args.baudrate, args.timeout)
        if ser:
            serial_conns[pn] = ser

    total_ok = 0
    total_fail = 0
    occupied = 0
    empty = 0

    for port_name in ["COM31", "COM32"]:
        port_spaces = [s for s in spaces if s.com_port == port_name]
        if not port_spaces:
            continue

        zone = port_spaces[0].zone
        header(f"Zone {zone} ({port_name}) - {len(port_spaces)} detectors")

        ser = serial_conns.get(port_name)
        if not ser:
            fail(f"{port_name} not available")
            total_fail += len(port_spaces)
            continue

        for space in port_spaces:
            if args.detail:
                req = build_read_all(space.slave_addr)
                resp = send_recv(ser, req, args.timeout)
                if not resp:
                    fail(f"Space {space.space_id:>2d} (addr {space.slave_addr:>2d}): no response")
                    total_fail += 1
                    continue

                parsed = parse_response(resp)
                if not parsed:
                    fail(f"Space {space.space_id:>2d}: parse error (RX: {resp.hex()})")
                    total_fail += 1
                    continue

                regs = parse_detector_registers(parsed["data"], parsed["start_reg"])
                status = regs.get("dev_status", {})
                label = status.get("label", "?")
                color = C.RED if status.get("value") else C.GREEN
                dist = regs.get("distance", {}).get("value", "?")
                dsp = regs.get("dsp_type", {}).get("label", "?")
                rs485 = regs.get("rs485_state", {}).get("label", "?")
                led = regs.get("user_color", {}).get("label", "?")

                ok(f"Space {space.space_id:>2d}: {color}{label:<4s}{C.END} "
                   f"dist={dist}dm dsp={dsp} 485={rs485} led={led}")
                total_ok += 1
                if status.get("value"):
                    occupied += 1
                else:
                    empty += 1
            else:
                req = build_read_status(space.slave_addr)
                resp = send_recv(ser, req, args.timeout)
                if not resp:
                    fail(f"Space {space.space_id:>2d} (addr {space.slave_addr:>2d}): no response")
                    total_fail += 1
                    continue

                parsed = parse_response(resp)
                if not parsed or not parsed["data"]:
                    fail(f"Space {space.space_id:>2d}: parse error")
                    total_fail += 1
                    continue

                val = parsed["data"][0]
                label = STATUS_NAMES.get(val, f"?({val})")
                color = C.RED if val else C.GREEN
                ok(f"Space {space.space_id:>2d}: {color}{label}{C.END}")
                total_ok += 1
                if val:
                    occupied += 1
                else:
                    empty += 1

            time.sleep(0.03)

    for ser in serial_conns.values():
        ser.close()

    header("Summary")
    print(f"  Online:   {C.GREEN}{total_ok}{C.END}")
    print(f"  Offline:  {C.RED}{total_fail}{C.END}")
    print(f"  有车:     {C.YELLOW}{occupied}{C.END}")
    print(f"  无车:     {C.GREEN}{empty}{C.END}")

    sys.exit(0 if total_fail == 0 else 1)


if __name__ == "__main__":
    main()
