#!/usr/bin/env python3
"""
Meter communication diagnostic tool.

Scans all meters on COM33, reads ALL available data including:
  - Realtime: voltage/current/power/frequency/energy
  - Daily history (ADL400): up to 7 days, with 尖峰平谷
  - Monthly history: up to 12 months
  - Yearly summary

Usage:
    python test_diagnose.py                   # Full scan, all data
    python test_diagnose.py --addr 6          # Diagnose single meter
    python test_diagnose.py --quick           # Quick scan, probe only
"""

import argparse
import struct
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from deps import ensure_deps
ensure_deps()

import logging
logging.basicConfig(level=logging.WARNING)

import serial
from meter import (
    build_read_request, parse_read_response, parse_register_value,
    crc16_modbus, verify_crc,
    ADL400_REALTIME, DJSF_RN_REALTIME, DJSF_RN6_REALTIME, get_realtime_regs,
    build_daily_history_request, build_monthly_history_request_adl400,
    build_monthly_history_request_djsf,
    parse_adl400_history_block, parse_djsf_monthly_energy,
    RegisterDef, MeterType, METERS, METER_BY_ADDR,
    ADL400_DAILY_MAX, ADL400_MONTHLY_MAX, DJSF_MONTHLY_MAX,
)


# ---------------------------------------------------------------------------
# Chinese labels
# ---------------------------------------------------------------------------

ADL400_LABELS = {
    "voltage_a": "A相电压(一次侧)",
    "voltage_b": "B相电压(一次侧)",
    "voltage_c": "C相电压(一次侧)",
    "current_a": "A相电流(一次侧)",
    "current_b": "B相电流(一次侧)",
    "current_c": "C相电流(一次侧)",
    "power_total": "总有功功率(一次侧)",
    "power_a": "A相功率(一次侧)",
    "power_b": "B相功率(一次侧)",
    "power_c": "C相功率(一次侧)",
    "reactive_power_total": "总无功功率(一次侧)",
    "apparent_power_total": "总视在功率(一次侧)",
    "power_factor": "总功率因数",
    "frequency": "频率",
    "energy_forward_total": "正向有功总电能",
    "energy_reverse_total": "反向有功总电能",
    "energy_combined_total": "组合有功总电能",
}

DJSF_LABELS = {
    "voltage": "直流电压",
    "current": "直流电流",
    "power": "直流功率",
    "energy_forward_total": "正向有功总电能",
    "energy_reverse_total": "反向有功总电能",
    "temperature": "内部温度",
}


from colors import C


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


def read_reg(ser, addr, reg, count, timeout=0.5):
    """Read with retry. Returns parsed data bytes or None."""
    for _ in range(3):
        req = build_read_request(addr, reg, count)
        resp = send_recv(ser, req, timeout)
        if resp:
            data = parse_read_response(resp)
            if data is not None:
                return data
    return None


def safe_read(ser, addr, reg, count, timeout=0.5):
    """Read with retry + single-register fallback."""
    data = read_reg(ser, addr, reg, count, timeout)
    if data is not None:
        return data
    if count <= 1:
        return None
    # Fallback: read one at a time
    combined = b""
    for i in range(count):
        d = read_reg(ser, addr, reg + i, 1, timeout)
        if d is None:
            return None
        combined += d
    return combined


# ---------------------------------------------------------------------------
# Read realtime data
# ---------------------------------------------------------------------------

def read_realtime(ser, addr, meter_type, timeout):
    """Read all realtime parameters. Returns list of (label, value_str)."""
    if meter_type == "ADL400":
        mt = MeterType.ADL400
    elif meter_type == "DJSF1352-RN-6":
        mt = MeterType.DJSF1352_RN_6
    else:
        mt = MeterType.DJSF1352_RN
    regs = get_realtime_regs(mt)
    labels = ADL400_LABELS if mt == MeterType.ADL400 else DJSF_LABELS

    results = []
    for name, rdef in regs.items():
        label = labels.get(name, name)
        data = safe_read(ser, addr, rdef.address, rdef.count, timeout)
        if data is not None:
            try:
                value = parse_register_value(data, rdef)
                results.append((label, f"{value:.4f}", rdef.unit, True))
            except Exception:
                results.append((label, "--", rdef.unit, False))
        else:
            results.append((label, "--", rdef.unit, False))
    return results


# ---------------------------------------------------------------------------
# Read ADL400 daily history
# ---------------------------------------------------------------------------

def read_adl400_daily(ser, addr, days, timeout):
    """Read daily frozen data for ADL400. Returns list of parsed blocks."""
    results = []
    for d in range(1, days + 1):
        req = build_daily_history_request(addr, d)
        if req is None:
            continue
        resp = send_recv(ser, req, timeout)
        if not resp:
            continue
        data = parse_read_response(resp)
        if data is None:
            continue
        block = parse_adl400_history_block(data)
        if block:
            results.append((d, block))
    return results


# ---------------------------------------------------------------------------
# Read monthly history
# ---------------------------------------------------------------------------

def read_adl400_monthly(ser, addr, months, timeout):
    """Read monthly frozen data for ADL400."""
    results = []
    for m in range(1, months + 1):
        req = build_monthly_history_request_adl400(addr, m)
        if req is None:
            continue
        resp = send_recv(ser, req, timeout)
        if not resp:
            continue
        data = parse_read_response(resp)
        if data is None:
            continue
        block = parse_adl400_history_block(data)
        if block:
            results.append((m, block))
    return results


def read_djsf_monthly(ser, addr, months, timeout):
    """Read monthly energy for DJSF."""
    results = []
    for m in range(1, months + 1):
        fwd, rev = None, None
        for direction in ("forward", "reverse"):
            req = build_monthly_history_request_djsf(addr, m, direction)
            if req is None:
                continue
            resp = send_recv(ser, req, timeout)
            if resp:
                data = parse_read_response(resp)
                if data:
                    fwd_or_rev = parse_djsf_monthly_energy(data)
                    if direction == "forward":
                        fwd = fwd_or_rev
                    else:
                        rev = fwd_or_rev
        if fwd is not None or rev is not None:
            results.append((m, fwd, rev))
    return results


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------

def print_realtime(results):
    subheader("实时数据")
    for label, value, unit, success in results:
        if success:
            print(f"  {C.GREEN}\u2713{C.END} {label:<16s} {value:>14s} {unit}")
        else:
            print(f"  {C.RED}\u2717{C.END} {label:<16s} {'--':>14s} {unit}")


def fmt_energy(val):
    """Format energy value, handle None (uninitialized)."""
    return f"{val:>10.2f}" if val is not None else "      未设置"


def print_adl400_daily(daily_data):
    if not daily_data:
        warn("日冻结: 无数据（电表可能未配置冻结功能）")
        return
    subheader("日冻结数据")
    for days_ago, block in daily_data:
        t = block["freeze_time"]
        print(f"  {C.GREEN}\u2713{C.END} {days_ago}天前 ({t})")
        print(f"      总有功: {fmt_energy(block['energy_active_total_kwh'])} kWh")
        print(f"      尖:     {fmt_energy(block['energy_active_peak_kwh'])} kWh")
        print(f"      峰:     {fmt_energy(block['energy_active_high_kwh'])} kWh")
        print(f"      平:     {fmt_energy(block['energy_active_mid_kwh'])} kWh")
        print(f"      谷:     {fmt_energy(block['energy_active_low_kwh'])} kWh")
        print(f"      无功:   {fmt_energy(block['energy_reactive_total_kvarh'])} kvarh")


def print_adl400_monthly(monthly_data):
    if not monthly_data:
        warn("月冻结: 无数据（电表可能未配置冻结功能）")
        return
    subheader("月冻结数据")
    total_year = 0.0
    for months_ago, block in monthly_data:
        t = block["freeze_time"]
        total = block["energy_active_total_kwh"]
        peak = block["energy_active_peak_kwh"]
        high = block["energy_active_high_kwh"]
        mid = block["energy_active_mid_kwh"]
        low = block["energy_active_low_kwh"]
        if total is not None:
            total_year += total
        print(f"  {C.GREEN}\u2713{C.END} {months_ago}月前 ({t})")
        print(f"      总有功: {fmt_energy(total)} kWh  "
              f"(尖:{fmt_energy(peak)} 峰:{fmt_energy(high)} "
              f"平:{fmt_energy(mid)} 谷:{fmt_energy(low)})")

    subheader("年汇总 (累加近12月)")
    print(f"  总有功电能: {C.BOLD}{total_year:>10.2f} kWh{C.END}")


def print_djsf_monthly(monthly_data):
    if not monthly_data:
        return
    subheader("月电能数据")
    total_fwd = 0.0
    total_rev = 0.0
    for month, fwd, rev in monthly_data:
        fwd_str = f"{fwd:.3f}" if fwd is not None else "--"
        rev_str = f"{rev:.3f}" if rev is not None else "--"
        print(f"  {C.GREEN}\u2713{C.END} 第{month:>2d}月  "
              f"正向: {fwd_str:>12s} kWh  反向: {rev_str:>12s} kWh")
        if fwd:
            total_fwd += fwd
        if rev:
            total_rev += rev

    subheader("年汇总 (累加12月)")
    print(f"  正向总电能: {C.BOLD}{total_fwd:>10.2f} kWh{C.END}")
    print(f"  反向总电能: {C.BOLD}{total_rev:>10.2f} kWh{C.END}")


# ---------------------------------------------------------------------------
# Full meter read
# ---------------------------------------------------------------------------

def read_full_meter(ser, addr, model, name, timeout):
    """Read ALL data from one meter and print."""
    is_ac = model == "ADL400"

    # Realtime
    rt = read_realtime(ser, addr, model, timeout)
    print_realtime(rt)

    # History
    if is_ac:
        subheader("读取日冻结 (近7天)...")
        daily = read_adl400_daily(ser, addr, 7, timeout)
        print_adl400_daily(daily)

        subheader("读取月冻结 (近12月)...")
        monthly = read_adl400_monthly(ser, addr, 12, timeout)
        print_adl400_monthly(monthly)
    else:
        subheader("读取月电能 (12月)...")
        monthly = read_djsf_monthly(ser, addr, 12, timeout)
        print_djsf_monthly(monthly)


# ---------------------------------------------------------------------------
# Diagnose single meter (baudrate scan + full register scan)
# ---------------------------------------------------------------------------

def diagnose_meter(port, addr, baudrates, timeout):
    meter_info = METER_BY_ADDR.get(addr)
    if not meter_info:
        fail(f"地址 {addr} 未在配置中定义 (有效地址: {list(METER_BY_ADDR.keys())})")
        return
    is_ac = meter_info.meter_type == MeterType.ADL400
    model = meter_info.model
    name = meter_info.name

    header(f"诊断 [{addr}] {name} ({model}) — {port}")

    # Choose probe register based on meter type
    if is_ac:
        probe_reg, probe_count, probe_name = 0x0834, 2, "频率"
        probe_scale, probe_unit = 1.0, "Hz"
    else:
        probe_reg, probe_count, probe_name = 5, 1, "温度"
        probe_scale, probe_unit = 0.1, "°C"

    subheader("波特率扫描")
    working_baud = None

    for baud in baudrates:
        try:
            ser = serial.Serial(port=port, baudrate=baud, bytesize=8,
                                parity="N", stopbits=1, timeout=timeout)
        except serial.SerialException as e:
            fail(f"{baud} baud: 无法打开 ({e})")
            continue

        data = read_reg(ser, addr, probe_reg, probe_count, timeout)
        ser.close()

        if data:
            if probe_count == 2 and len(data) >= 4:
                val = struct.unpack(">f", data)[0] * probe_scale
            else:
                val = struct.unpack(">h", data)[0] * probe_scale
            ok(f"{baud} baud: 正常 ({probe_name} = {val:.1f} {probe_unit})")
            working_baud = baud
            break
        else:
            fail(f"{baud} baud: 无有效响应")

    if working_baud is None:
        print(f"\n  {C.RED}{C.BOLD}未找到有效波特率。请检查接线和地址设置。{C.END}")
        return

    # Register scan — use correct register set for meter type
    subheader(f"寄存器扫描 @ {working_baud} baud")
    ser = serial.Serial(port=port, baudrate=working_baud, bytesize=8,
                        parity="N", stopbits=1, timeout=timeout)

    if is_ac:
        test_regs = [
            # === 变比 ===
            (0x008E, 1, "电压变比(PT)",       "uint16", 1.0,    ""),
            (0x008F, 1, "电流变比(CT)",       "uint16", 1.0,    ""),
            # === 二次侧 (原始值, 不含变比) ===
            (0x0061, 1, "A相电压(二次侧)",     "uint16", 0.1,    "V"),
            (0x0062, 1, "B相电压(二次侧)",     "uint16", 0.1,    "V"),
            (0x0063, 1, "C相电压(二次侧)",     "uint16", 0.1,    "V"),
            (0x0064, 1, "A相电流(二次侧)",     "uint16", 0.01,   "A"),
            (0x0065, 1, "B相电流(二次侧)",     "uint16", 0.01,   "A"),
            (0x0066, 1, "C相电流(二次侧)",     "uint16", 0.01,   "A"),
            (0x016A, 2, "总有功功率(二次侧)",   "int32",  0.001,  "kW"),
            (0x0172, 2, "总无功功率(二次侧)",   "int32",  0.001,  "kvar"),
            (0x017A, 2, "总视在功率(二次侧)",   "int32",  0.001,  "kVA"),
            (0x017F, 1, "功率因数(二次侧)",    "int16",  0.001,  ""),
            (0x0077, 1, "频率(二次侧)",       "uint16", 0.01,   "Hz"),
            (0x000A, 2, "正向电能(二次侧)",    "uint32", 0.01,   "kWh"),
            (0x0014, 2, "反向电能(二次侧)",    "uint32", 0.01,   "kWh"),
            (0x0000, 2, "组合电能(二次侧)",    "uint32", 0.01,   "kWh"),
            # === 一次侧 (含变比, Float) ===
            (0x0800, 2, "A相电压(一次侧)",     "float",  1.0,    "V"),
            (0x0802, 2, "B相电压(一次侧)",     "float",  1.0,    "V"),
            (0x0804, 2, "C相电压(一次侧)",     "float",  1.0,    "V"),
            (0x080C, 2, "A相电流(一次侧)",     "float",  1.0,    "A"),
            (0x080E, 2, "B相电流(一次侧)",     "float",  1.0,    "A"),
            (0x0810, 2, "C相电流(一次侧)",     "float",  1.0,    "A"),
            (0x081A, 2, "总有功功率(一次侧)",   "float",  1.0,    "kW"),
            (0x0822, 2, "总无功功率(一次侧)",   "float",  1.0,    "kvar"),
            (0x082A, 2, "总视在功率(一次侧)",   "float",  1.0,    "kVA"),
            (0x0832, 2, "总功率因数(一次侧)",   "float",  1.0,    ""),
            (0x0834, 2, "频率(一次侧)",       "float",  1.0,    "Hz"),
            (0x0842, 2, "组合电能(一次侧)",    "uint32", 0.01,   "kWh"),
            (0x0846, 2, "正向电能(一次侧)",    "uint32", 0.01,   "kWh"),
            (0x084E, 2, "反向电能(一次侧)",    "uint32", 0.01,   "kWh"),
        ]
    else:
        test_regs = [
            # === 变比 ===
            (16, 1, "电压变比",            "uint16", 1.0,    ""),
            (17, 1, "额定一次电流值",        "uint16", 1.0,    "A"),
            # === 整数寄存器 (含小数点) ===
            (0,  1, "电压值(整数)",         "uint16", 1.0,    ""),
            (1,  1, "电压小数点(DPT)",      "uint16", 1.0,    ""),
            (2,  1, "电流值(整数)",         "uint16", 1.0,    ""),
            (3,  1, "电流小数点(DCT)",      "uint16", 1.0,    ""),
            (5,  1, "温度",              "int16",  0.1,    "°C"),
            (8,  1, "功率值(整数)",         "uint16", 1.0,    ""),
            (9,  1, "功率小数点(DP)",       "uint16", 1.0,    ""),
            # === Float 寄存器 (一次侧) ===
            (50, 2, "电压(一次侧Float)",    "float",  1.0,    "V"),
            (52, 2, "电流(一次侧Float)",    "float",  1.0,    "A"),
            (54, 2, "功率(一次侧Float)",    "float",  1.0,    "kW"),
            # === 电能 ===
            (12, 2, "正向有功总电能",        "uint32", 0.0001, "kWh"),
            (14, 2, "反向有功总电能",        "uint32", 0.0001, "kWh"),
        ]

    ok_count = 0
    for reg, count, reg_name, parser_name, scale, unit in test_regs:
        # Build and send request
        req = build_read_request(addr, reg, count)
        resp = send_recv(ser, req, timeout)

        # Show TX/RX raw frames
        tx_hex = " ".join(f"{b:02X}" for b in req)
        if resp:
            rx_hex = " ".join(f"{b:02X}" for b in resp)
        else:
            rx_hex = "(无响应)"

        data = parse_read_response(resp) if resp else None

        if data and len(data) >= count * 2:
            # Show raw data bytes
            data_hex = " ".join(f"{b:02X}" for b in data)

            # Parse raw value before scaling
            rdef = RegisterDef(reg, count, parser_name, scale, unit)
            from meter import PARSERS
            raw_val = PARSERS[parser_name](data)
            final_val = round(raw_val * scale, 6)

            ok(f"reg 0x{reg:04X} {reg_name}")
            print(f"      TX: {C.CYAN}{tx_hex}{C.END}")
            print(f"      RX: {C.CYAN}{rx_hex}{C.END}")
            print(f"      数据: {C.CYAN}{data_hex}{C.END}")
            print(f"      解析: {parser_name}({data_hex}) = {raw_val}"
                  f" × {scale} = {C.BOLD}{final_val} {unit}{C.END}")
            ok_count += 1
        else:
            fail(f"reg 0x{reg:04X} {reg_name}")
            print(f"      TX: {C.CYAN}{tx_hex}{C.END}")
            print(f"      RX: {C.RED}{rx_hex}{C.END}")

    # Reliability test
    subheader(f"可靠性测试 ({probe_name}, 10次)")
    s = sum(1 for _ in range(10) if read_reg(ser, addr, probe_reg, probe_count, timeout))
    color = C.GREEN if s >= 8 else C.YELLOW if s >= 5 else C.RED
    print(f"  {color}成功率: {s}/10 ({s*10}%){C.END}")

    ser.close()

    # Full data read
    header(f"完整数据: [{addr}] {name}")
    ser = serial.Serial(port=port, baudrate=working_baud, bytesize=8,
                        parity="N", stopbits=1, timeout=timeout)
    read_full_meter(ser, addr, model, name, timeout)
    ser.close()

    header(f"诊断结果: [{addr}] {name} ({model})")
    print(f"  工作波特率: {C.GREEN}{working_baud}{C.END}")
    print(f"  可用寄存器: {C.GREEN}{ok_count}{C.END}/{len(test_regs)}")
    if s < 8:
        print(f"\n  {C.YELLOW}通信不稳定，请检查RS485接线{C.END}")


# ---------------------------------------------------------------------------
# Scan all meters
# ---------------------------------------------------------------------------

def scan_all(port, baudrate, timeout, quick=False):
    header(f"{'快速扫描' if quick else '完整扫描'}: {port} @ {baudrate} baud")

    try:
        ser = serial.Serial(port=port, baudrate=baudrate, bytesize=8,
                            parity="N", stopbits=1, timeout=timeout)
    except serial.SerialException as e:
        fail(f"无法打开 {port}: {e}")
        return

    online = 0
    offline = 0
    error = 0

    for m in METERS:
        addr = m.slave_addr
        model = m.model
        name = m.name
        is_ac = m.meter_type == MeterType.ADL400

        # Quick probe — use primary-side float for ADL400, int16 for DJSF
        if is_ac:
            probe_data = safe_read(ser, addr, 0x0834, 2, timeout)  # frequency float
        else:
            probe_data = read_reg(ser, addr, 5, 1, timeout)  # temperature int16

        if probe_data is None:
            # Retry once
            if is_ac:
                probe_data = safe_read(ser, addr, 0x0834, 2, timeout)
            else:
                probe_data = read_reg(ser, addr, 5, 1, timeout)

        if probe_data is None:
            fail(f"[{addr}] {name} ({model}): 无响应")
            offline += 1
            continue

        online += 1

        if quick:
            if is_ac:
                freq = struct.unpack(">f", probe_data)[0]
                ok(f"[{addr}] {name} ({model}): 频率 = {freq:.2f} Hz")
            else:
                temp = struct.unpack(">h", probe_data)[0] * 0.1
                ok(f"[{addr}] {name} ({model}): 温度 = {temp:.1f}°C")
        else:
            header(f"[{addr}] {name} ({model}) — {m.location}"
                   + (f" [{m.note}]" if m.note else ""))
            read_full_meter(ser, addr, model, name, timeout)

    ser.close()

    header("汇总")
    print(f"  在线: {C.GREEN}{online}{C.END}")
    print(f"  离线: {C.RED}{offline}{C.END}")
    print(f"  异常: {C.YELLOW}{error}{C.END}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="电表通信诊断工具")
    parser.add_argument("--port", default="COM33")
    parser.add_argument("--addr", type=int, help="诊断指定地址 (1-8)")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--quick", action="store_true", help="快速扫描(仅探测)")
    args = parser.parse_args()

    if args.addr:
        diagnose_meter(args.port, args.addr,
                       [9600, 4800, 19200, 2400, 38400, 1200], args.timeout)
    else:
        scan_all(args.port, args.baudrate, args.timeout, args.quick)


if __name__ == "__main__":
    main()
