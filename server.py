#!/usr/bin/env python3
"""
Unified MQTT WebSocket Serial Server + Meter API

Runs a single process that provides:
  1. MQTT WS transparent bridge for COM31, COM32, COM33
  2. REST API on port 8000 for meter data queries (COM33)

Both services share the same SerialManager instances per port,
protected by RLock to prevent concurrent bus conflicts.
"""

import os
import signal
import sys
import threading
import time
import logging
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # Not needed when config is hardcoded

import paho.mqtt.client as mqtt

from serial_manager import SerialManager, create_serial_manager

logger = logging.getLogger("serial-server")


def _get_base_dir():
    """Get base directory — works both as script and PyInstaller .exe"""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def load_config(path: str = "config.yaml") -> dict:
    # Try external config.yaml first (next to .exe or script)
    config_path = _get_base_dir() / path
    if not config_path.exists():
        config_path = Path(sys.executable).parent / path  # next to .exe
    if config_path.exists() and yaml:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # Built-in default configuration
    return {
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
            {"name": "COM31", "port": "COM31", "baudrate": 9600, "bytesize": 8,
             "parity": "N", "stopbits": 1, "timeout": 0.1, "mqtt_topic_prefix": "serial/com31"},
            {"name": "COM32", "port": "COM32", "baudrate": 9600, "bytesize": 8,
             "parity": "N", "stopbits": 1, "timeout": 0.1, "mqtt_topic_prefix": "serial/com32"},
            {"name": "COM33", "port": "COM33", "baudrate": 9600, "bytesize": 8,
             "parity": "N", "stopbits": 1, "timeout": 0.1, "mqtt_topic_prefix": "serial/com33"},
        ],
        "parking": {"enabled": True, "poll_interval": 5},
        "logging": {"level": "INFO", "file": "serial_server.log"},
    }


# ---------------------------------------------------------------------------
# Global registry: use state.py to avoid __main__ vs module import issue
# ---------------------------------------------------------------------------

from state import serial_managers


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
        """Continuously read from serial and publish to MQTT up topic.

        Uses inter-frame gap detection: after receiving data, waits briefly
        for more bytes. If no new data arrives within the gap time, considers
        the frame complete and publishes it as one MQTT message.
        """
        # Modbus RTU inter-frame gap: 3.5 char times at 9600 baud ~ 3.6ms
        # Use 5ms as a safe gap threshold
        frame_gap = 0.005

        while not self._stop_event.is_set():
            try:
                with self.mgr.lock():
                    data = self.mgr.read_available()
                    if data:
                        # Got some data — keep reading until frame gap detected
                        while True:
                            time.sleep(frame_gap)
                            more = self.mgr.read_available()
                            if more:
                                data += more
                            else:
                                break
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
        from logging.handlers import TimedRotatingFileHandler
        # Roll the active file at local midnight so each day gets its own
        # `serial_server.log.YYYY-MM-DD`; backup_count days of history kept.
        backup_count = int(log_cfg.get("backup_count", 14))
        file_handler = TimedRotatingFileHandler(
            Path(__file__).parent / log_file,
            when="midnight",
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)

    logging.basicConfig(level=level, handlers=handlers)


# ---------------------------------------------------------------------------
# Main — start both MQTT WS bridge + Flask API in one process
# ---------------------------------------------------------------------------

def main():
    from deps import ensure_deps
    ensure_deps()

    config = load_config()
    setup_logging(config)

    # 1. Create shared serial managers (one per port)
    for port_cfg in config["serial_ports"]:
        name = port_cfg["name"]
        mgr = create_serial_manager(port_cfg)
        serial_managers[name] = mgr

        # Try initial open (non-fatal if it fails)
        if mgr.open():
            logger.info("SerialManager [%s] (%s): connected", name, port_cfg["port"])
        else:
            logger.warning("SerialManager [%s] (%s): unavailable, will auto-reconnect",
                           name, port_cfg["port"])

        # Start background reconnect loop
        mgr.start_reconnect_loop()

    # 2. Start MQTT WS transparent bridge (non-blocking) — only if enabled.
    # The bridge's _read_loop continuously reads each serial port to publish
    # to MQTT topics; when this project doesn't actually use the MQTT side,
    # disabling it removes a constant background consumer of the bus and
    # noticeably reduces incomplete-frame errors.
    if config.get("mqtt", {}).get("enabled", True):
        mqtt_server = MQTTSerialServer(config)
        mqtt_server.start()
    else:
        mqtt_server = None
        logger.info("MQTT bridge disabled (config: mqtt.enabled=false)")

    # 3. Import and start Flask API (blocking)
    from meter_api import (app, init_bms, init_meter_cache, init_parking_cache,
                           init_odoo_cache, init_yearly_cache)
    init_bms(config)
    cache_cfg = config.get("cache", {})
    init_meter_cache(scan_interval_s=float(cache_cfg.get("meter_interval", 2.0)))
    init_parking_cache(scan_interval_s=float(cache_cfg.get("parking_interval", 2.0)))
    init_odoo_cache(ttl_s=float(cache_cfg.get("odoo_ttl", 5.0)))
    init_yearly_cache(refresh_interval_s=float(cache_cfg.get("yearly_refresh", 3600.0)))

    def _signal_handler(sig, frame):
        print("\n正在关闭...")
        if mqtt_server is not None:
            try:
                mqtt_server.stop()
            except Exception:
                pass
        for mgr in serial_managers.values():
            try:
                mgr.close()
            except Exception:
                pass
        os._exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Windows: Ctrl+C needs special handling for Flask threaded mode
    if sys.platform == 'win32':
        import atexit
        atexit.register(lambda: os._exit(0))

    api_port = config.get("api", {}).get("port", 8000)
    logger.info("Starting API service on http://0.0.0.0:%d ...", api_port)
    app.run(host="0.0.0.0", port=api_port, threaded=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已停止")
    except Exception as e:
        print("\n" + "=" * 50)
        print(f"  启动失败: {e}")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        input("\n按回车键退出...")
        sys.exit(1)
