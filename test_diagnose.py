#!/usr/bin/env python3
"""
Meter communication diagnostic tool.

Scans all meters on COM33, tests different baudrates, register ranges,
and identifies which meters respond correctly.

Usage:
    python test_diagnose.py
    python test_diagnose.py --port COM33
    python test_diagnose.py --addr 6         # Diagnose single meter
"""

import argparse
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from deps import ensure_deps
ensure_deps()

import serial
from meter import build_read_request, parse_read_response, crc16_modbus, verify_crc


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


def send_recv(ser, request, timeout=0.5):
    time.sleep(0.05)
    ser.reset_input_buffer()
    ser.write(request)
    time.sleep(0.08)

    response = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = ser.in_waiting
        if n > 0:
            response += ser.read(n)
            time.sleep(0.02)
        elif response:
            time.sleep(0.01)
            if ser.in_waiting == 0:
                break
        else:
            time.sleep(0.01)
    return response if response else None


def test_register(ser, addr, reg, count, timeout=0.5):
    """Test reading a register. Returns (success, raw_response, parsed_data)."""
    req = build_read_request(addr, reg, count)
    resp = send_recv(ser, req, timeout)
    if resp is None:
        return False, None, None
    data = parse_read_response(resp)
    return data is not None, resp, data


def diagnose_meter(port, addr, baudrates, timeout):
    """Run full diagnostics on one meter address."""
    header(f"Diagnosing address {addr} on {port}")

    # ---------------------------------------------------------------
    # Phase 1: Baudrate scan
    # ---------------------------------------------------------------
    subheader("Phase 1: Baudrate scan")
    working_baud = None

    for baud in baudrates:
        try:
            ser = serial.Serial(port=port, baudrate=baud, bytesize=8,
                                parity="N", stopbits=1, timeout=timeout)
        except serial.SerialException as e:
            fail(f"{baud} baud: cannot open port ({e})")
            continue

        # Use reg 5 (temperature) as probe — 1 register, known to work
        success, resp, data = test_register(ser, addr, 5, 1, timeout)
        ser.close()

        if success:
            val = struct.unpack(">h", data)[0] * 0.1
            ok(f"{baud} baud: OK (temperature = {val:.1f}°C)")
            working_baud = baud
            break
        elif resp:
            fail(f"{baud} baud: got response but CRC failed ({resp.hex()})")
        else:
            fail(f"{baud} baud: no response")

    if working_baud is None:
        print(f"\n  {C.RED}{C.BOLD}No working baudrate found for address {addr}.{C.END}")
        print(f"  Check: wiring, power, address setting on the meter.")
        return

    # ---------------------------------------------------------------
    # Phase 2: Register scan (at working baudrate)
    # ---------------------------------------------------------------
    subheader(f"Phase 2: Register scan @ {working_baud} baud")

    ser = serial.Serial(port=port, baudrate=working_baud, bytesize=8,
                        parity="N", stopbits=1, timeout=timeout)

    # Test all known DJSF registers
    test_regs = [
        (0, 1, "电压值 (integer)"),
        (1, 1, "电压小数点 (DPT)"),
        (2, 1, "电流值 (integer)"),
        (3, 1, "电流小数点 (DCT)"),
        (4, 1, "断线检测"),
        (5, 1, "温度"),
        (8, 1, "功率值 (integer)"),
        (9, 1, "功率小数点 (DP)"),
        (12, 1, "正向电能 (hi)"),
        (13, 1, "正向电能 (lo)"),
        (14, 1, "反向电能 (hi)"),
        (15, 1, "反向电能 (lo)"),
        (50, 1, "电压 Float (hi)"),
        (51, 1, "电压 Float (lo)"),
        (52, 1, "电流 Float (hi)"),
        (53, 1, "电流 Float (lo)"),
        (54, 1, "功率 Float (hi)"),
        (55, 1, "功率 Float (lo)"),
    ]

    working_regs = []
    failed_regs = []

    for reg, count, name in test_regs:
        success, resp, data = test_register(ser, addr, reg, count, timeout)
        if success:
            val = struct.unpack(">H", data)[0]
            ok(f"reg {reg:>3d} ({name:<20s}): 0x{val:04X} ({val})")
            working_regs.append((reg, name, val))
        elif resp:
            fail(f"reg {reg:>3d} ({name:<20s}): CRC FAIL ({resp.hex()})")
            failed_regs.append((reg, name))
        else:
            fail(f"reg {reg:>3d} ({name:<20s}): no response")
            failed_regs.append((reg, name))

    # ---------------------------------------------------------------
    # Phase 3: Multi-register read test
    # ---------------------------------------------------------------
    subheader("Phase 3: Multi-register read (count=2)")

    test_multi = [
        (5, 2, "reg 5-6"),
        (12, 2, "reg 12-13 (正向电能)"),
        (50, 2, "reg 50-51 (电压 Float)"),
        (52, 2, "reg 52-53 (电流 Float)"),
    ]

    for reg, count, name in test_multi:
        success, resp, data = test_register(ser, addr, reg, count, timeout)
        if success:
            ok(f"{name}: OK ({data.hex()})")
        elif resp:
            fail(f"{name}: CRC FAIL ({resp.hex()})")
        else:
            fail(f"{name}: no response")

    # ---------------------------------------------------------------
    # Phase 4: Reliability test (repeat same register 10 times)
    # ---------------------------------------------------------------
    subheader("Phase 4: Reliability test (reg 5, 10 reads)")

    success_count = 0
    fail_count = 0
    for i in range(10):
        success, resp, data = test_register(ser, addr, 5, 1, timeout)
        if success:
            success_count += 1
        else:
            fail_count += 1

    rate = success_count / 10 * 100
    color = C.GREEN if rate >= 80 else C.YELLOW if rate >= 50 else C.RED
    print(f"  {color}Success rate: {success_count}/10 ({rate:.0f}%){C.END}")

    if working_regs:
        # Test reliability on a float register
        float_reg = None
        for reg, name, val in working_regs:
            if reg >= 50:
                float_reg = reg
                break

        if float_reg:
            subheader(f"Phase 4b: Reliability test (reg {float_reg}, 10 reads)")
            s2 = 0
            for i in range(10):
                success, resp, data = test_register(ser, addr, float_reg, 1, timeout)
                if success:
                    s2 += 1
            rate2 = s2 / 10 * 100
            color2 = C.GREEN if rate2 >= 80 else C.YELLOW if rate2 >= 50 else C.RED
            print(f"  {color2}Success rate: {s2}/10 ({rate2:.0f}%){C.END}")

    ser.close()

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    header(f"Diagnosis for address {addr}")
    print(f"  Working baudrate:  {C.GREEN}{working_baud}{C.END}")
    print(f"  Working registers: {C.GREEN}{len(working_regs)}{C.END}/{len(test_regs)}")
    print(f"  Failed registers:  {C.RED}{len(failed_regs)}{C.END}")

    if failed_regs:
        print(f"\n  {C.BOLD}Failed registers:{C.END}")
        for reg, name in failed_regs:
            print(f"    reg {reg}: {name}")

    if rate < 80:
        print(f"\n  {C.YELLOW}{C.BOLD}Low reliability ({rate:.0f}%). Check:{C.END}")
        print(f"    - RS485 A/B wiring to this meter")
        print(f"    - Terminal resistor (120Ω between A and B)")
        print(f"    - Cable length and shielding")
        print(f"    - Other devices on the same bus")


def scan_all(port, baudrate, timeout):
    """Quick scan all 8 meter addresses."""
    header(f"Quick scan: {port} @ {baudrate} baud")

    try:
        ser = serial.Serial(port=port, baudrate=baudrate, bytesize=8,
                            parity="N", stopbits=1, timeout=timeout)
    except serial.SerialException as e:
        fail(f"Cannot open {port}: {e}")
        return

    meters = [
        (1, "ADL400", "电网侧电表", 0x0077, "frequency"),
        (2, "ADL400", "逆变侧电表", 0x0077, "frequency"),
        (3, "ADL400", "交流桩电表", 0x0077, "frequency"),
        (4, "ADL400", "用户负载电表", 0x0077, "frequency"),
        (5, "DJSF1352-RN-6", "整流侧电表", 5, "temperature"),
        (6, "DJSF1352-RN", "电池柜电表", 5, "temperature"),
        (7, "DJSF1352-RN", "直流桩电表", 5, "temperature"),
        (8, "DJSF1352-RN", "光伏电表", 5, "temperature"),
    ]

    online = 0
    for addr, model, name, probe_reg, probe_name in meters:
        success, resp, data = test_register(ser, addr, probe_reg, 1, timeout)

        if success:
            online += 1
            if probe_name == "temperature":
                val = struct.unpack(">h", data)[0] * 0.1
                ok(f"[{addr}] {name} ({model}): {probe_name} = {val:.1f}°C")
            elif probe_name == "frequency":
                val = struct.unpack(">H", data)[0] * 0.01
                ok(f"[{addr}] {name} ({model}): {probe_name} = {val:.2f} Hz")
        elif resp:
            warn(f"[{addr}] {name} ({model}): response but CRC FAIL ({resp.hex()})")
        else:
            fail(f"[{addr}] {name} ({model}): no response")

    ser.close()

    print(f"\n  Online: {C.GREEN}{online}{C.END}/8")


def main():
    parser = argparse.ArgumentParser(description="Meter communication diagnostics")
    parser.add_argument("--port", default="COM33", help="Serial port")
    parser.add_argument("--addr", type=int, help="Diagnose specific address (1-8)")
    parser.add_argument("--baudrate", type=int, default=9600, help="Default baudrate")
    parser.add_argument("--timeout", type=float, default=0.5, help="Response timeout")
    args = parser.parse_args()

    baudrates_to_try = [9600, 4800, 19200, 2400, 38400, 1200]

    if args.addr:
        diagnose_meter(args.port, args.addr, baudrates_to_try, args.timeout)
    else:
        # Quick scan first
        scan_all(args.port, args.baudrate, args.timeout)

        print(f"\n  {C.DIM}Tip: use --addr N for full diagnosis of a specific meter{C.END}")
        print(f"  {C.DIM}Example: python test_diagnose.py --addr 6{C.END}")


if __name__ == "__main__":
    main()
