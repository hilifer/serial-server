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
import requests as http_requests

from flask import Flask, jsonify, request, abort

from meter import (
    MeterType, MeterInfo, METERS, METER_BY_ADDR,
    ADL400_REALTIME, ADL400_BATCH_READS,
    DJSF_RN_REALTIME, DJSF_RN6_REALTIME,
    DJSF_BATCH_READS, DJSF_MONTHLY_MAX,
    get_realtime_regs,
    build_read_request, parse_read_response, parse_register_value,
    safe_read_registers,
    build_daily_history_request,
    build_monthly_history_request_adl400,
    build_monthly_history_request_djsf,
    parse_adl400_history_block,
    parse_djsf_monthly_energy,
)
from parking import (
    PARKING_SPACES, PARKING_BY_ID,
    build_read_status, build_read_all, build_set_display_mode, build_set_color,
    parse_response, parse_detector_registers,
    STATUS_NAMES, DISPLAY_MODE_NAMES, COLOR_NAMES,
)

import os

logger = logging.getLogger("meter-api")

# ---------------------------------------------------------------------------
# Flask application — serve API + static web files
# ---------------------------------------------------------------------------

web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
app = Flask(__name__, static_folder=web_dir, static_url_path="")


@app.route("/")
def serve_index():
    return app.send_static_file("index.html")


@app.route("/<path:path>")
def serve_static(path):
    """Serve static files, fall back to index.html for SPA routing."""
    file_path = os.path.join(web_dir, path)
    if os.path.isfile(file_path):
        return app.send_static_file(path)
    # API routes handled by Flask, not here
    abort(404)


def get_serial():
    """Get the shared SerialManager for COM33 from server.serial_managers."""
    from state import serial_managers
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
    from state import serial_managers
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

    results = {}

    regs = get_realtime_regs(meter.meter_type)

    with ser.lock():
        for name, rdef in regs.items():
            data = safe_read_registers(ser, meter.slave_addr,
                                       rdef.address, rdef.count)
            if data is None:
                results[name] = {"value": None, "unit": rdef.unit, "error": "no response"}
                continue
            try:
                value = parse_register_value(data, rdef)
                results[name] = {"value": value, "unit": rdef.unit}
            except Exception:
                results[name] = {"value": None, "unit": rdef.unit, "error": "parse error"}

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


# ===========================================================================
# Charging Pile/Gun API — Odoo proxy
# ===========================================================================

ODOO_URL = "http://yaorongiot.cn:8069"
ODOO_DB = "odoo12-yaorong"
ODOO_USER = "2355279188@qq.com"
ODOO_PASS = "123456"
_odoo_session = {"id": None}


def _odoo_login():
    """Authenticate with Odoo and get session_id."""
    try:
        resp = http_requests.post(
            f"{ODOO_URL}/web/session/authenticate",
            json={"jsonrpc": "2.0", "params": {
                "db": ODOO_DB, "login": ODOO_USER, "password": ODOO_PASS
            }},
            timeout=10,
        )
        sid = resp.cookies.get("session_id")
        if sid:
            _odoo_session["id"] = sid
            return sid
    except Exception as e:
        logger.warning("Odoo login failed: %s", e)
    return None


def _odoo_call(model, method, domain, fields=None):
    """Call Odoo JSON-RPC API."""
    sid = _odoo_session["id"] or _odoo_login()
    if not sid:
        return None

    payload = {
        "jsonrpc": "2.0", "method": "call",
        "params": {
            "model": model, "method": method,
            "args": [domain],
            "kwargs": {"fields": fields} if fields else {},
        },
    }

    for attempt in range(2):
        try:
            resp = http_requests.post(
                f"{ODOO_URL}/web/dataset/call_kw",
                json=payload,
                headers={"Cookie": f"session_id={sid}"},
                timeout=15,
            )
            data = resp.json()
            if "error" in data and attempt == 0:
                sid = _odoo_login()
                continue
            return data
        except Exception as e:
            logger.warning("Odoo call failed: %s", e)
            if attempt == 0:
                sid = _odoo_login()
    return None


@app.get("/charging/piles")
def get_charging_piles():
    """Proxy to Odoo: list charging piles."""
    data = _odoo_call(
        "pile.charge_server", "search_read",
        [["station_id", "=", 3]],
        ["id", "name", "pile_code", "pile_type", "gun_count", "status",
         "gun_ids", "description"],
    )
    if data:
        return jsonify(data)
    return jsonify({"result": []})


@app.get("/charging/guns")
def get_charging_guns():
    """Proxy to Odoo: list charging guns with status."""
    data = _odoo_call(
        "gun.charge_server", "search_read",
        [["station_id", "=", 3]],
        ["id", "gun_code", "gun_number", "gun_type", "status", "pile_id",
         "output_voltage", "output_current", "total_charge_time",
         "charge_degree"],
    )
    if data:
        return jsonify(data)
    return jsonify({"result": []})

def get_parking_serial(com_port: str):
    from state import serial_managers
    mgr = serial_managers.get(com_port)
    if mgr is None:
        abort(500, description=f"{com_port} SerialManager not initialized")
    if not mgr.is_open:
        abort(503, description=(
            f"{com_port} unavailable: {mgr.last_error or 'not connected'} "
            "(auto-reconnect is running)"
        ))
    return mgr


def _poll_space_status(mgr, space):
    """Poll one parking space status. Returns (status_int, label) or (None, 'no_response')."""
    req = build_read_status(space.slave_addr)
    resp = mgr.send_and_receive_unlocked(req, protocol="parking")
    if not resp:
        return None, "no_response"
    parsed = parse_response(resp)
    if parsed is None or not parsed["data"]:
        return None, "parse_error"
    val = parsed["data"][0]
    return val, STATUS_NAMES.get(val, f"unknown({val})")


@app.get("/parking/spaces")
def list_parking_spaces():
    return jsonify([
        {"space_id": s.space_id, "com_port": s.com_port,
         "slave_addr": s.slave_addr, "zone": s.zone}
        for s in PARKING_SPACES
    ])


@app.get("/parking/status")
def get_all_parking_status():
    """Poll parking spaces. Query: ?zone=A or ?zone=B"""
    from state import serial_managers
    zone = request.args.get("zone", "").upper()

    spaces = PARKING_SPACES
    if zone:
        spaces = [s for s in spaces if s.zone == zone]

    results = []
    by_port: dict[str, list] = {}
    for s in spaces:
        by_port.setdefault(s.com_port, []).append(s)

    for com_port, port_spaces in by_port.items():
        mgr = serial_managers.get(com_port)
        if mgr is None or not mgr.is_open:
            for s in port_spaces:
                results.append({"space_id": s.space_id, "zone": s.zone,
                                "status": None, "label": "offline"})
            continue

        with mgr.lock():
            for s in port_spaces:
                val, label = _poll_space_status(mgr, s)
                results.append({
                    "space_id": s.space_id, "zone": s.zone,
                    "status": val, "label": label,
                })

    results.sort(key=lambda r: r["space_id"])
    online = [r for r in results if r["status"] is not None]
    occupied = sum(1 for r in online if r["status"])

    return jsonify({
        "total": len(results), "online": len(online),
        "occupied": occupied, "empty": len(online) - occupied,
        "spaces": results,
    })


@app.get("/parking/space/<int:space_id>")
def get_parking_space_detail(space_id: int):
    """Read all 8 registers from a detector."""
    space = PARKING_BY_ID.get(space_id)
    if space is None:
        abort(404, description=f"Parking space {space_id} not found (valid: 1-54)")

    ser = get_parking_serial(space.com_port)
    req = build_read_all(space.slave_addr)
    resp = ser.send_and_receive(req, protocol="parking")

    if not resp:
        abort(504, description="No response from detector")

    parsed = parse_response(resp)
    if parsed is None:
        abort(502, description="Invalid response from detector")

    regs = parse_detector_registers(parsed["data"], parsed["start_reg"])

    return jsonify({
        "space_id": space.space_id, "zone": space.zone,
        "com_port": space.com_port, "slave_addr": space.slave_addr,
        "data": regs,
    })


@app.post("/parking/space/<int:space_id>/display_mode")
def set_parking_display_mode(space_id: int):
    """Set detector display mode. Body JSON: {"mode": 0-5}"""
    space = PARKING_BY_ID.get(space_id)
    if space is None:
        abort(404, description=f"Parking space {space_id} not found")

    body = request.get_json(silent=True) or {}
    mode = body.get("mode")
    if mode is None or not (0 <= mode <= 5):
        abort(400, description=f"mode must be 0-5: {DISPLAY_MODE_NAMES}")

    ser = get_parking_serial(space.com_port)
    req = build_set_display_mode(space.slave_addr, mode)
    resp = ser.send_and_receive(req, protocol="parking")

    parsed = parse_response(resp) if resp else None
    ok = parsed is not None and parsed["opcode"] == 0x81

    return jsonify({"success": ok, "mode": mode,
                    "label": DISPLAY_MODE_NAMES.get(mode, "?")})


@app.post("/parking/space/<int:space_id>/color")
def set_parking_color(space_id: int):
    """Set detector LED color. Body JSON: {"color": 0-7}"""
    space = PARKING_BY_ID.get(space_id)
    if space is None:
        abort(404, description=f"Parking space {space_id} not found")

    body = request.get_json(silent=True) or {}
    color = body.get("color")
    if color is None or not (0 <= color <= 7):
        abort(400, description=f"color must be 0-7: {COLOR_NAMES}")

    ser = get_parking_serial(space.com_port)
    req = build_set_color(space.slave_addr, color)
    resp = ser.send_and_receive(req, protocol="parking")

    parsed = parse_response(resp) if resp else None
    ok = parsed is not None and parsed["opcode"] == 0x81

    return jsonify({"success": ok, "color": color,
                    "label": COLOR_NAMES.get(color, "?")})


@app.get("/parking/summary")
def get_parking_summary():
    from state import serial_managers

    summary = {"A": {"total": 27, "occupied": 0, "empty": 0, "offline": 0},
               "B": {"total": 27, "occupied": 0, "empty": 0, "offline": 0}}

    for zone, com_port in [("A", "COM31"), ("B", "COM32")]:
        mgr = serial_managers.get(com_port)
        if mgr is None or not mgr.is_open:
            summary[zone]["offline"] = 27
            continue

        with mgr.lock():
            for addr in range(1, 28):
                req = build_read_status(addr)
                resp = mgr.send_and_receive_unlocked(req, protocol="parking")
                parsed = parse_response(resp) if resp else None

                if parsed and parsed["data"]:
                    if parsed["data"][0]:
                        summary[zone]["occupied"] += 1
                    else:
                        summary[zone]["empty"] += 1
                else:
                    summary[zone]["offline"] += 1

    total_occ = summary["A"]["occupied"] + summary["B"]["occupied"]
    total_empty = summary["A"]["empty"] + summary["B"]["empty"]

    return jsonify({
        "total_spaces": 54, "occupied": total_occ,
        "empty": total_empty, "offline": 54 - total_occ - total_empty,
        "zones": summary,
    })
