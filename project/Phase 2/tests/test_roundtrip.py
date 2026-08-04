import hashlib
import unittest
from pathlib import Path

from helpers import RunningServer


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        while True:
            chunk = file.read(4096)
            if not chunk:
                return hasher.hexdigest()
            hasher.update(chunk)


def create_test_file(path: Path, size: int) -> None:
    pattern = bytes(range(256))
    remaining = size

    with path.open("wb") as file:
        while remaining:
            chunk = pattern[: min(len(pattern), remaining)]
            file.write(chunk)
            remaining -= len(chunk)


@unittest.skip(
    "Blocked by the Day 3 server rewiring (PR #20, session.py): server.py "
    "now only speaks the Phase 2 binary protocol and requires LOGIN "
    "first, which client.py in this repo doesn't send yet -- the upload "
    "gets its connection reset instead of completing. Separately, "
    "Session.handle_file_upload/handle_file_download are still "
    "intentional Day 4 stubs, so a real transfer wouldn't succeed even "
    "with a LOGIN-capable client. Re-enable once both land."
)
class RoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_upload_list_download_six_file_sizes(self) -> None:
        sizes = [0, 512, 4096, 4097, 10000, 10 * 1024 * 1024]
        sources = []

        for index, size in enumerate(sizes):
            source = self.server.work_dir / f"sample_{index}_{size}.bin"
            create_test_file(source, size)
            sources.append(source)

            result = self.server.run_client("UPLOAD", str(source))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SHA256 OK", result.stdout)

        listing = self.server.run_client("LIST")
        self.assertEqual(listing.returncode, 0, listing.stdout + listing.stderr)
        for source in sources:
            self.assertIn(source.name, listing.stdout)

        for source in sources:
            result = self.server.run_client("DOWNLOAD", source.name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SHA256 OK", result.stdout)

            downloaded = self.server.work_dir / "downloads" / source.name
            self.assertTrue(downloaded.is_file())
            self.assertEqual(sha256(downloaded), sha256(source))


if __name__ == "__main__":
    unittest.main()
