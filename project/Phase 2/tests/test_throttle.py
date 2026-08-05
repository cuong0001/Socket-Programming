import unittest
import unittest.mock
import time
import os
import sys
import csv

# Add parent directory to path to import rate_limit
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rate_limit import TokenBucket
from progress import ProgressRenderer

class TestThrottle(unittest.TestCase):
    def test_throttle_math(self):
        # Target speed: 500 KB/s
        LIMIT_BPS = 500 * 1024

        # Test size: 20 MB
        FILE_SIZE = 20 * 1024 * 1024
        CHUNK = 4096

        results = []
        threshold = LIMIT_BPS * 1.10

        print(f"\n[INFO] Testing throttle. Simulating 3 runs of 20MB at 500KB/s...")
        for run in range(1, 4):
            bucket = TokenBucket(LIMIT_BPS)
            started = time.perf_counter()
            sent = 0

            # Simulate sending chunks
            while sent < FILE_SIZE:
                bucket.consume(CHUNK)
                sent += CHUNK

            elapsed = time.perf_counter() - started
            speed = FILE_SIZE / elapsed
            results.append({
                "Run": run,
                "Size_MB": FILE_SIZE / (1024*1024),
                "Time_s": round(elapsed, 2),
                "Speed_KBps": round(speed / 1024, 2),
                "Limit_KBps": 500
            })

            self.assertLessEqual(speed, threshold,
                f"Run {run}: Speed {speed/1024:.1f}KB/s exceeded threshold {threshold/1024:.1f}KB/s")
            print(f"[OK] Run {run} successful! Speed: {speed/1024:.1f}KB/s (Limit: 500KB/s)")

        # Save to CSV
        csv_file = "throttle_results.csv"
        with open(csv_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Run", "Size_MB", "Time_s", "Speed_KBps", "Limit_KBps"])
            writer.writeheader()
            writer.writerows(results)
        print(f"[INFO] Results saved to {csv_file}")

    def test_unlimited_mode(self):
        # Unlimited mode: rate_bps <= 0
        LIMIT_BPS = 0
        FILE_SIZE = 20 * 1024 * 1024
        CHUNK = 4096

        bucket = TokenBucket(LIMIT_BPS)
        started = time.perf_counter()
        sent = 0

        while sent < FILE_SIZE:
            bucket.consume(CHUNK)
            sent += CHUNK

        elapsed = time.perf_counter() - started
        # Should be almost instantaneous. Assert < 0.1s
        self.assertLess(elapsed, 0.1, f"Unlimited mode took too long: {elapsed:.2f}s")
        print(f"\n[OK] Unlimited mode completed in {elapsed:.4f}s")

class TestProgressRenderer(unittest.TestCase):
    @unittest.mock.patch('builtins.print')
    def test_progress_never_decreases(self, mock_print):
        progress = ProgressRenderer("test.bin", 100)
        progress.update(50)
        self.assertEqual(progress.current, 50)

        # Try to decrease
        progress.update(40)
        # Should still be 50
        self.assertEqual(progress.current, 50)

        progress.update(60)
        self.assertEqual(progress.current, 60)

if __name__ == '__main__':
    unittest.main()
