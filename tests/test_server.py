"""Unit tests for unified MQTT WS Serial Server."""

import threading
import time
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import SerialBridge, MQTTSerialServer, load_config, setup_logging
from serial_manager import SerialManager
import server as server_module


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
def mock_serial_mgr():
    mgr = MagicMock(spec=SerialManager)
    mgr.lock.return_value = threading.RLock()
    mgr.read_available.return_value = b""
    return mgr


@pytest.fixture
def bridge(mock_mqtt_client, port_cfg, mock_serial_mgr):
    return SerialBridge(mock_mqtt_client, port_cfg, mock_serial_mgr)


@pytest.fixture(autouse=True)
def setup_serial_managers():
    """Ensure server.serial_managers has entries for tests that create MQTTSerialServer."""
    original = server_module.serial_managers.copy()
    for port_cfg in SAMPLE_CONFIG["serial_ports"]:
        mgr = MagicMock(spec=SerialManager)
        mgr.lock.return_value = threading.RLock()
        mgr.read_available.return_value = b""
        server_module.serial_managers[port_cfg["name"]] = mgr
    yield
    server_module.serial_managers.clear()
    server_module.serial_managers.update(original)


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

    def test_uses_shared_manager(self, bridge, mock_serial_mgr):
        assert bridge.mgr is mock_serial_mgr


# ---------------------------------------------------------------------------
# Tests: SerialBridge.open
# ---------------------------------------------------------------------------

class TestSerialBridgeOpen:
    def test_open_calls_mgr_open(self, bridge, mock_serial_mgr):
        bridge.open()
        mock_serial_mgr.open.assert_called_once()

    def test_open_subscribes_mqtt_topic(self, bridge):
        bridge.open()
        bridge.mqtt_client.subscribe.assert_called_once_with(
            "serial/com31/down", qos=1
        )

    def test_open_starts_read_thread(self, bridge):
        bridge.open()
        assert bridge._read_thread is not None
        assert bridge._read_thread.is_alive()
        # Cleanup
        bridge._stop_event.set()
        bridge._read_thread.join(timeout=1)


# ---------------------------------------------------------------------------
# Tests: SerialBridge.write
# ---------------------------------------------------------------------------

class TestSerialBridgeWrite:
    def test_write_calls_mgr_write_raw(self, bridge, mock_serial_mgr):
        bridge.write(b"\x01\x02\x03")
        mock_serial_mgr.write_raw.assert_called_once_with(b"\x01\x02\x03")

    def test_write_handles_exception(self, bridge, mock_serial_mgr):
        mock_serial_mgr.write_raw.side_effect = Exception("write error")
        bridge.write(b"\x01")  # should not raise


# ---------------------------------------------------------------------------
# Tests: SerialBridge._read_loop
# ---------------------------------------------------------------------------

class TestSerialBridgeReadLoop:
    def test_read_loop_publishes_to_mqtt(self, bridge, mock_serial_mgr):
        """Simulate serial data arriving and verify MQTT publish."""
        call_count = 0

        def fake_read():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b"hello"
            return b""

        mock_serial_mgr.read_available.side_effect = fake_read

        def stop_after_publish(*args, **kwargs):
            bridge._stop_event.set()

        bridge.mqtt_client.publish.side_effect = stop_after_publish

        bridge._stop_event.clear()
        bridge._read_loop()

        bridge.mqtt_client.publish.assert_called_once_with(
            "serial/com31/up", b"hello", qos=1
        )

    def test_read_loop_stops_on_event(self, bridge):
        bridge._stop_event.set()
        bridge._read_loop()  # Should return immediately


# ---------------------------------------------------------------------------
# Tests: SerialBridge.close
# ---------------------------------------------------------------------------

class TestSerialBridgeClose:
    def test_close_sets_stop_event(self, bridge):
        bridge.close()
        assert bridge._stop_event.is_set()

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
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        assert len(srv.bridges) == 3
        assert set(srv.bridges.keys()) == {"COM31", "COM32", "COM33"}

    @patch("server.mqtt.Client")
    def test_bridges_use_shared_managers(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        for name, bridge in srv.bridges.items():
            assert bridge.mgr is server_module.serial_managers[name]

    @patch("server.mqtt.Client")
    def test_topic_bridge_map(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        assert "serial/com31/down" in srv._topic_bridge_map
        assert "serial/com32/down" in srv._topic_bridge_map
        assert "serial/com33/down" in srv._topic_bridge_map

    @patch("server.mqtt.Client")
    def test_mqtt_client_uses_websockets(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        mock_mqtt_cls.assert_called_once()
        assert "websockets" in str(mock_mqtt_cls.call_args)

    @patch("server.mqtt.Client")
    def test_mqtt_auth_when_username_set(self, mock_mqtt_cls):
        config = {**SAMPLE_CONFIG,
                  "mqtt": {**SAMPLE_CONFIG["mqtt"],
                           "username": "user", "password": "pass"}}
        srv = MQTTSerialServer(config)
        srv.mqtt_client.username_pw_set.assert_called_once_with("user", "pass")

    @patch("server.mqtt.Client")
    def test_mqtt_no_auth_when_empty(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        srv.mqtt_client.username_pw_set.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: MQTTSerialServer callbacks
# ---------------------------------------------------------------------------

class TestMQTTSerialServerCallbacks:
    @patch("server.mqtt.Client")
    def test_on_message_routes_to_bridge(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        srv.bridges["COM31"].write = MagicMock()

        msg = MagicMock()
        msg.topic = "serial/com31/down"
        msg.payload = b"\xAA\xBB"

        srv._on_message(None, None, msg)
        srv.bridges["COM31"].write.assert_called_once_with(b"\xAA\xBB")

    @patch("server.mqtt.Client")
    def test_on_message_unknown_topic(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        msg = MagicMock()
        msg.topic = "serial/com99/down"
        msg.payload = b"\x00"
        srv._on_message(None, None, msg)  # Should not raise

    @patch("server.mqtt.Client")
    def test_on_connect_success_opens_bridges(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        for bridge in srv.bridges.values():
            bridge.open = MagicMock()
        srv._on_connect(None, None, None, 0)
        for bridge in srv.bridges.values():
            bridge.open.assert_called_once()

    @patch("server.mqtt.Client")
    def test_on_connect_failure_does_not_open(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        for bridge in srv.bridges.values():
            bridge.open = MagicMock()
        srv._on_connect(None, None, None, 5)
        for bridge in srv.bridges.values():
            bridge.open.assert_not_called()

    @patch("server.mqtt.Client")
    def test_on_connect_tolerates_bridge_failure(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        bridges = list(srv.bridges.values())
        bridges[0].open = MagicMock(side_effect=Exception("fail"))
        bridges[1].open = MagicMock()
        bridges[2].open = MagicMock()

        srv._on_connect(None, None, None, 0)
        bridges[1].open.assert_called_once()
        bridges[2].open.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: MQTTSerialServer start/stop
# ---------------------------------------------------------------------------

class TestMQTTSerialServerStartStop:
    @patch("server.mqtt.Client")
    def test_stop_closes_all_bridges(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        for bridge in srv.bridges.values():
            bridge.close = MagicMock()
        srv.stop()
        for bridge in srv.bridges.values():
            bridge.close.assert_called_once()

    @patch("server.mqtt.Client")
    def test_stop_disconnects_mqtt(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        for bridge in srv.bridges.values():
            bridge.close = MagicMock()
        srv.stop()
        srv.mqtt_client.loop_stop.assert_called_once()
        srv.mqtt_client.disconnect.assert_called_once()

    @patch("server.mqtt.Client")
    def test_start_connects_to_broker(self, mock_mqtt_cls):
        srv = MQTTSerialServer(SAMPLE_CONFIG)
        srv.start()
        srv.mqtt_client.connect.assert_called_once_with(
            "localhost", 9001, keepalive=60
        )


# ---------------------------------------------------------------------------
# Tests: SerialManager shared instance
# ---------------------------------------------------------------------------

class TestSerialManagerShared:
    def test_serial_managers_dict_exists(self):
        assert isinstance(server_module.serial_managers, dict)

    def test_get_serial_manager(self):
        mgr = server_module.serial_managers.get("COM31")
        assert mgr is not None

    def test_get_serial_manager_missing(self):
        assert server_module.serial_managers.get("COM99") is None
