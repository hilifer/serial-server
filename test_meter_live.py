#!/usr/bin/env python3
"""
One-click live test script for energy meters via COM33.

Tests all 8 meters on the bus:
  - ADL400 (addr 1-4): AC voltage/current/power/energy + daily/monthly history
  - DJSF1352-RN-6 (addr 5): DC single-channel
  - DJSF1352-RN (addr 6-8): DC meters (addr 7,8 are dual-channel)

Usage:
    python test_meter_live.py
    python test_meter_live.py --port COM33 --baudrate 9600
    python test_meter_live.py --addr 1           # Test single meter
    python test_meter_live.py --addr 1,2,5       # Test specific meters
"""

import argparse
import struct
import sys
import time
import logging
from pathlib import Path

import serial

sys.path.insert(0, str(Path(__file__).parent))

from meter import (
    MeterType, METERS, METER_BY_ADDR,
    ADL400_REALTIME, DJSF_REALTIME,
    build_read_request, parse_read_response,
    parse_register_value, parse_adl400_history_block,
    parse_djsf_monthly_energy,
    build_daily_history_request,
    build_monthly_history_request_adl400,
    build_monthly_history_request_djsf,
)

# ---------------------------------------------------------------------------
# Color output helpers
# ---------------------------------------------------------------------------

class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def ok(msg: str):
    print(f"  {Color.GREEN}✓{Color.END} {msg}")


def fail(msg: str):
    print(f"  {Color.RED}✗{Color.END} {msg}")


def warn(msg: str):
    print(f"  {Color.YELLOW}⚠{Color.END} {msg}")


def header(msg: str):
    print(f"\n{Color.BOLD}{Color.CYAN}{'=' * 60}{Color.END}")
    print(f"{Color.BOLD}{Color.CYAN}  {msg}{Color.END}")
    print(f"{Color.BOLD}{Color.CYAN}{'=' * 60}{Color.END}")


def subheader(msg: str):
    print(f"\n  {Color.BOLD}{msg}{Color.END}")


# ---------------------------------------------------------------------------
# Serial communication
# ---------------------------------------------------------------------------

def send_recv(ser: serial.Serial, request: bytes,
              timeout: float = 0.5) -> bytes | None:
    """Send Modbus request and receive response."""
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


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------

def test_realtime(ser: serial.Serial, addr: int, meter_type: MeterType) -> tuple[int, int]:
    """Test reading all realtime registers. Returns (pass_count, fail_count)."""
    subheader("实时数据 (Realtime)")
    regs = ADL400_REALTIME if meter_type == MeterType.ADL400 else DJSF_REALTIME
    passed = 0
    failed = 0

    for name, rdef in regs.items():
        request = build_read_request(addr, rdef.address, rdef.count)
        response = send_recv(ser, request)

        if response is None:
            fail(f"{name}: 无响应")
            failed += 1
            continue

        data = parse_read_response(response)
        if data is None:
            fail(f"{name}: 解析失败 (RX: {response.hex()})")
            failed += 1
            continue

        value = parse_register_value(data, rdef)
        ok(f"{name}: {value} {rdef.unit}")
        passed += 1

    return passed, failed


def test_daily_history(ser: serial.Serial, addr: int) -> tuple[int, int]:
    """Test reading daily history for ADL400 (yesterday and 7 days ago)."""
    subheader("日冻结数据 (Daily History)")
    passed = 0
    failed = 0

    for days in [1, 7]:
        request = build_daily_history_request(addr, days)
        if request is None:
            continue

        response = send_recv(ser, request, timeout=1.0)
        if response is None:
            fail(f"{days}天前: 无响应")
            failed += 1
            continue

        data = parse_read_response(response)
        if data is None:
            fail(f"{days}天前: 解析失败")
            failed += 1
            continue

        block = parse_adl400_history_block(data)
        if block is None:
            fail(f"{days}天前: 数据块解析失败")
            failed += 1
            continue

        ok(f"{days}天前: 冻结时间={block['freeze_time']}, "
           f"总有功={block['energy_active_total_kwh']:.2f} kWh, "
           f"尖={block['energy_active_peak_kwh']:.2f}, "
           f"峰={block['energy_active_high_kwh']:.2f}, "
           f"平={block['energy_active_mid_kwh']:.2f}, "
           f"谷={block['energy_active_low_kwh']:.2f}")
        passed += 1

    return passed, failed


def test_monthly_history_adl400(ser: serial.Serial, addr: int) -> tuple[int, int]:
    """Test reading monthly history for ADL400 (last 3 months)."""
    subheader("月冻结数据 (Monthly History)")
    passed = 0
    failed = 0

    for months in [1, 2, 3]:
        request = build_monthly_history_request_adl400(addr, months)
        if request is None:
            continue

        response = send_recv(ser, request, timeout=1.0)
        if response is None:
            fail(f"{months}月前: 无响应")
            failed += 1
            continue

        data = parse_read_response(response)
        if data is None:
            fail(f"{months}月前: 解析失败")
            failed += 1
            continue

        block = parse_adl400_history_block(data)
        if block is None:
            fail(f"{months}月前: 数据块解析失败")
            failed += 1
            continue

        ok(f"{months}月前: 冻结时间={block['freeze_time']}, "
           f"总有功={block['energy_active_total_kwh']:.2f} kWh")
        passed += 1

    return passed, failed


def test_monthly_history_djsf(ser: serial.Serial, addr: int) -> tuple[int, int]:
    """Test reading monthly history for DJSF (last 3 months)."""
    subheader("月电能数据 (Monthly Energy)")
    passed = 0
    failed = 0

    for month in [1, 2, 3]:
        for direction in ["forward", "reverse"]:
            request = build_monthly_history_request_djsf(addr, month, direction)
            if request is None:
                continue

            label = "正向" if direction == "forward" else "反向"
            response = send_recv(ser, request, timeout=1.0)
            if response is None:
                fail(f"第{month}月 {label}: 无响应")
                failed += 1
                continue

            data = parse_read_response(response)
            if data is None:
                fail(f"第{month}月 {label}: 解析失败")
                failed += 1
                continue

            kwh = parse_djsf_monthly_energy(data)
            ok(f"第{month}月 {label}: {kwh:.3f} kWh")
            passed += 1

    return passed, failed


def test_communication(ser: serial.Serial, addr: int) -> bool:
    """Quick connectivity test: read 1 register."""
    meter = METER_BY_ADDR.get(addr)
    if not meter:
        return False

    if meter.meter_type == MeterType.ADL400:
        request = build_read_request(addr, 0x0077, 1)  # frequency
    else:
        request = build_read_request(addr, 50, 2)  # voltage float

    response = send_recv(ser, request)
    if response:
        data = parse_read_response(response)
        return data is not None
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Energy Meter Live Test (Modbus RTU via COM33)")
    parser.add_argument("--port", default="COM33",
                        help="Serial port (default: COM33)")
    parser.add_argument("--baudrate", type=int, default=9600,
                        help="Baud rate (default: 9600)")
    parser.add_argument("--addr", type=str, default="",
                        help="Comma-separated meter addresses to test (default: all)")
    parser.add_argument("--timeout", type=float, default=0.5,
                        help="Response timeout in seconds (default: 0.5)")
    args = parser.parse_args()

    header("MQTT WS 串口透传 - 电表协议测试")
    print(f"  串口: {args.port} @ {args.baudrate} baud")
    print(f"  超时: {args.timeout}s")

    # Determine which meters to test
    if args.addr:
        test_addrs = [int(a.strip()) for a in args.addr.split(",")]
    else:
        test_addrs = [m.slave_addr for m in METERS]

    print(f"  测试电表地址: {test_addrs}")

    # Open serial port
    try:
        ser = serial.Serial(
            port=args.port,
            baudrate=args.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=args.timeout,
        )
        ok(f"串口 {args.port} 打开成功")
    except serial.SerialException as e:
        fail(f"串口打开失败: {e}")
        sys.exit(1)

    total_passed = 0
    total_failed = 0
    meters_online = 0
    meters_offline = 0

    for addr in test_addrs:
        meter = METER_BY_ADDR.get(addr)
        if meter is None:
            warn(f"地址 {addr} 未配置，跳过")
            continue

        header(f"[地址 {addr}] {meter.name} ({meter.model}) - {meter.location}"
               + (f" [{meter.note}]" if meter.note else ""))

        # Connectivity test
        subheader("通信测试 (Communication)")
        if test_communication(ser, addr):
            ok("通信正常")
            meters_online += 1
        else:
            fail("通信失败 - 请检查接线和地址设置")
            meters_offline += 1
            total_failed += 1
            continue

        # Realtime data
        p, f = test_realtime(ser, addr, meter.meter_type)
        total_passed += p
        total_failed += f

        # History data
        if meter.meter_type == MeterType.ADL400:
            p, f = test_daily_history(ser, addr)
            total_passed += p
            total_failed += f

            p, f = test_monthly_history_adl400(ser, addr)
            total_passed += p
            total_failed += f
        else:
            p, f = test_monthly_history_djsf(ser, addr)
            total_passed += p
            total_failed += f

    # Summary
    header("测试汇总 (Summary)")
    print(f"  在线电表: {meters_online}/{meters_online + meters_offline}")
    print(f"  通过: {Color.GREEN}{total_passed}{Color.END}")
    print(f"  失败: {Color.RED}{total_failed}{Color.END}")

    if total_failed == 0 and meters_offline == 0:
        print(f"\n  {Color.GREEN}{Color.BOLD}所有测试通过！{Color.END}")
    elif meters_offline > 0:
        print(f"\n  {Color.YELLOW}{Color.BOLD}"
              f"有 {meters_offline} 个电表离线，请检查接线。{Color.END}")

    ser.close()
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
