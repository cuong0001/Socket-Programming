import hashlib
import socket
import sys
import os
import common
import protocol as P, struct


def send_packet(sock, opcode, payload=b"", user_id=0):
    sock.sendall(P.pack_packet(opcode, user_id, payload))

def recv_packet(sock):
    return P.read_packet(sock)


#python client.py 127.0.0.1 9000 LIST
HOST = sys.argv[1] #127.0.0.1
PORT = int(sys.argv[2]) # 9000
COMMAND = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else ""

def process_command(client, cmd):
    if not cmd:
        return True

    if cmd.upper().startswith("UPLOAD"):
        print("[INFO] Preparing to UPLOAD...")

        # Extract filename from command (e.g., "UPLOAD path/to/file.ext")
        parts = cmd.split(" ", 1)
        if len(parts) < 2:
            print("[ERROR] Missing filename. Usage: UPLOAD <filename>")
            return True
        filepath = parts[1]

        # Check if file exists locally before starting upload
        if not os.path.isfile(filepath):
            print("[ERROR] File not found!")
            return True
        size = os.path.getsize(filepath)
        filename = os.path.basename(filepath)

        # Send upload request and wait for server permission
        req_str = f"UPLOAD {size} {filename}"
        common.send_frame(client, req_str.encode("utf8"))
        reply = common.read_frame(client).decode("utf8")
        if reply.startswith("ERR"):
            print(f"[ERROR] {reply}")
            return True

        hasher = hashlib.sha256()

        # Server replied OK. Start streaming file data in chunks
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                common.send_frame(client, chunk)
                hasher.update(chunk)
        print("[OK] Upload complete! Waiting for SHA256 verification...")

        # Receive final ACK from server
        reply = common.read_frame(client).decode("utf8")
        if reply.startswith("ACK"):
            print(f"[OK] {reply}")
        else:
            print("[ERROR] Did not receive expected ACK from server")

        local_digest = hasher.hexdigest()
        if reply.startswith("ACK sha256 "):
            server_digest = reply.split(" ")[2].strip()
            if local_digest == server_digest:
                print(f"[OK] SHA256 OK")
            else:
                print(f"[ERROR] MISMATCH")
                print(f"  -> Local Hash : {local_digest}")  
                print(f"  -> Server Hash: {server_digest}")  
                sys.exit(1) 
        else:
            print(f"[ERROR] Invalid response from server")
            sys.exit(1)
        return True
        
    elif cmd.upper().startswith("DOWNLOAD"):
        print("[INFO] Preparing to DOWNLOAD...")
        
        # Extract filename from command
        parts = cmd.split(" ", 1)
        if len(parts) < 2:
            print("[ERROR] Missing filename. Usage: DOWNLOAD <filename>")
            return True
        filename = os.path.basename(parts[1].strip())

        # Send download request to server
        common.send_frame(client, cmd.encode("utf8"))
        reply = common.read_frame(client).decode("utf8")

        # Check if server rejected the request (e.g., file not found)
        if reply.startswith("ERR"):
            print(f"[ERROR] {reply}")
            return True

        # Extract file size from server's OK response (e.g., "OK 1024")
        size = int(reply.split()[1])
        downloads_dir = "downloads"
        os.makedirs(downloads_dir, exist_ok=True)
        local_path = os.path.join(downloads_dir, filename)
        part_path = local_path + ".part"
        received = 0
        hasher = hashlib.sha256()

        try:
        # Open local file and receive data in chunks
            with open(part_path, "wb") as f:
                while received < size:
                    chunk = common.read_frame(client)
                    if not chunk:
                        break
                    f.write(chunk)
                    hasher.update(chunk)
                    received += len(chunk)

            # Verify transfer completeness
            if received == size:
                print(f"[OK] Downloaded {filename} ({received} bytes). Verifying SHA256...")
                
                # Receive final ACK frame containing server's SHA256 digest
                reply = common.read_frame(client).decode("utf8")
                local_digest = hasher.hexdigest()
                
                # Ensure server replied with a valid SHA256 format before parsing
                if reply.startswith("ACK sha256 "):
                    server_digest = reply.split(" ")[2].strip()
                    
                    # Compare the local hash with the server's hash
                    if local_digest == server_digest:
                        print(f"[OK] SHA256 OK")
                        os.replace(part_path, local_path)
                    else:
                        print(f"[ERROR] MISMATCH")
                        print(f"  -> Local Hash : {local_digest}")  
                        print(f"  -> Server Hash: {server_digest}") 
                        os.remove(part_path)
                        sys.exit(1)

                else:
                    print(f"[ERROR] Invalid response from server: {reply}")
                    os.remove(part_path)
                    sys.exit(1)
            else:
                print(f"[ERROR] Incomplete data received ({received}/{size} bytes)")
            return True
        except Exception:
            try:
                os.remove(part_path)
            except OSError:
                pass
            raise

    else:
        send_packet(client, P.FILE_LIST, user_id=uid)
        op, uid, data = recv_packet(client)
        if op == P.FILE_LIST_RESP:
            for name, size in P.unpack_file_list_response(data):
                print(f"{size}\t{name}")
        elif op == P.ERROR:
            code, msg = struct.unpack("!HH", data[:4]); print(f"ERR {code}: {data[4:].decode()}")
        
        return True


client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    client.connect((HOST, PORT))
    print(f"[OK] Connected to {HOST}:{PORT}")
    
    if COMMAND:
        process_command(client, COMMAND)
    else:
        while True:
            cmd = input("\nEnter command: ").strip()
            if cmd.lower() == "exit":
                break
            is_connected = process_command(client, cmd)
            if not is_connected:
                break

except ConnectionRefusedError:
    print("[ERROR] Connection refused")
except ConnectionError as e:
    print(f"[ERROR] Connection lost during transfer: {e}")
except Exception as e:
    print(f"[ERROR] Unexpected error: {e}")
finally:
    client.close()
    print("[INFO] Connection closed")