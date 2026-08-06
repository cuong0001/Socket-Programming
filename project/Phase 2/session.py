"""Phase 2 session handler — one instance per connected client.

Each worker thread created by the accept loop wraps the socket in a Session
and calls ``session.serve()``.  The session implements a strict state machine
so opcodes received in the wrong state are refused cleanly (ERROR packet)
rather than causing undefined behaviour.

State machine
-------------

::

    CONNECTED ──LOGIN──▶ AUTHENTICATED ──FILE_UPLOAD──▶ UPLOADING
                                │                             │
                          FILE_DOWNLOAD                   FILE_CHUNK(×N)
                                │                             │
                           DOWNLOADING                  received==total
                                │                        ▼ checksum OK
                          server sends                AUTHENTICATED
                          FILE_CHUNK(×N)               (os.replace)
                          ACK final
                                │
                             LOGOUT ──▶ CLOSED  (cleanup idempotent)

Opcodes not in the current state's allow-set receive an ERROR packet; the
connection stays open so the client can recover.
"""

import os
import time

import protocol as P
from enum import Enum, auto

from file_handler import CHUNK_SIZE, read_chunks, sha256_file, sha256_incremental


# ────────────────────────────────────────────────────────────
# State machine
# ────────────────────────────────────────────────────────────

class State(Enum):
    """Session state — determines which opcodes the server will accept."""
    CONNECTED     = auto()   # only LOGIN allowed
    AUTHENTICATED = auto()   # LIST / UPLOAD / DOWNLOAD / DELETE / LOGOUT
    UPLOADING     = auto()   # only FILE_CHUNK (with correct offset)
    DOWNLOADING   = auto()   # server is sending — client waits
    CLOSED        = auto()   # cleanup done


# Opcode → allowed states (white-list)
_ALLOWED: dict[State, set[int]] = {
    State.CONNECTED:     {P.LOGIN},
    State.AUTHENTICATED: {P.FILE_LIST, P.FILE_UPLOAD, P.FILE_DOWNLOAD,
                          P.FILE_DELETE, P.LOGOUT},
    State.UPLOADING:     {P.FILE_CHUNK, P.LOGOUT},  # LOGOUT mid-upload keeps .part
    # DOWNLOADING: server drives — nothing accepted from client
}


# ────────────────────────────────────────────────────────────
# Error codes (mirror the mini-RFC in the plan)
# ────────────────────────────────────────────────────────────

class ErrorCode:
    MALFORMED           = 0x0064   # 100
    UNKNOWN_OPCODE      = 0x0065   # 101
    INVALID_USERNAME    = 0x0066   # 102
    NOT_LOGGED_IN       = 0x0067   # 103
    USER_ID_MISMATCH    = 0x0068   # 104
    USERNAME_IN_USE     = 0x0069   # 105
    INVALID_FILENAME    = 0x006E   # 110
    NOT_FOUND           = 0x006F   # 111
    FILE_EXISTS         = 0x0070   # 112
    OFFSET_MISMATCH     = 0x0071   # 113
    CHECKSUM_MISMATCH   = 0x0072   # 114
    RESUME_CONFLICT     = 0x0073   # 115
    SERVER_BUSY         = 0x0078   # 120
    FILE_BUSY           = 0x0079   # 121
    INTERNAL_ERROR      = 0x0082   # 130


# ────────────────────────────────────────────────────────────
# Protocol helpers
# ────────────────────────────────────────────────────────────

class ProtocolError(Exception):
    """Raised when the byte stream is no longer aligned on a packet boundary
    and the connection must be closed."""


# ────────────────────────────────────────────────────────────
# Filename validation (migrated from Phase 1 server.py)
# ────────────────────────────────────────────────────────────

PART_SUFFIX = ".part"
SIDECAR_SUFFIX = ".part.json"
BAD_SUFFIX = ".part.bad"  # quarantined upload that failed checksum verification

FORBIDDEN_PARTS = ("/", "\\", "..", ":")

WINDOWS_DEVICE_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{d}" for d in range(1, 10)]
    + [f"LPT{d}" for d in range(1, 10)]
)


def _normalized(name: str) -> str:
    """The name the filesystem will really use (Windows strips trailing dots)."""
    return name.rstrip(". ")


def _safe_path_component(name: str) -> bool:
    """True if ``name`` is safe to use as exactly one path segment.

    Shared by filenames and usernames -- both get joined onto a server-side
    directory and must not be able to add extra segments (``/``, ``\\``,
    ``..``), name a drive (``:``), or collide with a reserved Windows device
    name.
    """
    if not name:
        return False
    if not name.isprintable():
        return False
    if _normalized(name) != name:
        return False
    if name.split(".")[0].upper() in WINDOWS_DEVICE_NAMES:
        return False
    return not any(part in name for part in FORBIDDEN_PARTS)


def valid_filename(name: str) -> bool:
    """Accept only names we can store under exactly the name we were given."""
    if not _safe_path_component(name):
        return False
    if name.casefold().endswith(PART_SUFFIX):
        return False
    if name.casefold().endswith(SIDECAR_SUFFIX):
        return False
    if name.casefold().endswith(BAD_SUFFIX):
        return False
    return True


def valid_username(name: str) -> bool:
    """Accept only usernames safe to use as ``storage/<username>/``.

    Same path-segment rules as ``valid_filename`` -- a username is joined
    onto the storage root exactly like a filename is, so ``..``/``/``/``\\``
    would escape it (e.g. username ``..`` writes outside ``storage/``
    entirely) unless rejected here.
    """
    return _safe_path_component(name)


# ────────────────────────────────────────────────────────────
# Session class
# ────────────────────────────────────────────────────────────

class Session:
    """Handle one client's full lifecycle after its socket has been accepted.

    The caller (server accept loop) is responsible for:
    - LOGIN negotiation (so ``user_id`` and ``username`` are known on entry)
    - cleanup: ``UserRegistry.logout()`` and ``conn.close()`` in ``finally``

    This class owns the dispatch loop and all file-operation handlers.
    """

    def __init__(self, conn, addr, storage_dir, logger,
                 user_id: int = 0,
                 username: str = "",
                 file_lock_registry=None,
                 storage_service=None):
        self.conn = conn
        self.addr = addr
        self.ip = addr[0]
        self.storage_dir = storage_dir
        self.logger = logger
        self.user_id = user_id
        self.username = username
        self.file_locks = file_lock_registry
        self.storage = storage_service
        self.state = State.AUTHENTICATED   # server handles LOGIN before us

    # ── Wire helpers ──────────────────────────────────────────

    def send(self, opcode: int, payload: bytes = b"") -> None:
        """Send one Phase 2 packet."""
        self.conn.sendall(P.pack_packet(opcode, self.user_id, payload))

    def recv(self) -> tuple[int, int, bytes]:
        """Receive one Phase 2 packet: ``(opcode, user_id, payload)``."""
        return P.read_packet(self.conn)

    def send_error(self, code: int, message: str) -> None:
        """Send an ERROR packet."""
        self.send(P.ERROR, P.pack_error(code, message))

    def send_ack(self, acked_opcode: int, next_offset: int,
                 sha256: bytes = b"") -> None:
        """Send an ACK packet with optional SHA-256."""
        self.send(P.ACK, P.pack_ack(acked_opcode, next_offset, sha256))

    # ── Main dispatch loop ────────────────────────────────────

    def serve(self) -> None:
        """Process packets until LOGOUT or disconnect."""
        while self.state not in (State.CLOSED,):
            opcode, uid, payload = self.recv()

            # Check user_id matches session (anti-spoof)
            if self.user_id != 0 and uid != self.user_id:
                self.send_error(
                    ErrorCode.USER_ID_MISMATCH,
                    f"expected user_id={self.user_id}, got {uid}",
                )
                continue

            # State machine gate
            allowed = _ALLOWED.get(self.state, set())
            if opcode not in allowed:
                if self.state == State.CONNECTED:
                    code = ErrorCode.NOT_LOGGED_IN
                    msg = "must LOGIN first"
                else:
                    code = ErrorCode.MALFORMED
                    msg = (f"opcode {opcode:#06x} not allowed "
                           f"in state {self.state.name}")
                self.send_error(code, msg)
                continue

            self._dispatch(opcode, payload)

    def _dispatch(self, opcode: int, payload: bytes) -> None:
        """Route one validated packet to its handler."""
        handler = self._HANDLERS.get(opcode)
        if handler is None:
            self.send_error(ErrorCode.UNKNOWN_OPCODE,
                            f"opcode {opcode:#06x} not implemented")
            return
        handler(self, payload)

    # ── Handlers (stubs — filled in on subsequent days) ───────

    def handle_file_list(self, payload: bytes) -> None:
        """FILE_LIST → FILE_LIST_RESP with entries from user's storage dir."""
        entries = []
        for entry in sorted(os.listdir(self.storage_dir)):
            if entry.casefold().endswith(PART_SUFFIX):
                continue
            if entry.casefold().endswith(SIDECAR_SUFFIX):
                continue
            if entry.casefold().endswith(BAD_SUFFIX):
                continue
            path = os.path.join(self.storage_dir, entry)
            if os.path.isfile(path):
                entries.append((entry, os.path.getsize(path)))

        self.send(P.FILE_LIST_RESP, P.pack_file_list_response(entries))
        self.logger.command(self.ip, "FILE_LIST", f"OK {len(entries)}")

    def handle_logout(self, payload: bytes) -> None:
        """Clean LOGOUT → ACK → close."""
        self.send_ack(P.LOGOUT, 0)
        self.logger.command(self.ip, "LOGOUT", "OK")
        self.state = State.CLOSED

    def handle_file_upload(self, payload: bytes) -> None:
        """FILE_UPLOAD → stage in ``.part``, stream FILE_CHUNKs, verify, commit.

        Duplicate policy (R2.7): a complete file of this name is refused
        outright (FILE_EXISTS — the client must DELETE first). An
        incompatible ``.part`` (different total_size/sha256 in its sidecar)
        is wiped and restarted from 0; a compatible one is resumed.
        """
        try:
            filename, total_size, _requested_offset, sha256_expected = P.unpack_upload(payload)
        except ValueError:
            self.send_error(ErrorCode.MALFORMED, "malformed FILE_UPLOAD payload")
            self.logger.command(self.ip, "UPLOAD", "ERR malformed payload")
            return

        path = self.safe_path(filename)
        if path is None:
            self.send_error(ErrorCode.INVALID_FILENAME, "bad filename")
            self.logger.command(self.ip, "UPLOAD", "ERR bad filename")
            return

        part_path = path + PART_SUFFIX

        if os.path.isfile(path):
            self.send_error(ErrorCode.FILE_EXISTS, "file exists -- DELETE first")
            self.logger.command(self.ip, "UPLOAD", f"ERR file exists {filename}")
            return

        server_offset = 0
        if os.path.isfile(part_path):
            if self.storage.validate_sidecar(self.username, filename, total_size, sha256_expected):
                server_offset = os.path.getsize(part_path)
            else:
                # Incompatible staging file (different file under the same
                # name) -- wipe it and restart from 0 rather than corrupt it.
                self.storage.cleanup_staging(self.username, filename)

        if not self.file_locks.acquire(self.username, filename, timeout=5.0):
            self.send_error(ErrorCode.FILE_BUSY, "file busy, try again")
            self.logger.command(self.ip, "UPLOAD", f"ERR file busy {filename}")
            return

        try:
            self.send_ack(P.FILE_UPLOAD, server_offset)
            self.storage.write_sidecar(self.username, filename, total_size, sha256_expected)

            hasher = sha256_incremental()
            # Resuming: hash what's already on disk so the final digest
            # covers the whole file, not just the newly-received bytes.
            if server_offset > 0:
                with open(part_path, "rb") as f:
                    while chunk := f.read(CHUNK_SIZE):
                        hasher.update(chunk)

            received = server_offset
            started = time.perf_counter()
            self.state = State.UPLOADING

            try:
                with open(part_path, "ab") as f:
                    while received < total_size:
                        op, uid, chunk_payload = self.recv()
                        if op == P.LOGOUT:
                            # Client is bailing out -- keep .part for resume.
                            self.handle_logout(b"")
                            return
                        if self.user_id != 0 and uid != self.user_id:
                            raise ProtocolError(f"user_id mismatch mid-upload: {uid}")
                        if op != P.FILE_CHUNK:
                            self.send_error(ErrorCode.MALFORMED,
                                             f"expected FILE_CHUNK, got {op:#06x}")
                            self.state = State.AUTHENTICATED
                            self.logger.transfer(self.ip, "UPLOAD", filename, received,
                                                  time.perf_counter() - started, "ABORTED",
                                                  declared=total_size)
                            return
                        try:
                            offset, data = P.unpack_chunk(chunk_payload)
                        except ValueError:
                            self.send_error(ErrorCode.MALFORMED, "malformed FILE_CHUNK payload")
                            self.state = State.AUTHENTICATED
                            self.logger.transfer(self.ip, "UPLOAD", filename, received,
                                                  time.perf_counter() - started, "ABORTED",
                                                  declared=total_size)
                            return
                        if offset != received:
                            self.send_error(ErrorCode.OFFSET_MISMATCH,
                                             f"expected offset {received}, got {offset}")
                            self.state = State.AUTHENTICATED
                            self.logger.transfer(self.ip, "UPLOAD", filename, received,
                                                  time.perf_counter() - started, "ABORTED",
                                                  declared=total_size)
                            return
                        if received + len(data) > total_size:
                            # A chunk that overruns the size the client itself
                            # declared at FILE_UPLOAD time -- refuse it rather
                            # than write past the promised length and commit
                            # a file bigger than what the ACK/digest cover.
                            self.send_error(
                                ErrorCode.MALFORMED,
                                f"chunk of {len(data)} bytes at offset {offset} "
                                f"exceeds declared size {total_size}",
                            )
                            self.state = State.AUTHENTICATED
                            self.logger.transfer(self.ip, "UPLOAD", filename, received,
                                                  time.perf_counter() - started, "ABORTED",
                                                  declared=total_size)
                            return
                        f.write(data)
                        hasher.update(data)
                        received += len(data)
            except BaseException:
                self.logger.transfer(self.ip, "UPLOAD", filename, received,
                                      time.perf_counter() - started, "ABORTED",
                                      declared=total_size)
                raise

            actual_digest = hasher.digest()
            if sha256_expected and actual_digest != sha256_expected:
                # Isolate the corrupt staging file rather than delete it
                # outright -- it's evidence, and a retry needs a clean slate.
                os.replace(part_path, part_path + ".bad")
                self.storage.cleanup_staging(self.username, filename)
                self.send_error(ErrorCode.CHECKSUM_MISMATCH, "checksum mismatch")
                self.state = State.AUTHENTICATED
                self.logger.transfer(self.ip, "UPLOAD", filename, received,
                                      time.perf_counter() - started, "CHECKSUM-MISMATCH")
                return

            os.replace(part_path, path)
            self.storage.cleanup_staging(self.username, filename)

            duration = time.perf_counter() - started
            self.send_ack(P.FILE_UPLOAD, total_size, actual_digest)
            self.logger.transfer(self.ip, "UPLOAD", filename, total_size, duration, "SHA256-OK")
            self.state = State.AUTHENTICATED
        finally:
            self.file_locks.release(self.username, filename)

    def handle_file_download(self, payload: bytes) -> None:
        """FILE_DOWNLOAD → ACK(total_size, sha256) then stream FILE_CHUNKs.

        The client supplies its own resume offset (how much it already has
        locally); the server just validates it against the real file size
        and starts streaming from there. No trailing ACK -- the client
        already knows the whole-file digest from the opening ACK and
        verifies locally once ``received == total_size``.
        """
        try:
            filename, requested_offset = P.unpack_download(payload)
        except ValueError:
            self.send_error(ErrorCode.MALFORMED, "malformed FILE_DOWNLOAD payload")
            self.logger.command(self.ip, "DOWNLOAD", "ERR malformed payload")
            return

        path = self.safe_path(filename)
        if path is None:
            self.send_error(ErrorCode.INVALID_FILENAME, "bad filename")
            self.logger.command(self.ip, "DOWNLOAD", "ERR bad filename")
            return
        if not os.path.isfile(path):
            self.send_error(ErrorCode.NOT_FOUND, "no such file")
            self.logger.command(self.ip, "DOWNLOAD", f"ERR not found {filename}")
            return

        total_size = os.path.getsize(path)
        if not (0 <= requested_offset <= total_size):
            self.send_error(ErrorCode.OFFSET_MISMATCH,
                             f"requested offset {requested_offset} exceeds size {total_size}")
            self.logger.command(self.ip, "DOWNLOAD", f"ERR bad offset {filename}")
            return

        digest = sha256_file(path)
        self.send_ack(P.FILE_DOWNLOAD, total_size, digest)

        if requested_offset == total_size:
            # Client's local copy is already complete; nothing to stream.
            self.logger.transfer(self.ip, "DOWNLOAD", filename, total_size, 0.0, "SHA256-OK")
            return

        self.state = State.DOWNLOADING
        started = time.perf_counter()
        sent = requested_offset
        try:
            for offset, chunk in read_chunks(path, start_offset=requested_offset):
                self.send(P.FILE_CHUNK, P.pack_chunk(offset, chunk))
                sent += len(chunk)
        except BaseException:
            self.logger.transfer(self.ip, "DOWNLOAD", filename, sent,
                                  time.perf_counter() - started, "ABORTED",
                                  declared=total_size)
            raise
        else:
            duration = time.perf_counter() - started
            self.logger.transfer(self.ip, "DOWNLOAD", filename, total_size, duration, "SHA256-OK")
        finally:
            self.state = State.AUTHENTICATED

    def handle_file_delete(self, payload: bytes) -> None:
        """FILE_DELETE → remove the completed file (used before re-uploading)."""
        try:
            filename = P.unpack_filename(payload)
        except ValueError:
            self.send_error(ErrorCode.MALFORMED, "malformed FILE_DELETE payload")
            self.logger.command(self.ip, "DELETE", "ERR malformed payload")
            return

        path = self.safe_path(filename)
        if path is None:
            self.send_error(ErrorCode.INVALID_FILENAME, "bad filename")
            self.logger.command(self.ip, "DELETE", "ERR bad filename")
            return
        if not os.path.isfile(path):
            self.send_error(ErrorCode.NOT_FOUND, "no such file")
            self.logger.command(self.ip, "DELETE", f"ERR not found {filename}")
            return

        if not self.file_locks.acquire(self.username, filename, timeout=5.0):
            self.send_error(ErrorCode.FILE_BUSY, "file busy, try again")
            self.logger.command(self.ip, "DELETE", f"ERR file busy {filename}")
            return
        try:
            os.remove(path)
            self.send_ack(P.FILE_DELETE, 0)
            self.logger.command(self.ip, "DELETE", f"OK {filename}")
        finally:
            self.file_locks.release(self.username, filename)

    def handle_file_chunk(self, payload: bytes) -> None:
        """Placeholder — called during UPLOADING state on Day 4."""
        self.send_error(ErrorCode.MALFORMED, "unexpected FILE_CHUNK")

    # ── Path safety (2-layer validation) ──────────────────────

    def safe_path(self, filename: str) -> str | None:
        """Return the absolute path inside the user's storage dir, or None.

        Layer 1: reject forbidden characters and reserved names.
        Layer 2: resolve symlinks / .. and verify the result is still inside
        ``self.storage_dir``.
        """
        if not valid_filename(filename):
            return None
        root = os.path.realpath(self.storage_dir)
        candidate = os.path.realpath(os.path.join(root, filename))
        if candidate == root or candidate.startswith(root + os.sep):
            return candidate
        return None

    # ── Handler dispatch table ────────────────────────────────
    # Defined after the methods so the names are in scope.

    _HANDLERS: dict[int, "callable"] = {
        P.FILE_LIST:     handle_file_list,
        P.FILE_UPLOAD:   handle_file_upload,
        P.FILE_DOWNLOAD: handle_file_download,
        P.FILE_DELETE:   handle_file_delete,
        P.FILE_CHUNK:    handle_file_chunk,
        P.LOGOUT:        handle_logout,
    }
