#!/usr/bin/env python3
"""
Serial port send/receive test tool.

Supports four test modes:
  1. Raw hex:     Send arbitrary hex bytes, display response
  2. Modbus:      Build Modbus RTU frame (auto CRC), parse response
  3. Meter query: Quick-read a specific meter's register by name
  4. MQTT test:   Send data via MQTT WS topic, verify round-trip

Usage:
    # --- Raw hex mode ---
    python test_send.py --port COM33 --hex "01 03 00 61 00 01"

    # --- Modbus mode (auto-adds CRC) ---
    python test_send.py --port COM33 --modbus --addr 1 --reg 0x0061 --count 1

    # --- Meter query mode ---
    python test_send.py --port COM33 --meter 1 --param voltage_a
    python test_send.py --port COM33 --meter 5 --param voltage
    python test_send.py --port COM33 --meter 1 --param all

    # --- MQTT test mode ---
    python test_send.py --mqtt --topic serial/com33/down --hex "01 03 00 61 00 01 C5 D5"

    # --- List available parameters ---
    python test_send.py --list-params
"""

import argparse
import struct
import subprocess
import sys
import time
from pathlib import Path


def ensure_deps():
    """Auto-install dependencies if missing."""
    required = {"serial": "pyserial", "paho.mqtt": "paho-mqtt", "yaml": "pyyaml"}
    missing = []
    for mod, pkg in required.items():
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing missing dependencies: {', '.join(missing)} ...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *missing, "-q"],
            stdout=subprocess.DEVNULL,
        )


ensure_deps()

sys.path.insert(0, str(Path(__file__).parent))

from meter import (
    MeterType, METERS, METER_BY_ADDR,
    ADL400_REALTIME, DJSF_REALTIME,
    build_read_request, parse_read_response, parse_register_value,
    crc16_modbus, verify_crc,
)


# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------

class C:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    END = "\033[0m"


def hex_dump(data: bytes, label: str = "") -> str:
    """Format bytes as colored hex dump."""
    hex_str = " ".join(f"{b:02X}" for b in data)
    ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    prefix = f"{C.BOLD}{label}{C.END} " if label else ""
    return f"{prefix}{C.CYAN}{hex_str}{C.END}  {C.DIM}|{ascii_str}|{C.END}  ({len(data)} bytes)"


# ---------------------------------------------------------------------------
# Serial send/receive
# ---------------------------------------------------------------------------

def serial_send_recv(port: str, baudrate: int, data: bytes,
                     timeout: float = 0.5) -> bytes:
    import serial
    try:
        ser = serial.Serial(port=port, baudrate=baudrate, bytesize=8,
                            parity="N", stopbits=1, timeout=timeout)
    except serial.SerialException as e:
        print(f"{C.RED}Serial open failed: {e}{C.END}")
        sys.exit(1)

    ser.reset_input_buffer()
    ser.write(data)
    print(hex_dump(data, "TX:"))

    time.sleep(0.05)
    response = b""
    deadline = time.time() + timeout
    while time.time() < deadline:
        n = ser.in_waiting
        if n > 0:
            response += ser.read(n)
            time.sleep(0.02)
        elif response:
            break
        else:
            time.sleep(0.01)

    ser.close()

    if response:
        print(hex_dump(response, "RX:"))
        if len(response) >= 4:
            if verify_crc(response):
                print(f"  {C.GREEN}CRC: OK{C.END}")
            else:
                print(f"  {C.RED}CRC: FAIL{C.END}")
            # Check for Modbus exception
            if response[1] & 0x80:
                err_code = response[2] if len(response) > 2 else -1
                err_msgs = {1: "Illegal Function", 2: "Illegal Data Address",
                            3: "Illegal Data Value", 4: "Slave Device Failure"}
                print(f"  {C.RED}Modbus Exception: {err_msgs.get(err_code, f'code {err_code}')}{C.END}")
    else:
        print(f"  {C.YELLOW}RX: (no response, timeout {timeout}s){C.END}")

    return response


# ---------------------------------------------------------------------------
# Raw hex mode
# ---------------------------------------------------------------------------

def cmd_raw_hex(args):
    hex_str = args.hex.replace(",", " ").replace("0x", "").replace("0X", "")
    try:
        data = bytes.fromhex(hex_str.replace(" ", ""))
    except ValueError as e:
        print(f"{C.RED}Invalid hex: {e}{C.END}")
        sys.exit(1)

    print(f"\n{C.BOLD}Raw Hex Send{C.END}")
    print(f"  Port: {args.port} @ {args.baudrate} baud\n")
    serial_send_recv(args.port, args.baudrate, data, args.timeout)


# ---------------------------------------------------------------------------
# Modbus mode (auto CRC)
# ---------------------------------------------------------------------------

def cmd_modbus(args):
    frame = build_read_request(args.addr, args.reg, args.count)

    print(f"\n{C.BOLD}Modbus RTU Read (03H){C.END}")
    print(f"  Slave: {args.addr}, Register: 0x{args.reg:04X}, Count: {args.count}")
    print(f"  Port: {args.port} @ {args.baudrate} baud\n")

    response = serial_send_recv(args.port, args.baudrate, frame, args.timeout)

    if response:
        data = parse_read_response(response)
        if data:
            print(f"\n  {C.BOLD}Parsed data ({len(data)} bytes):{C.END}")
            if len(data) == 2:
                u16 = struct.unpack(">H", data)[0]
                i16 = struct.unpack(">h", data)[0]
                print(f"    UINT16: {u16}")
                print(f"    INT16:  {i16}")
            elif len(data) == 4:
                u32 = struct.unpack(">I", data)[0]
                i32 = struct.unpack(">i", data)[0]
                flt = struct.unpack(">f", data)[0]
                print(f"    UINT32: {u32}")
                print(f"    INT32:  {i32}")
                print(f"    FLOAT:  {flt:.6f}")


# ---------------------------------------------------------------------------
# Meter query mode
# ---------------------------------------------------------------------------

def cmd_meter_query(args):
    meter = METER_BY_ADDR.get(args.meter)
    if meter is None:
        print(f"{C.RED}Meter address {args.meter} not found. Valid: 1-8{C.END}")
        sys.exit(1)

    regs = ADL400_REALTIME if meter.meter_type == MeterType.ADL400 else DJSF_REALTIME

    if args.param == "all":
        params = list(regs.keys())
    else:
        if args.param not in regs:
            print(f"{C.RED}Unknown parameter '{args.param}' for {meter.model}{C.END}")
            print(f"  Available: {', '.join(regs.keys())}")
            sys.exit(1)
        params = [args.param]

    print(f"\n{C.BOLD}Meter Query: [{args.meter}] {meter.name} ({meter.model}){C.END}")
    print(f"  Port: {args.port} @ {args.baudrate} baud\n")

    import serial
    try:
        ser = serial.Serial(port=args.port, baudrate=args.baudrate, bytesize=8,
                            parity="N", stopbits=1, timeout=args.timeout)
    except serial.SerialException as e:
        print(f"{C.RED}Serial open failed: {e}{C.END}")
        sys.exit(1)

    for name in params:
        rdef = regs[name]
        request = build_read_request(meter.slave_addr, rdef.address, rdef.count)
        print(hex_dump(request, f"TX [{name}]:"))

        ser.reset_input_buffer()
        ser.write(request)
        time.sleep(0.05)

        response = b""
        deadline = time.time() + args.timeout
        while time.time() < deadline:
            n = ser.in_waiting
            if n > 0:
                response += ser.read(n)
                time.sleep(0.02)
            elif response:
                break
            else:
                time.sleep(0.01)

        if response:
            print(hex_dump(response, f"RX [{name}]:"))
            data = parse_read_response(response)
            if data:
                value = parse_register_value(data, rdef)
                print(f"  {C.GREEN}{name} = {value} {rdef.unit}{C.END}\n")
            else:
                print(f"  {C.RED}Parse failed{C.END}\n")
        else:
            print(f"  {C.YELLOW}No response{C.END}\n")

        time.sleep(0.05)  # inter-frame delay

    ser.close()


# ---------------------------------------------------------------------------
# MQTT test mode
# ---------------------------------------------------------------------------

def cmd_mqtt(args):
    import paho.mqtt.client as mqtt

    hex_str = args.hex.replace(",", " ").replace("0x", "").replace("0X", "")
    try:
        data = bytes.fromhex(hex_str.replace(" ", ""))
    except ValueError as e:
        print(f"{C.RED}Invalid hex: {e}{C.END}")
        sys.exit(1)

    # Derive the "up" topic from the "down" topic for listening
    if args.topic.endswith("/down"):
        up_topic = args.topic.rsplit("/down", 1)[0] + "/up"
    else:
        up_topic = args.topic + "/response"

    print(f"\n{C.BOLD}MQTT WebSocket Send Test{C.END}")
    print(f"  Broker: {args.mqtt_host}:{args.mqtt_port}")
    print(f"  Publish to:  {args.topic}")
    print(f"  Subscribe:   {up_topic}\n")

    received = []

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"  {C.GREEN}Connected to MQTT broker{C.END}")
            client.subscribe(up_topic, qos=1)
        else:
            print(f"  {C.RED}MQTT connect failed: rc={rc}{C.END}")
            sys.exit(1)

    def on_message(client, userdata, msg):
        print(f"\n{hex_dump(msg.payload, 'RX [MQTT]:')}")
        if len(msg.payload) >= 4 and verify_crc(msg.payload):
            print(f"  {C.GREEN}CRC: OK{C.END}")
            resp_data = parse_read_response(msg.payload)
            if resp_data:
                print(f"  Data bytes: {' '.join(f'{b:02X}' for b in resp_data)}")
        received.append(msg.payload)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, transport="websockets")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.mqtt_host, args.mqtt_port)
    except Exception as e:
        print(f"{C.RED}MQTT connect failed: {e}{C.END}")
        sys.exit(1)

    client.loop_start()
    time.sleep(0.5)  # wait for subscribe

    print(hex_dump(data, "TX [MQTT]:"))
    client.publish(args.topic, data, qos=1)

    # Wait for response
    deadline = time.time() + args.timeout
    while time.time() < deadline and not received:
        time.sleep(0.1)

    if not received:
        print(f"\n  {C.YELLOW}No response received within {args.timeout}s{C.END}")

    client.loop_stop()
    client.disconnect()


# ---------------------------------------------------------------------------
# List params mode
# ---------------------------------------------------------------------------

def cmd_parking(args):
    """Query a parking space sensor."""
    from parking import (
        PARKING_BY_ID, PARKING_REGISTERS,
        build_parking_status_request, build_parking_all_request,
        parse_parking_status, parse_parking_all,
    )

    space = PARKING_BY_ID.get(args.parking)
    if space is None:
        print(f"{C.RED}Parking space {args.parking} not found. Valid: 1-54{C.END}")
        sys.exit(1)

    port = args.port if args.port != "COM33" else space.com_port
    print(f"\n{C.BOLD}Parking Query: Space {space.space_id} (Zone {space.zone}){C.END}")
    print(f"  Port: {port} @ {args.baudrate} baud, Modbus addr: {space.slave_addr}\n")

    if args.param == "status":
        frame = build_parking_status_request(space.slave_addr)
    else:
        frame = build_parking_all_request(space.slave_addr)

    import serial as pyserial
    try:
        ser = pyserial.Serial(port=port, baudrate=args.baudrate, bytesize=8,
                              parity="N", stopbits=1, timeout=args.timeout)
    except pyserial.SerialException as e:
        print(f"{C.RED}Serial open failed: {e}{C.END}")
        sys.exit(1)

    print(hex_dump(frame, "TX:"))
    ser.reset_input_buffer()
    ser.write(frame)
    time.sleep(0.05)

    response = b""
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        n = ser.in_waiting
        if n > 0:
            response += ser.read(n)
            time.sleep(0.02)
        elif response:
            break
        else:
            time.sleep(0.01)

    ser.close()

    if not response:
        print(f"  {C.YELLOW}No response{C.END}")
        return

    print(hex_dump(response, "RX:"))
    data = parse_read_response(response)
    if data is None:
        print(f"  {C.RED}Parse failed{C.END}")
        return

    if args.param == "status":
        val = parse_parking_status(data)
        if val is not None:
            label = "OCCUPIED" if val else "EMPTY"
            color = C.RED if val else C.GREEN
            print(f"\n  {C.BOLD}Status: {color}{label}{C.END}")
    else:
        result = parse_parking_all(data)
        if result:
            print(f"\n  {C.BOLD}Sensor Data:{C.END}")
            for name, info in result.items():
                val = info.get("value", "?")
                unit = info.get("unit", "")
                label = info.get("label", "")
                extra = f"  ({label})" if label else ""
                print(f"    {name:<20s}: {val} {unit}{extra}")


def cmd_list_params():
    from parking import PARKING_SPACES, PARKING_REGISTERS

    print(f"\n{C.BOLD}=== Energy Meters (COM33) ==={C.END}\n")

    for m in METERS:
        regs = ADL400_REALTIME if m.meter_type == MeterType.ADL400 else DJSF_REALTIME
        print(f"  {C.BOLD}[{m.slave_addr}] {m.name} ({m.model}){C.END}")
        for name, rdef in regs.items():
            print(f"    {name:<30s} reg=0x{rdef.address:04X}  "
                  f"count={rdef.count}  scale={rdef.scale}  unit={rdef.unit}")
        print()

    print(f"\n{C.BOLD}=== Parking Spaces (COM31 + COM32) ==={C.END}\n")
    print(f"  Zone A (COM31): spaces 1-27,  Modbus addr 1-27")
    print(f"  Zone B (COM32): spaces 28-54, Modbus addr 1-27\n")
    print(f"  {C.BOLD}Sensor registers:{C.END}")
    for name, rdef in PARKING_REGISTERS.items():
        print(f"    {name:<20s} reg=0x{rdef.address:04X}  "
              f"count={rdef.count}  scale={rdef.scale}  unit={rdef.unit}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Serial port send/receive test tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send raw hex bytes
  python test_send.py --port COM33 --hex "01 03 00 61 00 01 C5 D5"

  # Modbus read (auto CRC): slave=1, reg=0x0061 (voltage_a), count=1
  python test_send.py --port COM33 --modbus --addr 1 --reg 0x0061 --count 1

  # Query meter 1 voltage_a
  python test_send.py --port COM33 --meter 1 --param voltage_a

  # Query all params from meter 5
  python test_send.py --port COM33 --meter 5 --param all

  # Send via MQTT WS
  python test_send.py --mqtt --topic serial/com33/down --hex "01 03 00 61 00 01 C5 D5"

  # List all meter parameters
  python test_send.py --list-params
""")

    parser.add_argument("--port", default="COM33", help="Serial port (default: COM33)")
    parser.add_argument("--baudrate", type=int, default=9600, help="Baud rate (default: 9600)")
    parser.add_argument("--timeout", type=float, default=1.0, help="Response timeout seconds (default: 1.0)")

    # Raw hex
    parser.add_argument("--hex", type=str, help="Hex bytes to send (e.g. '01 03 00 61 00 01 C5 D5')")

    # Modbus mode
    parser.add_argument("--modbus", action="store_true", help="Modbus RTU mode (auto CRC)")
    parser.add_argument("--addr", type=int, help="Modbus slave address")
    parser.add_argument("--reg", type=lambda x: int(x, 0), help="Register address (e.g. 0x0061)")
    parser.add_argument("--count", type=int, default=1, help="Number of registers to read")

    # Meter query mode
    parser.add_argument("--meter", type=int, help="Meter address (1-8)")
    parser.add_argument("--param", type=str, help="Parameter name or 'all'")

    # Parking mode
    parser.add_argument("--parking", type=int, help="Parking space ID (1-54)")
    # --param reused: 'status' or 'all' (default: all)

    # MQTT mode
    parser.add_argument("--mqtt", action="store_true", help="Send via MQTT WebSocket")
    parser.add_argument("--topic", type=str, help="MQTT topic (e.g. serial/com33/down)")
    parser.add_argument("--mqtt-host", default="localhost", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=9001, help="MQTT WS port")

    # List params
    parser.add_argument("--list-params", action="store_true", help="List all meter parameters")

    args = parser.parse_args()

    if args.list_params:
        cmd_list_params()
    elif args.mqtt and args.hex and args.topic:
        cmd_mqtt(args)
    elif args.parking is not None:
        if not args.param:
            args.param = "all"
        cmd_parking(args)
    elif args.meter is not None and args.param:
        cmd_meter_query(args)
    elif args.modbus and args.addr is not None and args.reg is not None:
        cmd_modbus(args)
    elif args.hex and not args.mqtt:
        cmd_raw_hex(args)
    else:
        parser.print_help()
        print(f"\n{C.YELLOW}Tip: use --list-params to see all parameters{C.END}")


if __name__ == "__main__":
    main()
