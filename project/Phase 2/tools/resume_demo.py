"""
resume_demo.py — Demonstrates interrupted upload AND download resume with SHA-256 verification.
Flow:
  1. Start server as a subprocess
  2. Generate a 20 MB random test file
  3. Upload Phase 1 — upload to ~37%, forcibly close socket (simulate network loss)
  4. Upload Phase 2 — reconnect, server reports offset ~37%, continue to ~73%, close again
  5. Upload Phase 3 — reconnect via client.py, server reports offset ~73%, finish to 100%
  6. Download Phase 1 — download to ~50%, forcibly close socket
  7. Download Phase 2 — reconnect via client.py, resume from ~50%, finish to 100%
  8. Verify final downloaded file SHA-256 matches the original
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
DEMO_FILE_SIZE = 20 * 1024 * 1024   # 20 MB
CHUNK_SIZE = 4096
KILL_AT_37 = int(DEMO_FILE_SIZE * 0.37)  # ~7.7 MB — first upload interrupt
KILL_AT_73 = int(DEMO_FILE_SIZE * 0.73)  # ~15.3 MB — second upload interrupt
KILL_DOWNLOAD_AT_50 = DEMO_FILE_SIZE // 2  # ~10 MB — download interrupt point

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

def partial_upload(filepath: str, file_hash: bytes, filesize: int, kill_after: int):
    """Connect, login, start upload from server-reported resume offset, kill at kill_after bytes."""
    sock = socket.create_connection((HOST, PORT))

    # Step 1: Login
    send_packet(sock, P.LOGIN, payload=P.pack_text(USERNAME))
    op, uid, payload = recv_packet(sock)
    assert op == P.ACK, f"LOGIN failed: {op}"
    _, user_id, _ = P.unpack_ack(payload)
    print(f"[DEMO] Logged in as '{USERNAME}' (uid={user_id})")

    # Step 2: Send FILE_UPLOAD header (offset=0; server replies with actual resume offset)
    upload_req = P.pack_upload(os.path.basename(filepath), filesize, 0, file_hash)
    send_packet(sock, P.FILE_UPLOAD, payload=upload_req, user_id=user_id)
    op, _, ack_payload = recv_packet(sock)
    assert op == P.ACK, f"FILE_UPLOAD rejected: {op}"

    # Server ACK contains the current .part size — this is where we must continue from
    _, resume_offset, _ = P.unpack_ack(ack_payload)
    print(f"[DEMO] Server offset (before): {resume_offset:,} bytes ({resume_offset/filesize*100:.1f}%)")
    print(f"[DEMO] Streaming from {resume_offset/filesize*100:.1f}% to {kill_after/filesize*100:.1f}%...")

    # Step 3: Send chunks from resume_offset to kill_after, then drop connection
    sent = resume_offset
    with open(filepath, "rb") as f:
        f.seek(resume_offset)
        while sent < kill_after:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            send_packet(sock, P.FILE_CHUNK, payload=P.pack_chunk(sent, chunk), user_id=user_id)
            sent += len(chunk)

    # Forcibly close — no LOGOUT, no EOF chunk
    sock.close()
    print(f"[DEMO] Connection killed at {sent:,} bytes ({sent/filesize*100:.1f}% of {filesize/1024/1024:.1f}MB)")


def partial_download(filename: str, kill_after: int, downloads_dir: str, filesize: int):
    """Connect, login, start download from offset 0, save chunks, kill at kill_after bytes."""
    from resume import write_sidecar

    sock = socket.create_connection((HOST, PORT))

    # Login
    send_packet(sock, P.LOGIN, payload=P.pack_text(USERNAME))
    op, uid, payload = recv_packet(sock)
    assert op == P.ACK, f"LOGIN failed: {op}"
    _, user_id, _ = P.unpack_ack(payload)
    print(f"[DEMO] Logged in as '{USERNAME}' (uid={user_id})")

    # Request download from offset 0
    send_packet(sock, P.FILE_DOWNLOAD, payload=P.pack_download(filename, 0), user_id=user_id)
    op, _, ack_payload = recv_packet(sock)
    assert op == P.ACK, f"FILE_DOWNLOAD rejected: {op}"
    _, total_size, server_digest = P.unpack_ack(ack_payload)
    print(f"[DEMO] Server offset (before download): 0 bytes (0.0%)")
    print(f"[DEMO] Receiving from 0.0% to {kill_after/total_size*100:.1f}%...")

    # Write sidecar so client.py can validate on resume
    write_sidecar(downloads_dir, filename, total_size, server_digest)

    # Receive chunks until kill_after bytes, save to .part file
    part_path = os.path.join(downloads_dir, filename + ".part")
    received = 0
    with open(part_path, "wb") as f:
        while received < kill_after:
            op, _, chunk_payload = recv_packet(sock)
            if op != P.FILE_CHUNK:
                break
            _, data = P.unpack_chunk(chunk_payload)
            f.write(data)
            received += len(data)

    # Forcibly close — no LOGOUT, leaves .part file for resume
    sock.close()
    print(f"[DEMO] Download killed at {received:,} bytes ({received/total_size*100:.1f}% of {total_size/1024/1024:.1f}MB)")

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

        # Phase 1: upload to ~37%, then interrupt
        print("\n[DEMO] === Phase 1: upload to 37%, then interrupt ===")
        partial_upload(filepath, file_hash, DEMO_FILE_SIZE, kill_after=KILL_AT_37)
        time.sleep(1)  # Give server time to finalize the dropped connection

        # Phase 2: reconnect, resume from ~37%, upload to ~73%, then interrupt
        print("\n[DEMO] === Phase 2: resume from 37%, upload to 73%, then interrupt ===")
        partial_upload(filepath, file_hash, DEMO_FILE_SIZE, kill_after=KILL_AT_73)
        time.sleep(1)

        # Phase 3: reconnect via client.py, resume from ~73%, finish to 100%
        print("\n[DEMO] === Phase 3: resume from 73% to 100% via client.py ===")
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

        print(f"\n[DEMO] ✅ Two-interrupt upload resume successful! SHA-256 verified by server.")

        # ── Download resume demo ─────────────────────────────────────────────
        filename = os.path.basename(filepath)
        downloads_dir = str(BASE_DIR / "downloads")
        os.makedirs(downloads_dir, exist_ok=True)

        # Download Phase 1: download to ~50%, kill connection
        print("\n[DEMO] === Download Phase 1: download to 50%, then interrupt ===")
        partial_download(filename, KILL_DOWNLOAD_AT_50, downloads_dir, DEMO_FILE_SIZE)
        time.sleep(1)

        # Download Phase 2: resume via client.py from ~50% to 100%
        print("\n[DEMO] === Download Phase 2: resume from 50% to 100% via client.py ===")
        dl_result = subprocess.run(
            [sys.executable, "client.py", HOST, str(PORT),
             "--username", USERNAME, f"DOWNLOAD {filename}"],
            cwd=str(BASE_DIR),
        )

        if dl_result.returncode != 0:
            print(
                f"\n[DEMO] ❌ Download resume failed (exit code {dl_result.returncode})",
                file=sys.stderr,
            )
            return 1

        print(f"\n[DEMO] ✅ Download resume successful! SHA-256 verified by client.")
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
