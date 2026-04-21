#!/usr/bin/env python3
"""BMS Modbus TCP reader — reads battery SOC from a TCP Modbus slave.

Thread-safe with a short TTL cache so the /battery/soc endpoint can be
polled aggressively without hammering the BMS.
"""
import logging
import socket
import struct
import threading
import time
from typing import Optional

logger = logging.getLogger("bms")


class BMSReader:
    def __init__(self, host: str, port: int = 502, unit: int = 5,
                 soc_addr: int = 304, capacity_kwh: float = 100.0,
                 timeout: float = 2.0, cache_ttl: float = 5.0):
        self.host = host
        self.port = port
        self.unit = unit
        self.soc_addr = soc_addr
        self.capacity_kwh = capacity_kwh
        self.timeout = timeout
        self.cache_ttl = cache_ttl

        self._lock = threading.Lock()
        self._last_soc: Optional[int] = None
        self._last_ts: float = 0.0
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def read_soc(self) -> Optional[int]:
        """Return SOC (0..100) or None on failure. Cached for cache_ttl seconds."""
        with self._lock:
            now = time.time()
            if self._last_soc is not None and (now - self._last_ts) < self.cache_ttl:
                return self._last_soc
            try:
                soc = self._read_once()
                self._last_soc = soc
                self._last_ts = now
                self._last_error = None
                return soc
            except Exception as e:
                self._last_error = str(e)
                logger.warning("BMS read failed: %s", e)
                # Expire stale cache on error; callers can decide what to show.
                self._last_soc = None
                return None

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _read_once(self) -> int:
        # MBAP: tx_id(2) proto(2) length(2) unit(1) + PDU: fc(1) addr(2) count(2)
        req = struct.pack(">HHHBBHH", 1, 0, 6, self.unit, 0x03, self.soc_addr, 1)
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as s:
            s.sendall(req)
            hdr = self._recv(s, 7)
            _, _, length, _ = struct.unpack(">HHHB", hdr)
            body = self._recv(s, length - 1)
        fc = body[0]
        if fc & 0x80:
            raise IOError(f"Modbus exception code=0x{body[1]:02x}")
        byte_count = body[1]
        if byte_count < 2:
            raise IOError(f"unexpected byte_count={byte_count}")
        return struct.unpack(">H", body[2:4])[0]

    @staticmethod
    def _recv(sock: socket.socket, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("remote closed while reading")
            buf += chunk
        return buf
