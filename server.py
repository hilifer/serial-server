#!/usr/bin/env python3
"""
MQTT WebSocket Serial Transparent Transmission Server

Bridges serial ports (COM31, COM32, COM33) with MQTT over WebSocket.
Each serial port maps to an MQTT topic pair:
  - serial/<port>/up   : serial -> MQTT (data read from serial)
  - serial/<port>/down : MQTT -> serial (data written to serial)
"""

import signal
import sys
import threading
import time
import logging
from pathlib import Path

import yaml
import serial
import paho.mqtt.client as mqtt

logger = logging.getLogger("serial-server")


def load_config(path: str = "config.yaml") -> dict:
    config_path = Path(__file__).parent / path
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class SerialBridge:
    """Manages one serial port <-> MQTT topic pair."""

    def __init__(self, mqtt_client: mqtt.Client, port_cfg: dict):
        self.mqtt_client = mqtt_client
        self.cfg = port_cfg
        self.name = port_cfg["name"]
        self.topic_up = f"{port_cfg['mqtt_topic_prefix']}/up"
        self.topic_down = f"{port_cfg['mqtt_topic_prefix']}/down"
        self.serial_conn: serial.Serial | None = None
        self._stop_event = threading.Event()
        self._read_thread: threading.Thread | None = None

    def open(self):
        """Open serial port and subscribe to the down topic."""
        try:
            self.serial_conn = serial.Serial(
                port=self.cfg["port"],
                baudrate=self.cfg["baudrate"],
                bytesize=self.cfg["bytesize"],
                parity=self.cfg["parity"],
                stopbits=self.cfg["stopbits"],
                timeout=self.cfg["timeout"],
            )
            logger.info("[%s] Serial port opened: %s @ %d baud",
                        self.name, self.cfg["port"], self.cfg["baudrate"])
        except serial.SerialException as e:
            logger.error("[%s] Failed to open serial port %s: %s",
                         self.name, self.cfg["port"], e)
            raise

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
                if self.serial_conn and self.serial_conn.in_waiting > 0:
                    data = self.serial_conn.read(self.serial_conn.in_waiting)
                    if data:
                        self.mqtt_client.publish(self.topic_up, data, qos=1)
                        logger.debug("[%s] Serial -> MQTT (%d bytes): %s",
                                     self.name, len(data), data.hex())
                else:
                    time.sleep(0.01)
            except serial.SerialException as e:
                logger.error("[%s] Serial read error: %s", self.name, e)
                self._stop_event.wait(1)
            except Exception as e:
                logger.error("[%s] Unexpected error in read loop: %s", self.name, e)
                self._stop_event.wait(1)

    def write(self, data: bytes):
        """Write data received from MQTT to the serial port."""
        if self.serial_conn and self.serial_conn.is_open:
            try:
                self.serial_conn.write(data)
                logger.debug("[%s] MQTT -> Serial (%d bytes): %s",
                             self.name, len(data), data.hex())
            except serial.SerialException as e:
                logger.error("[%s] Serial write error: %s", self.name, e)

    def close(self):
        self._stop_event.set()
        if self._read_thread:
            self._read_thread.join(timeout=2)
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            logger.info("[%s] Serial port closed", self.name)


class MQTTSerialServer:
    """Main server coordinating MQTT client and serial bridges."""

    def __init__(self, config: dict):
        self.config = config
        self.bridges: dict[str, SerialBridge] = {}
        self._stop_event = threading.Event()

        # Build topic -> bridge lookup
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

        # Create bridges
        for port_cfg in config["serial_ports"]:
            bridge = SerialBridge(self.mqtt_client, port_cfg)
            self.bridges[bridge.name] = bridge
            self._topic_bridge_map[bridge.topic_down] = bridge

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to MQTT broker via WebSocket")
            # Open all serial ports and subscribe topics
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
        self.mqtt_client.connect(broker, ws_port, keepalive=mqtt_cfg["keepalive"])
        self.mqtt_client.loop_start()

        logger.info("Server started. Press Ctrl+C to stop.")
        self._stop_event.wait()

    def stop(self):
        logger.info("Shutting down...")
        for bridge in self.bridges.values():
            bridge.close()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self._stop_event.set()
        logger.info("Server stopped.")


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


def main():
    config = load_config()
    setup_logging(config)

    server = MQTTSerialServer(config)

    def _signal_handler(sig, frame):
        server.stop()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        server.start()
    except KeyboardInterrupt:
        server.stop()


if __name__ == "__main__":
    main()
