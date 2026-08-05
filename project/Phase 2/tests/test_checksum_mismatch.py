import socket
import sys
import tempfile
import threading
import subprocess
import hashlib
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from common import read_frame, send_frame

def fake_server(sock):
    """Minimal fake TCP server: Sends corrupted data but a valid SHA-256 digest."""
    import protocol as P
    conn, _ = sock.accept()
    with conn:
        # 1. Receive LOGIN
        op, _, _ = P.read_packet(conn)
        assert op == P.LOGIN, f"Expected LOGIN, got {op}"
        conn.sendall(P.pack_packet(P.ACK, 0, P.pack_ack(P.LOGIN, 1234)))

        # 2. Receive FILE_DOWNLOAD
        op, _, payload = P.read_packet(conn)
        assert op == P.FILE_DOWNLOAD, f"Client did not send DOWNLOAD, got {op}"

        # 3. Send ACK with size and sha256
        original_data = b"\x00" * 10
        hasher = hashlib.sha256(original_data)
        ack_payload = P.pack_ack(P.FILE_DOWNLOAD, 10) + hasher.digest()
        conn.sendall(P.pack_packet(P.ACK, 1234, ack_payload))

        # 4. Send corrupted chunk
        chunk_payload = P.pack_chunk(0, b"\x01" * 10)
        conn.sendall(P.pack_packet(P.FILE_CHUNK, 1234, chunk_payload))

class TestChecksumMismatch(unittest.TestCase):
    def test_client_catches_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            downloads_dir = temp_path / "downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)

            target_file = downloads_dir / "fake.bin"
            target_file.write_text("old valid data")

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]

            # Fix: Use daemon=True so the thread doesn't keep the process alive if hung
            server_thread = threading.Thread(target=fake_server, args=(sock,), daemon=True)
            server_thread.start()

            # Fix: Use try...finally to guarantee cleanup even if subprocess.run times out
            try:
                result = subprocess.run(
                    [sys.executable, str(PROJECT_DIR / "client.py"), "127.0.0.1", str(port), "DOWNLOAD fake.bin"],
                    cwd=str(temp_path),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",           # Polish: Match helpers.py to avoid UnicodeDecodeError on Windows
                    stdin=subprocess.DEVNULL,   # Polish: Prevent client from blocking on stdin
                    timeout=5,
                )
            finally:
                sock.close()
                server_thread.join(timeout=5)

            self.assertEqual(result.returncode, 1, "Client must exit with code 1 on mismatch")
            self.assertIn("MISMATCH", result.stdout + result.stderr)
            self.assertFalse((downloads_dir / "fake.bin.part").exists(), "Staging file must be deleted")
            self.assertTrue(target_file.exists(), "Existing valid file was deleted")
            self.assertEqual(target_file.read_text(), "old valid data", "Existing valid file was corrupted")

if __name__ == "__main__":
    unittest.main()
