#!/usr/bin/env python3
"""
Parking space monitoring protocol (Modbus RTU over RS485).

Supports 54 parking spaces across two serial ports:
  - COM31: spaces 1-27 (Modbus addresses 1-27)
  - COM32: spaces 28-54 (Modbus addresses 1-27)

Protocol: Modbus RTU 03H read holding registers.
Each parking sensor reports:
  - Register 0x0000: Vehicle status (0=empty, 1=occupied)
  - Register 0x0001: Battery level (0-100%)
  - Register 0x0002: Signal strength (0-100%)
  - Register 0x0003: Fault code (0=normal)
  - Register 0x0004: Sensor temperature (INT16, 0.1°C)
  - Register 0x0005: Detection count (UINT16, cumulative)

NOTE: Register addresses may vary by sensor brand.
      Modify PARKING_REGISTERS below to match your hardware.
"""

import logging
from dataclasses import dataclass

from meter import RegisterDef, build_read_request, parse_read_response, parse_register_value

logger = logging.getLogger("parking")


# ---------------------------------------------------------------------------
# Parking sensor register definitions
# ---------------------------------------------------------------------------
# Modify these to match your actual parking sensor protocol

PARKING_REGISTERS = {
    "vehicle_status":    RegisterDef(0x0000, 1, "uint16", 1.0, ""),       # 0=空 1=占用
    "battery_level":     RegisterDef(0x0001, 1, "uint16", 1.0, "%"),      # 电池电量
    "signal_strength":   RegisterDef(0x0002, 1, "uint16", 1.0, "%"),      # 信号强度
    "fault_code":        RegisterDef(0x0003, 1, "uint16", 1.0, ""),       # 故障码 0=正常
    "temperature":       RegisterDef(0x0004, 1, "int16",  0.1, "°C"),     # 传感器温度
    "detection_count":   RegisterDef(0x0005, 1, "uint16", 1.0, ""),       # 累计检测次数
}

# Quick read: only vehicle status (for batch polling)
PARKING_STATUS_REG = RegisterDef(0x0000, 1, "uint16", 1.0, "")

# Batch read: all 6 registers in one request
PARKING_ALL_REG_START = 0x0000
PARKING_ALL_REG_COUNT = 6


# ---------------------------------------------------------------------------
# Parking space definitions
# ---------------------------------------------------------------------------

@dataclass
class ParkingSpace:
    """One parking space."""
    space_id: int          # Global space number: 1-54
    com_port: str          # "COM31" or "COM32"
    slave_addr: int        # Modbus address on this port: 1-27
    zone: str              # Zone label


def _build_spaces() -> list[ParkingSpace]:
    """Build all 54 parking space definitions."""
    spaces = []
    for i in range(1, 28):
        spaces.append(ParkingSpace(
            space_id=i,
            com_port="COM31",
            slave_addr=i,
            zone="A",
        ))
    for i in range(1, 28):
        spaces.append(ParkingSpace(
            space_id=27 + i,
            com_port="COM32",
            slave_addr=i,
            zone="B",
        ))
    return spaces


PARKING_SPACES: list[ParkingSpace] = _build_spaces()
PARKING_BY_ID: dict[int, ParkingSpace] = {s.space_id: s for s in PARKING_SPACES}


# ---------------------------------------------------------------------------
# Request builders
# ---------------------------------------------------------------------------

def build_parking_status_request(slave_addr: int) -> bytes:
    """Build request to read vehicle status (1 register)."""
    return build_read_request(slave_addr, PARKING_STATUS_REG.address,
                              PARKING_STATUS_REG.count)


def build_parking_all_request(slave_addr: int) -> bytes:
    """Build request to read all parking registers (6 registers)."""
    return build_read_request(slave_addr, PARKING_ALL_REG_START,
                              PARKING_ALL_REG_COUNT)


# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------

def parse_parking_status(data: bytes) -> int | None:
    """Parse single vehicle status response. Returns 0(empty) or 1(occupied)."""
    if data is None or len(data) < 2:
        return None
    return parse_register_value(data, PARKING_STATUS_REG)


def parse_parking_all(data: bytes) -> dict | None:
    """Parse all-register response (6 registers = 12 bytes).

    Returns dict with all parameter values, or None on error.
    """
    if data is None or len(data) < PARKING_ALL_REG_COUNT * 2:
        logger.error("Parking data too short: %d bytes", len(data) if data else 0)
        return None

    result = {}
    offset = 0
    for name, rdef in PARKING_REGISTERS.items():
        value = parse_register_value(data[offset:offset + rdef.count * 2], rdef)
        result[name] = {"value": value, "unit": rdef.unit}
        offset += rdef.count * 2

    # Add human-readable status
    status_val = result.get("vehicle_status", {}).get("value")
    if status_val is not None:
        result["vehicle_status"]["label"] = "occupied" if status_val else "empty"

    return result
