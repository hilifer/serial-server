#!/usr/bin/env python3
"""Debug: read raw monthly freeze data from ADL400 to see what meter returns."""
import sys, struct, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from meter import (build_read_request, parse_read_response, crc16_modbus,
                   ADL400_MONTHLY_BASE, ADL400_MONTHLY_STRIDE, parse_uint16, parse_uint32)
from serial_manager import SerialManager

port = sys.argv[1] if len(sys.argv) > 1 else 'COM33'
mgr = SerialManager(port=port, baudrate=9600, timeout=0.5)
if not mgr.open():
    print(f"Cannot open {port}")
    sys.exit(1)

print(f"Reading ADL400 addr=1 monthly freeze from 0x7000 area...")
print()

for m in range(1, 13):
    reg = ADL400_MONTHLY_BASE + (m - 1) * ADL400_MONTHLY_STRIDE
    req = build_read_request(1, reg, 34)
    resp = mgr.send_and_receive(req)

    if not resp:
        print(f"  Month {m:2d} (reg 0x{reg:04X}): NO RESPONSE")
        continue

    data = parse_read_response(resp)
    if data is None:
        print(f"  Month {m:2d} (reg 0x{reg:04X}): CRC/PARSE ERROR, raw: {resp.hex()}")
        continue

    # Show raw hex
    hex_str = data.hex()
    all_ff = all(b == 0xFF for b in data[:28])
    all_zero = all(b == 0x00 for b in data[:28])

    # Parse time fields
    ym = parse_uint16(data, 0)
    dh = parse_uint16(data, 2)
    year = (ym >> 8) + 2000
    month_val = ym & 0xFF
    day = dh >> 8
    hour = dh & 0xFF

    # Parse energy
    energy_total = parse_uint32(data, 4)

    status = ""
    if all_ff:
        status = "← ALL 0xFF (uninitialized)"
    elif all_zero:
        status = f"← ALL ZERO, time={year}-{month_val:02d}-{day:02d} {hour:02d}:00"
    else:
        status = f"← time={year}-{month_val:02d}-{day:02d} {hour:02d}:00, energy_total={energy_total * 0.01:.2f} kWh"

    print(f"  Month {m:2d} (reg 0x{reg:04X}): {hex_str[:40]}... {status}")

print()
print("Done. If all show 0xFF or ALL ZERO, the meter hasn't frozen any data yet.")
print("Freeze happens on the 1st of each month at 00:00.")
print("If the meter was recently installed, wait until next month 1st.")
mgr.close()
