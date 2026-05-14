#!/usr/bin/env python3
"""
Configure ADL400 freeze settings via Modbus RTU.

ADL400 registers:
  0x0121: Daily freeze time   - high byte: unused, low byte: hour (0-23)
  0x0122: Monthly freeze date - high byte: day (1-28), low byte: hour (0-23)

Usage:
  python configure_freeze.py [--port COM33] [--day 1] [--hour 0]

This writes to all ADL400 meters (addr 1,2,3,4) to enable monthly freeze
on the specified day and hour. After configuration, monthly energy data
will start accumulating from the next freeze date.
"""

import sys
import struct
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from meter import crc16_modbus, build_read_request, parse_read_response
from serial_manager import SerialManager

ADL400_ADDRS = [1, 2, 3, 4]
REG_DAILY_FREEZE = 0x0121
REG_MONTHLY_FREEZE = 0x0122


def build_write_single_register(slave_addr, register, value):
    """Build Modbus 06H (Write Single Register) request."""
    payload = struct.pack(">HH", register, value)
    frame = bytes([slave_addr, 0x06]) + payload
    crc = crc16_modbus(frame)
    return frame + struct.pack("<H", crc)


def read_register(mgr, slave_addr, register):
    """Read single register value."""
    req = build_read_request(slave_addr, register, 1)
    resp = mgr.send_and_receive(req)
    if resp:
        data = parse_read_response(resp)
        if data and len(data) >= 2:
            return struct.unpack(">H", data[:2])[0]
    return None


def main():
    parser = argparse.ArgumentParser(description='Configure ADL400 freeze settings')
    parser.add_argument('--port', default='COM33', help='Serial port (default: COM33)')
    parser.add_argument('--baudrate', type=int, default=9600, help='Baud rate (default: 9600)')
    parser.add_argument('--day', type=int, default=1, help='Monthly freeze day 1-28 (default: 1)')
    parser.add_argument('--hour', type=int, default=0, help='Freeze hour 0-23 (default: 0)')
    parser.add_argument('--daily-hour', type=int, default=0, help='Daily freeze hour 0-23 (default: 0)')
    parser.add_argument('--read-only', action='store_true', help='Only read current settings, do not write')
    args = parser.parse_args()

    if args.day < 1 or args.day > 28:
        print("Error: day must be 1-28")
        sys.exit(1)
    if args.hour < 0 or args.hour > 23:
        print("Error: hour must be 0-23")
        sys.exit(1)

    print("=" * 50)
    print("  ADL400 冻结配置工具")
    print("=" * 50)
    print(f"  串口: {args.port} @ {args.baudrate}")
    print(f"  月冻结: 每月{args.day}号 {args.hour}:00")
    print(f"  日冻结: 每天 {args.daily_hour}:00")
    print()

    mgr = SerialManager(port=args.port, baudrate=args.baudrate, timeout=0.5)
    if not mgr.open():
        print(f"Error: Cannot open {args.port}")
        sys.exit(1)

    for addr in ADL400_ADDRS:
        print(f"--- [{addr}] ---")

        # Read current settings
        current_daily = read_register(mgr, addr, REG_DAILY_FREEZE)
        current_monthly = read_register(mgr, addr, REG_MONTHLY_FREEZE)

        if current_daily is not None:
            d_high = (current_daily >> 8) & 0xFF
            d_low = current_daily & 0xFF
            print(f"  当前日冻结:  0x{current_daily:04X} (时={d_low})")
        else:
            print(f"  当前日冻结:  读取失败")

        if current_monthly is not None:
            m_day = (current_monthly >> 8) & 0xFF
            m_hour = current_monthly & 0xFF
            print(f"  当前月冻结:  0x{current_monthly:04X} (日={m_day}, 时={m_hour})")
        else:
            print(f"  当前月冻结:  读取失败")

        if args.read_only:
            print()
            continue

        # Write new settings
        # Daily freeze: high byte = 0x00 (unused), low byte = hour
        daily_value = (0x00 << 8) | (args.daily_hour & 0xFF)
        # Monthly freeze: high byte = day, low byte = hour
        monthly_value = ((args.day & 0xFF) << 8) | (args.hour & 0xFF)

        print(f"  写入日冻结:  0x{daily_value:04X} (时={args.daily_hour})")
        req = build_write_single_register(addr, REG_DAILY_FREEZE, daily_value)
        resp = mgr.send_and_receive(req)
        if resp and len(resp) >= 8:
            print(f"  ✓ 日冻结设置成功")
        else:
            print(f"  ✗ 日冻结设置失败")

        time.sleep(0.1)

        print(f"  写入月冻结:  0x{monthly_value:04X} (日={args.day}, 时={args.hour})")
        req = build_write_single_register(addr, REG_MONTHLY_FREEZE, monthly_value)
        resp = mgr.send_and_receive(req)
        if resp and len(resp) >= 8:
            print(f"  ✓ 月冻结设置成功")
        else:
            print(f"  ✗ 月冻结设置失败")

        time.sleep(0.1)

        # Verify
        new_monthly = read_register(mgr, addr, REG_MONTHLY_FREEZE)
        if new_monthly == monthly_value:
            print(f"  ✓ 验证通过")
        else:
            print(f"  ⚠ 验证失败: 读回 0x{new_monthly:04X}" if new_monthly else "  ⚠ 验证失败: 读取超时")

        print()

    mgr.close()
    print("=" * 50)
    if args.read_only:
        print("  只读模式，未修改配置")
    else:
        print("  配置完成！")
        print("  月冻结数据将从下个月1号开始记录")
    print("=" * 50)


if __name__ == '__main__':
    main()
