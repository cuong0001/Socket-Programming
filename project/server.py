import socket
import sys
import common

# python server.py 127.0.0.1 9000

# If the command line includes host's ip address then use it
# Otherwise default to loopback address 127.0.0.1
HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1" 

# If the command line includes port then use it
# Otherwise default to port 9000
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9000

# Create the socket, TCP protocol
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    server.bind((HOST, PORT))
    server.listen(5)
    server.settimeout(1.0)  # wake up every 1s so Ctrl+C can be handled on Windows
    print(f"[OK] Server listening on {HOST}:{PORT}")

    while True:
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue  # no client yet; loop back and check for Ctrl+C
        print(f"[INFO] Connection from {addr[0]}:{addr[1]}")

        try:
            command_bytes = common.read_frame(conn)
            command = command_bytes.decode("utf8")
            print(f"[INFO] Received command: '{command}'")

            reply = f"Server received: {command}"
            common.send_frame(conn, reply.encode("utf8"))

        except ConnectionError as e:
            print(f"[ERROR] Connection lost: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error: {e}")
        finally:
            conn.close()
            print("[INFO] Client connection closed")

except KeyboardInterrupt:
    print("\n[INFO] Server shutting down")
finally:
    server.close()
