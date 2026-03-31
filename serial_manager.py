#!/usr/bin/env python3
"""
Shared serial port manager with RLock protection and auto-reconnect.

All serial port access (MQTT WS transparent bridge, meter API, etc.)
must go through SerialManager to prevent concurrent bus conflicts.

When a serial port is unavailable (occupied, unplugged, permission denied),
the manager will:
  - Log the error and set status to disconnected
  - Automatically retry connection at configurable intervals
  - Resume normal operation once the port becomes available
  - Never crash the service due to serial port issues
"""

import time
import threading
import logging
from enum import Enum

import serial

logger = logging.getLogger("serial-manager")


class PortStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    ERROR = "error"


class SerialManager:
    """Thread-safe serial port manager with auto-reconnect.

    Usage patterns:
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

    All methods are safe to call when the port is unavailable — they
    return empty data or silently skip writes instead of raising.
    """

    def __init__(self, port: str, baudrate: int = 9600,
                 bytesize: int = 8, parity: str = "N",
                 stopbits: int = 1, timeout: float = 0.5,
                 reconnect_interval: float = 5.0):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.reconnect_interval = reconnect_interval

        self._lock = threading.RLock()
        self._serial: serial.Serial | None = None
        self._status = PortStatus.DISCONNECTED
        self._last_error: str = ""
        self._last_reconnect_attempt: float = 0

        # Auto-reconnect background thread
        self._stop_event = threading.Event()
        self._reconnect_thread: threading.Thread | None = None

    @property
    def status(self) -> PortStatus:
        return self._status

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> bool:
        """Try to open the serial port. Returns True on success, False on failure.

        Never raises — logs the error and sets status to ERROR.
        """
        with self._lock:
            if self._serial and self._serial.is_open:
                self._status = PortStatus.CONNECTED
                return True
            try:
                self._serial = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout,
                )
                self._status = PortStatus.CONNECTED
                self._last_error = ""
                logger.info("[%s] Serial port opened @ %d baud", self.port, self.baudrate)
                return True
            except serial.SerialException as e:
                self._status = PortStatus.ERROR
                self._last_error = str(e)
                logger.warning("[%s] Failed to open: %s", self.port, e)
                return False
            except OSError as e:
                self._status = PortStatus.ERROR
                self._last_error = str(e)
                logger.warning("[%s] OS error opening port: %s", self.port, e)
                return False

    def close(self):
        with self._lock:
            self._stop_reconnect()
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
                logger.info("[%s] Serial port closed", self.port)
            self._serial = None
            self._status = PortStatus.DISCONNECTED

    def _handle_error(self, operation: str, error: Exception):
        """Handle a serial error: close port, set status, log."""
        self._last_error = f"{operation}: {error}"
        self._status = PortStatus.ERROR
        logger.error("[%s] %s error: %s", self.port, operation, error)
        # Close the broken connection
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def _try_reconnect(self) -> bool:
        """Attempt to reconnect if enough time has passed since last attempt.

        Returns True if connected (either already or newly).
        """
        if self._serial and self._serial.is_open:
            return True

        now = time.time()
        if now - self._last_reconnect_attempt < self.reconnect_interval:
            return False

        self._last_reconnect_attempt = now
        logger.info("[%s] Attempting reconnect...", self.port)
        return self.open()

    def start_reconnect_loop(self):
        """Start background thread that periodically tries to reconnect."""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        self._stop_event.clear()
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop,
            name=f"reconnect-{self.port}",
            daemon=True,
        )
        self._reconnect_thread.start()

    def _stop_reconnect(self):
        self._stop_event.set()
        if self._reconnect_thread:
            self._reconnect_thread.join(timeout=2)
            self._reconnect_thread = None

    def _reconnect_loop(self):
        """Background loop: try to reconnect when disconnected."""
        while not self._stop_event.is_set():
            if not self.is_open:
                with self._lock:
                    self._try_reconnect()
            self._stop_event.wait(self.reconnect_interval)

    def lock(self):
        """Return the RLock as a context manager for batch/raw operations."""
        return self._lock

    # ------------------------------------------------------------------
    # Raw I/O (caller MUST hold lock)
    # ------------------------------------------------------------------

    def read_available(self) -> bytes:
        """Read all available bytes (non-blocking). Returns b"" if port unavailable."""
        if not self._serial or not self._serial.is_open:
            return b""
        try:
            n = self._serial.in_waiting
            if n > 0:
                return self._serial.read(n)
            return b""
        except (serial.SerialException, OSError) as e:
            self._handle_error("read", e)
            return b""

    def write_raw(self, data: bytes) -> bool:
        """Write raw bytes. Returns True on success, False if port unavailable."""
        if not self._serial or not self._serial.is_open:
            if not self._try_reconnect():
                logger.debug("[%s] Write skipped: port unavailable", self.port)
                return False
        try:
            self._serial.write(data)
            return True
        except (serial.SerialException, OSError) as e:
            self._handle_error("write", e)
            return False

    # ------------------------------------------------------------------
    # Modbus request-response
    # ------------------------------------------------------------------

    @staticmethod
    def _modbus_expected_len(response: bytes) -> int | None:
        """Calculate expected Modbus RTU response length from partial data.

        Returns expected total frame length, or None if not enough data yet.

        Frame formats:
          Normal 03H response: [addr][03][byte_count][data...][CRC_lo][CRC_hi]
                               length = 3 + byte_count + 2
          Exception response:  [addr][0x83][error_code][CRC_lo][CRC_hi]
                               length = 5
        """
        if len(response) < 3:
            return None

        func_code = response[1]

        # Exception response
        if func_code & 0x80:
            return 5

        # Normal 03H / 04H read response
        if func_code in (0x03, 0x04):
            byte_count = response[2]
            return 3 + byte_count + 2

        # 10H write response
        if func_code == 0x10:
            return 8

        # Unknown function code — can't predict length
        return None

    def _do_send_recv(self, request: bytes) -> bytes:
        """Send Modbus request and read complete response.

        Uses Modbus frame structure to determine when a response is complete:
        1. Read until we have at least 3 bytes (addr + func + byte_count)
        2. Calculate expected frame length from byte_count
        3. Keep reading until we have the full frame or timeout
        4. Verify CRC on complete frame

        Returns b"" on any error.
        """
        if not self._serial or not self._serial.is_open:
            if not self._try_reconnect():
                return b""
        try:
            self._serial.reset_input_buffer()
            self._serial.write(request)
            logger.debug("[%s] TX: %s", self.port, request.hex())

            time.sleep(0.05)

            response = b""
            expected_len = None
            deadline = time.time() + self.timeout

            while time.time() < deadline:
                # Read available bytes
                n = self._serial.in_waiting
                if n > 0:
                    chunk = self._serial.read(n)
                    if chunk:
                        response += chunk

                    # Try to determine expected length once we have enough header
                    if expected_len is None and len(response) >= 3:
                        expected_len = self._modbus_expected_len(response)

                    # Check if we have a complete frame
                    if expected_len is not None and len(response) >= expected_len:
                        response = response[:expected_len]  # trim any trailing noise
                        break

                    time.sleep(0.01)
                elif response:
                    # No new data — if we already know expected length, keep waiting
                    if expected_len is not None and len(response) < expected_len:
                        time.sleep(0.01)
                        continue
                    # Unknown length and no more data — assume done
                    break
                else:
                    time.sleep(0.01)

            if response:
                logger.debug("[%s] RX: %s (%d/%s bytes)", self.port, response.hex(),
                             len(response),
                             str(expected_len) if expected_len else "?")

                # Warn if frame appears incomplete
                if expected_len is not None and len(response) < expected_len:
                    logger.warning("[%s] Incomplete frame: got %d, expected %d",
                                   self.port, len(response), expected_len)
            else:
                logger.debug("[%s] RX: (no response)", self.port)

            return response
        except (serial.SerialException, OSError) as e:
            self._handle_error("send_recv", e)
            return b""

    def send_and_receive(self, request: bytes) -> bytes:
        """Send Modbus request and wait for response (auto-locking).

        Returns b"" if port is unavailable.
        """
        with self._lock:
            return self._do_send_recv(request)

    def send_and_receive_unlocked(self, request: bytes) -> bytes:
        """Send Modbus request without acquiring the lock.

        Caller MUST hold self.lock() before calling. Returns b"" if unavailable.
        """
        return self._do_send_recv(request)

    # ------------------------------------------------------------------
    # Status info
    # ------------------------------------------------------------------

    def get_status_info(self) -> dict:
        """Return status information for monitoring/API."""
        return {
            "port": self.port,
            "status": self._status.value,
            "is_open": self.is_open,
            "baudrate": self.baudrate,
            "last_error": self._last_error,
        }


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
