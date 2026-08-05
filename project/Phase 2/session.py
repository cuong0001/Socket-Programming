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

FORBIDDEN_PARTS = ("/", "\\", "..", ":")

WINDOWS_DEVICE_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{d}" for d in range(1, 10)]
    + [f"LPT{d}" for d in range(1, 10)]
)


def _normalized(name: str) -> str:
    """The name the filesystem will really use (Windows strips trailing dots)."""
    return name.rstrip(". ")


def valid_filename(name: str) -> bool:
    """Accept only names we can store under exactly the name we were given."""
    if not name:
        return False
    if not name.isprintable():
        return False
    if _normalized(name) != name:
        return False
    if name.casefold().endswith(PART_SUFFIX):
        return False
    if name.casefold().endswith(SIDECAR_SUFFIX):
        return False
    if name.split(".")[0].upper() in WINDOWS_DEVICE_NAMES:
        return False
    return not any(part in name for part in FORBIDDEN_PARTS)


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
        """Placeholder — full implementation on Day 4 (Ngày 4)."""
        self.send_error(ErrorCode.INTERNAL_ERROR, "UPLOAD not implemented yet")

    def handle_file_download(self, payload: bytes) -> None:
        """Placeholder — full implementation on Day 4 (Ngày 4)."""
        self.send_error(ErrorCode.INTERNAL_ERROR, "DOWNLOAD not implemented yet")

    def handle_file_delete(self, payload: bytes) -> None:
        """Placeholder — implement after core R2.1–R2.7."""
        self.send_error(ErrorCode.INTERNAL_ERROR, "DELETE not implemented yet")

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
