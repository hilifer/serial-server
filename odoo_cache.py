#!/usr/bin/env python3
"""Simple TTL cache for Odoo JSON-RPC calls.

Wraps a fetcher function with a time-based cache keyed by the call
arguments. Cache misses run the fetcher; hits within `ttl_s` return
the previous value instantly. On fetch failure the last known good
value is returned (soft fallback).
"""
import json
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("odoo-cache")


class OdooCache:
    def __init__(self, ttl_s: float = 5.0):
        self.ttl_s = ttl_s
        self._data: dict[str, tuple] = {}  # key -> (value, ts)
        self._lock = threading.Lock()

    @staticmethod
    def _make_key(*args, **kwargs) -> str:
        return json.dumps([args, kwargs], sort_keys=True, default=str)

    def get_or_fetch(self, fetcher: Callable, *args, **kwargs) -> Optional[object]:
        key = self._make_key(*args, **kwargs)
        now = time.time()

        with self._lock:
            entry = self._data.get(key)
            if entry is not None and (now - entry[1]) < self.ttl_s:
                return entry[0]
        # Miss or expired: fetch outside the lock so concurrent requests
        # for other keys aren't blocked.
        try:
            value = fetcher(*args, **kwargs)
        except Exception as e:
            logger.warning("Odoo fetch failed (%s); serving stale if any", e)
            with self._lock:
                entry = self._data.get(key)
            return entry[0] if entry else None

        with self._lock:
            self._data[key] = (value, time.time())
        return value

    def invalidate(self) -> None:
        with self._lock:
            self._data.clear()
