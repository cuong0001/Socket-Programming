"""Per-user storage helpers shared by every Session.

``FileLockRegistry`` serializes concurrent access to the same
``(username, filename)`` pair so two uploads of the same file can't
interleave and corrupt each other (R2.3/R2.7 duplicate policy).
``StorageService`` resolves per-user storage directories and wraps
``resume.py``'s sidecar functions so callers only deal in usernames,
never raw paths.
"""

import os
import threading

import resume


class FileLockRegistry:
    """One lock per (username, filename), created lazily.

    Lock order is always registry lock -> file lock, and the registry
    lock is only ever held long enough to fetch-or-create the per-key
    Lock object -- never while a file is being read or written.
    """

    def __init__(self) -> None:
        self._registry_lock = threading.Lock()
        self._locks: dict[tuple[str, str], threading.Lock] = {}

    def _get_lock(self, username: str, filename: str) -> threading.Lock:
        key = (username, filename)
        with self._registry_lock:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
            return lock

    def acquire(self, username: str, filename: str, timeout: float = 5.0) -> bool:
        """Block up to ``timeout`` seconds. Returns False on timeout."""
        return self._get_lock(username, filename).acquire(timeout=timeout)

    def release(self, username: str, filename: str) -> None:
        self._get_lock(username, filename).release()


class StorageService:
    """Resolves ``storage/<username>/`` and wraps resume.py's sidecar I/O."""

    def __init__(self, base_storage_dir: str) -> None:
        self.base_storage_dir = base_storage_dir

    def user_dir(self, username: str) -> str:
        path = os.path.join(self.base_storage_dir, username)
        os.makedirs(path, exist_ok=True)
        return path

    def write_sidecar(self, username: str, filename: str,
                       total_size: int, sha256: bytes) -> None:
        resume.write_sidecar(self.user_dir(username), filename, total_size, sha256)

    def validate_sidecar(self, username: str, filename: str,
                          total_size: int, sha256: bytes) -> bool:
        return resume.validate_sidecar(self.user_dir(username), filename, total_size, sha256)

    def cleanup_staging(self, username: str, filename: str) -> None:
        resume.cleanup_staging(self.user_dir(username), filename)
