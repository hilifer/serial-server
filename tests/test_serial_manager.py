"""Unit tests for shared SerialManager."""

import threading
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from serial_manager import SerialManager, create_serial_manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mgr():
    return SerialManager("COM33", baudrate=9600)


# ---------------------------------------------------------------------------
# Tests: init
# ---------------------------------------------------------------------------

class TestSerialManagerInit:
    def test_defaults(self):
        mgr = SerialManager("COM33")
        assert mgr.port == "COM33"
        assert mgr.baudrate == 9600
        assert mgr.bytesize == 8
        assert mgr.parity == "N"
        assert mgr.stopbits == 1
        assert mgr.timeout == 0.5

    def test_custom_params(self):
        mgr = SerialManager("COM31", baudrate=115200, parity="E", timeout=1.0)
        assert mgr.baudrate == 115200
        assert mgr.parity == "E"
        assert mgr.timeout == 1.0

    def test_not_open_initially(self, mgr):
        assert mgr.is_open is False


# ---------------------------------------------------------------------------
# Tests: open / close
# ---------------------------------------------------------------------------

class TestSerialManagerOpenClose:
    @patch("serial_manager.serial.Serial")
    def test_open_creates_connection(self, mock_serial_cls, mgr):
        mgr.open()
        mock_serial_cls.assert_called_once_with(
            port="COM33",
            baudrate=9600,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.5,
        )

    @patch("serial_manager.serial.Serial")
    def test_open_idempotent(self, mock_serial_cls, mgr):
        mock_serial_cls.return_value.is_open = True
        mgr.open()
        mgr.open()  # second call should not create another
        mock_serial_cls.assert_called_once()

    @patch("serial_manager.serial.Serial")
    def test_close(self, mock_serial_cls, mgr):
        mock_serial_cls.return_value.is_open = True
        mgr.open()
        mgr.close()
        mgr._serial.close.assert_called_once()

    def test_close_when_not_open(self, mgr):
        mgr.close()  # should not raise


# ---------------------------------------------------------------------------
# Tests: lock
# ---------------------------------------------------------------------------

class TestSerialManagerLock:
    def test_lock_is_rlock(self, mgr):
        assert isinstance(mgr._lock, type(threading.RLock()))

    def test_lock_context_manager(self, mgr):
        with mgr.lock():
            pass  # should not deadlock

    def test_lock_reentrant(self, mgr):
        with mgr.lock():
            with mgr.lock():
                pass  # RLock allows reentrant locking


# ---------------------------------------------------------------------------
# Tests: read_available / write_raw
# ---------------------------------------------------------------------------

class TestSerialManagerRawIO:
    @patch("serial_manager.serial.Serial")
    def test_read_available_with_data(self, mock_serial_cls, mgr):
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mock_conn.in_waiting = 5
        mock_conn.read.return_value = b"hello"
        mgr._serial = mock_conn

        data = mgr.read_available()
        assert data == b"hello"
        mock_conn.read.assert_called_once_with(5)

    @patch("serial_manager.serial.Serial")
    def test_read_available_empty(self, mock_serial_cls, mgr):
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mock_conn.in_waiting = 0
        mgr._serial = mock_conn

        data = mgr.read_available()
        assert data == b""

    def test_read_available_not_open(self, mgr):
        assert mgr.read_available() == b""

    @patch("serial_manager.serial.Serial")
    def test_write_raw(self, mock_serial_cls, mgr):
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mgr._serial = mock_conn

        mgr.write_raw(b"\x01\x02\x03")
        mock_conn.write.assert_called_once_with(b"\x01\x02\x03")


# ---------------------------------------------------------------------------
# Tests: send_and_receive
# ---------------------------------------------------------------------------

class TestSerialManagerModbus:
    @patch("serial_manager.serial.Serial")
    def test_send_and_receive_auto_locks(self, mock_serial_cls, mgr):
        mock_conn = MagicMock()
        mock_conn.is_open = True
        expected = b"\x01\x03\x02\x00\x00\xB8\x44"
        # First read returns data, second read returns empty to break loop
        mock_conn.read.side_effect = [expected, b""]
        call_count = 0
        def fake_in_waiting():
            nonlocal call_count
            call_count += 1
            return 7 if call_count == 1 else 0
        type(mock_conn).in_waiting = PropertyMock(side_effect=fake_in_waiting)
        mgr._serial = mock_conn

        resp = mgr.send_and_receive(b"\x01\x03\x00\x00\x00\x01")
        assert resp == expected
        mock_conn.write.assert_called_once()

    @patch("serial_manager.serial.Serial")
    def test_send_and_receive_unlocked(self, mock_serial_cls, mgr):
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mock_conn.read.side_effect = [b"reply", b""]
        call_count = 0
        def fake_in_waiting():
            nonlocal call_count
            call_count += 1
            return 5 if call_count == 1 else 0
        type(mock_conn).in_waiting = PropertyMock(side_effect=fake_in_waiting)
        mgr._serial = mock_conn

        with mgr.lock():
            resp = mgr.send_and_receive_unlocked(b"request")
        assert resp == b"reply"

    @patch("serial_manager.serial.Serial")
    def test_batch_locking_prevents_interleave(self, mock_serial_cls):
        """Verify that batch lock holds across multiple send_and_receive_unlocked calls."""
        mgr = SerialManager("COM33")
        mock_conn = MagicMock()
        mock_conn.is_open = True
        mock_conn.in_waiting = 0
        mock_conn.read.return_value = b""
        mgr._serial = mock_conn

        acquired_during_batch = threading.Event()

        def try_acquire():
            result = mgr._lock.acquire(timeout=0.1)
            if result:
                acquired_during_batch.set()
                mgr._lock.release()

        with mgr.lock():
            # Another thread tries to acquire during batch
            t = threading.Thread(target=try_acquire)
            t.start()
            mgr.send_and_receive_unlocked(b"\x01")
            mgr.send_and_receive_unlocked(b"\x02")
            t.join()

        # The other thread should NOT have acquired the lock during batch
        assert not acquired_during_batch.is_set()


# ---------------------------------------------------------------------------
# Tests: create_serial_manager
# ---------------------------------------------------------------------------

class TestCreateSerialManager:
    def test_from_config(self):
        cfg = {
            "port": "COM33",
            "baudrate": 9600,
            "bytesize": 8,
            "parity": "N",
            "stopbits": 1,
            "timeout": 0.5,
        }
        mgr = create_serial_manager(cfg)
        assert mgr.port == "COM33"
        assert mgr.baudrate == 9600

    def test_from_config_defaults(self):
        cfg = {"port": "/dev/ttyUSB0", "baudrate": 115200}
        mgr = create_serial_manager(cfg)
        assert mgr.bytesize == 8
        assert mgr.parity == "N"
        assert mgr.stopbits == 1
        assert mgr.timeout == 0.5
