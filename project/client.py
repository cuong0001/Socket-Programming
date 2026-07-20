import socket
import sys
import os
import common

#python client.py 127.0.0.1 9000 LIST
HOST = sys.argv[1] #127.0.0.1
PORT = int(sys.argv[2]) # 9000
COMMAND = sys.argv[3] if len(sys.argv) > 3 else ""

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    client.connect((HOST, PORT))
    print(f"[OK] Connected to {HOST}:{PORT}")
    
    if COMMAND:
        common.send_frame(client, COMMAND.encode("utf8"))
        response_bytes = common.read_frame(client)
        if response_bytes:
            print(f"[OK] Received {response_bytes.decode('utf8')}")
        else:
            print("[ERROR] No response from server")
    while True:
        cmd = input("\nEnter command: ").strip()
        if cmd.lower() == "exit":
            break
        if not cmd:
            continue
        if cmd.upper().startswith("UPLOAD"):
            print("[INFO] Preparing to UPLOAD...")

            # Extract filename from command (e.g., "UPLOAD path/to/file.ext")
            parts = cmd.split(" ", 1)
            if len(parts) < 2:
                print("[ERROR] Missing filename. Usage: UPLOAD <filename>")
                continue
            filepath = parts[1]

            # Check if file exists locally before starting upload
            if not os.path.isfile(filepath):
                print("[ERROR] File not found!")
                continue
            size = os.path.getsize(filepath)
            filename = os.path.basename(filepath)

            # Send upload request and wait for server permission
            req_str = f"UPLOAD {size} {filename}"
            common.send_frame(client, req_str.encode("utf8"))
            reply = common.read_frame(client).decode("utf8")
            if reply.startswith("ERR"):
                print(f"[ERROR] {reply}")
                continue

            # Server replied OK. Start streaming file data in chunks
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(4096)
                    if not chunk:
                        break
                    common.send_frame(client, chunk)
            print("[OK] Upload complete!")

            # Receive final ACK from server
            reply = common.read_frame(client).decode("utf8")
            if reply.startswith("ACK"):
                print(f"[OK] {reply}")
            else:
                print("[ERROR] Did not receive expected ACK from server")
                

        elif cmd.upper().startswith("DOWNLOAD"):
            print("[INFO] Preparing to DOWNLOAD...")
            
            # Extract filename from command
            parts = cmd.split(" ", 1)
            if len(parts) < 2:
                print("[ERROR] Missing filename. Usage: DOWNLOAD <filename>")
                continue
            filename = parts[1]

            # Send download request to server
            common.send_frame(client, cmd.encode("utf8"))
            reply = common.read_frame(client).decode("utf8")

            # Check if server rejected the request (e.g., file not found)
            if reply.startswith("ERR"):
                print(f"[ERROR] {reply}")
                continue

            # Extract file size from server's OK response (e.g., "OK 1024")
            size = int(reply.split()[1])
            local_path = "dl_" + filename
            received = 0

            # Open local file and receive data in chunks
            with open(local_path, "wb") as f:
                while received < size:
                    chunk = common.read_frame(client)
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)

                # Verify transfer completeness
                if received == size:
                    print(f"[OK] Downloaded {filename} ({received} bytes).")
                else:
                    print(f"[ERROR] Incomplete data received ({received}/{size} bytes)")

        else:
            common.send_frame(client, cmd.encode("utf8"))
            response_bytes = common.read_frame(client)
            if not response_bytes: 
                print("[INFO] Server closed the connection!")
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