"""SERVER_BUSY / max_clients coverage -- a real capacity limit reachable
through server.py's live accept loop, with zero prior test coverage."""

import socket
import sys
import time
import unittest
from pathlib import Path

from helpers import RunningServer

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import protocol as P
from config import ServerConfig
from session import ErrorCode


class ServerBusyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()
        # server.py doesn't currently override max_clients from the CLI, so
        # this is exactly the limit the running server was built with.
        cls.max_clients = ServerConfig().max_clients

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_connection_past_capacity_gets_server_busy_then_a_freed_slot_recovers(self) -> None:
        address = ("127.0.0.1", self.server.port)

        # Fill every slot. A capacity slot is claimed the instant the
        # connection is accepted (before LOGIN), so these don't need to
        # send anything to occupy it.
        held = [socket.create_connection(address) for _ in range(self.max_clients)]
        try:
            # One connection past capacity: the server still accepts the TCP
            # connection (an OS-level refusal would look identical to "the
            # server is dead" from the client's side) and replies
            # SERVER_BUSY immediately, without ever reading a LOGIN.
            with socket.create_connection(address) as overflow:
                op, _, payload = P.read_packet(overflow)
                self.assertEqual(op, P.ERROR)
                code, _msg = P.unpack_error(payload)
                self.assertEqual(code, ErrorCode.SERVER_BUSY)

            # Free exactly one slot...
            held.pop().close()

            # ...and the next connection must get through instead of
            # SERVER_BUSY. Poll briefly: release_slot() runs in the freed
            # connection's server-side cleanup thread, not synchronously
            # with our close() call here.
            deadline = time.monotonic() + 3
            while True:
                sock = socket.create_connection(address)
                sock.sendall(P.pack_packet(P.LOGIN, 0, P.pack_text("server-busy-recovery")))
                op, _, payload = P.read_packet(sock)
                if op == P.ACK:
                    sock.close()
                    break
                code, _msg = P.unpack_error(payload)
                self.assertEqual(code, ErrorCode.SERVER_BUSY)  # still full -- retry
                sock.close()
                self.assertLess(time.monotonic(), deadline, "freed slot never became usable")
                time.sleep(0.05)
        finally:
            for sock in held:
                sock.close()


if __name__ == "__main__":
    unittest.main()
