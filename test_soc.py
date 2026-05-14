#!/usr/bin/env python3
"""Battery SOC read test via Modbus TCP.

Target: 10.6.120.10:502, unit 5, FC 0x03 (read holding registers),
        start addr 304, count 1. Value is SOC in %.

Usage: python test_soc.py [--host IP] [--port P] [--unit N] [--addr A]
"""
import argparse
import socket
import struct
import sys


def read_holding_register(host: str, port: int, unit: int, addr: int, count: int = 1,
                          timeout: float = 3.0) -> bytes:
    # MBAP (7 bytes) + PDU (5 bytes for FC03 request)
    tx_id = 1
    proto_id = 0
    length = 6  # unit + fc + addr + count
    mbap = struct.pack(">HHHB", tx_id, proto_id, length, unit)
    pdu = struct.pack(">BHH", 0x03, addr, count)
    req = mbap + pdu

    with socket.create_connection((host, port), timeout=timeout) as s:
        print(f"→ request  : {req.hex(' ')}")
        s.sendall(req)

        # Read response: MBAP (7 bytes) first
        hdr = _recv_all(s, 7)
        r_tx, r_proto, r_len, r_unit = struct.unpack(">HHHB", hdr)
        body = _recv_all(s, r_len - 1)
        print(f"← response : {(hdr + body).hex(' ')}")
        return body  # starts with function code


def _recv_all(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("remote closed while reading")
        buf += chunk
    return buf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="10.6.120.10")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--unit", type=int, default=5)
    ap.add_argument("--addr", type=int, default=304)
    ap.add_argument("--count", type=int, default=1)
    args = ap.parse_args()

    print(f"Reading Modbus TCP: {args.host}:{args.port}  "
          f"unit={args.unit}  addr={args.addr}  count={args.count}")

    try:
        body = read_holding_register(args.host, args.port, args.unit,
                                     args.addr, args.count)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    fc = body[0]
    if fc & 0x80:
        # Exception response
        ex_code = body[1]
        print(f"Modbus exception: fc=0x{fc:02x} code=0x{ex_code:02x}")
        sys.exit(2)

    byte_count = body[1]
    data = body[2:2 + byte_count]
    regs = [struct.unpack(">H", data[i:i + 2])[0] for i in range(0, len(data), 2)]
    print(f"Registers  : {regs}")
    print(f"SOC        : {regs[0]} %")


if __name__ == "__main__":
    main()
