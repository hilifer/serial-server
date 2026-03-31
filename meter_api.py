#!/usr/bin/env python3
"""
Meter Data API (Flask routes)

Uses shared SerialManager from server.py for COM33 access.
Coexists with MQTT WS transparent bridge — both share the same
serial port lock, preventing bus conflicts.

Endpoints:
  GET /status                          - Serial port status
  GET /meters                          - List all meters
  GET /meter/{addr}/realtime           - Realtime data
  GET /meter/{addr}/daily?days_ago=1   - Daily history (ADL400 only)
  GET /meter/{addr}/monthly?months_ago=1 - Monthly history
  GET /meter/{addr}/yearly             - Yearly summary (sum of 12 months)
"""

import logging

from flask import Flask, jsonify, request, abort

from meter import (
    MeterType, MeterInfo, METERS, METER_BY_ADDR,
    ADL400_REALTIME, DJSF_REALTIME, DJSF_MONTHLY_MAX,
    build_read_request, parse_read_response, parse_register_value,
    build_daily_history_request,
    build_monthly_history_request_adl400,
    build_monthly_history_request_djsf,
    parse_adl400_history_block,
    parse_djsf_monthly_energy,
)

logger = logging.getLogger("meter-api")

# ---------------------------------------------------------------------------
# Flask application
# ---------------------------------------------------------------------------

app = Flask(__name__)


def get_serial():
    """Get the shared SerialManager for COM33 from server.serial_managers."""
    from server import serial_managers
    mgr = serial_managers.get("COM33")
    if mgr is None:
        abort(500, description="COM33 SerialManager not initialized")
    if not mgr.is_open:
        abort(503, description=(
            f"COM33 serial port unavailable: {mgr.last_error or 'not connected'} "
            "(auto-reconnect is running)"
        ))
    return mgr


def get_meter(addr: int) -> MeterInfo:
    meter = METER_BY_ADDR.get(addr)
    if meter is None:
        abort(404, description=f"Meter with address {addr} not found")
    return meter


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(500)
@app.errorhandler(502)
@app.errorhandler(503)
@app.errorhandler(504)
def handle_error(e):
    return jsonify({"error": e.description}), e.code


# ---------------------------------------------------------------------------
# CORS support
# ---------------------------------------------------------------------------

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/status")
def get_status():
    """Get serial port status for all ports."""
    from server import serial_managers
    return jsonify({
        "ports": {
            name: mgr.get_status_info()
            for name, mgr in serial_managers.items()
        }
    })


@app.get("/meters")
def list_meters():
    """List all configured meters."""
    return jsonify([
        {
            "address": m.slave_addr,
            "name": m.name,
            "model": m.model,
            "type": "AC" if m.meter_type == MeterType.ADL400 else "DC",
            "location": m.location,
            "note": m.note,
        }
        for m in METERS
    ])


@app.get("/meter/<int:addr>/realtime")
def get_realtime(addr: int):
    """Read all realtime parameters from a meter."""
    meter = get_meter(addr)
    ser = get_serial()

    regs = ADL400_REALTIME if meter.meter_type == MeterType.ADL400 else DJSF_REALTIME
    results = {}

    with ser.lock():
        for name, rdef in regs.items():
            req = build_read_request(meter.slave_addr, rdef.address, rdef.count)
            response = ser.send_and_receive_unlocked(req)
            if not response:
                results[name] = {"value": None, "unit": rdef.unit, "error": "no response"}
                continue
            data = parse_read_response(response)
            if data is None:
                results[name] = {"value": None, "unit": rdef.unit, "error": "parse error"}
                continue
            value = parse_register_value(data, rdef)
            results[name] = {"value": value, "unit": rdef.unit}

    return jsonify({
        "address": addr,
        "name": meter.name,
        "model": meter.model,
        "data": results,
    })


@app.get("/meter/<int:addr>/daily")
def get_daily(addr: int):
    """Read daily frozen energy data."""
    days_ago = request.args.get("days_ago", 1, type=int)
    if days_ago < 1 or days_ago > 90:
        abort(400, description=f"days_ago must be 1-90, got {days_ago}")

    meter = get_meter(addr)

    if meter.meter_type != MeterType.ADL400:
        abort(400, description=(
            f"Daily history not available for {meter.model} via Modbus "
            "(only supported via DLT645 protocol)"
        ))

    ser = get_serial()
    req = build_daily_history_request(meter.slave_addr, days_ago)
    if req is None:
        abort(400, description=f"days_ago must be 1-90, got {days_ago}")

    response = ser.send_and_receive(req)
    if not response:
        abort(504, description="No response from meter")

    data = parse_read_response(response)
    if data is None:
        abort(502, description="Invalid response from meter")

    result = parse_adl400_history_block(data)
    if result is None:
        abort(502, description="Failed to parse history block")

    return jsonify({
        "address": addr,
        "name": meter.name,
        "model": meter.model,
        "period": "daily",
        "days_ago": days_ago,
        "data": result,
    })


@app.get("/meter/<int:addr>/monthly")
def get_monthly(addr: int):
    """Read monthly frozen energy data."""
    months_ago = request.args.get("months_ago", 1, type=int)

    meter = get_meter(addr)
    ser = get_serial()

    if meter.meter_type == MeterType.ADL400:
        if months_ago < 1 or months_ago > 48:
            abort(400, description=f"months_ago must be 1-48, got {months_ago}")

        req = build_monthly_history_request_adl400(meter.slave_addr, months_ago)
        if req is None:
            abort(400, description=f"months_ago must be 1-48, got {months_ago}")

        response = ser.send_and_receive(req)
        if not response:
            abort(504, description="No response from meter")

        data = parse_read_response(response)
        if data is None:
            abort(502, description="Invalid response from meter")

        result = parse_adl400_history_block(data)
        if result is None:
            abort(502, description="Failed to parse history block")

        return jsonify({
            "address": addr,
            "name": meter.name,
            "model": meter.model,
            "period": "monthly",
            "months_ago": months_ago,
            "data": result,
        })
    else:
        if months_ago < 1 or months_ago > DJSF_MONTHLY_MAX:
            abort(400, description=f"DJSF supports up to 12 months, got {months_ago}")

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

        return jsonify({
            "address": addr,
            "name": meter.name,
            "model": meter.model,
            "period": "monthly",
            "month": months_ago,
            "data": {
                "energy_forward_kwh": fwd_kwh,
                "energy_reverse_kwh": rev_kwh,
            },
        })


@app.get("/meter/<int:addr>/yearly")
def get_yearly(addr: int):
    """Read yearly energy summary (aggregated from monthly data)."""
    meter = get_meter(addr)
    ser = get_serial()

    if meter.meter_type == MeterType.ADL400:
        monthly_data = []
        total_energy = 0.0

        with ser.lock():
            for m in range(1, 13):
                req = build_monthly_history_request_adl400(meter.slave_addr, m)
                if req is None:
                    continue
                response = ser.send_and_receive_unlocked(req)
                if not response:
                    continue
                data = parse_read_response(response)
                if data is None:
                    continue
                block = parse_adl400_history_block(data)
                if block:
                    monthly_data.append(block)
                    total_energy += block["energy_active_total_kwh"]

        return jsonify({
            "address": addr,
            "name": meter.name,
            "model": meter.model,
            "period": "yearly",
            "total_energy_kwh": round(total_energy, 2),
            "months": monthly_data,
        })
    else:
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

        return jsonify({
            "address": addr,
            "name": meter.name,
            "model": meter.model,
            "period": "yearly",
            "total_forward_kwh": round(total_fwd, 2),
            "total_reverse_kwh": round(total_rev, 2),
            "months": months,
        })
