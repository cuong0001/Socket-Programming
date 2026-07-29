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
        req = read_frame(conn)  # Client sends 'DOWNLOAD fake.bin'
        send_frame(conn, b"OK 10")  # Tell the client to expect 10 bytes
        
        # Create the original data (10 zero bytes) and hash it
        original_data = b"\x00" * 10
        hasher = hashlib.sha256(original_data)
        
        # SEND CORRUPTED DATA (10 one bytes)
        send_frame(conn, b"\x01" * 10)
        
        # Send the hash of the original data to deceive the client
        send_frame(conn, f"ACK sha256 {hasher.hexdigest()}".encode("utf-8"))

class TestChecksumMismatch(unittest.TestCase):
    def test_client_catches_mismatch(self):
        # 1. Use a temporary directory to avoid polluting real storage/ and logs/
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            downloads_dir = temp_path / "downloads"
            downloads_dir.mkdir(parents=True, exist_ok=True)
            
            # Create a pre-existing completed file to ensure the client doesn't overwrite/delete it
            target_file = downloads_dir / "fake.bin"
            target_file.write_text("old valid data")
            
            # 2. Start the Fake Server
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]
            
            server_thread = threading.Thread(target=fake_server, args=(sock,))
            server_thread.start()
            
            # 3. Launch the client to connect to the Fake Server
            result = subprocess.run(
                [sys.executable, str(PROJECT_DIR / "client.py"), "127.0.0.1", str(port), "DOWNLOAD fake.bin"],
                cwd=str(temp_path),
                capture_output=True,
                text=True,
                timeout=5
            )
            
            sock.close()
            server_thread.join()
            
            # 4. ASSERTIONS based on the reviewer's requirements:
            # - Client must exit with code 1
            self.assertEqual(result.returncode, 1, "Client must exit with code 1 on mismatch")
            # - Must print MISMATCH
            self.assertIn("MISMATCH", result.stdout + result.stderr)
            # - The staging file (.part) must be deleted
            self.assertFalse((downloads_dir / "fake.bin.part").exists(), "Staging file must be deleted")
            # - The old valid file must remain completely untouched
            self.assertTrue(target_file.exists(), "Existing valid file was deleted")
            self.assertEqual(target_file.read_text(), "old valid data", "Existing valid file was corrupted")

if __name__ == "__main__":
    unittest.main()
