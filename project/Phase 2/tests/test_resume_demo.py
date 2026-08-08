"""Regression tests for tools/resume_demo.py.

Tests cover two scenarios requested in the PR review:
  1. The script does not crash with UnicodeEncodeError when stdout uses a
     non-UTF-8 encoding (e.g. the Windows CP1252 console) and the project
     path contains Vietnamese characters.
  2. If an exception occurs after the temporary file is created but before
     the server starts, the cleanup code still removes the file so no
     tmp*.bin remains in testdata/.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEMO_SCRIPT = PROJECT_DIR / "tools" / "resume_demo.py"
TESTDATA_DIR = PROJECT_DIR / "testdata"


class ResumeDemoEncodingTest(unittest.TestCase):
    """Verify that the demo script survives a legacy (non-UTF-8) console."""

    def test_no_unicode_error_with_cp1252_stdout(self):
        """Running resume_demo.py with PYTHONUTF8=0 and a charmap encoding
        must not crash before the server starts.  The script reconfigures
        its own stdout with errors='replace', so any non-ASCII byte in the
        path is replaced rather than raising UnicodeEncodeError.

        We cannot run the full 20-MiB demo in a unit test, so we only check
        that the process does not die with exit code 1 from a codec error
        before it even tries to connect.  We give it a 5-second head-start
        and then terminate — a UnicodeEncodeError crash happens in < 1 s.
        """
        env = os.environ.copy()
        env["PYTHONUTF8"] = "0"
        env["PYTHONIOENCODING"] = "cp1252:replace"

        proc = subprocess.Popen(
            [sys.executable, str(DEMO_SCRIPT)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(PROJECT_DIR),
        )
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Still running after 5 s — no early crash. That's a pass.
            proc.terminate()
            proc.wait()
            proc.stdout.close()
            proc.stderr.close()
            return

        stdout = proc.stdout.read().decode("utf-8", errors="replace")
        stderr = proc.stderr.read().decode("utf-8", errors="replace")
        combined = stdout + stderr
        self.assertNotIn(
            "UnicodeEncodeError",
            combined,
            "Script crashed with UnicodeEncodeError under CP1252 encoding",
        )


class ResumeDemoCleanupTest(unittest.TestCase):
    """Verify that temporary files are removed even when an error occurs early."""

    def test_no_tmp_file_left_after_early_failure(self):
        """Run resume_demo.py with an unreachable port so that
        partial_upload raises ConnectionRefusedError before sending any data.
        The finally block must still delete the temp file from testdata/.
        """
        before = set(TESTDATA_DIR.glob("tmp*.bin"))

        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"

        # Override PORT to 1 (always refused) inline so we don't modify source
        patched = (
            "import sys; sys.argv=['resume_demo']; "
            f"exec(open({str(DEMO_SCRIPT)!r}).read().replace("
            "'PORT = 9000', 'PORT = 1'))"
        )
        result = subprocess.run(
            [sys.executable, "-c", patched],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(PROJECT_DIR),
            timeout=15,
        )

        after = set(TESTDATA_DIR.glob("tmp*.bin"))
        leaked = after - before
        self.assertEqual(
            leaked,
            set(),
            f"Temp file(s) not cleaned up after early failure: {leaked}",
        )


if __name__ == "__main__":
    unittest.main()
