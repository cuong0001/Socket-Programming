import hashlib
import os
import socket
import sys
import time
import common
from logger import Logger

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
BASE_DIR = os.getcwd()
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
LOG_FILE = os.path.join(BASE_DIR, "logs", "server.log")

# Session log (R1.4): every CONNECT/transfer/DISCONNECT line lands in
# logs/server.log and is echoed to the console.
logger = Logger(LOG_FILE)

CHUNK_SIZE = 4096

# Incoming uploads are staged under this suffix and only renamed onto the
# real name once every declared byte has arrived. Reserved: clients may not
# use it (see valid_filename) and LIST never advertises it.
PART_SUFFIX = ".part"

# Longest command word echoed into the log. Frames may be up to 1 MiB, and
# a rejected command is logged verbatim -- without a cap a client could flood
# logs/server.log with one request.
MAX_LOGGED_VERB = 20

# Anything that could steer a path outside storage/ (path traversal):
# separators, parent-dir hops, Windows drive/stream syntax
FORBIDDEN_PARTS = ("/", "\\", "..", ":")


class FatalSessionError(Exception):
    """Mid-transfer failure: the byte stream is no longer aligned on a
    frame boundary, so this connection cannot be reused and must close."""


def valid_filename(name):
    if not name:
        return False
    if name.endswith(PART_SUFFIX):
        # Reserved for upload staging. A client-owned "x.part" would collide
        # with the staging file and then be hidden by LIST -- a file nobody
        # can see. Refuse it up front instead.
        return False
    return not any(part in name for part in FORBIDDEN_PARTS)


def _discard(path):
    """Remove a staging file, ignoring the case where it is already gone."""
    try:
        os.remove(path)
    except OSError:
        pass


def _verb(command):
    """The command word, trimmed for the log.

    The client controls this text, so cap it: a megabyte-long "command" must
    not turn into a megabyte-long log line.
    """
    return command.split(" ", 1)[0][:MAX_LOGGED_VERB] or "(empty)"


def reject(conn, ip, verb, reason):
    """Answer 'ERR <reason>' and log the refusal.

    Every command leaves exactly one record in the log (R1.4), including the
    ones that never reach a handler.
    """
    common.send_frame(conn, f"ERR {reason}".encode("utf8"))
    logger.command(ip, verb, f"ERR {reason}")


def handle_list(conn, ip):
    """Reply 'OK <count>' plus one 'size<TAB>name' line per stored file."""
    lines = []
    for entry in sorted(os.listdir(STORAGE_DIR)):
        # An upload in progress (or one orphaned by a hard kill) is not a
        # real file yet -- never advertise it
        if entry.endswith(PART_SUFFIX):
            continue
        path = os.path.join(STORAGE_DIR, entry)
        if os.path.isfile(path):
            lines.append(f"{os.path.getsize(path)}\t{entry}")

    reply = f"OK {len(lines)}"
    if lines:
        reply += "\n" + "\n".join(lines)
    common.send_frame(conn, reply.encode("utf8"))
    logger.command(ip, "LIST", f"OK {len(lines)}")


def handle_upload(conn, ip, size, name):
    """OK -> stream data frames into <name>.part until `size bytes` -> atomic commit -> ACK sha256 <digest>.

    Bytes are staged in a .part file and only renamed onto the real name once
    every declared byte has arrived. The destination is never opened while the
    transfer is in flight, so an interrupted upload cannot damage an existing
    file of the same name -- a failed upload is a no-op.
    """
    final_path = os.path.join(STORAGE_DIR, name)
    part_path = final_path + PART_SUFFIX
    try:
        f = open(part_path, "wb")
    except OSError:
        reject(conn, ip, "UPLOAD", f"cannot open {name}")
        return

    received = 0
    # Hash incrementally as bytes arrive -- never re-read the file (R1.3).
    hasher = hashlib.sha256()
    # perf_counter, not monotonic: Windows monotonic ticks in ~15.6ms steps,
    # which reads 0.0s for small files and wrecks the KB/s column (R1.4).
    started = time.perf_counter()
    try:
        with f:
            common.send_frame(conn, b"OK")  # ready to receive

            # A 0-byte file runs this loop zero times and is committed as-is
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
                hasher.update(data)
                received += len(data)
    except BaseException:
        # Discard the staging file only. Any existing file under `name` was
        # never opened, so it survives untouched.
        _discard(part_path)
        raise

    # Every declared byte arrived, and `with` has closed the file -- Windows
    # cannot rename an open file. os.replace is atomic and overwrites: `name`
    # flips straight from the old complete version to the new one, with no
    # instant where it is missing or half-written.
    try:
        os.replace(part_path, final_path)
    except OSError as e:
        # The stream is still frame-aligned, so this is recoverable: report it
        # and keep the session alive rather than dropping the connection.
        # Log e.strerror, not str(e) -- the latter embeds absolute paths.
        _discard(part_path)
        common.send_frame(conn, f"ERR cannot store {name}".encode("utf8"))
        logger.command(
            ip, "UPLOAD", f"ERR cannot store {name} ({e.strerror or type(e).__name__})"
        )
        return

    duration = time.perf_counter() - started

    # Terminal frame: our digest of the stored bytes. The client compares it
    # against the digest it computed while sending -> SHA256 OK / MISMATCH.
    common.send_frame(conn, f"ACK sha256 {hasher.hexdigest()}".encode("utf8"))
    logger.transfer(ip, "UPLOAD", name, received, duration, "SHA256-OK")


def handle_download(conn, ip, name):
    """OK <size> -> send file as 4096-byte data frames -> ACK sha256 <digest>."""
    path = os.path.join(STORAGE_DIR, name)
    if not os.path.isfile(path):
        reject(conn, ip, "DOWNLOAD", "no such file")
        return

    size = os.path.getsize(path)
    common.send_frame(conn, f"OK {size}".encode("utf8"))

    remaining = size
    # Hash incrementally as bytes leave -- never re-read the file (R1.3).
    hasher = hashlib.sha256()
    started = time.perf_counter()
    with open(path, "rb") as f:
        while remaining > 0:
            chunk = f.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                # The client was promised `size` bytes and counts on every
                # one of them; short delivery would desync the stream
                raise FatalSessionError(f"{name} shrank while sending")
            common.send_frame(conn, chunk)
            hasher.update(chunk)
            remaining -= len(chunk)

    duration = time.perf_counter() - started

    # Terminal frame: the client reads exactly `size` bytes, then this digest
    # to verify the download -> SHA256 OK / MISMATCH.
    common.send_frame(conn, f"ACK sha256 {hasher.hexdigest()}".encode("utf8"))
    logger.transfer(ip, "DOWNLOAD", name, size, duration, "SHA256-OK")


def dispatch(conn, ip, command):
    if command == "LIST":
        handle_list(conn, ip)
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
            reject(conn, ip, "UPLOAD", "bad command")
        elif not valid_filename(name):
            reject(conn, ip, "UPLOAD", "bad filename")
        else:
            handle_upload(conn, ip, size, name)
        return

    # DOWNLOAD <filename>
    if parts[0] == "DOWNLOAD" and len(parts) >= 2:
        name = command.split(" ", 1)[1]
        if not valid_filename(name):
            reject(conn, ip, "DOWNLOAD", "bad filename")
        else:
            handle_download(conn, ip, name)
        return

    reject(conn, ip, _verb(command), "bad command")


def serve_one(conn, addr):
    """Serve one client until it disconnects (many commands per connection)."""
    while True:
        command_bytes = common.read_frame(conn)

        try:
            command = command_bytes.decode("utf8")
        except UnicodeDecodeError:
            # The frame was still read whole, so the stream stays aligned:
            # answer ERR and keep the session alive
            reject(conn, addr[0], "(binary)", "bad command")
            continue

        dispatch(conn, addr[0], command)


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
    print(f"[OK] Server listening on {HOST or '0.0.0.0'}:{PORT}")
    print(f"[OK] Storage dir: {STORAGE_DIR}")

    while True:
        try:
            conn, addr = server.accept()
        except socket.timeout:
            continue  # no client yet; loop back and check for Ctrl+C
        logger.connect(addr[0])

        try:
            serve_one(conn, addr)
        except ConnectionError:
            # Normal end of a session: the client closed (cleanly or not,
            # including a kill mid-upload). The DISCONNECT line records it.
            pass
        except FatalSessionError as e:
            logger.error(addr[0], f"protocol violation: {e}")
        except Exception as e:
            # Last line of defence: no client behaviour may kill the server
            logger.error(addr[0], f"internal error: {type(e).__name__}: {e}")
        finally:
            conn.close()
            logger.disconnect(addr[0])

except KeyboardInterrupt:
    print("\n[INFO] Server shutting down")
finally:
    server.close()
    logger.close()
