#!/usr/bin/env python3
"""
Unified MQTT WebSocket Serial Server + Meter API

Runs a single process that provides:
  1. MQTT WS transparent bridge for COM31, COM32, COM33
  2. REST API on port 8000 for meter data queries (COM33)

Both services share the same SerialManager instances per port,
protected by RLock to prevent concurrent bus conflicts.
"""

import signal
import sys
import threading
import time
import logging
from pathlib import Path

import yaml
import paho.mqtt.client as mqtt
import uvicorn

from serial_manager import SerialManager, create_serial_manager

logger = logging.getLogger("serial-server")


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(__file__).parent / path
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Global registry: port name -> SerialManager (shared across MQTT + API)
# ---------------------------------------------------------------------------

serial_managers: dict[str, SerialManager] = {}


def get_serial_manager(name: str) -> SerialManager | None:
    return serial_managers.get(name)


# ---------------------------------------------------------------------------
# MQTT WS Transparent Bridge
# ---------------------------------------------------------------------------

class SerialBridge:
    """Manages one serial port <-> MQTT topic pair using a shared SerialManager."""

    def __init__(self, mqtt_client: mqtt.Client, port_cfg: dict,
                 mgr: SerialManager):
        self.mqtt_client = mqtt_client
        self.cfg = port_cfg
        self.name = port_cfg["name"]
        self.topic_up = f"{port_cfg['mqtt_topic_prefix']}/up"
        self.topic_down = f"{port_cfg['mqtt_topic_prefix']}/down"
        self.mgr = mgr
        self._stop_event = threading.Event()
        self._read_thread: threading.Thread | None = None

    def open(self):
        """Open serial port and subscribe to the down topic."""
        self.mgr.open()

        # Subscribe to MQTT down topic (MQTT -> serial)
        self.mqtt_client.subscribe(self.topic_down, qos=1)
        logger.info("[%s] Subscribed to MQTT topic: %s", self.name, self.topic_down)

        # Start reading thread (serial -> MQTT)
        self._stop_event.clear()
        self._read_thread = threading.Thread(
            target=self._read_loop, name=f"serial-read-{self.name}", daemon=True
        )
        self._read_thread.start()

    def _read_loop(self):
        """Continuously read from serial and publish to MQTT up topic."""
        while not self._stop_event.is_set():
            try:
                with self.mgr.lock():
                    data = self.mgr.read_available()
                if data:
                    self.mqtt_client.publish(self.topic_up, data, qos=1)
                    logger.debug("[%s] Serial -> MQTT (%d bytes): %s",
                                 self.name, len(data), data.hex())
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.error("[%s] Read loop error: %s", self.name, e)
                self._stop_event.wait(1)

    def write(self, data: bytes):
        """Write data received from MQTT to the serial port."""
        try:
            with self.mgr.lock():
                self.mgr.write_raw(data)
            logger.debug("[%s] MQTT -> Serial (%d bytes): %s",
                         self.name, len(data), data.hex())
        except Exception as e:
            logger.error("[%s] Serial write error: %s", self.name, e)

    def close(self):
        self._stop_event.set()
        if self._read_thread:
            self._read_thread.join(timeout=2)
        logger.info("[%s] Bridge stopped", self.name)


class MQTTSerialServer:
    """Coordinates MQTT client and serial bridges using shared SerialManagers."""

    def __init__(self, config: dict):
        self.config = config
        self.bridges: dict[str, SerialBridge] = {}
        self._stop_event = threading.Event()
        self._topic_bridge_map: dict[str, SerialBridge] = {}

        # Setup MQTT client
        mqtt_cfg = config["mqtt"]
        client_id = f"{mqtt_cfg['client_id_prefix']}_{int(time.time())}"
        self.mqtt_client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport="websockets",
        )
        if mqtt_cfg.get("username"):
            self.mqtt_client.username_pw_set(
                mqtt_cfg["username"], mqtt_cfg.get("password", "")
            )

        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        self.mqtt_client.on_message = self._on_message

        # Create bridges using shared serial managers
        for port_cfg in config["serial_ports"]:
            name = port_cfg["name"]
            mgr = serial_managers[name]
            bridge = SerialBridge(self.mqtt_client, port_cfg, mgr)
            self.bridges[name] = bridge
            self._topic_bridge_map[bridge.topic_down] = bridge

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to MQTT broker via WebSocket")
            for bridge in self.bridges.values():
                try:
                    bridge.open()
                except Exception:
                    logger.error("Failed to start bridge for %s", bridge.name)
        else:
            logger.error("MQTT connection failed with code: %d", rc)

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            logger.warning("Unexpected MQTT disconnection (rc=%d), will auto-reconnect", rc)

    def _on_message(self, client, userdata, msg):
        bridge = self._topic_bridge_map.get(msg.topic)
        if bridge:
            bridge.write(msg.payload)
        else:
            logger.warning("Received message on unknown topic: %s", msg.topic)

    def start(self):
        mqtt_cfg = self.config["mqtt"]
        broker = mqtt_cfg["broker"]
        ws_port = mqtt_cfg["ws_port"]

        logger.info("Connecting to MQTT broker at ws://%s:%d ...", broker, ws_port)
        try:
            self.mqtt_client.connect(broker, ws_port, keepalive=mqtt_cfg["keepalive"])
            self.mqtt_client.loop_start()
            logger.info("MQTT WS bridge started.")
        except Exception as e:
            logger.warning("MQTT connection failed: %s (API service will still run)", e)

    def stop(self):
        logger.info("Stopping MQTT bridge...")
        for bridge in self.bridges.values():
            bridge.close()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self._stop_event.set()
        logger.info("MQTT bridge stopped.")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(config: dict):
    log_cfg = config.get("logging", {})
    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)

    handlers = [console]

    log_file = log_cfg.get("file")
    if log_file:
        file_handler = logging.FileHandler(
            Path(__file__).parent / log_file, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)


# ---------------------------------------------------------------------------
# Main — start both MQTT WS bridge + FastAPI in one process
# ---------------------------------------------------------------------------

def main():
    config = load_config()
    setup_logging(config)

    # 1. Create shared serial managers (one per port)
    for port_cfg in config["serial_ports"]:
        name = port_cfg["name"]
        mgr = create_serial_manager(port_cfg)
        serial_managers[name] = mgr
        logger.info("SerialManager created for %s (%s)", name, port_cfg["port"])

    # 2. Start MQTT WS transparent bridge (non-blocking)
    mqtt_server = MQTTSerialServer(config)
    mqtt_server.start()

    # 3. Import and start FastAPI (blocking — runs uvicorn)
    from meter_api import app  # noqa: import here to use shared serial_managers

    def _signal_handler(sig, frame):
        mqtt_server.stop()
        for mgr in serial_managers.values():
            mgr.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info("Starting API service on http://0.0.0.0:8000 ...")
    logger.info("API docs: http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    main()
