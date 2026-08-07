import hashlib
import socket
import sys
import os
import common
import protocol as P
import struct
import argparse
from progress import ProgressRenderer
from rate_limit import TokenBucket

sys.stdout.reconfigure(encoding="utf8", errors="replace")
sys.stderr.reconfigure(encoding="utf8", errors="replace")

def send_packet(sock, opcode, payload=b"", user_id=0):
    sock.sendall(P.pack_packet(opcode, user_id, payload))

def recv_packet(sock):
    return P.read_packet(sock)

def process_command(client, cmd, uid, limit_bps=0 ):
    if not cmd:
        return True

    if cmd.upper().startswith("UPLOAD"):
        print("[INFO] Preparing to UPLOAD...")
        parts = cmd.split(" ", 1)
        if len(parts) < 2:
            print("[ERROR] Missing filename. Usage: UPLOAD <filename>")
            return True
        filepath = parts[1]

        if not os.path.isfile(filepath):
            print("[ERROR] File not found!")
            return False

        size = os.path.getsize(filepath)
        filename = os.path.basename(filepath)

        from file_handler import sha256_file
        print("[INFO] Calculating SHA-256 for upload validation...")
        sha256_digest = sha256_file(filepath)

        # 1. Send FILE_UPLOAD request (Client always starts by proposing offset 0)
        upload_req = P.pack_upload(filename, size, 0, sha256_digest)
        send_packet(client, P.FILE_UPLOAD, payload=upload_req, user_id=uid)

        # 2. Wait for ACK from server to begin transfer
        op, _, payload = recv_packet(client)
        if op == P.ERROR:
            code, msg = P.unpack_error(payload)
            print(f"[ERROR] Server rejected upload ({code}): {msg}")
            return False
        elif op != P.ACK:
            print(f"[ERROR] Expected ACK, got {op}")
            return False

        acked_opcode, next_offset, _ = P.unpack_ack(payload)
        if acked_opcode != P.FILE_UPLOAD:
            print(f"[ERROR] Expected ACK for FILE_UPLOAD, got {acked_opcode}")
            return False

        # Server tells us where to start (resuming if > 0)
        start_offset = next_offset
        if not (0 <= start_offset <= size):
            print(f"[ERROR] Invalid resume offset {start_offset} for file size {size}")
            return False
        if start_offset > 0:
            print(f"[INFO] Resuming upload from {start_offset} bytes...")

        # 3. Stream chunks using Phase 2 FILE_CHUNK

        # Create rate limiter and progress bar for upload
        bucket = TokenBucket(limit_bps)
        progress = ProgressRenderer(filename, size, start_offset)

        sent = start_offset
        with open(filepath, "rb") as f:
            f.seek(start_offset)
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break

                bucket.consume(len(chunk))
                send_packet(client, P.FILE_CHUNK, payload=P.pack_chunk(sent, chunk), user_id=uid)
                sent += len(chunk)
                progress.update(sent)
        print("[OK] Upload stream finished! Waiting for server SHA256 verification...")

        # 4. Receive final ACK from server
        op, _, payload = recv_packet(client)
        if op == P.ACK:
            _, _, server_digest = P.unpack_ack(payload)
            if server_digest == sha256_digest:
                print(f"[OK] SHA256 Verification OK")
                progress.done()
            else:
                print(f"[ERROR] SHA256 MISMATCH")
                print(f"  -> Local Hash : {sha256_digest.hex()}")
                print(f"  -> Server Hash: {server_digest.hex()}")
                sys.exit(1)
        elif op == P.ERROR:
            code, msg = P.unpack_error(payload)
            print(f"[ERROR] Upload failed ({code}): {msg}")
            sys.exit(1)
        else:
            print(f"[ERROR] Invalid response from server")
            sys.exit(1)

        return True

    elif cmd.upper().startswith("DOWNLOAD"):
        print("[INFO] Preparing to DOWNLOAD...")
        parts = cmd.split(" ", 1)
        if len(parts) < 2:
            print("[ERROR] Missing filename. Usage: DOWNLOAD <filename>")
            return True
        filename = os.path.basename(parts[1].strip())

        from resume import get_download_offset, write_sidecar, validate_sidecar, commit_download, cleanup_staging
        downloads_dir = "downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        local_offset = get_download_offset(downloads_dir, filename)

        # 1. Send FILE_DOWNLOAD request
        download_req = P.pack_download(filename, local_offset)
        send_packet(client, P.FILE_DOWNLOAD, payload=download_req, user_id=uid)

        # 2. Wait for ACK from server containing total_size and sha256
        op, _, payload = recv_packet(client)
        if op == P.ERROR:
            code, msg = P.unpack_error(payload)
            print(f"[ERROR] Server rejected download ({code}): {msg}")
            return False
        elif op != P.ACK:
            print(f"[ERROR] Expected ACK, got {op}")
            return False

        acked_opcode, total_size, server_digest = P.unpack_ack(payload)
        if acked_opcode != P.FILE_DOWNLOAD:
            print(f"[ERROR] Expected ACK for FILE_DOWNLOAD, got {acked_opcode}")
            return False

        # Validate sidecar if resuming
        if local_offset > 0:
            if not validate_sidecar(downloads_dir, filename, total_size, server_digest):
                print("[WARN] Invalid sidecar or file changed. Staging files cleared. Connection dropped. Please try again.")
                cleanup_staging(downloads_dir, filename)
                return False
            else:
                print(f"[INFO] Resuming download from {local_offset} bytes...")

        # Save sidecar
        write_sidecar(downloads_dir, filename, total_size, server_digest)

        # 3. Stream chunks using Phase 2 FILE_CHUNK

        part_path = os.path.join(downloads_dir, filename + ".part")
        received = local_offset
        hasher = hashlib.sha256()

        # Create rate limiter and progress bar for download
        bucket = TokenBucket(limit_bps)
        progress = ProgressRenderer(filename, total_size, local_offset)

        try:
            mode = "ab" if local_offset > 0 else "wb"
            with open(part_path, mode) as f:
                # Need to hash existing data if resuming to verify at the end
                if local_offset > 0:
                    with open(part_path, "rb") as existing_f:
                        while True:
                            old_chunk = existing_f.read(4096)
                            if not old_chunk: break
                            hasher.update(old_chunk)

                while received < total_size:
                    op, _, chunk_payload = recv_packet(client)
                    if op == P.ERROR:
                        code, msg = P.unpack_error(chunk_payload)
                        print(f"\n[ERROR] Server aborted transfer ({code}): {msg}")
                        return True
                    if op != P.FILE_CHUNK:
                        print(f"\n[ERROR] Expected FILE_CHUNK, got {op}")
                        return True

                    chunk_offset, data = P.unpack_chunk(chunk_payload)

                    bucket.consume(len(data))

                    if chunk_offset != received:
                        print(f"\n[ERROR] Out of order chunk. Expected {received}, got {chunk_offset}")
                        return True

                    f.write(data)
                    hasher.update(data)
                    received += len(data)
                    progress.update(received)

            # Verify hash
            local_digest = hasher.digest()
            if local_digest == server_digest:
                print(f"[OK] SHA256 Verification OK")
                commit_download(downloads_dir, filename)
                cleanup_staging(downloads_dir, filename)
                progress.done()
            else:
                print(f"[ERROR] SHA256 MISMATCH")
                print(f"  -> Local Hash : {local_digest.hex()}")
                print(f"  -> Server Hash: {server_digest.hex()}")
                cleanup_staging(downloads_dir, filename)
                sys.exit(1)

        except Exception as e:
            print(f"\n[ERROR] Download interrupted: {e}")
            raise

        return True

    elif cmd.upper().startswith("DELETE"):
        parts = cmd.split(" ", 1)
        if len(parts) < 2:
            print("[ERROR] Missing filename. Usage: DELETE <filename>")
            return True
        filename = os.path.basename(parts[1].strip())
        print(f"[INFO] Requesting to DELETE {filename}...")

        send_packet(client, P.FILE_DELETE, payload=P.pack_text(filename), user_id=uid)

        op, _, payload = recv_packet(client)

        if op == P.ACK:
            acked_opcode, _, _ = P.unpack_ack(payload)
            if acked_opcode != P.FILE_DELETE:
                print(f"[ERROR] Expected ACK for FILE_DELETE, got {acked_opcode}")
                return False
            print(f"[OK] File '{filename}' has been deleted from server.")
            return True
        elif op == P.ERROR:
            code, msg = P.unpack_error(payload)
            print(f"[ERROR] Failed to delete '{filename}' ({code}): {msg}")
            return False
        else:
            print(f"[ERROR] Expected ACK or ERROR, got {op}")
            return False

    else:
        send_packet(client, P.FILE_LIST, user_id=uid)
        op, _, data = recv_packet(client)
        if op == P.FILE_LIST_RESP:
            for name, size in P.unpack_file_list_response(data):
                print(f"{size}\t{name}")
        elif op == P.ERROR:
            code, msg = P.unpack_error(data); print(f"ERR {code}: {msg}")
            return False

        return True

def main():
    parser = argparse.ArgumentParser(description="Phase 2 File Transfer Client")
    parser.add_argument("host", help="Server host IP")
    parser.add_argument("port", type=int, help="Server port")
    parser.add_argument("--username", required=True, help="Username to login")
    parser.add_argument("--limit", type=int, default=0, help="Bandwidth limit in KB/s (0 for unlimited)")
    parser.add_argument("command", nargs="*", help="Command to execute")
    args = parser.parse_args()

    cmd_str = " ".join(args.command).strip()

    # KB/s -> Bytes/s
    limit_bps = args.limit * 1024

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        client.connect((args.host, args.port))
        print(f"[OK] Connected to {args.host}:{args.port}")

        # Must login first to acquire a valid uid from the server
        send_packet(client, P.LOGIN, payload=P.pack_text(args.username))
        op, _, payload = recv_packet(client)

        if op == P.ERROR:
            code, msg = P.unpack_error(payload)
            print(f"[ERROR] LOGIN failed ({code}): {msg}")
            sys.exit(1)

        if op != P.ACK:
            print(f"[ERROR] Unexpected opcode {op} during login")
            sys.exit(1)

        # Unpack the ACK packet to extract the user_id
        acked_opcode, uid, _ = P.unpack_ack(payload)
        if acked_opcode != P.LOGIN:
            print(f"[ERROR] Expected ACK for LOGIN, got ACK for {acked_opcode}")
            sys.exit(1)

        if cmd_str:
            if not process_command(client, cmd_str, uid, limit_bps):
                sys.exit(1)
        else:
            while True:
                cmd = input("\nEnter command: ").strip()
                if cmd.lower() == "exit":
                    break
                process_command(client, cmd, uid, limit_bps)

    except ConnectionRefusedError:
        print("[ERROR] Connection refused")
        sys.exit(1)
    except ConnectionError as e:
        print(f"[ERROR] Connection lost during transfer: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        sys.exit(1)
    finally:
        client.close()
        print("[INFO] Connection closed")

if __name__ == "__main__":
    main()
