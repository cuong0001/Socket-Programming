"""Per-user storage helpers shared by every Session.

``FileLockRegistry`` serializes concurrent access to the same
``(username, filename)`` pair so two uploads of the same file can't
interleave and corrupt each other (R2.3/R2.7 duplicate policy).
``StorageService`` resolves per-user storage directories and wraps
``resume.py``'s sidecar functions so callers only deal in usernames,
never raw paths.

Note on ``FILE_BUSY``: this registry is keyed by ``(username, filename)``,
but ``UserRegistry`` only ever allows one active session per username (the
assignment specifies a unique username with no password, so a second LOGIN
for the same name is rejected outright). That means two sessions can never
actually contend for the same key through the live protocol today --
``FILE_BUSY`` is defensive/internal, not currently reachable. It's kept
rather than removed in case that one-session-per-username rule ever
changes; if it does, the upload preflight checks in
``Session.handle_file_upload`` (the FILE_EXISTS / ``.part`` sidecar checks)
would need to move to after the lock is acquired, to close the
time-of-check/time-of-use window that opens up once two sessions can share
a username.
"""

import os
import threading

import resume


class _Entry:
    """A per-key lock plus a count of callers currently holding a reference
    to it (waiting on it or actively holding it) -- lets the registry know
    when it's safe to drop the entry instead of keeping it forever."""

    __slots__ = ("lock", "refcount")

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.refcount = 0


class FileLockRegistry:
    """One lock per (username, filename), created lazily and dropped once
    nobody references it, so long-running servers don't accumulate one
    entry per file ever uploaded/deleted.

    Lock order is always registry lock -> file lock, and the registry
    lock is only ever held long enough to fetch-or-create the per-key
    entry / adjust its refcount -- never while a file is being read or
    written, and never across the (possibly blocking) file-lock
    acquire/release itself.
    """

    def __init__(self) -> None:
        self._registry_lock = threading.Lock()
        self._locks: dict[tuple[str, str], _Entry] = {}

    def _checkout(self, key: tuple[str, str]) -> _Entry:
        with self._registry_lock:
            entry = self._locks.get(key)
            if entry is None:
                entry = _Entry()
                self._locks[key] = entry
            entry.refcount += 1
            return entry

    def _checkin(self, key: tuple[str, str], entry: _Entry) -> None:
        with self._registry_lock:
            entry.refcount -= 1
            if entry.refcount == 0 and self._locks.get(key) is entry:
                del self._locks[key]

    def acquire(self, username: str, filename: str, timeout: float = 5.0) -> bool:
        """Block up to ``timeout`` seconds. Returns False on timeout."""
        key = (username, filename)
        entry = self._checkout(key)
        acquired = entry.lock.acquire(timeout=timeout)
        if not acquired:
            # Never got the lock -- release our claim on the entry so it can
            # still be cleaned up once whoever does hold it releases.
            self._checkin(key, entry)
        return acquired

    def release(self, username: str, filename: str) -> None:
        key = (username, filename)
        with self._registry_lock:
            entry = self._locks.get(key)
        if entry is None:
            raise RuntimeError(f"release() on a lock that was never acquired: {key!r}")
        entry.lock.release()
        self._checkin(key, entry)


class StorageService:
    """Resolves ``storage/<username>/`` and wraps resume.py's sidecar I/O."""

    def __init__(self, base_storage_dir: str) -> None:
        self.base_storage_dir = base_storage_dir

    def user_dir(self, username: str) -> str:
        """Resolve ``storage/<username>/``, creating it if needed.

        Defense-in-depth: ``server.py`` already rejects unsafe usernames
        before this is ever called, but callers must not be able to escape
        the storage root through this API either -- a username like ``..``
        would otherwise resolve outside it.
        """
        root = os.path.realpath(self.base_storage_dir)
        candidate = os.path.realpath(os.path.join(root, username))
        if candidate != root and not candidate.startswith(root + os.sep):
            raise ValueError(f"username escapes storage root: {username!r}")
        os.makedirs(candidate, exist_ok=True)
        return candidate

    def write_sidecar(self, username: str, filename: str,
                       total_size: int, sha256: bytes) -> None:
        resume.write_sidecar(self.user_dir(username), filename, total_size, sha256)

    def validate_sidecar(self, username: str, filename: str,
                          total_size: int, sha256: bytes) -> bool:
        return resume.validate_sidecar(self.user_dir(username), filename, total_size, sha256)

    def cleanup_staging(self, username: str, filename: str) -> None:
        resume.cleanup_staging(self.user_dir(username), filename)
