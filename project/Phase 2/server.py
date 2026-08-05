import os
import socket
import sys
import threading

import protocol as P
from config import ServerConfig
from logger import Logger
from session import ErrorCode, Session
from storage_service import FileLockRegistry, StorageService
from users import UserRegistry, UsernameInUse

# python server.py 9000  [host]

# Port is the first argument -- the assignment launches the server as
# `python server.py <port>`. Default to 9000 when omitted.
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9000

# Optional host override as the second argument. Default "" binds every
# interface (INADDR_ANY), so the client can reach it on 127.0.0.1.
HOST = sys.argv[2] if len(sys.argv) > 2 else ""

# storage/ and logs/ live under the current working directory, resolved once
# at startup. Anchoring them to where the server is launched (not to server.py)
# lets the test harness isolate each run in its own temp dir and keeps test
# uploads/logs out of the real project tree. Launch from project/ for the
# normal layout; the storage path is printed at startup so it's never a guess.
config = ServerConfig()
config.host = HOST
config.port = PORT
config.storage_dir = os.path.join(os.getcwd(), "storage")
config.log_file = os.path.join(os.getcwd(), "logs", "server.log")

# Session log (R1.4): every CONNECT/transfer/DISCONNECT line lands in
# logs/server.log and is echoed to the console.
logger = Logger(config.log_file)

# Bounds concurrent clients (R2.7) and hands out the user_id each Session
# is built with. One instance shared by every worker thread.
registry = UserRegistry(config.max_clients)

# Per-(username, filename) locks and sidecar I/O, shared by every Session so
# two connections uploading the same file can't corrupt each other (R2.3/R2.7).
file_locks = FileLockRegistry()
storage = StorageService(config.storage_dir)


def _send_error(conn, uid, code, message):
    """Send a standalone ERROR packet, before a Session exists to do it."""
    conn.sendall(P.pack_packet(P.ERROR, uid, P.pack_error(code, message)))


def negotiate_login(conn, ip):
    """Block until the client completes LOGIN; return (uid, username).

    Any opcode other than LOGIN, or a LOGIN with a bad/duplicate username,
    gets an ERROR reply and the loop keeps listening -- the client can
    retry without reconnecting, matching the state machine's "wrong opcode
    never closes the connection" rule. A real disconnect surfaces as
    ConnectionError from ``P.read_packet`` and is handled by the caller.
    """
    while True:
        opcode, _uid, payload = P.read_packet(conn)

        if opcode != P.LOGIN:
            _send_error(conn, 0, ErrorCode.NOT_LOGGED_IN, "must LOGIN first")
            continue

        try:
            username, _ = P.unpack_text(payload)
        except ValueError:
            _send_error(conn, 0, ErrorCode.INVALID_USERNAME, "malformed LOGIN payload")
            continue

        if not username or not username.isprintable():
            _send_error(conn, 0, ErrorCode.INVALID_USERNAME, "invalid username")
            continue

        try:
            uid = registry.login(username)
        except UsernameInUse:
            _send_error(conn, 0, ErrorCode.USERNAME_IN_USE, f"{username} already online")
            continue

        conn.sendall(P.pack_packet(P.ACK, uid, P.pack_ack(P.LOGIN, uid)))
        logger.command(ip, "LOGIN", f"OK uid={uid} user={username}")
        return uid, username


def serve_client(conn, addr):
    """Worker-thread entry point: one Session per accepted connection."""
    ip = addr[0]
    logger.connect(ip)

    if not registry.try_acquire_slot():
        # Accept first, THEN report full -- an OS-level refusal would look
        # identical to "server is dead" from the client's side (see the
        # plan's classic-mistake list).
        try:
            _send_error(conn, 0, ErrorCode.SERVER_BUSY, "server is full")
        except OSError:
            pass
        conn.close()
        logger.disconnect(ip)
        return

    uid = None
    try:
        uid, username = negotiate_login(conn, ip)
        session = Session(conn, addr, storage.user_dir(username), logger,
                           user_id=uid, username=username,
                           file_lock_registry=file_locks, storage_service=storage)
        session.serve()
    except ConnectionError:
        # Normal end of a session: the client closed (cleanly or not).
        pass
    except Exception as e:
        # Last line of defence: no client behaviour may kill the server.
        logger.error(ip, f"internal error: {type(e).__name__}: {e}")
    finally:
        if uid is not None:
            registry.logout(uid)
        registry.release_slot()
        conn.close()
        logger.disconnect(ip)


# Windows consoles may use a legacy codepage (cp1252): printing Vietnamese
# error text would then raise UnicodeEncodeError inside an exception
# handler and kill the server. Force UTF-8, never fail on print.
sys.stdout.reconfigure(encoding="utf8", errors="replace")
sys.stderr.reconfigure(encoding="utf8", errors="replace")

# Create the socket, TCP protocol
server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

try:
    os.makedirs(config.storage_dir, exist_ok=True)
    server.bind((config.host, config.port))
    server.listen(5)
    server.settimeout(1.0)  # wake up every 1s so Ctrl+C can be handled on Windows
    print(f"[OK] Server listening on {config.host or '0.0.0.0'}:{config.port}")
    print(f"[OK] Storage dir: {config.storage_dir}")
    print(f"[OK] Max clients: {config.max_clients}")

    while True:
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue  # no client yet; loop back and check for Ctrl+C

        # daemon=True: on shutdown we don't wait for threads blocked in a
        # client's recv() -- the process exit takes them down with it.
        thread = threading.Thread(target=serve_client, args=(conn, addr), daemon=True)
        thread.start()

except KeyboardInterrupt:
    print("\n[INFO] Server shutting down")
finally:
    server.close()
    logger.close()
