"""500 connect/login/logout cycles against a real server subprocess --
confirms threads and OS handles return to baseline instead of growing one
per connection (a leak would show up as roughly +500 by the end).

Requires psutil (see requirements-test.txt) -- threading.active_count()
can't see across the process boundary to the real server subprocess that
RunningServer launches.
"""

import socket
import sys
import time
import unittest
from pathlib import Path

import psutil

from helpers import RunningServer

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import protocol as P

CHURN_ITERATIONS = 500


def login_and_logout(port: int, username: str) -> None:
    with socket.create_connection(("127.0.0.1", port)) as sock:
        sock.sendall(P.pack_packet(P.LOGIN, 0, P.pack_text(username)))
        op, uid, _payload = P.read_packet(sock)
        assert op == P.ACK, f"LOGIN failed: opcode {op}"
        sock.sendall(P.pack_packet(P.LOGOUT, uid))
        op, _, _payload = P.read_packet(sock)
        assert op == P.ACK, f"LOGOUT failed: opcode {op}"


def _handle_count(proc: psutil.Process) -> int:
    """OS handle/fd count -- num_handles() on Windows, num_fds() elsewhere."""
    if hasattr(proc, "num_handles"):
        return proc.num_handles()
    return proc.num_fds()


def _wait_for_stable(measure, deadline_seconds: float = 5.0, settle_reads: int = 3) -> int:
    """Poll ``measure()`` until it stops changing across ``settle_reads``
    consecutive samples, or ``deadline_seconds`` elapses.

    A closed connection's server-side thread finishes its cleanup
    (registry.logout/release_slot/conn.close) in a background thread after
    the client already saw the LOGOUT ACK and moved on, so counts taken
    immediately after the loop can still be mid-teardown. This waits for
    the transient churn to settle before asserting anything.
    """
    deadline = time.monotonic() + deadline_seconds
    last = measure()
    stable_count = 1
    while time.monotonic() < deadline and stable_count < settle_reads:
        time.sleep(0.1)
        current = measure()
        if current == last:
            stable_count += 1
        else:
            stable_count = 1
            last = current
    return last


class ConnectionChurnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()
        cls.proc = psutil.Process(cls.server.process.pid)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_500_connect_login_logout_cycles_do_not_leak_threads_or_handles(self) -> None:
        # One warm-up cycle first so first-connection-only housekeeping
        # (e.g. lazy imports, first storage dir creation) isn't counted as
        # "leaked" in the baseline.
        login_and_logout(self.server.port, "churn-warmup")
        baseline_threads = _wait_for_stable(self.proc.num_threads)
        baseline_handles = _wait_for_stable(lambda: _handle_count(self.proc))

        for i in range(CHURN_ITERATIONS):
            login_and_logout(self.server.port, f"churn-{i}")

        final_threads = _wait_for_stable(self.proc.num_threads)
        final_handles = _wait_for_stable(lambda: _handle_count(self.proc))

        # Not asserting "== baseline" -- some slack for OS/GC scheduling
        # jitter -- but nowhere near +500, which is what a real
        # per-connection thread/handle leak would produce.
        self.assertLess(
            final_threads, baseline_threads + 20,
            f"thread count grew from {baseline_threads} to {final_threads} "
            f"over {CHURN_ITERATIONS} cycles -- looks like a leak",
        )
        self.assertLess(
            final_handles, baseline_handles + 50,
            f"handle count grew from {baseline_handles} to {final_handles} "
            f"over {CHURN_ITERATIONS} cycles -- looks like a leak",
        )


if __name__ == "__main__":
    unittest.main()
