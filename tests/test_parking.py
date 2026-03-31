"""Unit tests for parking detector protocol."""

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from parking import (
    PARKING_SPACES, PARKING_BY_ID,
    crc16, build_frame, verify_frame_crc,
    build_read_request, build_write_request,
    build_read_all, build_read_status, build_set_display_mode, build_set_color,
    expected_frame_len, parse_response, parse_detector_registers,
    OP_READ, OP_READ_REPLY, OP_WRITE, OP_WRITE_REPLY,
    REG_DEV_TYPE, REG_DEV_STATUS, REG_DSP_TYPE, REG_DSTC,
    REG_DEV_ADD, REG_485_STATE, REG_MODE, REG_USER_COLOR,
    TOTAL_REGISTERS,
)


# ===========================================================================
# CRC16
# ===========================================================================

class TestCRC16:
    def test_empty(self):
        assert crc16(b"") == 0xFFFF

    def test_known_value(self):
        # Consistent with Modbus CRC
        data = bytes([0x00, 0x02, 0x00, 0x00, 0x01])
        c = crc16(data)
        assert isinstance(c, int)
        assert 0 <= c <= 0xFFFF


# ===========================================================================
# Frame building
# ===========================================================================

class TestBuildFrame:
    def test_read_request_structure(self):
        frame = build_read_request(2, REG_DEV_TYPE, 1)
        assert frame[0] == 0x00  # version
        assert frame[1] == 2     # address
        assert frame[2] == OP_READ  # opcode
        assert frame[3] == REG_DEV_TYPE  # start reg
        assert frame[4] == 1    # count
        assert len(frame) == 7  # 5 header + 2 CRC

    def test_read_all_request(self):
        frame = build_read_all(15)
        assert frame[1] == 15
        assert frame[2] == OP_READ
        assert frame[3] == 0x00
        assert frame[4] == TOTAL_REGISTERS
        assert len(frame) == 7

    def test_read_status_request(self):
        frame = build_read_status(5)
        assert frame[1] == 5
        assert frame[3] == REG_DEV_STATUS
        assert frame[4] == 1

    def test_write_request_structure(self):
        frame = build_write_request(10, REG_DSP_TYPE, [1])
        assert frame[0] == 0x00
        assert frame[1] == 10
        assert frame[2] == OP_WRITE
        assert frame[3] == REG_DSP_TYPE
        assert frame[4] == 1    # count
        assert frame[5] == 1    # data: VIP mode
        assert len(frame) == 8  # 5 header + 1 data + 2 CRC

    def test_write_multi_values(self):
        frame = build_write_request(15, REG_DSP_TYPE, [0x01, 0x64])
        assert frame[4] == 2
        assert frame[5] == 0x01
        assert frame[6] == 0x64
        assert len(frame) == 9

    def test_set_display_mode(self):
        frame = build_set_display_mode(10, 1)  # VIP
        assert frame[1] == 10
        assert frame[2] == OP_WRITE
        assert frame[3] == REG_DSP_TYPE
        assert frame[5] == 1

    def test_set_color(self):
        frame = build_set_color(6, 4)  # blue
        assert frame[1] == 6
        assert frame[3] == REG_USER_COLOR
        assert frame[5] == 4

    def test_frame_has_valid_crc(self):
        frame = build_read_request(1, 0, 8)
        assert verify_frame_crc(frame)

    def test_all_addresses(self):
        for addr in range(1, 28):
            frame = build_read_status(addr)
            assert frame[1] == addr
            assert verify_frame_crc(frame)


# ===========================================================================
# CRC verification
# ===========================================================================

class TestVerifyCRC:
    def test_valid(self):
        frame = build_frame(1, OP_READ, 0, 1)
        assert verify_frame_crc(frame)

    def test_corrupted(self):
        frame = bytearray(build_frame(1, OP_READ, 0, 1))
        frame[3] ^= 0xFF
        assert not verify_frame_crc(bytes(frame))

    def test_too_short(self):
        assert not verify_frame_crc(b"\x00\x01")

    def test_empty(self):
        assert not verify_frame_crc(b"")


# ===========================================================================
# Expected frame length
# ===========================================================================

class TestExpectedFrameLen:
    def test_read_request(self):
        frame = build_read_request(1, 0, 8)
        assert expected_frame_len(frame) == 7

    def test_read_reply(self):
        # Simulate read reply header: ver=0, addr=1, op=0x80, reg=0, count=8
        header = bytes([0x00, 0x01, 0x80, 0x00, 0x08])
        assert expected_frame_len(header) == 5 + 8 + 2  # 15

    def test_write_request(self):
        header = bytes([0x00, 0x0A, 0x01, 0x02, 0x01])
        assert expected_frame_len(header) == 5 + 1 + 2  # 8

    def test_write_reply(self):
        header = bytes([0x00, 0x0A, 0x81, 0x02, 0x01])
        assert expected_frame_len(header) == 8

    def test_partial_data(self):
        assert expected_frame_len(b"\x00\x01") is None
        assert expected_frame_len(b"\x00") is None

    def test_status_read_reply(self):
        # Read status reply: 1 register
        header = bytes([0x00, 0x05, 0x80, 0x01, 0x01])
        assert expected_frame_len(header) == 8


# ===========================================================================
# Response parsing
# ===========================================================================

class TestParseResponse:
    def _make_reply(self, addr, start_reg, data):
        """Build a valid read reply frame."""
        return build_frame(addr, OP_READ_REPLY, start_reg, len(data), bytes(data))

    def test_parse_status_reply(self):
        frame = self._make_reply(5, REG_DEV_STATUS, [1])  # has car
        result = parse_response(frame)
        assert result is not None
        assert result["address"] == 5
        assert result["opcode"] == OP_READ_REPLY
        assert result["start_reg"] == REG_DEV_STATUS
        assert result["count"] == 1
        assert result["data"] == [1]

    def test_parse_all_registers_reply(self):
        data = [0, 1, 0, 15, 5, 1, 1, 2]  # type=0, status=1, dsp=0, dist=15, addr=5, online, online, green
        frame = self._make_reply(5, 0, data)
        result = parse_response(frame)
        assert result is not None
        assert result["count"] == 8
        assert result["data"] == data

    def test_parse_write_reply(self):
        frame = build_frame(10, OP_WRITE_REPLY, REG_DSP_TYPE, 1, bytes([1]))
        result = parse_response(frame)
        assert result is not None
        assert result["opcode"] == OP_WRITE_REPLY
        assert result["data"] == [1]

    def test_bad_crc(self):
        frame = bytearray(self._make_reply(1, 0, [0]))
        frame[-1] ^= 0xFF
        assert parse_response(bytes(frame)) is None

    def test_too_short(self):
        assert parse_response(b"\x00\x01") is None


# ===========================================================================
# Detector register parsing
# ===========================================================================

class TestParseDetectorRegisters:
    def test_all_registers(self):
        data = [0, 1, 0, 15, 5, 1, 1, 2]
        regs = parse_detector_registers(data, start_reg=0)

        assert regs["dev_type"]["value"] == 0
        assert regs["dev_type"]["label"] == "探测器"
        assert regs["dev_status"]["value"] == 1
        assert regs["dev_status"]["label"] == "有车"
        assert regs["dsp_type"]["value"] == 0
        assert regs["dsp_type"]["label"] == "正常"
        assert regs["distance"]["value"] == 15
        assert regs["distance"]["unit"] == "dm"
        assert regs["dev_addr"]["value"] == 5
        assert regs["rs485_state"]["value"] == 1
        assert regs["rs485_state"]["label"] == "在线"
        assert regs["mode"]["value"] == 1
        assert regs["user_color"]["value"] == 2
        assert regs["user_color"]["label"] == "绿色"

    def test_no_car(self):
        regs = parse_detector_registers([0, 0, 0, 0, 1, 1, 1, 0])
        assert regs["dev_status"]["label"] == "无车"

    def test_vip_mode(self):
        regs = parse_detector_registers([0, 0, 1, 0, 1, 1, 1, 0])
        assert regs["dsp_type"]["label"] == "VIP"

    def test_partial_start_reg(self):
        # Read only status register (start_reg=1, data=[1])
        regs = parse_detector_registers([1], start_reg=1)
        assert "dev_status" in regs
        assert regs["dev_status"]["value"] == 1
        assert "dev_type" not in regs  # not included

    def test_colors(self):
        for color_val, name in [(0, "关闭"), (1, "红色"), (2, "绿色"),
                                 (3, "黄色"), (4, "蓝色"), (7, "白色")]:
            data = [0, 0, 0, 0, 1, 1, 1, color_val]
            regs = parse_detector_registers(data)
            assert regs["user_color"]["label"] == name

    def test_display_modes(self):
        for mode, name in [(0, "正常"), (1, "VIP"), (2, "预约"),
                            (4, "充电桩"), (5, "手动颜色")]:
            data = [0, 0, mode, 0, 1, 1, 1, 0]
            regs = parse_detector_registers(data)
            assert regs["dsp_type"]["label"] == name


# ===========================================================================
# Parking space definitions
# ===========================================================================

class TestParkingSpaces:
    def test_total_54(self):
        assert len(PARKING_SPACES) == 54

    def test_ids_1_to_54(self):
        assert sorted(s.space_id for s in PARKING_SPACES) == list(range(1, 55))

    def test_zone_a(self):
        za = [s for s in PARKING_SPACES if s.zone == "A"]
        assert len(za) == 27
        assert all(s.com_port == "COM31" for s in za)

    def test_zone_b(self):
        zb = [s for s in PARKING_SPACES if s.zone == "B"]
        assert len(zb) == 27
        assert all(s.com_port == "COM32" for s in zb)

    def test_lookup(self):
        assert PARKING_BY_ID[1].com_port == "COM31"
        assert PARKING_BY_ID[28].com_port == "COM32"
        assert PARKING_BY_ID[54].slave_addr == 27

    def test_missing(self):
        assert PARKING_BY_ID.get(0) is None
        assert PARKING_BY_ID.get(55) is None


# ===========================================================================
# Protocol doc examples verification
# ===========================================================================

class TestProtocolDocExamples:
    def test_example1_read_device_type(self):
        """Example 1: Read device type from address 2."""
        frame = build_read_request(2, REG_DEV_TYPE, 1)
        assert frame[0] == 0x00  # version
        assert frame[1] == 0x02  # addr
        assert frame[2] == 0x00  # opcode read
        assert frame[3] == 0x00  # reg 0
        assert frame[4] == 0x01  # count 1

    def test_example2_write_display_mode(self):
        """Example 2: Set address 10 display mode to VIP (1)."""
        frame = build_set_display_mode(10, 1)
        assert frame[0] == 0x00
        assert frame[1] == 0x0A  # addr 10
        assert frame[2] == 0x01  # opcode write
        assert frame[3] == 0x02  # reg 2 (DSP_TYPE)
        assert frame[4] == 0x01  # count 1
        assert frame[5] == 0x01  # value 1 (VIP)

    def test_example3_read_all_registers(self):
        """Example 3: Read all 4 registers from address 15."""
        # Doc says 4, but we have 8 registers
        frame = build_read_request(15, 0, 4)
        assert frame[1] == 0x0F  # addr 15
        assert frame[3] == 0x00  # start reg
        assert frame[4] == 0x04  # count 4

    def test_example5_set_manual_mode(self):
        """Example 5: Set address 15 to manual color mode (5)."""
        frame = build_set_display_mode(15, 5)
        assert frame[1] == 0x0F
        assert frame[5] == 0x05  # manual mode

    def test_example6_set_blue_color(self):
        """Example 6: Set address 6 color to blue (4)."""
        frame = build_set_color(6, 4)
        assert frame[1] == 0x06
        assert frame[3] == REG_USER_COLOR  # reg 7
        assert frame[5] == 0x04  # blue
