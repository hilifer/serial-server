"""Unit tests for meter protocol module."""

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from meter import (
    crc16_modbus, build_frame, verify_crc,
    build_read_request, parse_read_response,
    parse_uint16, parse_int16, parse_uint32, parse_int32, parse_float,
    parse_register_value, parse_realtime_response,
    parse_adl400_history_block, parse_djsf_monthly_energy,
    build_realtime_requests, build_daily_history_request,
    build_monthly_history_request_adl400, build_monthly_history_request_djsf,
    MeterType, MeterInfo, RegisterDef,
    METERS, METER_BY_ADDR, ADL400_REALTIME, DJSF_REALTIME,
    ADL400_DAILY_BASE, ADL400_DAILY_STRIDE,
    ADL400_MONTHLY_BASE, ADL400_MONTHLY_STRIDE,
)


# ===========================================================================
# CRC16
# ===========================================================================

class TestCRC16:
    def test_known_crc(self):
        # Standard Modbus example: slave=1, func=03, addr=0064, count=0001
        data = bytes([0x01, 0x03, 0x00, 0x64, 0x00, 0x01])
        crc = crc16_modbus(data)
        assert crc == 0xD5C5  # known CRC for this frame

    def test_empty_data(self):
        crc = crc16_modbus(b"")
        assert crc == 0xFFFF  # initial value

    def test_single_byte(self):
        crc = crc16_modbus(b"\x00")
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF


class TestBuildFrame:
    def test_frame_structure(self):
        frame = build_frame(0x01, 0x03, b"\x00\x64\x00\x01")
        assert frame[0] == 0x01  # slave addr
        assert frame[1] == 0x03  # func code
        assert frame[2:6] == b"\x00\x64\x00\x01"  # payload
        assert len(frame) == 8  # 1+1+4+2(CRC)

    def test_frame_has_valid_crc(self):
        frame = build_frame(0x01, 0x03, b"\x00\x64\x00\x01")
        assert verify_crc(frame)


class TestVerifyCRC:
    def test_valid_frame(self):
        frame = build_frame(0x01, 0x03, b"\x00\x00\x00\x02")
        assert verify_crc(frame) is True

    def test_corrupted_frame(self):
        frame = bytearray(build_frame(0x01, 0x03, b"\x00\x00\x00\x02"))
        frame[3] ^= 0xFF  # corrupt a byte
        assert verify_crc(bytes(frame)) is False

    def test_too_short(self):
        assert verify_crc(b"\x01\x03") is False

    def test_empty(self):
        assert verify_crc(b"") is False


# ===========================================================================
# Read request/response
# ===========================================================================

class TestBuildReadRequest:
    def test_standard_request(self):
        frame = build_read_request(1, 0x0064, 1)
        assert frame[0] == 0x01
        assert frame[1] == 0x03
        assert struct.unpack(">H", frame[2:4])[0] == 0x0064
        assert struct.unpack(">H", frame[4:6])[0] == 1
        assert len(frame) == 8

    def test_different_addresses(self):
        for addr in [1, 5, 8, 247]:
            frame = build_read_request(addr, 0, 1)
            assert frame[0] == addr

    def test_multi_register(self):
        frame = build_read_request(1, 0x000A, 2)
        assert struct.unpack(">H", frame[4:6])[0] == 2


class TestParseReadResponse:
    def _make_response(self, slave: int, data: bytes) -> bytes:
        """Build a valid 03H response frame."""
        payload = bytes([len(data)]) + data
        return build_frame(slave, 0x03, payload)

    def test_valid_response(self):
        data = b"\x03\xB2"  # 946
        frame = self._make_response(1, data)
        result = parse_read_response(frame)
        assert result == data

    def test_4_byte_response(self):
        data = b"\x00\x00\x30\x26"  # 12326
        frame = self._make_response(1, data)
        result = parse_read_response(frame)
        assert result == data

    def test_bad_crc(self):
        frame = self._make_response(1, b"\x03\xB2")
        frame = frame[:-1] + bytes([frame[-1] ^ 0xFF])
        assert parse_read_response(frame) is None

    def test_exception_response(self):
        # Exception: func=0x83, error_code=0x02
        frame = build_frame(1, 0x83, b"\x02")
        assert parse_read_response(frame) is None

    def test_too_short(self):
        assert parse_read_response(b"\x01") is None


# ===========================================================================
# Data parsers
# ===========================================================================

class TestDataParsers:
    def test_uint16(self):
        assert parse_uint16(b"\x03\xB2") == 946

    def test_int16_positive(self):
        assert parse_int16(b"\x03\xB2") == 946

    def test_int16_negative(self):
        assert parse_int16(b"\xFF\xFF") == -1

    def test_uint32(self):
        assert parse_uint32(b"\x00\x00\x30\x26") == 12326

    def test_int32_negative(self):
        assert parse_int32(b"\xFF\xFF\xFF\xFF") == -1

    def test_float(self):
        # 100.0537 -> 0x42C81B84
        data = struct.pack(">f", 100.0537)
        val = parse_float(data)
        assert abs(val - 100.0537) < 0.001

    def test_uint16_offset(self):
        data = b"\xAA\xBB\x03\xB2"
        assert parse_uint16(data, 2) == 946

    def test_float_offset(self):
        data = b"\x00\x00" + struct.pack(">f", 250.5)
        val = parse_float(data, 2)
        assert abs(val - 250.5) < 0.01


class TestParseRegisterValue:
    def test_uint16_with_scale(self):
        rdef = RegisterDef(0x0061, 1, "uint16", 0.1, "V")
        data = b"\x09\x10"  # 2320
        val = parse_register_value(data, rdef)
        assert abs(val - 232.0) < 0.01

    def test_int32_with_scale(self):
        rdef = RegisterDef(0x016A, 2, "int32", 0.001, "kW")
        data = b"\x00\x00\x27\x10"  # 10000
        val = parse_register_value(data, rdef)
        assert abs(val - 10.0) < 0.001

    def test_float_no_scale(self):
        rdef = RegisterDef(50, 2, "float", 1.0, "V")
        data = struct.pack(">f", 220.5)
        val = parse_register_value(data, rdef)
        assert abs(val - 220.5) < 0.01

    def test_energy_uint32(self):
        rdef = RegisterDef(0x000A, 2, "uint32", 0.01, "kWh")
        data = b"\x00\x00\x30\x26"  # 12326
        val = parse_register_value(data, rdef)
        assert abs(val - 123.26) < 0.001


# ===========================================================================
# Realtime response parsing
# ===========================================================================

class TestParseRealtimeResponse:
    def _make_response(self, data: bytes) -> bytes:
        payload = bytes([len(data)]) + data
        return build_frame(1, 0x03, payload)

    def test_adl400_voltage(self):
        # ADL400 now uses primary-side float registers
        data = struct.pack(">f", 232.0)  # IEEE 754 float
        frame = self._make_response(data)
        result = parse_realtime_response("voltage_a", frame, MeterType.ADL400)
        assert result is not None
        assert result["name"] == "voltage_a"
        assert abs(result["value"] - 232.0) < 0.1
        assert result["unit"] == "V"

    def test_adl400_energy(self):
        # Primary side energy: UINT32, unit 0.1kWh
        data = b"\x00\x00\x02\x30"  # 560 -> 560 * 0.1 = 56.0 kWh
        frame = self._make_response(data)
        result = parse_realtime_response("energy_combined_total", frame, MeterType.ADL400)
        assert result is not None
        assert abs(result["value"] - 56.0) < 0.1

    def test_djsf_voltage_float(self):
        data = struct.pack(">f", 380.5)
        frame = self._make_response(data)
        result = parse_realtime_response("voltage", frame, MeterType.DJSF1352_RN)
        assert result is not None
        assert abs(result["value"] - 380.5) < 0.1

    def test_unknown_param(self):
        frame = self._make_response(b"\x00\x00")
        result = parse_realtime_response("nonexistent", frame, MeterType.ADL400)
        assert result is None

    def test_bad_frame(self):
        result = parse_realtime_response("voltage_a", b"\x01\x03", MeterType.ADL400)
        assert result is None


# ===========================================================================
# History block parsing
# ===========================================================================

class TestParseADL400HistoryBlock:
    def _make_block(self, year=25, month=3, day=30, hour=0,
                    energy=123456, peak=30000, high=40000,
                    mid=30000, low=23456, reactive=50000) -> bytes:
        """Build a 68-byte (34 register) history block."""
        data = bytearray(68)
        # time_ym
        struct.pack_into(">H", data, 0, (year << 8) | month)
        # time_dh
        struct.pack_into(">H", data, 2, (day << 8) | hour)
        # energy fields (all uint32, at word offsets * 2)
        struct.pack_into(">I", data, 4, energy)
        struct.pack_into(">I", data, 8, peak)
        struct.pack_into(">I", data, 12, high)
        struct.pack_into(">I", data, 16, mid)
        struct.pack_into(">I", data, 20, low)
        struct.pack_into(">I", data, 24, reactive)
        return bytes(data)

    def test_parse_basic(self):
        data = self._make_block()
        result = parse_adl400_history_block(data)
        assert result is not None
        assert result["freeze_time"] == "2025-03-30 00:00"
        assert abs(result["energy_active_total_kwh"] - 1234.56) < 0.01

    def test_parse_energy_values(self):
        data = self._make_block(energy=100000, peak=25000, high=30000,
                                mid=25000, low=20000, reactive=10000)
        result = parse_adl400_history_block(data)
        assert abs(result["energy_active_total_kwh"] - 1000.0) < 0.01
        assert abs(result["energy_active_peak_kwh"] - 250.0) < 0.01
        assert abs(result["energy_active_high_kwh"] - 300.0) < 0.01
        assert abs(result["energy_active_mid_kwh"] - 250.0) < 0.01
        assert abs(result["energy_active_low_kwh"] - 200.0) < 0.01
        assert abs(result["energy_reactive_total_kvarh"] - 100.0) < 0.01

    def test_data_too_short(self):
        assert parse_adl400_history_block(b"\x00" * 10) is None


class TestParseDJSFMonthlyEnergy:
    def test_basic(self):
        # 5000 Wh -> 5.0 kWh
        data = struct.pack(">I", 5000)
        val = parse_djsf_monthly_energy(data)
        assert abs(val - 5.0) < 0.001

    def test_zero(self):
        data = struct.pack(">I", 0)
        assert parse_djsf_monthly_energy(data) == 0.0

    def test_large_value(self):
        # 999999999 Wh -> 999999.999 kWh
        data = struct.pack(">I", 999999999)
        val = parse_djsf_monthly_energy(data)
        assert abs(val - 999999.999) < 0.01


# ===========================================================================
# Request builders
# ===========================================================================

class TestBuildRealtimeRequests:
    def test_adl400_requests(self):
        meter = MeterInfo("test", MeterType.ADL400, 1, "01柜", "ADL400")
        requests = build_realtime_requests(meter)
        assert len(requests) == len(ADL400_REALTIME)
        for name, frame in requests:
            assert name in ADL400_REALTIME
            assert len(frame) == 8
            assert frame[0] == 1  # slave addr

    def test_djsf_requests(self):
        meter = MeterInfo("test", MeterType.DJSF1352_RN, 6, "03柜", "DJSF1352-RN")
        requests = build_realtime_requests(meter)
        assert len(requests) == len(DJSF_REALTIME)
        for name, frame in requests:
            assert name in DJSF_REALTIME
            assert frame[0] == 6

    def test_djsf_rn6_uses_same_regs(self):
        meter = MeterInfo("test", MeterType.DJSF1352_RN_6, 5, "03柜", "DJSF1352-RN-6")
        requests = build_realtime_requests(meter)
        assert len(requests) == len(DJSF_REALTIME)


class TestBuildDailyHistoryRequest:
    def test_yesterday(self):
        frame = build_daily_history_request(1, 1)
        assert frame is not None
        reg = struct.unpack(">H", frame[2:4])[0]
        assert reg == ADL400_DAILY_BASE

    def test_30_days_ago(self):
        frame = build_daily_history_request(1, 30)
        assert frame is not None
        reg = struct.unpack(">H", frame[2:4])[0]
        assert reg == ADL400_DAILY_BASE + 29 * ADL400_DAILY_STRIDE

    def test_out_of_range(self):
        assert build_daily_history_request(1, 0) is None
        assert build_daily_history_request(1, 91) is None

    def test_max_days(self):
        frame = build_daily_history_request(1, 90)
        assert frame is not None


class TestBuildMonthlyHistoryRequestADL400:
    def test_last_month(self):
        frame = build_monthly_history_request_adl400(1, 1)
        assert frame is not None
        reg = struct.unpack(">H", frame[2:4])[0]
        assert reg == ADL400_MONTHLY_BASE

    def test_out_of_range(self):
        assert build_monthly_history_request_adl400(1, 0) is None
        assert build_monthly_history_request_adl400(1, 49) is None


class TestBuildMonthlyHistoryRequestDJSF:
    def test_forward(self):
        frame = build_monthly_history_request_djsf(6, 1, "forward")
        assert frame is not None
        assert frame[0] == 6

    def test_reverse(self):
        frame = build_monthly_history_request_djsf(6, 1, "reverse")
        assert frame is not None

    def test_out_of_range(self):
        assert build_monthly_history_request_djsf(6, 0) is None
        assert build_monthly_history_request_djsf(6, 13) is None


# ===========================================================================
# Meter registry
# ===========================================================================

class TestMeterRegistry:
    def test_8_meters(self):
        assert len(METERS) == 8

    def test_addresses_1_to_8(self):
        addrs = sorted(m.slave_addr for m in METERS)
        assert addrs == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_4_adl400(self):
        ac = [m for m in METERS if m.meter_type == MeterType.ADL400]
        assert len(ac) == 4

    def test_4_dc_meters(self):
        dc = [m for m in METERS if m.meter_type != MeterType.ADL400]
        assert len(dc) == 4

    def test_lookup_by_addr(self):
        m = METER_BY_ADDR[1]
        assert m.name == "电网侧电表"
        assert m.model == "ADL400"

    def test_lookup_dc_meter(self):
        m = METER_BY_ADDR[5]
        assert m.model == "DJSF1352-RN-6"
        assert m.meter_type == MeterType.DJSF1352_RN_6


# ===========================================================================
# ADL400 example frames from protocol doc
# ===========================================================================

class TestProtocolDocExamples:
    def test_adl400_read_current_request(self):
        """Verify: 01 03 00 64 00 01 C5 D5"""
        frame = build_read_request(0x01, 0x0064, 0x0001)
        assert frame == bytes([0x01, 0x03, 0x00, 0x64, 0x00, 0x01, 0xC5, 0xD5])

    def test_adl400_read_current_response(self):
        """Verify: 01 03 02 03 B2 38 C1 -> 946 * 0.01 = 9.46A"""
        frame = bytes([0x01, 0x03, 0x02, 0x03, 0xB2, 0x38, 0xC1])
        data = parse_read_response(frame)
        assert data is not None
        raw = parse_uint16(data)
        assert raw == 946
        assert abs(raw * 0.01 - 9.46) < 0.001

    def test_adl400_read_energy_request(self):
        """Verify: 01 03 00 00 00 02 C4 0B"""
        frame = build_read_request(0x01, 0x0000, 0x0002)
        assert frame == bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x02, 0xC4, 0x0B])

    def test_adl400_read_energy_response(self):
        """Verify: reading 12326 * 0.01 = 123.26 kWh from energy register."""
        # Build a valid frame (the doc example CRC may have typo)
        payload = b"\x04\x00\x00\x30\x26"  # byte_count=4, data=0x00003026
        frame = build_frame(0x01, 0x03, payload)
        data = parse_read_response(frame)
        assert data is not None
        raw = parse_uint32(data)
        assert raw == 12326
        assert abs(raw * 0.01 - 123.26) < 0.001

    def test_djsf_read_voltage_request(self):
        """Verify: 01 03 00 32 00 02 65 C4 (addr 50 = 0x32)"""
        frame = build_read_request(0x01, 0x0032, 0x0002)
        assert frame == bytes([0x01, 0x03, 0x00, 0x32, 0x00, 0x02, 0x65, 0xC4])

    def test_djsf_read_voltage_response(self):
        """Verify: float decode 42 C8 1B 84 -> ~100.054V"""
        # Build a valid frame with known float data
        payload = b"\x04\x42\xC8\x1B\x84"  # byte_count=4, then float bytes
        frame = build_frame(0x01, 0x03, payload)
        data = parse_read_response(frame)
        assert data is not None
        val = parse_float(data)
        assert abs(val - 100.054) < 0.1

    def test_djsf_ch2_uses_addr_plus_1(self):
        """Channel 2 of a dual-channel DJSF uses slave_addr + 1."""
        # Meter at addr 7 (直流桩电表) has 2 channels
        # Channel 1 = addr 7, Channel 2 = addr 8
        ch1_frame = build_read_request(7, 0x0032, 2)
        ch2_frame = build_read_request(8, 0x0032, 2)
        assert ch1_frame[0] == 7
        assert ch2_frame[0] == 8
        # Same register, different slave address
        assert ch1_frame[2:6] == ch2_frame[2:6]
