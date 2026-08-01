"""Server session log (R1.4).

One record per line, appended to logs/server.log and echoed to stdout.
Fields are separated by " | " so the columns stay readable by eye and are
trivial to split when parsing:

    [2026-07-23 10:30:15] | 127.0.0.1 | CONNECT
    [2026-07-23 10:30:15] | 127.0.0.1 | LIST | OK 3
    [2026-07-23 10:30:16] | 127.0.0.1 | UPLOAD | data.bin | 10485760B | 6.201s | 1650.4KB/s | SHA256-OK
    [2026-07-23 10:30:17] | 127.0.0.1 | HELLO | ERR bad command
    [2026-07-23 10:30:20] | 127.0.0.1 | DISCONNECT

Every command produces exactly one record, so the log doubles as a full
transcript of the session.

The transfer line carries the five graded fields: timestamp, IP, command,
duration, and speed in KB/s. Durations must use time.perf_counter(), not
time.monotonic(): on Windows monotonic ticks in ~15.6 ms steps, so with it
a small file would measure 0.0s and the KB/s column would be garbage.
perf_counter is sub-microsecond, so it stays accurate.
"""

import os
import threading
from datetime import datetime


FIELD_SEPARATOR = " | "

# Milliseconds. A 2 MB transfer on loopback takes ~0.05s, which one decimal
# place would round to "0.0s" -- next to a non-zero KB/s, that reads as a
# broken measurement.
DURATION_DECIMALS = 3


def _clean(value):
    """Flatten one field onto a single line.

    Filenames and command words come from the client, so without this a name
    containing a newline could forge extra records in the log.
    """
    return "".join(ch if ch.isprintable() else "?" for ch in str(value))


class Logger:
    """Append-only session logger. Safe to share between threads."""

    def __init__(self, path, echo=True):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Append so a restart never wipes the demo history; the flush below
        # keeps every completed line on disk even if the server is killed.
        self._file = open(path, "a", encoding="utf8")
        self._echo = echo
        # One lock around both sinks: session threads (day 7) must never
        # interleave half-written lines.
        self._lock = threading.Lock()

    def log(self, ip, *fields):
        """Write '[timestamp] | <ip> | <fields...>' to the file and stdout."""
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parts = [f"[{stamp}]", _clean(ip)]
        parts.extend(_clean(field) for field in fields)
        line = FIELD_SEPARATOR.join(parts)
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

    def command(self, ip, command, result):
        """One record for a command that moves no file: 'LIST | OK 3'."""
        self.log(ip, command, result)

    def transfer(self, ip, command, filename, nbytes, duration, checksum,
                 declared=None):
        """The graded session line: command, file, size, time, speed, checksum.

        `declared` is the size the transfer was supposed to reach. Pass it only
        when the transfer did not finish, so the record shows how far it got
        ("7B/100000B"); a completed transfer keeps the plain "10485760B" shape.
        """
        # A 0-byte file can finish between two perf_counter reads; never
        # divide by zero for it.
        speed = (nbytes / 1024) / duration if duration > 0 else 0.0
        size_field = f"{nbytes}B" if declared is None else f"{nbytes}B/{declared}B"
        self.log(
            ip,
            command,
            filename,
            size_field,
            f"{duration:.{DURATION_DECIMALS}f}s",
            f"{speed:.1f}KB/s",
            checksum,
        )

    def close(self):
        with self._lock:
            self._file.close()
