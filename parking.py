#!/usr/bin/env python3
"""
Parking space detector protocol (custom RS485, NOT Modbus RTU).

Based on: docs/主控与探测器屏通信协议.docx
Device type: 探测器 (detector) only.

Architecture:
  - COM31: Zone A, 27 detectors (addresses 1-27)
  - COM32: Zone B, 27 detectors (addresses 1-27)
  - Total: 54 parking spaces

Frame structure:
  [版本 1B][地址 1B][操作码 1B][起始寄存器 1B][数据长度 1B][数据 NB][CRC16 2B]

  Read request:   00 [addr] 00 [start_reg] [count]          [CRC_lo CRC_hi]
  Read response:  00 [addr] 80 [start_reg] [count] [data..] [CRC_lo CRC_hi]
  Write request:  00 [addr] 01 [start_reg] [count] [data..] [CRC_lo CRC_hi]
  Write response: 00 [addr] 81 [start_reg] [count] [data..] [CRC_lo CRC_hi]

Detector register map (each register = 1 byte):
  0x0  DEV_TYPE       设备类型     0x00=探测器 (固定)
  0x1  DEV_STATUS     车位状态     0=无车, 1=有车
  0x2  DSP_TYPE       显示模式     0=正常,1=VIP,2=预约,3=测试,4=充电桩,5=手动颜色
  0x3  DSTC           检测距离     单位：分米
  0x4  DEV_ADD        设备地址
  0x5  485_STATE      485状态     0=离线, 1=在线
  0x6  MODE           工作模式     0=离线, 1=在线
  0x7  USER_DEF_COLOR 手动颜色     0=关,1=红,2=绿,3=黄,4=蓝,5=品红,6=青,7=白
"""

import struct
import logging
from dataclasses import dataclass

logger = logging.getLogger("parking")


# ---------------------------------------------------------------------------
# CRC16
# ---------------------------------------------------------------------------

def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

PROTOCOL_VERSION = 0x00

OP_READ = 0x00
OP_READ_REPLY = 0x80
OP_WRITE = 0x01
OP_WRITE_REPLY = 0x81

# Register addresses
REG_DEV_TYPE = 0x00
REG_DEV_STATUS = 0x01
REG_DSP_TYPE = 0x02
REG_DSTC = 0x03
REG_DEV_ADD = 0x04
REG_485_STATE = 0x05
REG_MODE = 0x06
REG_USER_COLOR = 0x07

TOTAL_REGISTERS = 8

# Label maps
DISPLAY_MODE_NAMES = {
    0: "正常", 1: "VIP", 2: "预约", 3: "测试", 4: "充电桩", 5: "手动颜色",
}
COLOR_NAMES = {
    0: "关闭", 1: "红色", 2: "绿色", 3: "黄色", 4: "蓝色",
    5: "品红", 6: "青色", 7: "白色",
}
STATUS_NAMES = {0: "无车", 1: "有车"}
ONLINE_NAMES = {0: "离线", 1: "在线"}


# ---------------------------------------------------------------------------
# Frame building
# ---------------------------------------------------------------------------

def build_frame(addr: int, opcode: int, start_reg: int,
                count: int, data: bytes = b"") -> bytes:
    """Build a complete protocol frame with CRC16."""
    frame = bytes([PROTOCOL_VERSION, addr, opcode, start_reg, count]) + data
    c = crc16(frame)
    return frame + struct.pack("<H", c)


def verify_frame_crc(frame: bytes) -> bool:
    if len(frame) < 7:
        return False
    data, crc_recv = frame[:-2], struct.unpack("<H", frame[-2:])[0]
    return crc16(data) == crc_recv


def build_read_request(addr: int, start_reg: int, count: int) -> bytes:
    """Build read register request (no data field)."""
    return build_frame(addr, OP_READ, start_reg, count)


def build_write_request(addr: int, start_reg: int, values: list[int]) -> bytes:
    """Build write register request."""
    return build_frame(addr, OP_WRITE, start_reg, len(values), bytes(values))


# --- Convenience builders ---

def build_read_all(addr: int) -> bytes:
    """Read all 8 registers."""
    return build_read_request(addr, REG_DEV_TYPE, TOTAL_REGISTERS)


def build_read_status(addr: int) -> bytes:
    """Read vehicle status (register 0x01, 1 byte)."""
    return build_read_request(addr, REG_DEV_STATUS, 1)


def build_set_display_mode(addr: int, mode: int) -> bytes:
    """Set display mode (0=正常,1=VIP,2=预约,3=测试,4=充电桩,5=手动颜色)."""
    return build_write_request(addr, REG_DSP_TYPE, [mode])


def build_set_color(addr: int, color: int) -> bytes:
    """Set LED color (0=关,1=红,2=绿,3=黄,4=蓝,5=品红,6=青,7=白)."""
    return build_write_request(addr, REG_USER_COLOR, [color])


# ---------------------------------------------------------------------------
# Frame length calculation (for serial_manager frame detection)
# ---------------------------------------------------------------------------

def expected_frame_len(partial: bytes) -> int | None:
    """Calculate expected total frame length from partial data.

    Returns None if not enough data to determine.
    """
    if len(partial) < 5:
        return None
    opcode = partial[2]
    count = partial[4]

    if opcode == OP_READ:
        return 7  # read request has no data: 5 header + 2 CRC
    # Read reply, write request, write reply all have 'count' data bytes
    return 5 + count + 2


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_response(frame: bytes) -> dict | None:
    """Parse a response frame. Returns dict or None on error."""
    if not verify_frame_crc(frame):
        logger.error("Parking CRC failed: %s", frame.hex())
        return None

    if len(frame) < 7:
        logger.error("Parking frame too short: %d bytes", len(frame))
        return None

    addr = frame[1]
    opcode = frame[2]
    start_reg = frame[3]
    count = frame[4]
    data = list(frame[5:5 + count])

    if len(data) != count:
        logger.error("Parking data length mismatch: expected %d got %d", count, len(data))
        return None

    return {
        "address": addr,
        "opcode": opcode,
        "start_reg": start_reg,
        "count": count,
        "data": data,
    }


def parse_detector_registers(data: list[int], start_reg: int = 0) -> dict:
    """Parse detector register values into a named dict.

    data: list of register byte values
    start_reg: the starting register address
    """
    result = {}
    reg_parsers = {
        REG_DEV_TYPE:   lambda v: {"value": v, "label": "探测器"},
        REG_DEV_STATUS: lambda v: {"value": v, "label": STATUS_NAMES.get(v, f"?({v})")},
        REG_DSP_TYPE:   lambda v: {"value": v, "label": DISPLAY_MODE_NAMES.get(v, f"?({v})")},
        REG_DSTC:       lambda v: {"value": v, "unit": "dm"},
        REG_DEV_ADD:    lambda v: {"value": v},
        REG_485_STATE:  lambda v: {"value": v, "label": ONLINE_NAMES.get(v, f"?({v})")},
        REG_MODE:       lambda v: {"value": v, "label": ONLINE_NAMES.get(v, f"?({v})")},
        REG_USER_COLOR: lambda v: {"value": v, "label": COLOR_NAMES.get(v, f"?({v})")},
    }
    reg_names = {
        REG_DEV_TYPE: "dev_type",
        REG_DEV_STATUS: "dev_status",
        REG_DSP_TYPE: "dsp_type",
        REG_DSTC: "distance",
        REG_DEV_ADD: "dev_addr",
        REG_485_STATE: "rs485_state",
        REG_MODE: "mode",
        REG_USER_COLOR: "user_color",
    }

    for i, val in enumerate(data):
        reg_addr = start_reg + i
        name = reg_names.get(reg_addr)
        parser = reg_parsers.get(reg_addr)
        if name and parser:
            result[name] = parser(val)

    return result


# ---------------------------------------------------------------------------
# Parking space definitions
# ---------------------------------------------------------------------------

@dataclass
class ParkingSpace:
    space_id: int       # Global: 1-54
    com_port: str       # "COM31" or "COM32"
    slave_addr: int     # Address on bus: 1-27
    zone: str           # "A" or "B"


def _build_spaces() -> list[ParkingSpace]:
    spaces = []
    for i in range(1, 28):
        spaces.append(ParkingSpace(i, "COM31", i, "A"))
    for i in range(1, 28):
        spaces.append(ParkingSpace(27 + i, "COM32", i, "B"))
    return spaces


PARKING_SPACES: list[ParkingSpace] = _build_spaces()
PARKING_BY_ID: dict[int, ParkingSpace] = {s.space_id: s for s in PARKING_SPACES}
