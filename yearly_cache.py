#!/usr/bin/env python3
"""Background yearly-energy cache.

Unlike MeterCache which scans every couple seconds, YearlyCache runs
a heavy 12-months-per-meter scan on a long interval (default 1 hour).
Energy registers don't change rapidly — yearly totals only really
update as the current month accumulates — so refreshing hourly is
more than enough, and it keeps the RS485 bus free most of the time.

On startup, fires a first scan immediately so the /yearly endpoint
has data within the first few minutes instead of waiting an hour.
"""
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("yearly-cache")


class YearlyCache:
    def __init__(self, meter_list, reader_fn: Callable,
                 serial_mgr_provider: Callable,
                 refresh_interval_s: float = 3600.0):
        """
        meter_list: MeterInfo objects to poll (scan order).
        reader_fn: function(serial_mgr, meter) -> response_dict. Handles its own locking.
        serial_mgr_provider: callable returning the shared COM33 SerialManager.
        refresh_interval_s: seconds between full refresh cycles (default 1h).
        """
        self._meters = list(meter_list)
        self._read = reader_fn
        self._get_ser = serial_mgr_provider
        self._interval = refresh_interval_s
        self._cache: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="yearly-cache", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def get(self, addr: int) -> Optional[dict]:
        with self._lock:
            entry = self._cache.get(addr)
            return dict(entry) if entry else None

    def _loop(self):
        logger.info("YearlyCache loop started (%d meters, refresh=%.0fs)",
                    len(self._meters), self._interval)
        # First pass fires immediately on startup.
        while not self._stop.is_set():
            for m in self._meters:
                if self._stop.is_set():
                    return
                ser = self._get_ser()
                if ser is None or not getattr(ser, "is_open", False):
                    self._stop.wait(1.0)
                    continue
                try:
                    payload = self._read(ser, m)
                    now = time.time()
                    with self._lock:
                        self._cache[m.slave_addr] = {
                            "payload": payload,
                            "ts": now,
                            "error": None,
                        }
                    logger.debug("YearlyCache addr=%d refreshed", m.slave_addr)
                except Exception as e:
                    with self._lock:
                        entry = self._cache.get(m.slave_addr) or {}
                        entry["error"] = str(e)
                        entry["error_ts"] = time.time()
                        self._cache[m.slave_addr] = entry
                    logger.warning("YearlyCache addr=%d read failed: %s",
                                   m.slave_addr, e)
                # Small pause between meters so MeterCache / MQTT can get
                # a turn on the bus without waiting for the full 12-month scan
                # of the next meter.
                self._stop.wait(0.2)
            if self._stop.wait(self._interval):
                return
