#!/usr/bin/env python3
"""
Set ADL400 RTC clock via Modbus RTU.

ADL400 date/time registers (0x0099-0x009E, 6 registers, BCD format):
  0x0099: year (BCD, e.g. 0x0026 = 2026)
  0x009A: month (BCD, e.g. 0x0004 = April)
  0x009B: day (BCD)
  0x009C: hour (BCD)
  0x009D: minute (BCD)
  0x009E: second (BCD)

Usage:
  python set_time.py                    # Set all ADL400 to current system time
  python set_time.py --read-only        # Only read current RTC
  python set_time.py --addr 1           # Set only meter addr 1
"""

import sys
import struct
import time
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from meter import crc16_modbus, build_read_request, parse_read_response
from serial_manager import SerialManager

ADL400_ADDRS = [1, 2, 3, 4]
REG_DATETIME = 0x0099  # 6 registers: year, month, day, hour, minute, second


def to_bcd(val):
    """Convert integer to BCD uint16."""
    tens = val // 10
    ones = val % 10
    return (tens << 4) | ones


def from_bcd(val):
    """Convert BCD uint16 to integer."""
    return ((val >> 4) & 0x0F) * 10 + (val & 0x0F)


def build_write_multiple_registers(slave_addr, start_reg, values):
    """Build Modbus 10H (Write Multiple Registers) request."""
    count = len(values)
    byte_count = count * 2
    payload = struct.pack(">HHB", start_reg, count, byte_count)
    for v in values:
        payload += struct.pack(">H", v)
    frame = bytes([slave_addr, 0x10]) + payload
    crc = crc16_modbus(frame)
    return frame + struct.pack("<H", crc)


def read_datetime(mgr, addr):
    """Read current RTC from meter. Returns (year, month, day, hour, minute, second) or None."""
    req = build_read_request(addr, REG_DATETIME, 6)
    resp = mgr.send_and_receive(req)
    if not resp:
        return None
    data = parse_read_response(resp)
    if not data or len(data) < 12:
        return None
    vals = []
    for i in range(6):
        raw = struct.unpack(">H", data[i*2:i*2+2])[0]
        vals.append(from_bcd(raw & 0xFF))
    return tuple(vals)  # (year, month, day, hour, minute, second)


def write_datetime(mgr, addr, dt):
    """Write datetime to meter RTC."""
    year_bcd = to_bcd(dt.year % 100)  # 2-digit year
    values = [
        year_bcd,
        to_bcd(dt.month),
        to_bcd(dt.day),
        to_bcd(dt.hour),
        to_bcd(dt.minute),
        to_bcd(dt.second),
    ]
    req = build_write_multiple_registers(addr, REG_DATETIME, values)
    resp = mgr.send_and_receive(req)
    return resp and len(resp) >= 8


def main():
    parser = argparse.ArgumentParser(description='Set ADL400 RTC clock')
    parser.add_argument('--port', default='COM33')
    parser.add_argument('--baudrate', type=int, default=9600)
    parser.add_argument('--addr', type=int, help='Only set this meter address')
    parser.add_argument('--read-only', action='store_true', help='Only read, do not write')
    args = parser.parse_args()

    addrs = [args.addr] if args.addr else ADL400_ADDRS

    print("=" * 50)
    print("  ADL400 RTC 时钟设置工具")
    print("=" * 50)

    mgr = SerialManager(port=args.port, baudrate=args.baudrate, timeout=0.5)
    if not mgr.open():
        print(f"无法打开 {args.port}")
        sys.exit(1)

    now = datetime.now()
    print(f"  系统时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    for addr in addrs:
        print(f"--- [{addr}] ---")

        # Read current
        dt = read_datetime(mgr, addr)
        if dt:
            y, mo, d, h, mi, s = dt
            valid = (0 < mo <= 12 and 0 < d <= 31 and h <= 23 and mi <= 59 and s <= 59)
            status = "正常" if valid else "异常"
            print(f"  当前RTC: 20{y:02d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}  ({status})")
        else:
            print(f"  当前RTC: 读取失败")

        if args.read_only:
            print()
            continue

        # Write current system time
        print(f"  写入时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        if write_datetime(mgr, addr, now):
            print(f"  ✓ 写入成功")
        else:
            print(f"  ✗ 写入失败")

        # Verify
        time.sleep(0.2)
        dt2 = read_datetime(mgr, addr)
        if dt2:
            y, mo, d, h, mi, s = dt2
            print(f"  验证RTC: 20{y:02d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}")
        print()

    mgr.close()
    print("=" * 50)
    if args.read_only:
        print("  只读模式")
    else:
        print("  时钟设置完成！")
        print("  月冻结将在下个月1号0点自动触发")
    print("=" * 50)


if __name__ == '__main__':
    main()
