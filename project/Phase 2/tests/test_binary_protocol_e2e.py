import socket
import sys
import tempfile
import threading
import subprocess
import hashlib
import unittest
import os
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

def run_client(port, command, work_dir):
    return subprocess.run(
        [sys.executable, str(CLIENT_FILE), "127.0.0.1", str(port), "--username", "alice", *command],
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


class TestBinaryProtocolE2E(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_login_and_list(self):
        def handler(conn):
            op, _, payload = P.read_packet(conn)
            assert op == P.LOGIN
            # Send ACK for LOGIN with user id 999
            conn.sendall(P.pack_packet(P.ACK, 0, P.pack_ack(P.LOGIN, 999)))

            # Read FILE_LIST command
            op, uid, payload = P.read_packet(conn)
            assert op == P.FILE_LIST
            assert uid == 999
            
            resp = P.pack_file_list_response([("file1.bin", 100), ("file2.txt", 200)])
            conn.sendall(P.pack_packet(P.FILE_LIST_RESP, 999, resp))

        server = FakeServer(handler)
        server.start()
        
        result = run_client(server.port, ["LIST"], self.work_dir)
        server.join()
        
        if server.error: raise server.error
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("file1.bin", result.stdout)
        self.assertIn("file2.txt", result.stdout)

    def test_upload_with_0x00_byte(self):
        test_file = self.work_dir / "zero.bin"
        # Create a file containing exactly a 0x00 byte
        data = b"\x01\x02\x00\x03\x04"
        test_file.write_bytes(data)
        hasher = hashlib.sha256(data)
        
        def handler(conn):
            # LOGIN
            P.read_packet(conn)
            conn.sendall(P.pack_packet(P.ACK, 0, P.pack_ack(P.LOGIN, 999)))

            # UPLOAD
            op, uid, payload = P.read_packet(conn)
            assert op == P.FILE_UPLOAD
            filename, size, offset, digest = P.unpack_upload(payload)
            assert filename == "zero.bin"
            assert size == len(data)
            assert offset == 0
            
            # Send ACK for UPLOAD, expecting start offset 0
            conn.sendall(P.pack_packet(P.ACK, 999, P.pack_ack(P.FILE_UPLOAD, 0)))

            # FILE_CHUNK
            op, uid, payload = P.read_packet(conn)
            assert op == P.FILE_CHUNK
            chunk_offset, chunk_data = P.unpack_chunk(payload)
            assert chunk_offset == 0
            assert chunk_data == data

            # Final ACK with SHA256 to confirm success
            conn.sendall(P.pack_packet(P.ACK, 999, P.pack_ack(P.FILE_UPLOAD, size, hasher.digest())))

        server = FakeServer(handler)
        server.start()
        
        result = run_client(server.port, ["UPLOAD", str(test_file)], self.work_dir)
        server.join()
        
        if server.error: raise server.error
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SHA256 Verification OK", result.stdout)

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
        import json
        import time
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

    def test_command_failure_nonzero_exit(self):
        def handler(conn):
            P.read_packet(conn)
            conn.sendall(P.pack_packet(P.ACK, 0, P.pack_ack(P.LOGIN, 999)))

            P.read_packet(conn)
            # Send an explicit ERROR back for the command
            err = P.pack_error(404, "File not found")
            conn.sendall(P.pack_packet(P.ERROR, 999, err))

        server = FakeServer(handler)
        server.start()
        
        result = run_client(server.port, ["DOWNLOAD", "missing.bin"], self.work_dir)
        server.join()
        
        if server.error: raise server.error
        self.assertEqual(result.returncode, 1)
        self.assertIn("File not found", result.stdout + result.stderr)

if __name__ == '__main__':
    unittest.main()
