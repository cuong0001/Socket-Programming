import socket
import sys
import common

#python client.py 127.0.0.1 9000 LIST
HOST = sys.argv[1] #127.0.0.1
PORT = int(sys.argv[2]) # 9000
COMMAND = sys.argv[3] #LIST

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    client.connect((HOST, PORT))
    print(f"[OK] Connected to {HOST}:{PORT}")
    print(f"[INFO] Sending command: '{COMMAND}'")
    common.send_frame(client, COMMAND.encode("utf8"))
    print("[INFO] Waiting for server response...")
    response_bytes = common.read_frame(client)
    print(response_bytes.decode("utf8"))

except ConnectionRefusedError:
    print("[ERROR] Connection refused")
except ConnectionError as e:
    print(f"[ERROR] Connection lost during transfer: {e}")
except Exception as e:
    print(f"[ERROR] Unexpected error: {e}")
finally:
    client.close()
    print("[INFO] Connection closed")