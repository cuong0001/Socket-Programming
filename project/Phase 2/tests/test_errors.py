import hashlib
import socket
import sys
import unittest
from pathlib import Path

from helpers import RunningServer


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import protocol as P


def login(sock: socket.socket, username: str) -> int:
    sock.sendall(P.pack_packet(P.LOGIN, 0, P.pack_text(username)))
    op, uid, _payload = P.read_packet(sock)
    assert op == P.ACK, f"LOGIN failed: opcode {op}"
    return uid


def interrupt_upload(port: int, filename: str, total_size: int, partial: bytes,
                      username: str = "alice") -> None:
    """LOGIN, start a FILE_UPLOAD, send one chunk, then disconnect without finishing."""
    sock = socket.create_connection(("127.0.0.1", port))
    try:
        uid = login(sock, username)

        fake_hash = hashlib.sha256(b"fake").digest()
        upload_req = P.pack_upload(filename, total_size, 0, fake_hash)
        sock.sendall(P.pack_packet(P.FILE_UPLOAD, uid, upload_req))
        op, _, _ = P.read_packet(sock)
        assert op == P.ACK, f"FILE_UPLOAD start failed: opcode {op}"

        sock.sendall(P.pack_packet(P.FILE_CHUNK, uid, P.pack_chunk(0, partial)))
    finally:
        sock.close()


class ErrorHandlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_bad_requests_return_error_and_session_stays_alive(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
            uid = login(sock, "alice")

            # Opcode nobody defines.
            sock.sendall(P.pack_packet(0x9999, uid))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.ERROR)

            # Path traversal in the upload filename.
            sock.sendall(P.pack_packet(
                P.FILE_UPLOAD, uid, P.pack_upload("../secret", 10, 0)))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.ERROR)

            # Download of a file that was never uploaded.
            sock.sendall(P.pack_packet(
                P.FILE_DOWNLOAD, uid, P.pack_download("does-not-exist.bin")))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.ERROR)

            # None of the above should have killed the session.
            sock.sendall(P.pack_packet(P.FILE_LIST, uid))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.FILE_LIST_RESP)

    def test_disconnect_mid_upload_does_not_kill_server(self) -> None:
        partial = b"only a small part"
        interrupt_upload(
            self.server.port,
            "broken.bin", 100000,
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

    def test_upload_of_existing_filename_is_refused_without_touching_it(self) -> None:
        """R2.7 duplicate policy: a complete file is never overwritten by
        UPLOAD -- the request is refused with FILE_EXISTS before any
        staging begins, so there's no window where an interrupted transfer
        could corrupt the original (stronger than "interrupted overwrite
        preserves the file": the overwrite is never even allowed to start).
        """
        # run_client always logs in as "alice" (see helpers.py) -- storage
        # is namespaced per user, so the file lives under storage/alice/.
        storage = self.server.work_dir / "storage" / "alice"
        storage.mkdir(parents=True, exist_ok=True)
        target = storage / "existing.bin"
        staging = storage / "existing.bin.part"
        original = b"the complete original file"
        target.write_bytes(original)

        with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
            uid = login(sock, "alice")
            sock.sendall(P.pack_packet(
                P.FILE_UPLOAD, uid, P.pack_upload("existing.bin", 100000, 0)))
            op, _, payload = P.read_packet(sock)
            self.assertEqual(op, P.ERROR)
            code, _msg = P.unpack_error(payload)
            self.assertEqual(code, 0x0070)  # FILE_EXISTS

            sock.sendall(P.pack_packet(P.FILE_LIST, uid))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.FILE_LIST_RESP)

        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(staging.exists())

    def test_part_suffix_is_rejected_case_insensitively(self) -> None:
        storage = self.server.work_dir / "storage" / "alice"
        storage.mkdir(parents=True, exist_ok=True)
        target = storage / "legacy.PART"
        original = b"existing uppercase-suffix file"
        target.write_bytes(original)

        with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
            uid = login(sock, "alice")

            sock.sendall(P.pack_packet(
                P.FILE_UPLOAD, uid, P.pack_upload("legacy.PART", 100000, 0)))
            op, _, payload = P.read_packet(sock)
            self.assertEqual(op, P.ERROR)
            code, _msg = P.unpack_error(payload)
            self.assertEqual(code, 0x006E)  # INVALID_FILENAME

            sock.sendall(P.pack_packet(P.FILE_LIST, uid))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.FILE_LIST_RESP)

        self.assertEqual(target.read_bytes(), original)

    def test_nul_filename_returns_error_and_session_stays_alive(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
            uid = login(sock, "alice")

            sock.sendall(P.pack_packet(
                P.FILE_UPLOAD, uid, P.pack_upload("bad\x00name", 1, 0)))
            op, _, payload = P.read_packet(sock)
            self.assertEqual(op, P.ERROR)
            code, _msg = P.unpack_error(payload)
            self.assertEqual(code, 0x006E)  # INVALID_FILENAME

            sock.sendall(P.pack_packet(P.FILE_LIST, uid))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.FILE_LIST_RESP)


class SecurityAndRobustnessTests(unittest.TestCase):
    """Regression coverage for the PR #24 review: username path traversal,
    oversized upload chunks, and malformed transfer payloads killing the
    session instead of returning a clean ERROR."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_username_path_traversal_is_rejected(self) -> None:
        for n, bad_username in enumerate(("..", "../escape", "a/b", "a\\b", "C:x")):
            with self.subTest(username=bad_username):
                with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
                    sock.sendall(P.pack_packet(P.LOGIN, 0, P.pack_text(bad_username)))
                    op, _, payload = P.read_packet(sock)
                    self.assertEqual(op, P.ERROR)
                    code, _msg = P.unpack_error(payload)
                    self.assertEqual(code, 0x0066)  # INVALID_USERNAME

                    # Connection must still be usable afterward. Unique name
                    # per iteration -- the previous connection's LOGOUT may
                    # not have been processed by the server yet.
                    uid = login(sock, f"traversal-retry-{n}")
                    self.assertGreater(uid, 0)

        # No file/directory should have escaped storage/ into work_dir.
        self.assertFalse((self.server.work_dir / "escaped.bin").exists())
        self.assertFalse((self.server.work_dir / "escape").exists())

    def test_oversized_chunk_is_rejected_and_not_committed(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
            uid = login(sock, "chunk-overflow")
            sock.sendall(P.pack_packet(
                P.FILE_UPLOAD, uid, P.pack_upload("small.bin", 3, 0)))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.ACK)

            # Declares total_size=3 but sends 5 bytes.
            sock.sendall(P.pack_packet(P.FILE_CHUNK, uid, P.pack_chunk(0, b"ABCDE")))
            op, _, payload = P.read_packet(sock)
            self.assertEqual(op, P.ERROR)

            sock.sendall(P.pack_packet(P.FILE_LIST, uid))
            op, _, payload = P.read_packet(sock)
            self.assertEqual(op, P.FILE_LIST_RESP)
            self.assertEqual(P.unpack_file_list_response(payload), [])

        storage = self.server.work_dir / "storage" / "chunk-overflow"
        self.assertFalse((storage / "small.bin").exists())

    def test_malformed_transfer_payloads_return_malformed_and_keep_session_alive(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
            uid = login(sock, "malformed-payloads")

            for opcode in (P.FILE_UPLOAD, P.FILE_DOWNLOAD, P.FILE_DELETE):
                with self.subTest(opcode=opcode):
                    sock.sendall(P.pack_packet(opcode, uid, b"\x00"))
                    op, _, payload = P.read_packet(sock)
                    self.assertEqual(op, P.ERROR)
                    code, _msg = P.unpack_error(payload)
                    self.assertEqual(code, 0x0064)  # MALFORMED

                    sock.sendall(P.pack_packet(P.FILE_LIST, uid))
                    op, _, _ = P.read_packet(sock)
                    self.assertEqual(op, P.FILE_LIST_RESP)

    def test_malformed_chunk_mid_upload_returns_malformed_and_keeps_session_alive(self) -> None:
        with socket.create_connection(("127.0.0.1", self.server.port)) as sock:
            uid = login(sock, "malformed-chunk")
            sock.sendall(P.pack_packet(
                P.FILE_UPLOAD, uid, P.pack_upload("chunked.bin", 10, 0)))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.ACK)

            # Shorter than the 8-byte offset field unpack_chunk requires.
            sock.sendall(P.pack_packet(P.FILE_CHUNK, uid, b"\x00\x00\x00"))
            op, _, payload = P.read_packet(sock)
            self.assertEqual(op, P.ERROR)
            code, _msg = P.unpack_error(payload)
            self.assertEqual(code, 0x0064)  # MALFORMED

            sock.sendall(P.pack_packet(P.FILE_LIST, uid))
            op, _, _ = P.read_packet(sock)
            self.assertEqual(op, P.FILE_LIST_RESP)


if __name__ == "__main__":
    unittest.main()
