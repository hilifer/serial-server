"""Unit tests for parking space monitoring module."""

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from meter import build_frame, parse_read_response, build_read_request
from parking import (
    PARKING_SPACES, PARKING_BY_ID, PARKING_REGISTERS,
    PARKING_STATUS_REG, PARKING_ALL_REG_START, PARKING_ALL_REG_COUNT,
    ParkingSpace,
    build_parking_status_request, build_parking_all_request,
    parse_parking_status, parse_parking_all,
)


# ===========================================================================
# Space definitions
# ===========================================================================

class TestParkingSpaces:
    def test_total_54_spaces(self):
        assert len(PARKING_SPACES) == 54

    def test_space_ids_1_to_54(self):
        ids = sorted(s.space_id for s in PARKING_SPACES)
        assert ids == list(range(1, 55))

    def test_zone_a_com31(self):
        zone_a = [s for s in PARKING_SPACES if s.zone == "A"]
        assert len(zone_a) == 27
        assert all(s.com_port == "COM31" for s in zone_a)
        assert sorted(s.slave_addr for s in zone_a) == list(range(1, 28))

    def test_zone_b_com32(self):
        zone_b = [s for s in PARKING_SPACES if s.zone == "B"]
        assert len(zone_b) == 27
        assert all(s.com_port == "COM32" for s in zone_b)
        assert sorted(s.slave_addr for s in zone_b) == list(range(1, 28))

    def test_zone_a_space_ids(self):
        zone_a = [s for s in PARKING_SPACES if s.zone == "A"]
        ids = sorted(s.space_id for s in zone_a)
        assert ids == list(range(1, 28))

    def test_zone_b_space_ids(self):
        zone_b = [s for s in PARKING_SPACES if s.zone == "B"]
        ids = sorted(s.space_id for s in zone_b)
        assert ids == list(range(28, 55))

    def test_lookup_by_id(self):
        s = PARKING_BY_ID[1]
        assert s.com_port == "COM31"
        assert s.slave_addr == 1
        assert s.zone == "A"

    def test_lookup_by_id_zone_b(self):
        s = PARKING_BY_ID[28]
        assert s.com_port == "COM32"
        assert s.slave_addr == 1
        assert s.zone == "B"

    def test_lookup_last_space(self):
        s = PARKING_BY_ID[54]
        assert s.com_port == "COM32"
        assert s.slave_addr == 27

    def test_lookup_missing(self):
        assert PARKING_BY_ID.get(0) is None
        assert PARKING_BY_ID.get(55) is None


# ===========================================================================
# Register definitions
# ===========================================================================

class TestParkingRegisters:
    def test_6_registers(self):
        assert len(PARKING_REGISTERS) == 6

    def test_vehicle_status_register(self):
        r = PARKING_REGISTERS["vehicle_status"]
        assert r.address == 0x0000
        assert r.count == 1

    def test_all_regs_start_and_count(self):
        assert PARKING_ALL_REG_START == 0x0000
        assert PARKING_ALL_REG_COUNT == 6


# ===========================================================================
# Request builders
# ===========================================================================

class TestBuildParkingRequest:
    def test_status_request(self):
        frame = build_parking_status_request(1)
        assert frame[0] == 1  # slave addr
        assert frame[1] == 0x03  # func code
        assert struct.unpack(">H", frame[2:4])[0] == 0x0000  # register
        assert struct.unpack(">H", frame[4:6])[0] == 1  # count

    def test_all_request(self):
        frame = build_parking_all_request(1)
        assert frame[0] == 1
        assert struct.unpack(">H", frame[4:6])[0] == 6  # 6 registers

    def test_different_addresses(self):
        for addr in [1, 15, 27]:
            frame = build_parking_status_request(addr)
            assert frame[0] == addr

    def test_frame_length(self):
        frame = build_parking_status_request(1)
        assert len(frame) == 8  # addr+func+reg(2)+count(2)+crc(2)


# ===========================================================================
# Response parsers
# ===========================================================================

class TestParseParkingStatus:
    def _make_response(self, slave, data):
        payload = bytes([len(data)]) + data
        return build_frame(slave, 0x03, payload)

    def test_empty_status(self):
        frame = self._make_response(1, b"\x00\x00")  # status=0 (empty)
        data = parse_read_response(frame)
        val = parse_parking_status(data)
        assert val == 0

    def test_occupied_status(self):
        frame = self._make_response(1, b"\x00\x01")  # status=1 (occupied)
        data = parse_read_response(frame)
        val = parse_parking_status(data)
        assert val == 1

    def test_none_on_no_data(self):
        assert parse_parking_status(None) is None

    def test_none_on_short_data(self):
        assert parse_parking_status(b"\x00") is None


class TestParseParkingAll:
    def _make_data(self, status=0, battery=85, signal=72,
                   fault=0, temp=250, count=1234):
        """Build 12 bytes (6 registers) of parking sensor data."""
        return struct.pack(">HHHHHH", status, battery, signal,
                           fault, temp, count)

    def test_parse_empty_space(self):
        data = self._make_data(status=0)
        result = parse_parking_all(data)
        assert result is not None
        assert result["vehicle_status"]["value"] == 0
        assert result["vehicle_status"]["label"] == "empty"

    def test_parse_occupied_space(self):
        data = self._make_data(status=1)
        result = parse_parking_all(data)
        assert result["vehicle_status"]["value"] == 1
        assert result["vehicle_status"]["label"] == "occupied"

    def test_parse_battery(self):
        data = self._make_data(battery=85)
        result = parse_parking_all(data)
        assert result["battery_level"]["value"] == 85
        assert result["battery_level"]["unit"] == "%"

    def test_parse_temperature(self):
        data = self._make_data(temp=250)  # 250 * 0.1 = 25.0°C
        result = parse_parking_all(data)
        assert abs(result["temperature"]["value"] - 25.0) < 0.01

    def test_parse_negative_temp(self):
        # -50 as int16 -> 0xFFCE -> -50 * 0.1 = -5.0°C
        data = self._make_data(temp=65486)  # 0xFFCE = -50 signed
        result = parse_parking_all(data)
        assert result["temperature"]["value"] < 0

    def test_parse_fault(self):
        data = self._make_data(fault=3)
        result = parse_parking_all(data)
        assert result["fault_code"]["value"] == 3

    def test_parse_count(self):
        data = self._make_data(count=1234)
        result = parse_parking_all(data)
        assert result["detection_count"]["value"] == 1234

    def test_none_on_short_data(self):
        assert parse_parking_all(b"\x00" * 4) is None

    def test_none_on_none(self):
        assert parse_parking_all(None) is None

    def test_all_fields_present(self):
        data = self._make_data()
        result = parse_parking_all(data)
        for name in PARKING_REGISTERS:
            assert name in result, f"Missing field: {name}"
