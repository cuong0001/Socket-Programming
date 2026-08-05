"""Registry of active sessions for the Phase 2 server.

The accept loop consults this before and during LOGIN: a capacity slot
(``try_acquire_slot``/``release_slot``) bounds how many clients can be
connected at once, and ``login``/``logout`` hand out the per-connection
``user_id`` used everywhere else (``Session``, storage namespacing).
"""

import threading


class UsernameInUse(Exception):
    """Raised by ``login()`` when the username is already active."""


class UserRegistry:
    """Thread-safe uid assignment + capacity limiting."""

    def __init__(self, max_clients: int) -> None:
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_clients)
        self._next_uid = 1
        self._uid_by_username: dict[str, int] = {}
        self._username_by_uid: dict[int, str] = {}

    def try_acquire_slot(self) -> bool:
        """Reserve one of ``max_clients`` slots. Non-blocking."""
        return self._semaphore.acquire(blocking=False)

    def release_slot(self) -> None:
        """Give back a slot acquired via ``try_acquire_slot``."""
        self._semaphore.release()

    def login(self, username: str) -> int:
        """Bind ``username`` to a fresh ``user_id`` and return it.

        Raises ``UsernameInUse`` if the name is already bound to an
        active session.
        """
        with self._lock:
            if username in self._uid_by_username:
                raise UsernameInUse(username)
            uid = self._next_uid
            self._next_uid += 1
            self._uid_by_username[username] = uid
            self._username_by_uid[uid] = username
            return uid

    def logout(self, uid: int) -> None:
        """Release ``uid``'s username so it can log in again. Idempotent."""
        with self._lock:
            username = self._username_by_uid.pop(uid, None)
            if username is not None:
                self._uid_by_username.pop(username, None)
