"""End-to-end smoke coverage for tools/stress_clients.py."""

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import RunningServer


PROJECT_DIR = Path(__file__).resolve().parents[1]
STRESS_TOOL = PROJECT_DIR / "tools" / "stress_clients.py"


class StressClientToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = RunningServer().start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.stop()

    def test_writes_json_and_csv_for_a_successful_concurrent_run(self) -> None:
        with tempfile.TemporaryDirectory() as output_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(STRESS_TOOL),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.server.port),
                    "--clients",
                    "12",
                    "--rounds",
                    "1",
                    "--seed",
                    "2026",
                    "--payload-kb",
                    "1",
                    "--timeout",
                    "30",
                    "--output-dir",
                    output_dir,
                ],
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=40,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("[PASS] 12/12 clients", result.stdout)

            json_path = Path(output_dir) / "stress.json"
            csv_path = Path(output_dir) / "stress.csv"
            self.assertTrue(json_path.is_file())
            self.assertTrue(csv_path.is_file())

            report = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertTrue(report["summary"]["passed"])
            self.assertEqual(report["summary"]["expected_clients"], 12)
            self.assertEqual(report["summary"]["successful_clients"], 12)
            self.assertEqual(report["summary"]["operations"], 84)
            self.assertEqual(report["failures"], [])

            with csv_path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 12)
            self.assertTrue(all(row["success"] == "True" for row in rows))


if __name__ == "__main__":
    unittest.main()
