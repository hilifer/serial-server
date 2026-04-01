#!/usr/bin/env python3
"""
Modbus RTU protocol implementation for energy meters.

Supports:
  - ADL400: Three-phase AC energy meter (Modbus addresses 1-4)
  - DJSF1352-RN: DC energy meter, dual-channel (Modbus addresses 6-8)
  - DJSF1352-RN-6: DC energy meter, single-channel (Modbus address 5)

All meters communicate via Modbus RTU over RS485 (COM33).
"""

import struct
import logging
from dataclasses import dataclass, field
from enum import IntEnum

logger = logging.getLogger("meter")


# ---------------------------------------------------------------------------
# CRC16 (Modbus)
# ---------------------------------------------------------------------------

def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def build_frame(slave_addr: int, func_code: int, payload: bytes) -> bytes:
    """Build a complete Modbus RTU frame with CRC."""
    frame = bytes([slave_addr, func_code]) + payload
    crc = crc16_modbus(frame)
    return frame + struct.pack("<H", crc)


def verify_crc(frame: bytes) -> bool:
    """Verify the CRC of a received Modbus RTU frame."""
    if len(frame) < 4:
        return False
    data, crc_recv = frame[:-2], struct.unpack("<H", frame[-2:])[0]
    return crc16_modbus(data) == crc_recv


# ---------------------------------------------------------------------------
# Modbus function code helpers
# ---------------------------------------------------------------------------

def build_read_request(slave_addr: int, register: int, count: int) -> bytes:
    """Build a 03H (Read Holding Registers) request frame."""
    payload = struct.pack(">HH", register, count)
    return build_frame(slave_addr, 0x03, payload)


def parse_read_response(frame: bytes) -> bytes | None:
    """Parse a 03H response and return the register data bytes.

    Returns None on error (bad CRC, exception response, etc.).
    """
    if not verify_crc(frame):
        logger.debug("CRC check failed: %s", frame.hex())
        return None
    if len(frame) < 5:
        logger.error("Frame too short: %s", frame.hex())
        return None
    func_code = frame[1]
    if func_code & 0x80:  # exception response
        error_code = frame[2]
        logger.error("Modbus exception response: func=0x%02X error=%d",
                      func_code, error_code)
        return None
    byte_count = frame[2]
    data = frame[3:3 + byte_count]
    if len(data) != byte_count:
        logger.error("Data length mismatch: expected %d got %d",
                      byte_count, len(data))
        return None
    return data


MAX_RETRIES = 3


def _read_with_retry(serial_mgr, slave_addr: int, start_reg: int,
                     count: int) -> bytes | None:
    """Read registers with retry on CRC failure.

    RS485 bus noise can cause random bit errors. Retry up to MAX_RETRIES
    times before giving up.
    """
    for attempt in range(MAX_RETRIES):
        req = build_read_request(slave_addr, start_reg, count)
        resp = serial_mgr.send_and_receive_unlocked(req)
        if resp:
            data = parse_read_response(resp)
            if data is not None:
                return data
        if attempt < MAX_RETRIES - 1:
            logger.debug("Retry %d/%d for addr=%d reg=%d count=%d",
                         attempt + 1, MAX_RETRIES, slave_addr, start_reg, count)
    return None


def safe_read_registers(serial_mgr, slave_addr: int, start_reg: int,
                        count: int) -> bytes | None:
    """Read registers with retry and automatic fallback to single reads.

    Strategy:
      1. Try multi-register read with retry (up to 3 attempts)
      2. If still fails and count>1, try reading one register at a time
         (each with retry), then combine results

    Handles both:
      - RS485 noise (random CRC failures → fixed by retry)
      - Meters that don't support multi-register reads (→ fixed by fallback)
    """
    # Try normal multi-register read with retry
    data = _read_with_retry(serial_mgr, slave_addr, start_reg, count)
    if data is not None:
        return data

    # Fallback: read one register at a time
    if count <= 1:
        return None

    logger.debug("Multi-register read failed for addr=%d reg=%d count=%d, "
                 "falling back to single reads", slave_addr, start_reg, count)
    combined = b""
    for i in range(count):
        data = _read_with_retry(serial_mgr, slave_addr, start_reg + i, 1)
        if data is None:
            return None
        combined += data

    return combined


# ---------------------------------------------------------------------------
# Data parsing helpers
# ---------------------------------------------------------------------------

def parse_uint16(data: bytes, offset: int = 0) -> int:
    return struct.unpack(">H", data[offset:offset + 2])[0]


def parse_int16(data: bytes, offset: int = 0) -> int:
    return struct.unpack(">h", data[offset:offset + 2])[0]


def parse_uint32(data: bytes, offset: int = 0) -> int:
    return struct.unpack(">I", data[offset:offset + 4])[0]


def parse_int32(data: bytes, offset: int = 0) -> int:
    return struct.unpack(">i", data[offset:offset + 4])[0]


def parse_float(data: bytes, offset: int = 0) -> float:
    return struct.unpack(">f", data[offset:offset + 4])[0]


# ---------------------------------------------------------------------------
# Register definitions
# ---------------------------------------------------------------------------

class MeterType(IntEnum):
    ADL400 = 1
    DJSF1352_RN = 2
    DJSF1352_RN_6 = 3


@dataclass
class RegisterDef:
    """Definition of a single register read."""
    address: int        # Modbus register address (hex value)
    count: int          # Number of registers to read
    parser: str         # Parser name: "uint16", "int16", "uint32", "int32", "float"
    scale: float = 1.0  # Multiply raw value by this to get actual
    unit: str = ""


# --- ADL400 registers ---
ADL400_REALTIME = {
    "voltage_a":   RegisterDef(0x0061, 1, "uint16", 0.1, "V"),
    "voltage_b":   RegisterDef(0x0062, 1, "uint16", 0.1, "V"),
    "voltage_c":   RegisterDef(0x0063, 1, "uint16", 0.1, "V"),
    "current_a":   RegisterDef(0x0064, 1, "uint16", 0.01, "A"),
    "current_b":   RegisterDef(0x0065, 1, "uint16", 0.01, "A"),
    "current_c":   RegisterDef(0x0066, 1, "uint16", 0.01, "A"),
    "power_total": RegisterDef(0x016A, 2, "int32", 0.001, "kW"),
    "power_a":     RegisterDef(0x0164, 2, "int32", 0.001, "kW"),
    "power_b":     RegisterDef(0x0166, 2, "int32", 0.001, "kW"),
    "power_c":     RegisterDef(0x0168, 2, "int32", 0.001, "kW"),
    "reactive_power_total": RegisterDef(0x0172, 2, "int32", 0.001, "kvar"),
    "apparent_power_total": RegisterDef(0x017A, 2, "int32", 0.001, "kVA"),
    "power_factor": RegisterDef(0x017F, 1, "int16", 0.001, ""),
    "frequency":   RegisterDef(0x0077, 1, "uint16", 0.01, "Hz"),
    "energy_forward_total":  RegisterDef(0x000A, 2, "uint32", 0.01, "kWh"),
    "energy_reverse_total":  RegisterDef(0x0014, 2, "uint32", 0.01, "kWh"),
    "energy_combined_total": RegisterDef(0x0000, 2, "uint32", 0.01, "kWh"),
}

# Batch read groups for ADL400 — read contiguous registers in one request.
#   Group 1: reg 0x0000, count 2  → energy_combined_total
#   Group 2: reg 0x000A, count 2  → energy_forward_total
#   Group 3: reg 0x0014, count 2  → energy_reverse_total
#   Group 4: reg 0x0061, count 6  → voltage_a/b/c + current_a/b/c
#   Group 5: reg 0x0077, count 1  → frequency
#   Group 6: reg 0x0164, count 8  → power_a/b/c/total (0x0164-0x016B)
#   Group 7: reg 0x0172, count 2  → reactive_power_total
#   Group 8: reg 0x017A, count 2  → apparent_power_total
#   Group 9: reg 0x017F, count 1  → power_factor
# Total: 9 requests instead of 17
ADL400_BATCH_READS = [
    {"start": 0x0000, "count": 2, "fields": [
        ("energy_combined_total", RegisterDef(0x0000, 2, "uint32", 0.01, "kWh"), 0),
    ]},
    {"start": 0x000A, "count": 2, "fields": [
        ("energy_forward_total", RegisterDef(0x000A, 2, "uint32", 0.01, "kWh"), 0),
    ]},
    {"start": 0x0014, "count": 2, "fields": [
        ("energy_reverse_total", RegisterDef(0x0014, 2, "uint32", 0.01, "kWh"), 0),
    ]},
    {"start": 0x0061, "count": 6, "fields": [
        ("voltage_a", RegisterDef(0x0061, 1, "uint16", 0.1, "V"), 0),
        ("voltage_b", RegisterDef(0x0062, 1, "uint16", 0.1, "V"), 2),
        ("voltage_c", RegisterDef(0x0063, 1, "uint16", 0.1, "V"), 4),
        ("current_a", RegisterDef(0x0064, 1, "uint16", 0.01, "A"), 6),
        ("current_b", RegisterDef(0x0065, 1, "uint16", 0.01, "A"), 8),
        ("current_c", RegisterDef(0x0066, 1, "uint16", 0.01, "A"), 10),
    ]},
    {"start": 0x0077, "count": 1, "fields": [
        ("frequency", RegisterDef(0x0077, 1, "uint16", 0.01, "Hz"), 0),
    ]},
    {"start": 0x0164, "count": 8, "fields": [
        ("power_a",     RegisterDef(0x0164, 2, "int32", 0.001, "kW"), 0),
        ("power_b",     RegisterDef(0x0166, 2, "int32", 0.001, "kW"), 4),
        ("power_c",     RegisterDef(0x0168, 2, "int32", 0.001, "kW"), 8),
        ("power_total", RegisterDef(0x016A, 2, "int32", 0.001, "kW"), 12),
    ]},
    {"start": 0x0172, "count": 2, "fields": [
        ("reactive_power_total", RegisterDef(0x0172, 2, "int32", 0.001, "kvar"), 0),
    ]},
    {"start": 0x017A, "count": 2, "fields": [
        ("apparent_power_total", RegisterDef(0x017A, 2, "int32", 0.001, "kVA"), 0),
    ]},
    {"start": 0x017F, "count": 1, "fields": [
        ("power_factor", RegisterDef(0x017F, 1, "int16", 0.001, ""), 0),
    ]},
]

# ADL400 daily history: base 0x6000, stride 0x22, up to 90 days
# Each block: 34 registers
#   offset 0-1: freeze time (year-month, day-hour)
#   offset 2-3: total active energy (UINT32, 0.01kWh)
ADL400_DAILY_BASE = 0x6000
ADL400_DAILY_STRIDE = 0x0022
ADL400_DAILY_MAX = 90

# ADL400 monthly history: base 0x7000, stride 0x22, up to 48 months
ADL400_MONTHLY_BASE = 0x7000
ADL400_MONTHLY_STRIDE = 0x0022
ADL400_MONTHLY_MAX = 48

# ADL400 history block layout (offsets in registers from block base)
ADL400_HISTORY_LAYOUT = {
    "time_ym":             0,   # year-month (uint16)
    "time_dh":             1,   # day-hour (uint16)
    "energy_active_total": 2,   # uint32, 0.01 kWh
    "energy_active_peak":  4,   # uint32, 0.01 kWh (尖)
    "energy_active_high":  6,   # uint32, 0.01 kWh (峰)
    "energy_active_mid":   8,   # uint32, 0.01 kWh (平)
    "energy_active_low":   10,  # uint32, 0.01 kWh (谷)
    "energy_reactive_total": 12,  # uint32, 0.01 kvarh
}

# --- DJSF1352-RN / RN-6 registers (DC meters) ---
DJSF_REALTIME = {
    "voltage":       RegisterDef(50, 2, "float", 1.0, "V"),
    "current":       RegisterDef(52, 2, "float", 1.0, "A"),
    "power":         RegisterDef(54, 2, "float", 1.0, "kW"),
    "energy_forward_total":  RegisterDef(12, 2, "uint32", 0.0001, "kWh"),
    "energy_reverse_total":  RegisterDef(14, 2, "uint32", 0.0001, "kWh"),
    "temperature":   RegisterDef(5, 1, "int16", 0.1, "°C"),
}

# Batch read groups for DJSF — read contiguous registers in one request
# to avoid inter-frame timing issues with slower meters.
#   Group 1: reg 5, count 1 → temperature
#   Group 2: reg 12, count 4 → energy_forward(12-13) + energy_reverse(14-15)
#   Group 3: reg 50, count 6 → voltage(50-51) + current(52-53) + power(54-55)
DJSF_BATCH_READS = [
    {"start": 5, "count": 1, "fields": [
        ("temperature", RegisterDef(5, 1, "int16", 0.1, "°C"), 0),
    ]},
    {"start": 12, "count": 4, "fields": [
        ("energy_forward_total", RegisterDef(12, 2, "uint32", 0.0001, "kWh"), 0),
        ("energy_reverse_total", RegisterDef(14, 2, "uint32", 0.0001, "kWh"), 4),
    ]},
    {"start": 50, "count": 6, "fields": [
        ("voltage", RegisterDef(50, 2, "float", 1.0, "V"), 0),
        ("current", RegisterDef(52, 2, "float", 1.0, "A"), 4),
        ("power",   RegisterDef(54, 2, "float", 1.0, "kW"), 8),
    ]},
]

# DJSF monthly energy (Modbus): base address 2000 area
# Current month total forward: addr 2010-2011 (2 regs, unit Wh)
# Month 1~12 forward total: addr 2020 + (month-1)*10 for 2 regs each
DJSF_MONTHLY_CURRENT_FWD = 2010     # current month total forward energy
DJSF_MONTHLY_CURRENT_REV = 2150     # current month total reverse energy
DJSF_MONTHLY_HISTORY_FWD_BASE = 2020  # month 1 forward total
DJSF_MONTHLY_HISTORY_REV_BASE = 2160  # month 1 reverse total
DJSF_MONTHLY_STRIDE = 10            # 10 registers per month (5 rates x 2 regs)
DJSF_MONTHLY_MAX = 12


# ---------------------------------------------------------------------------
# Meter definitions (from image table)
# ---------------------------------------------------------------------------

@dataclass
class MeterInfo:
    """Describes one logical meter."""
    name: str
    meter_type: MeterType
    slave_addr: int
    location: str
    model: str
    note: str = ""


# All meters on COM33
METERS: list[MeterInfo] = [
    MeterInfo("电网侧电表",   MeterType.ADL400,          1, "01柜", "ADL400"),
    MeterInfo("逆变侧电表",   MeterType.ADL400,          2, "05柜", "ADL400"),
    MeterInfo("交流桩电表",   MeterType.ADL400,          3, "05柜", "ADL400"),
    MeterInfo("用户负载电表", MeterType.ADL400,          4, "05柜", "ADL400"),
    MeterInfo("整流侧电表",   MeterType.DJSF1352_RN_6,  5, "03柜", "DJSF1352-RN-6", "1路"),
    MeterInfo("电池柜电表",   MeterType.DJSF1352_RN,    6, "03柜", "DJSF1352-RN"),
    MeterInfo("直流桩电表",   MeterType.DJSF1352_RN,    7, "03柜", "DJSF1352-RN",
              "2路,直流桩1&直流桩2"),
    MeterInfo("光伏电表",     MeterType.DJSF1352_RN,    8, "03柜", "DJSF1352-RN",
              "2路,光伏1&光伏2"),
]

METER_BY_ADDR: dict[int, MeterInfo] = {m.slave_addr: m for m in METERS}


# ---------------------------------------------------------------------------
# High-level request builders
# ---------------------------------------------------------------------------

def build_realtime_requests(meter: MeterInfo) -> list[tuple[str, bytes]]:
    """Build Modbus request frames for all realtime registers of a meter.

    Returns list of (param_name, request_frame).
    """
    if meter.meter_type == MeterType.ADL400:
        regs = ADL400_REALTIME
    else:
        regs = DJSF_REALTIME

    result = []
    for name, rdef in regs.items():
        frame = build_read_request(meter.slave_addr, rdef.address, rdef.count)
        result.append((name, frame))
    return result


def build_daily_history_request(slave_addr: int, days_ago: int) -> bytes | None:
    """Build request for ADL400 daily history (1 = yesterday, up to 90).

    Returns None for non-ADL400 meters (DC meters don't support daily via Modbus).
    """
    if days_ago < 1 or days_ago > ADL400_DAILY_MAX:
        return None
    addr = ADL400_DAILY_BASE + (days_ago - 1) * ADL400_DAILY_STRIDE
    return build_read_request(slave_addr, addr, 34)


def build_monthly_history_request_adl400(slave_addr: int, months_ago: int) -> bytes | None:
    """Build request for ADL400 monthly history (1 = last month, up to 48)."""
    if months_ago < 1 or months_ago > ADL400_MONTHLY_MAX:
        return None
    addr = ADL400_MONTHLY_BASE + (months_ago - 1) * ADL400_MONTHLY_STRIDE
    return build_read_request(slave_addr, addr, 34)


def build_monthly_history_request_djsf(slave_addr: int, month: int,
                                       direction: str = "forward") -> bytes | None:
    """Build request for DJSF monthly history.

    month: 1-12 (calendar month). direction: 'forward' or 'reverse'.
    """
    if month < 1 or month > DJSF_MONTHLY_MAX:
        return None
    if direction == "forward":
        addr = DJSF_MONTHLY_HISTORY_FWD_BASE + (month - 1) * DJSF_MONTHLY_STRIDE
    else:
        addr = DJSF_MONTHLY_HISTORY_REV_BASE + (month - 1) * DJSF_MONTHLY_STRIDE
    return build_read_request(slave_addr, addr, 2)


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

PARSERS = {
    "uint16": parse_uint16,
    "int16":  parse_int16,
    "uint32": parse_uint32,
    "int32":  parse_int32,
    "float":  parse_float,
}


def parse_register_value(data: bytes, rdef: RegisterDef) -> float:
    """Parse raw register data using the register definition."""
    parser = PARSERS[rdef.parser]
    raw = parser(data)
    return round(raw * rdef.scale, 6)


def parse_realtime_response(param_name: str, frame: bytes,
                            meter_type: MeterType) -> dict | None:
    """Parse a realtime register response.

    Returns {"name": ..., "value": ..., "unit": ...} or None on error.
    """
    data = parse_read_response(frame)
    if data is None:
        return None

    regs = ADL400_REALTIME if meter_type == MeterType.ADL400 else DJSF_REALTIME
    rdef = regs.get(param_name)
    if rdef is None:
        return None

    value = parse_register_value(data, rdef)
    return {"name": param_name, "value": value, "unit": rdef.unit}


def parse_adl400_history_block(data: bytes) -> dict | None:
    """Parse a 34-register ADL400 history block (daily or monthly).

    Returns None if data is too short or all 0xFF (uninitialized).
    """
    if len(data) < 68:  # 34 regs * 2 bytes
        logger.error("History block too short: %d bytes", len(data))
        return None

    # Check if block is uninitialized (all 0xFF)
    if all(b == 0xFF for b in data[:28]):
        return None

    layout = ADL400_HISTORY_LAYOUT
    ym = parse_uint16(data, layout["time_ym"] * 2)
    dh = parse_uint16(data, layout["time_dh"] * 2)

    # Validate time fields
    year_raw = ym >> 8
    month_raw = ym & 0xFF
    day_raw = dh >> 8
    hour_raw = dh & 0xFF

    if year_raw > 99 or month_raw > 12 or day_raw > 31 or hour_raw > 23:
        return None  # Invalid time = uninitialized data

    year = year_raw + 2000
    month = month_raw
    day = day_raw
    hour = hour_raw

    def safe_energy(offset_key):
        val = parse_uint32(data, layout[offset_key] * 2)
        if val == 0xFFFFFFFF:
            return None  # uninitialized
        return val * 0.01

    result = {
        "freeze_time": f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:00",
        "energy_active_total_kwh": safe_energy("energy_active_total"),
        "energy_active_peak_kwh":  safe_energy("energy_active_peak"),
        "energy_active_high_kwh":  safe_energy("energy_active_high"),
        "energy_active_mid_kwh":   safe_energy("energy_active_mid"),
        "energy_active_low_kwh":   safe_energy("energy_active_low"),
        "energy_reactive_total_kvarh": safe_energy("energy_reactive_total"),
    }

    # If all energy values are None, the block is empty
    energy_vals = [v for v in result.values() if isinstance(v, (int, float))]
    if not energy_vals:
        return None

    return result


def parse_djsf_monthly_energy(data: bytes) -> float:
    """Parse DJSF monthly energy response (2 registers = uint32, unit Wh)."""
    raw = parse_uint32(data)
    return raw / 1000.0  # Wh -> kWh
