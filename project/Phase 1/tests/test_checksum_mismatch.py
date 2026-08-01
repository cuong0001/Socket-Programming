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
    conn, _ = sock.accept()
    with conn:
        req = read_frame(conn)
        # Polish: Fail fast if the client sends an unexpected command
        assert req.decode("utf-8").startswith("DOWNLOAD"), "Client did not send DOWNLOAD"

        send_frame(conn, b"OK 10")

        original_data = b"\x00" * 10
        hasher = hashlib.sha256(original_data)

        send_frame(conn, b"\x01" * 10)

        send_frame(conn, f"ACK sha256 {hasher.hexdigest()}".encode("utf-8"))

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
