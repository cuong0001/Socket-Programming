import socket
import sys
import time
import unittest
from pathlib import Path

from helpers import RunningServer


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from common import read_frame, send_frame


def send_command(sock: socket.socket, command: str) -> str:
    send_frame(sock, command.encode("utf-8"))
    return read_frame(sock).decode("utf-8")


class ErrorHandlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_bad_commands_return_err_and_session_stays_alive(self) -> None:
        bad_commands = [
            "HELLO",
            "UPLOAD",
            "UPLOAD not-a-number data.bin",
            "DOWNLOAD",
            "DOWNLOAD ../secret",
        ]

        with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
            for command in bad_commands:
                with self.subTest(command=command):
                    self.assertTrue(send_command(sock, command).startswith("ERR"))

            self.assertTrue(send_command(sock, "LIST").startswith("OK"))

    def test_disconnect_mid_upload_does_not_kill_server(self) -> None:
        sock = socket.create_connection(("127.0.0.1", self.server.port))
        send_frame(sock, b"UPLOAD 100000 broken.bin")
        self.assertTrue(read_frame(sock).decode("utf-8").startswith("OK"))
        send_frame(sock, b"only a small part")
        sock.close()

        time.sleep(0.1)
        listing = self.server.run_client("LIST")
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertNotIn("broken.bin", listing.stdout)


if __name__ == "__main__":
    unittest.main()
