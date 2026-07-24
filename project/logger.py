"""Server session log (R1.4).

One line per event, appended to logs/server.log and echoed to stdout:

    [2026-07-23 10:30:15] 127.0.0.1 CONNECT
    [2026-07-23 10:30:16] 127.0.0.1 UPLOAD data.bin 10485760B 6.2s 1650.4KB/s SHA256-OK
    [2026-07-23 10:30:20] 127.0.0.1 DISCONNECT

The transfer line carries the five graded fields: timestamp, IP, command,
duration, and speed in KB/s. Durations must use time.perf_counter(), not
time.monotonic(): on Windows monotonic ticks in ~15.6 ms steps, so with it
a small file would measure 0.0s and the KB/s column would be garbage.
perf_counter is sub-microsecond, so it stays accurate.
"""

import os
import threading
from datetime import datetime


class Logger:
    """Append-only session logger. Safe to share between threads."""

    def __init__(self, path, echo=True):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Append so a restart never wipes the demo history; line-buffered
        # writes below keep every completed line on disk even if killed.
        self._file = open(path, "a", encoding="utf8")
        self._echo = echo
        # One lock around both sinks: session threads (day 7) must never
        # interleave half-written lines.
        self._lock = threading.Lock()

    def log(self, ip, *fields):
        """Write '[timestamp] <ip> <fields...>' to the file and stdout."""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = " ".join([f"[{stamp}]", ip, *map(str, fields)])
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()
            if self._echo:
                print(line)

    def connect(self, ip):
        self.log(ip, "CONNECT")

    def disconnect(self, ip):
        self.log(ip, "DISCONNECT")

    def error(self, ip, message):
        self.log(ip, "ERROR", message)

    def transfer(self, ip, command, filename, nbytes, duration, checksum):
        """The graded session line: command, file, size, time, speed, checksum."""
        # A 0-byte file can finish between two perf_counter ticks; never
        # divide by zero for it.
        speed = (nbytes / 1024) / duration if duration > 0 else 0.0
        self.log(
            ip,
            command,
            filename,
            f"{nbytes}B",
            f"{duration:.1f}s",
            f"{speed:.1f}KB/s",
            checksum,
        )

    def close(self):
        with self._lock:
            self._file.close()
