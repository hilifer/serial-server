#!/usr/bin/env python3
"""
Meter Data API Service

Provides REST API to query energy meter data over Modbus RTU via serial port (COM33).
Supports ADL400 (AC) and DJSF1352-RN/RN-6 (DC) meters.

Endpoints:
  GET /meters                          - List all meters
  GET /meter/{addr}/realtime           - Realtime data
  GET /meter/{addr}/daily?days_ago=1   - Daily history (ADL400 only)
  GET /meter/{addr}/monthly?month=1    - Monthly history
  GET /meter/{addr}/yearly             - Yearly summary (sum of 12 months)
"""

import time
import threading
import logging
from pathlib import Path

import serial
import yaml
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from meter import (
    MeterType, MeterInfo, METERS, METER_BY_ADDR,
    ADL400_REALTIME, DJSF_REALTIME,
    build_read_request, parse_read_response, parse_register_value,
    build_realtime_requests,
    build_daily_history_request,
    build_monthly_history_request_adl400,
    build_monthly_history_request_djsf,
    parse_adl400_history_block,
    parse_djsf_monthly_energy,
    DJSF_MONTHLY_CURRENT_FWD, DJSF_MONTHLY_CURRENT_REV,
)

logger = logging.getLogger("meter-api")

# ---------------------------------------------------------------------------
# Serial port manager (thread-safe)
# ---------------------------------------------------------------------------

class SerialManager:
    """Thread-safe serial port manager for Modbus RTU communication.

    Supports two usage patterns:
      1. Single request: ser.send_and_receive(frame) — auto locks per call.
      2. Batch requests: with ser.lock():
             ser.send_and_receive_unlocked(frame1)
             ser.send_and_receive_unlocked(frame2)
         — holds the lock for the entire batch, preventing interleaving.
    """

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 0.5):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._lock = threading.RLock()
        self._serial: serial.Serial | None = None

    def open(self):
        if self._serial and self._serial.is_open:
            return
        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=self.timeout,
        )
        logger.info("Serial port %s opened @ %d baud", self.port, self.baudrate)

    def close(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
            logger.info("Serial port %s closed", self.port)

    def lock(self):
        """Return the RLock as a context manager for batch operations.

        Usage:
            with ser.lock():
                ser.send_and_receive_unlocked(req1)
                ser.send_and_receive_unlocked(req2)
        """
        return self._lock

    def _do_send_recv(self, request: bytes) -> bytes:
        """Internal: send request and read response (caller must hold lock)."""
        if not self._serial or not self._serial.is_open:
            self.open()
        self._serial.reset_input_buffer()
        self._serial.write(request)
        logger.debug("TX: %s", request.hex())

        time.sleep(0.05)

        response = b""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            chunk = self._serial.read(self._serial.in_waiting or 1)
            if chunk:
                response += chunk
                time.sleep(0.02)
            elif response:
                break

        logger.debug("RX: %s", response.hex())
        return response

    def send_and_receive(self, request: bytes) -> bytes:
        """Send a Modbus request and wait for response (auto-locking)."""
        with self._lock:
            return self._do_send_recv(request)

    def send_and_receive_unlocked(self, request: bytes) -> bytes:
        """Send a Modbus request without acquiring the lock.

        Caller MUST hold self.lock() before calling this method.
        """
        return self._do_send_recv(request)


# ---------------------------------------------------------------------------
# Load config for serial port
# ---------------------------------------------------------------------------

def load_serial_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    # Find COM33 config
    for port_cfg in config["serial_ports"]:
        if port_cfg["name"] == "COM33":
            return port_cfg
    # Fallback to last port
    return config["serial_ports"][-1]


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Energy Meter API",
    description="Query energy meter data via Modbus RTU (COM33)",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global serial manager
serial_mgr: SerialManager | None = None


@app.on_event("startup")
def startup():
    global serial_mgr
    port_cfg = load_serial_config()
    serial_mgr = SerialManager(
        port=port_cfg["port"],
        baudrate=port_cfg["baudrate"],
        timeout=port_cfg.get("timeout", 0.5),
    )
    try:
        serial_mgr.open()
    except serial.SerialException as e:
        logger.warning("Could not open serial port on startup: %s (will retry on first request)", e)


@app.on_event("shutdown")
def shutdown():
    if serial_mgr:
        serial_mgr.close()


def get_serial() -> SerialManager:
    if serial_mgr is None:
        raise HTTPException(500, "Serial port not initialized")
    return serial_mgr


def get_meter(addr: int) -> MeterInfo:
    meter = METER_BY_ADDR.get(addr)
    if meter is None:
        raise HTTPException(404, f"Meter with address {addr} not found")
    return meter


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/meters")
def list_meters():
    """List all configured meters."""
    return [
        {
            "address": m.slave_addr,
            "name": m.name,
            "model": m.model,
            "type": "AC" if m.meter_type == MeterType.ADL400 else "DC",
            "location": m.location,
            "note": m.note,
        }
        for m in METERS
    ]


@app.get("/meter/{addr}/realtime")
def get_realtime(addr: int):
    """Read all realtime parameters from a meter."""
    meter = get_meter(addr)
    ser = get_serial()

    regs = ADL400_REALTIME if meter.meter_type == MeterType.ADL400 else DJSF_REALTIME
    results = {}

    with ser.lock():
        for name, rdef in regs.items():
            request = build_read_request(meter.slave_addr, rdef.address, rdef.count)
            response = ser.send_and_receive_unlocked(request)
            if not response:
                results[name] = {"value": None, "unit": rdef.unit, "error": "no response"}
                continue
            data = parse_read_response(response)
            if data is None:
                results[name] = {"value": None, "unit": rdef.unit, "error": "parse error"}
                continue
            value = parse_register_value(data, rdef)
            results[name] = {"value": value, "unit": rdef.unit}

    return {
        "address": addr,
        "name": meter.name,
        "model": meter.model,
        "data": results,
    }


@app.get("/meter/{addr}/daily")
def get_daily(addr: int, days_ago: int = Query(1, ge=1, le=90)):
    """Read daily frozen energy data.

    ADL400: supports up to 90 days history.
    DJSF: daily data not available via Modbus.
    """
    meter = get_meter(addr)

    if meter.meter_type != MeterType.ADL400:
        raise HTTPException(
            400,
            f"Daily history not available for {meter.model} via Modbus "
            "(only supported via DLT645 protocol)"
        )

    ser = get_serial()
    request = build_daily_history_request(meter.slave_addr, days_ago)
    if request is None:
        raise HTTPException(400, f"days_ago must be 1-90, got {days_ago}")

    response = ser.send_and_receive(request)
    if not response:
        raise HTTPException(504, "No response from meter")

    data = parse_read_response(response)
    if data is None:
        raise HTTPException(502, "Invalid response from meter")

    result = parse_adl400_history_block(data)
    if result is None:
        raise HTTPException(502, "Failed to parse history block")

    return {
        "address": addr,
        "name": meter.name,
        "model": meter.model,
        "period": "daily",
        "days_ago": days_ago,
        "data": result,
    }


@app.get("/meter/{addr}/monthly")
def get_monthly(addr: int, months_ago: int = Query(1, ge=1, le=48)):
    """Read monthly frozen energy data.

    ADL400: supports up to 48 months history.
    DJSF: supports up to 12 months (calendar month 1-12).
    """
    meter = get_meter(addr)
    ser = get_serial()

    if meter.meter_type == MeterType.ADL400:
        request = build_monthly_history_request_adl400(meter.slave_addr, months_ago)
        if request is None:
            raise HTTPException(400, f"months_ago must be 1-48, got {months_ago}")

        response = ser.send_and_receive(request)
        if not response:
            raise HTTPException(504, "No response from meter")

        data = parse_read_response(response)
        if data is None:
            raise HTTPException(502, "Invalid response from meter")

        result = parse_adl400_history_block(data)
        if result is None:
            raise HTTPException(502, "Failed to parse history block")

        return {
            "address": addr,
            "name": meter.name,
            "model": meter.model,
            "period": "monthly",
            "months_ago": months_ago,
            "data": result,
        }
    else:
        # DJSF: read month by calendar month number
        if months_ago > DJSF_MONTHLY_MAX:
            raise HTTPException(400, f"DJSF supports up to 12 months, got {months_ago}")

        # Read forward energy for that month
        req_fwd = build_monthly_history_request_djsf(
            meter.slave_addr, months_ago, "forward")
        req_rev = build_monthly_history_request_djsf(
            meter.slave_addr, months_ago, "reverse")

        fwd_kwh = None
        rev_kwh = None

        with ser.lock():
            if req_fwd:
                resp = ser.send_and_receive_unlocked(req_fwd)
                data = parse_read_response(resp) if resp else None
                if data:
                    fwd_kwh = parse_djsf_monthly_energy(data)

            if req_rev:
                resp = ser.send_and_receive_unlocked(req_rev)
                data = parse_read_response(resp) if resp else None
                if data:
                    rev_kwh = parse_djsf_monthly_energy(data)

        return {
            "address": addr,
            "name": meter.name,
            "model": meter.model,
            "period": "monthly",
            "month": months_ago,
            "data": {
                "energy_forward_kwh": fwd_kwh,
                "energy_reverse_kwh": rev_kwh,
            },
        }


@app.get("/meter/{addr}/yearly")
def get_yearly(addr: int):
    """Read yearly energy summary (aggregated from monthly data).

    ADL400: sums up to 12 recent months of history.
    DJSF: sums 12 calendar months.
    """
    meter = get_meter(addr)
    ser = get_serial()

    if meter.meter_type == MeterType.ADL400:
        monthly_data = []
        total_energy = 0.0

        with ser.lock():
            for m in range(1, 13):
                request = build_monthly_history_request_adl400(meter.slave_addr, m)
                if request is None:
                    continue
                response = ser.send_and_receive_unlocked(request)
                if not response:
                    continue
                data = parse_read_response(response)
                if data is None:
                    continue
                block = parse_adl400_history_block(data)
                if block:
                    monthly_data.append(block)
                    total_energy += block["energy_active_total_kwh"]

        return {
            "address": addr,
            "name": meter.name,
            "model": meter.model,
            "period": "yearly",
            "total_energy_kwh": round(total_energy, 2),
            "months": monthly_data,
        }
    else:
        # DJSF: sum 12 months
        total_fwd = 0.0
        total_rev = 0.0
        months = []

        with ser.lock():
            for m in range(1, 13):
                fwd_kwh = None
                rev_kwh = None

                req_fwd = build_monthly_history_request_djsf(
                    meter.slave_addr, m, "forward")
                if req_fwd:
                    resp = ser.send_and_receive_unlocked(req_fwd)
                    data = parse_read_response(resp) if resp else None
                    if data:
                        fwd_kwh = parse_djsf_monthly_energy(data)
                        total_fwd += fwd_kwh

                req_rev = build_monthly_history_request_djsf(
                    meter.slave_addr, m, "reverse")
                if req_rev:
                    resp = ser.send_and_receive_unlocked(req_rev)
                    data = parse_read_response(resp) if resp else None
                    if data:
                        rev_kwh = parse_djsf_monthly_energy(data)
                        total_rev += rev_kwh

                months.append({
                    "month": m,
                    "energy_forward_kwh": fwd_kwh,
                    "energy_reverse_kwh": rev_kwh,
                })

        return {
            "address": addr,
            "name": meter.name,
            "model": meter.model,
            "period": "yearly",
            "total_forward_kwh": round(total_fwd, 2),
            "total_reverse_kwh": round(total_rev, 2),
            "months": months,
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
