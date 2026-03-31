#!/usr/bin/env python3
"""
Shared serial port manager with RLock protection.

All serial port access (MQTT WS transparent bridge, meter API, etc.)
must go through SerialManager to prevent concurrent bus conflicts.
"""

import time
import threading
import logging

import serial

logger = logging.getLogger("serial-manager")


class SerialManager:
    """Thread-safe serial port manager.

    Supports three usage patterns:
      1. Single Modbus request-response:
             response = mgr.send_and_receive(request)

      2. Batch Modbus requests (atomic, no interleaving):
             with mgr.lock():
                 mgr.send_and_receive_unlocked(req1)
                 mgr.send_and_receive_unlocked(req2)

      3. Raw read/write for transparent bridge:
             with mgr.lock():
                 mgr.write_raw(data)
                 data = mgr.read_available()
    """

    def __init__(self, port: str, baudrate: int = 9600,
                 bytesize: int = 8, parity: str = "N",
                 stopbits: int = 1, timeout: float = 0.5):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self._lock = threading.RLock()
        self._serial: serial.Serial | None = None

    def open(self):
        with self._lock:
            if self._serial and self._serial.is_open:
                return
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
            )
            logger.info("Serial port %s opened @ %d baud", self.port, self.baudrate)

    def close(self):
        with self._lock:
            if self._serial and self._serial.is_open:
                self._serial.close()
                logger.info("Serial port %s closed", self.port)

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def lock(self):
        """Return the RLock as a context manager for batch/raw operations."""
        return self._lock

    # ------------------------------------------------------------------
    # Raw I/O (caller MUST hold lock)
    # ------------------------------------------------------------------

    def read_available(self) -> bytes:
        """Read all available bytes from the serial port (non-blocking).

        Caller MUST hold self.lock().
        """
        if not self._serial or not self._serial.is_open:
            return b""
        n = self._serial.in_waiting
        if n > 0:
            return self._serial.read(n)
        return b""

    def write_raw(self, data: bytes):
        """Write raw bytes to the serial port.

        Caller MUST hold self.lock().
        """
        if not self._serial or not self._serial.is_open:
            self.open()
        self._serial.write(data)

    # ------------------------------------------------------------------
    # Modbus request-response
    # ------------------------------------------------------------------

    def _do_send_recv(self, request: bytes) -> bytes:
        """Internal: send Modbus request and read response (caller must hold lock)."""
        if not self._serial or not self._serial.is_open:
            self.open()
        self._serial.reset_input_buffer()
        self._serial.write(request)
        logger.debug("[%s] TX: %s", self.port, request.hex())

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

        logger.debug("[%s] RX: %s", self.port, response.hex())
        return response

    def send_and_receive(self, request: bytes) -> bytes:
        """Send a Modbus request and wait for response (auto-locking)."""
        with self._lock:
            return self._do_send_recv(request)

    def send_and_receive_unlocked(self, request: bytes) -> bytes:
        """Send a Modbus request without acquiring the lock.

        Caller MUST hold self.lock() before calling.
        """
        return self._do_send_recv(request)


def create_serial_manager(port_cfg: dict) -> SerialManager:
    """Create a SerialManager from a config.yaml port entry."""
    return SerialManager(
        port=port_cfg["port"],
        baudrate=port_cfg["baudrate"],
        bytesize=port_cfg.get("bytesize", 8),
        parity=port_cfg.get("parity", "N"),
        stopbits=port_cfg.get("stopbits", 1),
        timeout=port_cfg.get("timeout", 0.5),
    )
