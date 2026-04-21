#!/usr/bin/env python3
"""Background parking-space cache.

One worker thread per parking COM port (COM31 Zone A, COM32 Zone B) so
the two buses are polled in parallel. Each worker walks its spaces,
reading one detector at a time under the port's lock, with a small
sleep between full passes to keep other traffic (MQTT bridge) moving.
"""
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("parking-cache")


class ParkingCache:
    def __init__(self, spaces_by_port: dict, poll_fn: Callable,
                 serial_mgr_provider: Callable,
                 scan_interval_s: float = 2.0):
        """
        spaces_by_port: {"COM31": [ParkingSpace, ...], "COM32": [...]}
        poll_fn: function(serial_mgr, space) -> (status_int_or_None, label_str)
        serial_mgr_provider: callable(com_port) -> SerialManager or None
        scan_interval_s: sleep between full passes per port
        """
        self._spaces_by_port = dict(spaces_by_port)
        self._poll = poll_fn
        self._get_ser = serial_mgr_provider
        self._interval = scan_interval_s
        self._cache: dict[int, dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self):
        if self._threads and any(t.is_alive() for t in self._threads):
            return
        self._stop.clear()
        self._threads = []
        for com_port, spaces in self._spaces_by_port.items():
            t = threading.Thread(
                target=self._port_loop, args=(com_port, spaces),
                name=f"parking-cache-{com_port}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stop.set()

    def get_all(self) -> list[dict]:
        """Snapshot of all cached spaces, sorted by space_id."""
        with self._lock:
            return sorted((dict(v) for v in self._cache.values()),
                          key=lambda x: x["space_id"])

    def get(self, space_id: int) -> Optional[dict]:
        with self._lock:
            entry = self._cache.get(space_id)
            return dict(entry) if entry else None

    def _port_loop(self, com_port: str, spaces: list):
        logger.info("ParkingCache loop started for %s (%d spaces)",
                    com_port, len(spaces))
        while not self._stop.is_set():
            mgr = self._get_ser(com_port)
            if mgr is None or not getattr(mgr, "is_open", False):
                if self._stop.wait(1.0):
                    return
                continue
            for s in spaces:
                if self._stop.is_set():
                    return
                try:
                    with mgr.lock():
                        status, label = self._poll(mgr, s)
                    now = time.time()
                    with self._lock:
                        self._cache[s.space_id] = {
                            "space_id": s.space_id, "zone": s.zone,
                            "status": status, "label": label,
                            "ts": now, "error": None,
                        }
                except Exception as e:
                    with self._lock:
                        entry = self._cache.get(s.space_id) or {
                            "space_id": s.space_id, "zone": s.zone,
                        }
                        entry["error"] = str(e)
                        entry["error_ts"] = time.time()
                        self._cache[s.space_id] = entry
                    logger.debug("ParkingCache space=%d failed: %s",
                                 s.space_id, e)
            if self._stop.wait(self._interval):
                return
