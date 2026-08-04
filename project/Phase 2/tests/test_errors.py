import socket
import sys
import unittest
from pathlib import Path

from helpers import RunningServer


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from common import read_frame, send_frame


def send_command(sock: socket.socket, command: str) -> str:
    send_frame(sock, command.encode("utf-8"))
    return read_frame(sock).decode("utf-8")


def interrupt_upload(port: int, command: bytes, partial: bytes) -> None:
    sock = socket.create_connection(("127.0.0.1", port))
    try:
        send_frame(sock, command)
        reply = read_frame(sock).decode("utf-8")
        if not reply.startswith("OK"):
            raise AssertionError(f"Server did not accept upload: {reply}")
        send_frame(sock, partial)
    finally:
        sock.close()


@unittest.skip(
    "Blocked by the Day 3 server rewiring (PR #20, session.py): server.py "
    "now only speaks the Phase 2 binary protocol and requires a LOGIN "
    "packet before anything else. client.py in this repo hasn't been "
    "updated to send LOGIN yet, so every connection here gets its old "
    "Phase 1 text frame reset by the server -- ConnectionResetError, not "
    "a meaningful test result. Also, every assertion in this class relies "
    "on the real Phase 1 UPLOAD path (staging file, atomic commit, "
    "filename validation during upload), and Session.handle_file_upload "
    "is still an intentional stub (Day 4). Re-enable once client.py "
    "speaks the binary protocol (LOGIN) and real UPLOAD lands in Session. "
    "Bad-opcode/malformed-payload coverage for the new protocol lives in "
    "tests/test_session.py in the meantime."
)
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
        partial = b"only a small part"
        interrupt_upload(
            self.server.port,
            b"UPLOAD 100000 broken.bin",
            partial,
        )

        listing = self.server.run_client("LIST")
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertNotIn("broken.bin", listing.stdout)

        log = (self.server.work_dir / "logs" / "server.log").read_text(
            encoding="utf-8"
        )
        matching_lines = [
            line
            for line in log.splitlines()
            if "| UPLOAD | broken.bin |" in line
        ]
        self.assertEqual(len(matching_lines), 1)
        self.assertIn(f"| {len(partial)}B/100000B |", matching_lines[0])
        self.assertTrue(matching_lines[0].endswith("| ABORTED"))

    def test_interrupted_overwrite_preserves_existing_file(self) -> None:
        storage = self.server.work_dir / "storage"
        target = storage / "existing.bin"
        staging = storage / "existing.bin.part"
        original = b"the complete original file"
        target.write_bytes(original)

        interrupt_upload(
            self.server.port,
            b"UPLOAD 100000 existing.bin",
            b"incomplete replacement",
        )

        # LIST is also a synchronization point: the single-threaded server
        # cannot answer it until cleanup for the disconnected upload finishes.
        listing = self.server.run_client("LIST")
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(staging.exists())
        self.assertIn("existing.bin", listing.stdout)

    def test_part_suffix_is_rejected_case_insensitively(self) -> None:
        storage = self.server.work_dir / "storage"
        target = storage / "legacy.PART"
        original = b"existing uppercase-suffix file"
        target.write_bytes(original)

        with socket.create_connection(
            ("127.0.0.1", self.server.port)
        ) as sock:
            self.assertEqual(
                send_command(sock, "UPLOAD 100000 legacy.PART"),
                "ERR bad filename",
            )
            self.assertTrue(send_command(sock, "LIST").startswith("OK"))

        self.assertEqual(target.read_bytes(), original)

    def test_nul_filename_returns_err_and_session_stays_alive(self) -> None:
        with socket.create_connection(
            ("127.0.0.1", self.server.port)
        ) as sock:
            send_frame(sock, b"UPLOAD 1 bad\x00name")
            self.assertEqual(
                read_frame(sock).decode("utf-8"),
                "ERR bad filename",
            )
            self.assertTrue(send_command(sock, "LIST").startswith("OK"))


if __name__ == "__main__":
    unittest.main()
