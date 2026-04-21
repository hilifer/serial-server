#!/usr/bin/env python3
"""Background meter cache.

A daemon thread continuously polls every meter on COM33 and stores the
latest successful read in memory. The /meter/{addr}/realtime endpoint
returns from this cache instead of hitting the serial bus on every
request, which cuts response time from ~20s (all 10 meters serialized)
to <1ms.

Failed reads preserve the previous successful payload and attach an
`error` marker so the caller can decide whether to treat it as stale.
"""
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("meter-cache")


class MeterCache:
    def __init__(self, meter_list, reader_fn: Callable,
                 serial_mgr_provider: Callable,
                 scan_interval_s: float = 2.0):
        """
        meter_list: list of MeterInfo objects to poll (scan order).
        reader_fn: function(serial_mgr, meter) -> response_dict. Must handle
                   its own locking on serial_mgr.
        serial_mgr_provider: callable returning the shared COM33 SerialManager,
                             or None if unavailable.
        scan_interval_s: sleep between full scan passes.
        """
        self._meters = list(meter_list)
        self._read = reader_fn
        self._get_ser = serial_mgr_provider
        self._interval = scan_interval_s
        self._cache: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="meter-cache", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def get(self, addr: int) -> Optional[dict]:
        """Return a shallow copy of the cached entry or None."""
        with self._lock:
            entry = self._cache.get(addr)
            return dict(entry) if entry else None

    def _loop(self):
        logger.info("MeterCache loop started (%d meters, interval=%.1fs)",
                    len(self._meters), self._interval)
        while not self._stop.is_set():
            for m in self._meters:
                if self._stop.is_set():
                    return
                ser = self._get_ser()
                if ser is None or not getattr(ser, "is_open", False):
                    # Port not ready — give auto-reconnect a chance.
                    self._stop.wait(0.5)
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
                except Exception as e:
                    with self._lock:
                        entry = self._cache.get(m.slave_addr) or {}
                        entry["error"] = str(e)
                        entry["error_ts"] = time.time()
                        self._cache[m.slave_addr] = entry
                    logger.debug("MeterCache addr=%d read failed: %s",
                                 m.slave_addr, e)
            if self._stop.wait(self._interval):
                return
