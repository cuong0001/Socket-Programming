"""
resume_demo.py — Demonstrates interrupted upload resume with SHA-256 verification.
Flow:
  1. Start server as a subprocess
  2. Generate a 20 MB random test file
  3. Upload the first ~40% then forcibly close the socket (simulate network loss)
  4. Reconnect using client.py — it will auto-detect the .part offset and resume
  5. Verify the final SHA-256 matches the original file
"""

import os
import sys
import time
import socket
import hashlib
import subprocess
import tempfile
from pathlib import Path

# Windows may use a legacy console encoding (e.g. CP1252). The repository path
# can contain Vietnamese characters, so reconfigure stdout/stderr to UTF-8 to
# prevent UnicodeEncodeError when printing file paths that include those chars.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(BASE_DIR))
import protocol as P
HOST = "127.0.0.1"
PORT = 9000
USERNAME = "demo-user"
DEMO_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
CHUNK_SIZE = 4096
KILL_AFTER_BYTES = int(DEMO_FILE_SIZE * 0.40)  # Kill connection after 40%

def sha256_of_file(filepath: str) -> bytes:
    """Calculate SHA-256 hash of a local file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.digest()

def send_packet(sock, opcode, payload=b"", user_id=0):
    sock.sendall(P.pack_packet(opcode, user_id, payload))
def recv_packet(sock):
    return P.read_packet(sock)

def partial_upload(filepath: str, file_hash: bytes, filesize: int):
    """Connect, login, start upload, then forcibly close socket after KILL_AFTER_BYTES."""
    sock = socket.create_connection((HOST, PORT))

    # Step 1: Login
    send_packet(sock, P.LOGIN, payload=P.pack_text(USERNAME))
    op, uid, payload = recv_packet(sock)
    assert op == P.ACK, f"LOGIN failed: {op}"
    _, user_id, _ = P.unpack_ack(payload)
    print(f"[DEMO] Logged in as '{USERNAME}' (uid={user_id})")

    # Step 2: Send FILE_UPLOAD header
    upload_req = P.pack_upload(os.path.basename(filepath), filesize, 0, file_hash)
    send_packet(sock, P.FILE_UPLOAD, payload=upload_req, user_id=user_id)
    op, _, payload = recv_packet(sock)
    assert op == P.ACK, f"FILE_UPLOAD rejected: {op}"
    print(f"[DEMO] Server accepted upload. Starting partial transfer...")

    # Step 3: Send chunks until KILL_AFTER_BYTES, then drop connection
    sent = 0
    with open(filepath, "rb") as f:
        while sent < KILL_AFTER_BYTES:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            send_packet(sock, P.FILE_CHUNK, payload=P.pack_chunk(sent, chunk), user_id=user_id)
            sent += len(chunk)

    # Forcibly close — no LOGOUT, no EOF chunk
    sock.close()
    print(f"[DEMO] Connection killed at {sent:,} bytes ({sent/filesize*100:.1f}% of {filesize/1024/1024:.1f}MB)")

def main() -> int:
    filepath: str | None = None
    server_proc: subprocess.Popen | None = None

    try:
        # Generate test file
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".bin", dir=BASE_DIR / "testdata"
        ) as tmp:
            tmp.write(os.urandom(DEMO_FILE_SIZE))
            filepath = tmp.name

        print(f"[DEMO] Created test file: {filepath} ({DEMO_FILE_SIZE/1024/1024:.0f} MB)")
        file_hash = sha256_of_file(filepath)
        print(f"[DEMO] SHA-256: {file_hash.hex()[:16]}...")

        # Start server
        server_proc = subprocess.Popen(
            [sys.executable, "server.py"],
            cwd=str(BASE_DIR),
        )
        time.sleep(1.5)  # Wait for server to be ready
        print(f"[DEMO] Server started (pid={server_proc.pid})")

        # Partial upload then kill
        partial_upload(filepath, file_hash, DEMO_FILE_SIZE)
        time.sleep(1)  # Give server time to clean up the dropped connection

        # Resume via client.py
        print(f"\n[DEMO] Reconnecting and resuming upload...")
        result = subprocess.run(
            [sys.executable, "client.py", HOST, str(PORT),
             "--username", USERNAME, f"UPLOAD {filepath}"],
            cwd=str(BASE_DIR),
        )

        if result.returncode != 0:
            print(
                f"\n[DEMO] ❌ Resume failed (exit code {result.returncode})",
                file=sys.stderr,
            )
            return 1

        print(f"\n[DEMO] ✅ Resume successful! SHA-256 verified by server.")
        return 0

    finally:
        if server_proc is not None:
            server_proc.terminate()
            server_proc.wait()
            print("[DEMO] Server stopped.")
        if filepath is not None and os.path.exists(filepath):
            os.remove(filepath)
            print("[DEMO] Test file cleaned up.")



if __name__ == "__main__":
    raise SystemExit(main())
