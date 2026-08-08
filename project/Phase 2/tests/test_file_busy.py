"""Documents why FILE_BUSY (0x0079) has no positive-case test in this suite.

FileLockRegistry is keyed by (username, filename), so two sessions holding
the same file lock at once is the only way to actually observe FILE_BUSY.
But UserRegistry allows only one active session per username at a time
(the assignment specifies a single, password-less username per user --
see assignment_text.txt), so a second LOGIN for an in-use username is
rejected with USERNAME_IN_USE before it could ever reach a second
FILE_UPLOAD/FILE_DELETE. That makes two sessions contending for the same
lock unreachable through the live protocol as currently designed.

This isn't an oversight -- it was verified directly (see docs/pr_23_review_comment.md,
docs/pr_24_review_response.md, and the module docstring of storage_service.py)
and the decision was to keep usernames exclusive rather than relax that to make
FILE_BUSY reachable, since a second concurrent session per username would need
some other way to prove identity once two connections can claim it at once, and
the assignment doesn't ask for that.

This test locks in the architectural fact as a regression check: if
UserRegistry is ever changed to allow multiple concurrent sessions per
username, this test will start failing at the "second LOGIN" step (it
will unexpectedly succeed instead of getting USERNAME_IN_USE) -- that's
the signal to come back and write a real FILE_BUSY-producing test instead
of this one.
"""

import socket
import sys
import unittest
from pathlib import Path

from helpers import RunningServer

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

import protocol as P
from session import ErrorCode


class FileBusyUnreachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_file_busy_is_unreachable_because_usernames_are_exclusive(self) -> None:
        address = ("127.0.0.1", self.server.port)
        username = "file-busy-check"
        filename = "contested.bin"

        with socket.create_connection(address) as first:
            first.sendall(P.pack_packet(P.LOGIN, 0, P.pack_text(username)))
            op, uid, _payload = P.read_packet(first)
            self.assertEqual(op, P.ACK)

            # Start (but don't finish) an upload -- this is exactly the
            # moment a second session would need to exist concurrently for
            # FILE_BUSY to ever be observable: the file lock is held from
            # here until the upload completes, errors out, or the
            # connection closes.
            first.sendall(P.pack_packet(
                P.FILE_UPLOAD, uid, P.pack_upload(filename, 1024, 0)))
            op, _, _payload = P.read_packet(first)
            self.assertEqual(op, P.ACK)

            # A second session for the SAME username, while the first is
            # mid-upload and holding the lock: rejected at LOGIN, long
            # before it could ever attempt to touch the same file.
            with socket.create_connection(address) as second:
                second.sendall(P.pack_packet(P.LOGIN, 0, P.pack_text(username)))
                op, _, payload = P.read_packet(second)
                self.assertEqual(op, P.ERROR)
                code, _msg = P.unpack_error(payload)
                self.assertEqual(code, ErrorCode.USERNAME_IN_USE)
                # Never got far enough to see FILE_BUSY (0x0079) -- that's
                # the point of this test.
                self.assertNotEqual(code, ErrorCode.FILE_BUSY)


if __name__ == "__main__":
    unittest.main()
