import hashlib
import socket
import sys
import os
import common

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
        else:
            print(f"[ERROR] Invalid response from server")
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
        local_path = "dl_" + filename
        received = 0
        hasher = hashlib.sha256()

        # Open local file and receive data in chunks
        with open(local_path, "wb") as f:
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
            reply_bytes = common.read_frame(client).decode("utf8")
            local_digest = hasher.hexdigest()
            
            # Ensure server replied with a valid SHA256 format before parsing
            if reply_bytes.startswith("ACK sha256 "):
                server_digest = reply_bytes.split(" ")[2].strip()
                
                # Compare the local hash with the server's hash
                if local_digest == server_digest:
                    print(f"[OK] SHA256 OK")
                else:
                    print(f"[ERROR] MISMATCH")
                    print(f"  -> Local Hash : {local_digest}")  
                    print(f"  -> Server Hash: {server_digest}") 
            else:
                print(f"[ERROR] Invalid response from server: {reply_bytes}")
        else:
            print(f"[ERROR] Incomplete data received ({received}/{size} bytes)")
        return True

    else:
        common.send_frame(client, cmd.encode("utf8"))
        response_bytes = common.read_frame(client)
        if not response_bytes: 
            print("[INFO] Server closed the connection!")
            return False
        print(f"--- SERVER RESPONSE ---\n{response_bytes.decode('utf8')}")
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