import socket
import sys
import tempfile
import threading
import subprocess
import hashlib
import unittest
import os
import json
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
CLIENT_FILE = PROJECT_DIR / "client.py"

import protocol as P

def get_free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port

def run_client(port, command, work_dir, username="alice"):
    return subprocess.run(
        [sys.executable, str(CLIENT_FILE), "127.0.0.1", str(port), "--username", username, *command],
        cwd=work_dir, capture_output=True, text=True, timeout=5
    )

class FakeServer(threading.Thread):
    def __init__(self, handler, port=None):
        super().__init__()
        self.port = port or get_free_port()
        self.handler = handler
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", self.port))
        self.sock.listen(1)
        self.sock.settimeout(3.0)
        self.error = None
        self.daemon = True

    def run(self):
        try:
            conn, _ = self.sock.accept()
            with conn:
                self.handler(conn)
        except Exception as e:
            self.error = e
        finally:
            self.sock.close()


class TestResumeAndLogin(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_login_and_list_scoping(self):
        def handler_alice(conn):
            op, _, payload = P.read_packet(conn)
            assert op == P.LOGIN
            username, _ = P.unpack_text(payload)
            assert username == "alice"
            conn.sendall(P.pack_packet(P.ACK, 0, P.pack_ack(P.LOGIN, 100)))

            op, uid, payload = P.read_packet(conn)
            assert op == P.FILE_LIST
            assert uid == 100  # Client MUST use uid 100
            
            resp = P.pack_file_list_response([("alice_secret.txt", 1024)])
            conn.sendall(P.pack_packet(P.FILE_LIST_RESP, 100, resp))

        def handler_bob(conn):
            op, _, payload = P.read_packet(conn)
            assert op == P.LOGIN
            username, _ = P.unpack_text(payload)
            assert username == "bob"
            conn.sendall(P.pack_packet(P.ACK, 0, P.pack_ack(P.LOGIN, 200)))

            op, uid, payload = P.read_packet(conn)
            assert op == P.FILE_LIST
            assert uid == 200  # Client MUST use uid 200
            
            resp = P.pack_file_list_response([("bob_secret.txt", 2048)])
            conn.sendall(P.pack_packet(P.FILE_LIST_RESP, 200, resp))

        # Test Alice
        server_alice = FakeServer(handler_alice)
        server_alice.start()
        result_alice = run_client(server_alice.port, ["LIST"], self.work_dir, username="alice")
        server_alice.join()
        if server_alice.error: raise server_alice.error
        self.assertEqual(result_alice.returncode, 0, result_alice.stderr)
        self.assertIn("alice_secret.txt", result_alice.stdout)
        self.assertNotIn("bob_secret.txt", result_alice.stdout)

        # Test Bob
        server_bob = FakeServer(handler_bob)
        server_bob.start()
        result_bob = run_client(server_bob.port, ["LIST"], self.work_dir, username="bob")
        server_bob.join()
        if server_bob.error: raise server_bob.error
        self.assertEqual(result_bob.returncode, 0, result_bob.stderr)
        self.assertIn("bob_secret.txt", result_bob.stdout)
        self.assertNotIn("alice_secret.txt", result_bob.stdout)


    def test_upload_resume(self):
        test_file = self.work_dir / "resume.bin"
        data = b"\x11\x22\x33\x44\x55"
        test_file.write_bytes(data)
        hasher = hashlib.sha256(data)

        def handler(conn):
            P.read_packet(conn)
            conn.sendall(P.pack_packet(P.ACK, 0, P.pack_ack(P.LOGIN, 999)))

            op, _, payload = P.read_packet(conn)
            assert op == P.FILE_UPLOAD
            
            # Server says: I already have 2 bytes, start from offset 2!
            conn.sendall(P.pack_packet(P.ACK, 999, P.pack_ack(P.FILE_UPLOAD, 2)))

            op, _, payload = P.read_packet(conn)
            assert op == P.FILE_CHUNK
            chunk_offset, chunk_data = P.unpack_chunk(payload)
            assert chunk_offset == 2
            assert chunk_data == b"\x33\x44\x55"

            conn.sendall(P.pack_packet(P.ACK, 999, P.pack_ack(P.FILE_UPLOAD, 5, hasher.digest())))

        server = FakeServer(handler)
        server.start()
        
        result = run_client(server.port, ["UPLOAD", str(test_file)], self.work_dir)
        server.join()
        
        if server.error: raise server.error
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_download_resume(self):
        downloads_dir = self.work_dir / "downloads"
        downloads_dir.mkdir()
        part_file = downloads_dir / "target.bin.part"
        part_file.write_bytes(b"\xAA\xBB")
        
        sidecar_file = downloads_dir / "target.bin.part.json"
        hasher = hashlib.sha256(b"\xAA\xBB\xCC\xDD")
        
        sidecar_file.write_text(json.dumps({
            "total_size": 4,
            "expected_sha256": hasher.hexdigest(),
            "timestamp": time.time(),
            "protocol_version": 2
        }))

        def handler(conn):
            P.read_packet(conn)
            conn.sendall(P.pack_packet(P.ACK, 0, P.pack_ack(P.LOGIN, 999)))

            op, _, payload = P.read_packet(conn)
            assert op == P.FILE_DOWNLOAD
            filename, local_offset = P.unpack_download(payload)
            assert filename == "target.bin"
            assert local_offset == 2

            # Server sends ACK with total size and SHA256
            conn.sendall(P.pack_packet(P.ACK, 999, P.pack_ack(P.FILE_DOWNLOAD, 4, hasher.digest())))

            # Server sends remaining 2 bytes
            chunk = P.pack_chunk(2, b"\xCC\xDD")
            conn.sendall(P.pack_packet(P.FILE_CHUNK, 999, chunk))

        server = FakeServer(handler)
        server.start()
        
        result = run_client(server.port, ["DOWNLOAD", "target.bin"], self.work_dir)
        server.join()
        
        if server.error: raise server.error
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        
        final_file = downloads_dir / "target.bin"
        self.assertTrue(final_file.exists())
        self.assertFalse(part_file.exists())
        self.assertEqual(final_file.read_bytes(), b"\xAA\xBB\xCC\xDD")


if __name__ == '__main__':
    unittest.main()
