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
# Source: docs/ADL400_导轨式多功能电能表.pdf
#
# ADL400 has TWO sets of registers:
#   - Secondary side (0x0061+): raw meter values, need ×PT ×CT conversion
#   - Primary side (0x0800+): Float, already includes PT/CT ratios
#
# We use PRIMARY SIDE (0x0800+) so readings are correct regardless of
# whether CT/PT transformers are configured.
#
# Ratio registers (PyMuPDF verified from PDF Page 17):
#   0x008D: 电压变比 PT (R/W, UINT16)
#   0x008E: 电流变比 CT (R/W, UINT16)

ADL400_REALTIME = {
    # Primary side float registers (0x0800+), already include PT/CT ratios
    "voltage_a":   RegisterDef(0x0800, 2, "float", 1.0, "V"),
    "voltage_b":   RegisterDef(0x0802, 2, "float", 1.0, "V"),
    "voltage_c":   RegisterDef(0x0804, 2, "float", 1.0, "V"),
    "current_a":   RegisterDef(0x080C, 2, "float", 1.0, "A"),
    "current_b":   RegisterDef(0x080E, 2, "float", 1.0, "A"),
    "current_c":   RegisterDef(0x0810, 2, "float", 1.0, "A"),
    "power_a":     RegisterDef(0x0814, 2, "float", 1.0, "kW"),
    "power_b":     RegisterDef(0x0816, 2, "float", 1.0, "kW"),
    "power_c":     RegisterDef(0x0818, 2, "float", 1.0, "kW"),
    "power_total": RegisterDef(0x081A, 2, "float", 1.0, "kW"),
    "reactive_power_total": RegisterDef(0x0822, 2, "float", 1.0, "kvar"),
    "apparent_power_total": RegisterDef(0x082A, 2, "float", 1.0, "kVA"),
    "power_factor": RegisterDef(0x0832, 2, "float", 1.0, ""),
    "frequency":   RegisterDef(0x0834, 2, "float", 1.0, "Hz"),
    # Energy: primary side, UINT32, unit 0.1kWh
    "energy_combined_total":     RegisterDef(0x0842, 2, "uint32", 0.1, "kWh"),   # 组合有功总
    "energy_combined_peak":      RegisterDef(0x0844, 2, "uint32", 0.1, "kWh"),   # 组合有功尖
    "energy_combined_high":      RegisterDef(0x0846, 2, "uint32", 0.1, "kWh"),   # 组合有功峰
    "energy_combined_mid":       RegisterDef(0x0848, 2, "uint32", 0.1, "kWh"),   # 组合有功平
    "energy_combined_low":       RegisterDef(0x084A, 2, "uint32", 0.1, "kWh"),   # 组合有功谷
    "energy_forward_total":      RegisterDef(0x084C, 2, "uint32", 0.1, "kWh"),   # 正向总有功
    "energy_forward_peak":       RegisterDef(0x084E, 2, "uint32", 0.1, "kWh"),   # 正向有功尖
    "energy_forward_high":       RegisterDef(0x0850, 2, "uint32", 0.1, "kWh"),   # 正向有功峰
    "energy_forward_mid":        RegisterDef(0x0852, 2, "uint32", 0.1, "kWh"),   # 正向有功平
    "energy_forward_low":        RegisterDef(0x0854, 2, "uint32", 0.1, "kWh"),   # 正向有功谷
    "energy_reverse_total":      RegisterDef(0x0856, 2, "uint32", 0.1, "kWh"),   # 反向总有功
    "energy_reverse_peak":       RegisterDef(0x0858, 2, "uint32", 0.1, "kWh"),   # 反向有功尖
    "energy_reverse_high":       RegisterDef(0x085A, 2, "uint32", 0.1, "kWh"),   # 反向有功峰
    "energy_reverse_mid":        RegisterDef(0x085C, 2, "uint32", 0.1, "kWh"),   # 反向有功平
    "energy_reverse_low":        RegisterDef(0x085E, 2, "uint32", 0.1, "kWh"),   # 反向有功谷
}

# Ratio registers for ADL400
ADL400_RATIO_REGS = {
    "pt": RegisterDef(0x008D, 1, "uint16", 1.0, ""),  # 电压变比 PT
    "ct": RegisterDef(0x008E, 1, "uint16", 1.0, ""),  # 电流变比 CT
}

# Batch reads no longer used for ADL400 (primary-side floats are not contiguous
# in the same way). Individual reads via safe_read_registers are used instead.
ADL400_BATCH_READS = []

# ADL400 daily history: base 0x6000, stride 0x22, up to 90 days
# NOTE: History blocks are SECONDARY SIDE data (二次侧, 单位0.01kWh).
# For meters with CT/PT configured, these values need ×PT×CT to get actual.
# The realtime registers (0x0800+) are primary side and don't need conversion.
ADL400_DAILY_BASE = 0x6000
ADL400_DAILY_STRIDE = 0x0022
ADL400_DAILY_MAX = 90

# ADL400 monthly history: base 0x7000, stride 0x22, up to 48 months
# Also secondary side data (二次侧).
ADL400_MONTHLY_BASE = 0x7000
ADL400_MONTHLY_STRIDE = 0x0022
ADL400_MONTHLY_MAX = 48

# ADL400 history block layout (offsets in registers from block base)
# Unit: 0.01 kWh (二次侧, 需乘以PT×CT得到实际值)
ADL400_HISTORY_LAYOUT = {
    "time_ym":             0,   # year-month (uint16)
    "time_dh":             1,   # day-hour (uint16)
    "energy_active_total": 2,   # uint32, 0.01 kWh (二次侧)
    "energy_active_peak":  4,   # uint32, 0.01 kWh (尖)
    "energy_active_high":  6,   # uint32, 0.01 kWh (峰)
    "energy_active_mid":   8,   # uint32, 0.01 kWh (平)
    "energy_active_low":   10,  # uint32, 0.01 kWh (谷)
    "energy_reactive_total": 12,  # uint32, 0.01 kvarh (二次侧)
}

# --- DJSF1352-RN registers (DC meter) ---
# Source: docs/DJSF1352-RN_导轨式直流电能表.pdf (PyMuPDF Page 15-16)
# Float registers 50-55 are PRIMARY SIDE values (已含变比).
# Ratio registers: 16=电压变比, 17=额定一次电流值
# Energy reg 12-15: PDF says "一次侧电能，单位WH" (Wh)
DJSF_RN_REALTIME = {
    "voltage":       RegisterDef(50, 2, "float", 1.0, "V"),       # 50-51 Float V (一次侧)
    "current":       RegisterDef(52, 2, "float", 1.0, "A"),       # 52-53 Float A (一次侧)
    "power":         RegisterDef(54, 2, "float", 1.0, "kW"),      # 54-55 Float kW (一次侧)
    "energy_forward_total":  RegisterDef(12, 2, "uint32", 0.001, "kWh"),  # 12-13 一次侧 单位Wh
    "energy_reverse_total":  RegisterDef(14, 2, "uint32", 0.001, "kWh"),  # 14-15 一次侧 单位Wh
    "temperature":   RegisterDef(5, 1, "int16", 0.1, "°C"),       # 5 -400~1250 0.1℃
}

DJSF_RN_RATIO_REGS = {
    "voltage_ratio": RegisterDef(16, 1, "uint16", 1.0, ""),  # 电压变比
    "current_ratio": RegisterDef(17, 1, "uint16", 1.0, ""),  # 额定一次电流值
}

# --- DJSF1352-RN-6 registers (DC meter) ---
# Source: docs/537_DJSF1352-RN-6导轨式直流电能表说明书V1.1(中英)(2).pdf (PyMuPDF Page 28)
# Register table starts from address 4 (no integer regs 0-3).
# Float registers 50-55 are PRIMARY SIDE values (一次值，已含变比).
# Ratio registers: 16=电压变比, 17=额定一次电流值
# Energy reg 12-15: PDF says "一次侧电能，单位0.1wh" (0.1Wh) — different from RN!
DJSF_RN6_REALTIME = {
    "voltage":       RegisterDef(50, 2, "float", 1.0, "V"),       # 50-51 Float V (一次值)
    "current":       RegisterDef(52, 2, "float", 1.0, "A"),       # 52-53 Float A (一次值)
    "power":         RegisterDef(54, 2, "float", 1.0, "kW"),      # 54-55 Float kW (一次值)
    "energy_forward_total":  RegisterDef(12, 2, "uint32", 0.0001, "kWh"),  # 12-13 一次侧 单位0.1Wh
    "energy_reverse_total":  RegisterDef(14, 2, "uint32", 0.0001, "kWh"),  # 14-15 一次侧 单位0.1Wh
    "temperature":   RegisterDef(5, 1, "int16", 0.1, "°C"),       # 5 -400~1250 0.1℃
}

DJSF_RN6_RATIO_REGS = {
    "voltage_ratio": RegisterDef(16, 1, "uint16", 1.0, ""),  # 电压变比
    "current_ratio": RegisterDef(17, 1, "uint16", 1.0, ""),  # 额定一次电流值(第一路)
}

# Unified accessor — select register set by meter type
def get_realtime_regs(meter_type: 'MeterType') -> dict:
    if meter_type == MeterType.ADL400:
        return ADL400_REALTIME
    elif meter_type == MeterType.DJSF1352_RN_6:
        return DJSF_RN6_REALTIME
    else:  # DJSF1352_RN
        return DJSF_RN_REALTIME

# Keep backward compat alias (used in tests)
DJSF_REALTIME = DJSF_RN_REALTIME

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

# --- DJSF-RN monthly energy (Modbus): address 2000 area, unit Wh ---
# Source: DJSF1352-RN PDF Page 16-17
DJSF_RN_MONTHLY_CURRENT_FWD = 2010      # 当月总正向有功电能
DJSF_RN_MONTHLY_CURRENT_REV = 2150      # 当月总反向有功电能
DJSF_RN_MONTHLY_FWD_BASE = 2020         # 1-12月正向 (stride 10)
DJSF_RN_MONTHLY_REV_BASE = 2160         # 1-12月反向 (stride 10)
DJSF_RN_MONTHLY_STRIDE = 10
DJSF_RN_MONTHLY_MAX = 12
DJSF_RN_MONTHLY_UNIT_WH = True          # 单位: Wh (÷1000→kWh)

# --- DJSF-RN6 monthly energy (Modbus): address 12288 area, unit 0.1Wh ---
# Source: DJSF1352-RN-6 PDF Page 28-30 (decimal address 12288 = 0x3000)
DJSF_RN6_MONTHLY_FWD_TOTAL = 12288      # 总正向有功电能
DJSF_RN6_MONTHLY_CURRENT_FWD = 12306    # 当月总正向有功电能
DJSF_RN6_MONTHLY_REV_TOTAL = 12324      # 总反向有功电能
DJSF_RN6_MONTHLY_CURRENT_REV = 12342    # 当月总反向有功电能
DJSF_RN6_MONTHLY_UNIT_WH = False        # 单位: 0.1Wh (÷10000→kWh)

# Backward compat aliases
DJSF_MONTHLY_CURRENT_FWD = DJSF_RN_MONTHLY_CURRENT_FWD
DJSF_MONTHLY_CURRENT_REV = DJSF_RN_MONTHLY_CURRENT_REV
DJSF_MONTHLY_MAX = DJSF_RN_MONTHLY_MAX


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
    MeterInfo("直流充电桩1", MeterType.DJSF1352_RN,    8, "03柜", "DJSF1352-RN"),
    MeterInfo("直流充电桩2", MeterType.DJSF1352_RN,    9, "03柜", "DJSF1352-RN"),
    MeterInfo("光伏1",       MeterType.DJSF1352_RN,   10, "03柜", "DJSF1352-RN"),
    MeterInfo("光伏2",       MeterType.DJSF1352_RN,   11, "03柜", "DJSF1352-RN"),
]

METER_BY_ADDR: dict[int, MeterInfo] = {m.slave_addr: m for m in METERS}


# ---------------------------------------------------------------------------
# High-level request builders
# ---------------------------------------------------------------------------

def build_realtime_requests(meter: MeterInfo) -> list[tuple[str, bytes]]:
    """Build Modbus request frames for all realtime registers of a meter.

    Returns list of (param_name, request_frame).
    """
    regs = get_realtime_regs(meter.meter_type)

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
                                       direction: str = "forward",
                                       meter_type: MeterType = MeterType.DJSF1352_RN
                                       ) -> bytes | None:
    """Build request for DJSF monthly history.

    RN uses address 2000 area (unit Wh).
    RN-6 uses address 12288 area (unit 0.1Wh).
    """
    if month < 1 or month > 12:
        return None

    if meter_type == MeterType.DJSF1352_RN_6:
        # RN-6: 12288 area, stride unknown for monthly history per-month
        # RN-6 only has current month and total, not per-month history
        # Use current month registers
        if direction == "forward":
            addr = DJSF_RN6_MONTHLY_CURRENT_FWD
        else:
            addr = DJSF_RN6_MONTHLY_CURRENT_REV
        return build_read_request(slave_addr, addr, 2)
    else:
        # RN: 2000 area, per-month with stride 10
        if direction == "forward":
            addr = DJSF_RN_MONTHLY_FWD_BASE + (month - 1) * DJSF_RN_MONTHLY_STRIDE
        else:
            addr = DJSF_RN_MONTHLY_REV_BASE + (month - 1) * DJSF_RN_MONTHLY_STRIDE
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

    regs = get_realtime_regs(meter_type)
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


def parse_djsf_monthly_energy(data: bytes,
                              meter_type: MeterType = MeterType.DJSF1352_RN
                              ) -> float:
    """Parse DJSF monthly energy response (2 registers = uint32).

    RN: unit Wh → ÷1000 → kWh
    RN-6: unit 0.1Wh → ÷10000 → kWh
    """
    raw = parse_uint32(data)
    if meter_type == MeterType.DJSF1352_RN_6:
        return raw / 10000.0  # 0.1Wh -> kWh
    return raw / 1000.0  # Wh -> kWh
