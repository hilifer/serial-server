"""Unit tests for MQTT WebSocket Serial Server."""

import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import SerialBridge, MQTTSerialServer, load_config, setup_logging


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PORT_CFG = {
    "name": "COM31",
    "port": "COM31",
    "baudrate": 9600,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout": 0.1,
    "mqtt_topic_prefix": "serial/com31",
}

SAMPLE_CONFIG = {
    "mqtt": {
        "broker": "localhost",
        "port": 1883,
        "ws_port": 9001,
        "username": "",
        "password": "",
        "client_id_prefix": "serial-server",
        "keepalive": 60,
    },
    "serial_ports": [
        SAMPLE_PORT_CFG,
        {**SAMPLE_PORT_CFG, "name": "COM32", "port": "COM32",
         "mqtt_topic_prefix": "serial/com32"},
        {**SAMPLE_PORT_CFG, "name": "COM33", "port": "COM33",
         "mqtt_topic_prefix": "serial/com33"},
    ],
    "logging": {"level": "DEBUG", "file": ""},
}


@pytest.fixture
def mock_mqtt_client():
    client = MagicMock()
    client.subscribe = MagicMock()
    client.publish = MagicMock()
    return client


@pytest.fixture
def port_cfg():
    return SAMPLE_PORT_CFG.copy()


@pytest.fixture
def bridge(mock_mqtt_client, port_cfg):
    return SerialBridge(mock_mqtt_client, port_cfg)


# ---------------------------------------------------------------------------
# Tests: load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_load_config_returns_dict(self):
        config = load_config()
        assert isinstance(config, dict)
        assert "mqtt" in config
        assert "serial_ports" in config

    def test_load_config_has_three_ports(self):
        config = load_config()
        assert len(config["serial_ports"]) == 3

    def test_load_config_port_names(self):
        config = load_config()
        names = [p["name"] for p in config["serial_ports"]]
        assert names == ["COM31", "COM32", "COM33"]

    def test_load_config_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("nonexistent.yaml")


# ---------------------------------------------------------------------------
# Tests: setup_logging
# ---------------------------------------------------------------------------

class TestSetupLogging:
    def test_setup_logging_no_error(self):
        setup_logging({"logging": {"level": "DEBUG"}})

    def test_setup_logging_empty_config(self):
        setup_logging({})


# ---------------------------------------------------------------------------
# Tests: SerialBridge init
# ---------------------------------------------------------------------------

class TestSerialBridgeInit:
    def test_topic_up(self, bridge):
        assert bridge.topic_up == "serial/com31/up"

    def test_topic_down(self, bridge):
        assert bridge.topic_down == "serial/com31/down"

    def test_name(self, bridge):
        assert bridge.name == "COM31"

    def test_serial_conn_initially_none(self, bridge):
        assert bridge.serial_conn is None


# ---------------------------------------------------------------------------
# Tests: SerialBridge.open
# ---------------------------------------------------------------------------

class TestSerialBridgeOpen:
    @patch("server.serial.Serial")
    def test_open_creates_serial_connection(self, mock_serial_cls, bridge):
        bridge.open()
        mock_serial_cls.assert_called_once_with(
            port="COM31",
            baudrate=9600,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.1,
        )
        assert bridge.serial_conn is not None

    @patch("server.serial.Serial")
    def test_open_subscribes_mqtt_topic(self, mock_serial_cls, bridge):
        bridge.open()
        bridge.mqtt_client.subscribe.assert_called_once_with(
            "serial/com31/down", qos=1
        )

    @patch("server.serial.Serial")
    def test_open_starts_read_thread(self, mock_serial_cls, bridge):
        bridge.open()
        assert bridge._read_thread is not None
        assert bridge._read_thread.is_alive()
        # Cleanup
        bridge._stop_event.set()
        bridge._read_thread.join(timeout=1)

    @patch("server.serial.Serial", side_effect=Exception("port not found"))
    def test_open_raises_on_serial_failure(self, mock_serial_cls, bridge):
        with pytest.raises(Exception, match="port not found"):
            bridge.open()


# ---------------------------------------------------------------------------
# Tests: SerialBridge.write
# ---------------------------------------------------------------------------

class TestSerialBridgeWrite:
    def test_write_sends_data_to_serial(self, bridge):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        bridge.serial_conn = mock_serial

        bridge.write(b"\x01\x02\x03")
        mock_serial.write.assert_called_once_with(b"\x01\x02\x03")

    def test_write_noop_when_not_open(self, bridge):
        bridge.serial_conn = None
        bridge.write(b"\x01\x02\x03")  # should not raise

    def test_write_noop_when_closed(self, bridge):
        mock_serial = MagicMock()
        mock_serial.is_open = False
        bridge.serial_conn = mock_serial

        bridge.write(b"\x01\x02\x03")
        mock_serial.write.assert_not_called()

    def test_write_handles_serial_exception(self, bridge):
        import serial as pyserial
        mock_serial = MagicMock()
        mock_serial.is_open = True
        mock_serial.write.side_effect = pyserial.SerialException("write error")
        bridge.serial_conn = mock_serial

        bridge.write(b"\x01")  # should not raise


# ---------------------------------------------------------------------------
# Tests: SerialBridge._read_loop
# ---------------------------------------------------------------------------

class TestSerialBridgeReadLoop:
    @patch("server.serial.Serial")
    def test_read_loop_publishes_to_mqtt(self, mock_serial_cls, bridge):
        """Simulate serial data arriving and verify MQTT publish."""
        mock_serial = MagicMock()
        # First call: data available; second call: stop
        mock_serial.in_waiting = PropertyMock(side_effect=[5, 0])
        type(mock_serial).in_waiting = PropertyMock(side_effect=[5, 0, 0])
        mock_serial.read.return_value = b"hello"
        bridge.serial_conn = mock_serial

        # Run one iteration then stop
        def stop_after_publish(*args, **kwargs):
            bridge._stop_event.set()

        bridge.mqtt_client.publish.side_effect = stop_after_publish

        bridge._stop_event.clear()
        bridge._read_loop()

        bridge.mqtt_client.publish.assert_called_once_with(
            "serial/com31/up", b"hello", qos=1
        )

    def test_read_loop_stops_on_event(self, bridge):
        bridge.serial_conn = MagicMock()
        type(bridge.serial_conn).in_waiting = PropertyMock(return_value=0)
        bridge._stop_event.set()
        # Should return immediately
        bridge._read_loop()


# ---------------------------------------------------------------------------
# Tests: SerialBridge.close
# ---------------------------------------------------------------------------

class TestSerialBridgeClose:
    def test_close_sets_stop_event(self, bridge):
        bridge.close()
        assert bridge._stop_event.is_set()

    def test_close_closes_serial(self, bridge):
        mock_serial = MagicMock()
        mock_serial.is_open = True
        bridge.serial_conn = mock_serial

        bridge.close()
        mock_serial.close.assert_called_once()

    def test_close_joins_thread(self, bridge):
        mock_thread = MagicMock()
        bridge._read_thread = mock_thread

        bridge.close()
        mock_thread.join.assert_called_once_with(timeout=2)


# ---------------------------------------------------------------------------
# Tests: MQTTSerialServer
# ---------------------------------------------------------------------------

class TestMQTTSerialServer:
    @patch("server.mqtt.Client")
    def test_creates_three_bridges(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)
        assert len(server.bridges) == 3
        assert set(server.bridges.keys()) == {"COM31", "COM32", "COM33"}

    @patch("server.mqtt.Client")
    def test_topic_bridge_map(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)
        assert "serial/com31/down" in server._topic_bridge_map
        assert "serial/com32/down" in server._topic_bridge_map
        assert "serial/com33/down" in server._topic_bridge_map

    @patch("server.mqtt.Client")
    def test_mqtt_client_uses_websockets(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)
        mock_mqtt_cls.assert_called_once()
        args, kwargs = mock_mqtt_cls.call_args
        assert kwargs.get("transport") == "websockets" or \
               (len(args) >= 3 and args[2] == "websockets") or \
               "websockets" in str(mock_mqtt_cls.call_args)

    @patch("server.mqtt.Client")
    def test_mqtt_auth_when_username_set(self, mock_mqtt_cls):
        config = SAMPLE_CONFIG.copy()
        config["mqtt"] = {**config["mqtt"], "username": "user", "password": "pass"}
        server = MQTTSerialServer(config)
        server.mqtt_client.username_pw_set.assert_called_once_with("user", "pass")

    @patch("server.mqtt.Client")
    def test_mqtt_no_auth_when_empty(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)
        server.mqtt_client.username_pw_set.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: MQTTSerialServer callbacks
# ---------------------------------------------------------------------------

class TestMQTTSerialServerCallbacks:
    @patch("server.mqtt.Client")
    def test_on_message_routes_to_bridge(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)

        # Mock write on bridge
        server.bridges["COM31"].write = MagicMock()

        msg = MagicMock()
        msg.topic = "serial/com31/down"
        msg.payload = b"\xAA\xBB"

        server._on_message(None, None, msg)
        server.bridges["COM31"].write.assert_called_once_with(b"\xAA\xBB")

    @patch("server.mqtt.Client")
    def test_on_message_unknown_topic(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)

        msg = MagicMock()
        msg.topic = "serial/com99/down"
        msg.payload = b"\x00"

        # Should not raise
        server._on_message(None, None, msg)

    @patch("server.mqtt.Client")
    def test_on_connect_success_opens_bridges(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)

        for bridge in server.bridges.values():
            bridge.open = MagicMock()

        server._on_connect(None, None, None, 0)

        for bridge in server.bridges.values():
            bridge.open.assert_called_once()

    @patch("server.mqtt.Client")
    def test_on_connect_failure_does_not_open(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)

        for bridge in server.bridges.values():
            bridge.open = MagicMock()

        server._on_connect(None, None, None, 5)  # rc != 0

        for bridge in server.bridges.values():
            bridge.open.assert_not_called()

    @patch("server.mqtt.Client")
    def test_on_connect_tolerates_bridge_failure(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)

        # First bridge fails, others should still open
        bridges = list(server.bridges.values())
        bridges[0].open = MagicMock(side_effect=Exception("fail"))
        bridges[1].open = MagicMock()
        bridges[2].open = MagicMock()

        server._on_connect(None, None, None, 0)

        bridges[1].open.assert_called_once()
        bridges[2].open.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: MQTTSerialServer start/stop
# ---------------------------------------------------------------------------

class TestMQTTSerialServerStartStop:
    @patch("server.mqtt.Client")
    def test_stop_closes_all_bridges(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)
        for bridge in server.bridges.values():
            bridge.close = MagicMock()

        server.stop()

        for bridge in server.bridges.values():
            bridge.close.assert_called_once()

    @patch("server.mqtt.Client")
    def test_stop_disconnects_mqtt(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)
        for bridge in server.bridges.values():
            bridge.close = MagicMock()

        server.stop()
        server.mqtt_client.loop_stop.assert_called_once()
        server.mqtt_client.disconnect.assert_called_once()

    @patch("server.mqtt.Client")
    def test_start_connects_to_broker(self, mock_mqtt_cls):
        server = MQTTSerialServer(SAMPLE_CONFIG)

        # Make start() return immediately
        def set_stop(*a, **kw):
            server._stop_event.set()

        server.mqtt_client.loop_start.side_effect = set_stop

        server.start()
        server.mqtt_client.connect.assert_called_once_with(
            "localhost", 9001, keepalive=60
        )
