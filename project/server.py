import os
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

# storage/ sits next to server.py so the server works no matter
# which directory it is launched from
STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "storage")

CHUNK_SIZE = 4096

# Anything that could steer a path outside storage/ (path traversal):
# separators, parent-dir hops, Windows drive/stream syntax
FORBIDDEN_PARTS = ("/", "\\", "..", ":")


class FatalSessionError(Exception):
    """Mid-transfer failure: the byte stream is no longer aligned on a
    frame boundary, so this connection cannot be reused and must close."""


def valid_filename(name):
    if not name:
        return False
    return not any(part in name for part in FORBIDDEN_PARTS)


def handle_list(conn):
    """Reply 'OK <count>' plus one 'size<TAB>name' line per stored file."""
    lines = []
    for entry in sorted(os.listdir(STORAGE_DIR)):
        path = os.path.join(STORAGE_DIR, entry)
        if os.path.isfile(path):
            lines.append(f"{os.path.getsize(path)}\t{entry}")

    reply = f"OK {len(lines)}"
    if lines:
        reply += "\n" + "\n".join(lines)
    common.send_frame(conn, reply.encode("utf8"))


def handle_upload(conn, size, name):
    """OK -> receive data frames until `size` bytes -> ACK <size>."""
    path = os.path.join(STORAGE_DIR, name)
    try:
        f = open(path, "wb")
    except OSError:
        common.send_frame(conn, f"ERR cannot open {name}".encode("utf8"))
        return

    received = 0
    try:
        with f:
            common.send_frame(conn, b"OK")  # ready to receive

            # A 0-byte file runs this loop zero times and is ACKed right away
            while received < size:
                data = common.read_frame(conn)
                if not data:
                    raise FatalSessionError("empty data frame during upload")
                if received + len(data) > size:
                    common.send_frame(conn, b"ERR too many bytes")
                    raise FatalSessionError(
                        f"client declared {size} bytes but sent more"
                    )
                f.write(data)
                received += len(data)
    except BaseException:
        # Half-written upload: delete it so LIST never shows a broken file
        try:
            os.remove(path)
        except OSError:
            pass
        raise

    common.send_frame(conn, f"ACK {received}".encode("utf8"))


def handle_download(conn, name):
    """OK <size> -> send the file as 4096-byte data frames."""
    path = os.path.join(STORAGE_DIR, name)
    if not os.path.isfile(path):
        common.send_frame(conn, b"ERR no such file")
        return

    size = os.path.getsize(path)
    common.send_frame(conn, f"OK {size}".encode("utf8"))

    remaining = size
    with open(path, "rb") as f:
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                # The client was promised `size` bytes and counts on every
                # one of them; short delivery would desync the stream
                raise FatalSessionError(f"{name} shrank while sending")
            common.send_frame(conn, chunk)
            remaining -= len(chunk)


def dispatch(conn, command):
    if command == "LIST":
        handle_list(conn)
        return

    parts = command.split(" ", 2)

    # UPLOAD <size> <filename> -- size first because the name may
    # contain spaces, so the name is always the tail of the command
    if parts[0] == "UPLOAD" and len(parts) == 3:
        try:
            size = int(parts[1])
        except ValueError:
            size = -1
        name = parts[2]
        if size < 0:
            common.send_frame(conn, b"ERR bad command")
        elif not valid_filename(name):
            common.send_frame(conn, b"ERR bad filename")
        else:
            handle_upload(conn, size, name)
        return

    # DOWNLOAD <filename>
    if parts[0] == "DOWNLOAD" and len(parts) >= 2:
        name = command.split(" ", 1)[1]
        if not valid_filename(name):
            common.send_frame(conn, b"ERR bad filename")
        else:
            handle_download(conn, name)
        return

    common.send_frame(conn, b"ERR bad command")


def serve_one(conn, addr):
    """Serve one client until it disconnects (many commands per connection)."""
    while True:
        command_bytes = common.read_frame(conn)

        try:
            command = command_bytes.decode("utf8")
        except UnicodeDecodeError:
            # The frame was still read whole, so the stream stays aligned:
            # answer ERR and keep the session alive
            common.send_frame(conn, b"ERR bad command")
            continue

        print(f"[INFO] {addr[0]}:{addr[1]} -> {command!r}")
        dispatch(conn, command)


# Windows consoles may use a legacy codepage (cp1252): printing Vietnamese
# error text from common.py would then raise UnicodeEncodeError inside an
# exception handler and kill the server. Force UTF-8, never fail on print.
sys.stdout.reconfigure(encoding="utf8", errors="replace")
sys.stderr.reconfigure(encoding="utf8", errors="replace")

# Create the socket, TCP protocol
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    os.makedirs(STORAGE_DIR, exist_ok=True)
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
            serve_one(conn, addr)
        except ConnectionError as e:
            # Normal end of a session: the client closed (cleanly or not)
            print(f"[INFO] Client disconnected: {e}")
        except FatalSessionError as e:
            print(f"[ERROR] Protocol violation from {addr[0]}: {e}")
        except Exception as e:
            # Last line of defence: no client behaviour may kill the server
            print(f"[ERROR] Unexpected error: {type(e).__name__}: {e}")
        finally:
            conn.close()
            print("[INFO] Client connection closed")

except KeyboardInterrupt:
    print("\n[INFO] Server shutting down")
finally:
    server.close()
