import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from storage_service import FileLockRegistry, StorageService


class FileLockRegistryTests(unittest.TestCase):
    def test_locks_are_shared_per_user_and_filename(self) -> None:
        locks = FileLockRegistry()

        self.assertTrue(locks.acquire("alice", "report.bin", timeout=0))
        try:
            self.assertFalse(locks.acquire("alice", "report.bin", timeout=0))

            self.assertTrue(locks.acquire("alice", "other.bin", timeout=0))
            locks.release("alice", "other.bin")

            self.assertTrue(locks.acquire("bob", "report.bin", timeout=0))
            locks.release("bob", "report.bin")
        finally:
            locks.release("alice", "report.bin")

        self.assertTrue(locks.acquire("alice", "report.bin", timeout=0))
        locks.release("alice", "report.bin")

    def test_released_locks_are_removed_from_the_registry(self) -> None:
        """A registry that never forgets released locks leaks one dict
        entry per (username, filename) ever touched -- unbounded over a
        server's lifetime. Releasing must actually drop the entry."""
        locks = FileLockRegistry()
        for i in range(1000):
            filename = f"file-{i}.bin"
            self.assertTrue(locks.acquire("alice", filename, timeout=0))
            locks.release("alice", filename)

        self.assertEqual(len(locks._locks), 0)

    def test_timed_out_acquire_does_not_leak_a_registry_entry(self) -> None:
        locks = FileLockRegistry()
        self.assertTrue(locks.acquire("alice", "busy.bin", timeout=0))
        # Someone else already holds it -- this claim must not be counted
        # against cleanup once the real holder releases.
        self.assertFalse(locks.acquire("alice", "busy.bin", timeout=0))
        locks.release("alice", "busy.bin")

        self.assertEqual(len(locks._locks), 0)


class StorageServiceUserDirTests(unittest.TestCase):
    def test_user_dir_rejects_usernames_that_escape_the_storage_root(self) -> None:
        with tempfile.TemporaryDirectory() as base:
            service = StorageService(base)
            for bad_username in ("..", "../escape", "a/../../b"):
                with self.subTest(username=bad_username):
                    with self.assertRaises(ValueError):
                        service.user_dir(bad_username)

    def test_user_dir_accepts_a_normal_username(self) -> None:
        with tempfile.TemporaryDirectory() as base:
            service = StorageService(base)
            path = service.user_dir("alice")
            self.assertTrue(Path(path).is_dir())
            self.assertEqual(Path(path).parent, Path(base).resolve())


if __name__ == "__main__":
    unittest.main()
