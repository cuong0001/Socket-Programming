import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from storage_service import FileLockRegistry


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


if __name__ == "__main__":
    unittest.main()
