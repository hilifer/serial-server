#!/usr/bin/env python3
"""Daily-rotated log handler with a per-file size cap.

File naming scheme:
    serial_server.log                       current day, in-flight
    serial_server.log.2026-05-07            previous full day
    serial_server.log.2026-05-08            today's first slice (rotated mid-day by size)
    serial_server.log.2026-05-08.1          today's second slice
    serial_server.log.2026-05-08.2          today's third slice
    ...

Rotation triggers:
    1. Local-time midnight crossing (TimedRotatingFileHandler logic).
    2. Active file size reaches `max_bytes` — rolled mid-day with today's
       date suffix; collisions disambiguated with .1 / .2 / ... numeric tail.

`backup_count` caps the total number of rolled files kept (oldest first
deleted, files sorted lexicographically — which matches chronological
order for ISO date suffixes).
"""
import os
import time
from logging.handlers import TimedRotatingFileHandler


class TimedSizedRotatingFileHandler(TimedRotatingFileHandler):
    """Rotates daily at local midnight AND whenever file exceeds max_bytes."""

    def __init__(self, filename, max_bytes: int = 0, backup_count: int = 14,
                 encoding=None):
        super().__init__(
            filename,
            when="midnight",
            backupCount=backup_count,
            encoding=encoding,
        )
        self.max_bytes = max_bytes

    # The base TimedRotatingFileHandler.shouldRollover checks time only.
    # We extend it: also roll if writing this record would push the file
    # past max_bytes.
    def shouldRollover(self, record) -> int:
        if super().shouldRollover(record):
            return 1
        if self.max_bytes > 0:
            try:
                if self.stream is None:
                    self.stream = self._open()
                msg = self.format(record) + "\n"
                self.stream.seek(0, 2)
                if self.stream.tell() + len(msg.encode("utf-8")) >= self.max_bytes:
                    return 1
            except (OSError, ValueError):
                pass
        return 0

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None

        # When a midnight crossing triggered the roll, parent uses
        # `self.rolloverAt - self.interval` (the period that just ended,
        # i.e. yesterday). For size-triggered rolls mid-day, "today" is the
        # right label.
        now = int(time.time())
        if now >= self.rolloverAt:
            t = self.rolloverAt - self.interval
        else:
            t = now

        suffix = time.strftime(self.suffix, time.localtime(t))
        target = f"{self.baseFilename}.{suffix}"

        # If today already has a slice, append .1 / .2 / ...
        if os.path.exists(target):
            i = 1
            while os.path.exists(f"{target}.{i}"):
                i += 1
            target = f"{target}.{i}"

        try:
            self.rotate(self.baseFilename, target)
        except OSError:
            pass

        # Honor backup_count by deleting the oldest rolled files. The base
        # extMatch regex already accepts the optional .N suffix, so daily
        # files and same-day slices both qualify.
        if self.backupCount > 0:
            for old in self.getFilesToDelete():
                try:
                    os.remove(old)
                except OSError:
                    pass

        if not self.delay:
            self.stream = self._open()

        new_at = self.computeRollover(now)
        while new_at <= now:
            new_at += self.interval
        self.rolloverAt = new_at
