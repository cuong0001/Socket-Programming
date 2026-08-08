import unittest
import unittest.mock
import time
import os
import sys
import csv
import tempfile

# Add parent directory to path to import rate_limit
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import client
import protocol as P
from rate_limit import TokenBucket
from progress import ProgressRenderer

class TestThrottle(unittest.TestCase):
    @unittest.mock.patch('client.send_packet')
    @unittest.mock.patch('client.recv_packet')
    def test_throttle_math(self, mock_recv_packet, mock_send_packet):
        # Target speed: 500 KB/s
        LIMIT_KBPS = 500
        LIMIT_BPS = LIMIT_KBPS * 1024
        THRESHOLD_BPS = LIMIT_BPS * 1.10  # +10% threshold

        # Test size: 2 MB
        FILE_SIZE = 2 * 1024 * 1024
        CHUNK = 4096

        print(f"\n[INFO] Testing REAL Client UPLOAD flow. Simulating 3 runs of 2MB at 500KB/s...")

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(os.urandom(FILE_SIZE))
            filepath = tmp.name

        results = []

        try:
            from file_handler import sha256_file
            file_hash = sha256_file(filepath)

            for run in range(1, 4):
                # 1. Mock the two server ACKs that client.process_command expects
                #    - First ACK: Server accepts FILE_UPLOAD, start offset = 0
                #    - Second ACK: Server receives FILE_CHUNK EOF, hash matches
                mock_recv_packet.side_effect = [
                    (P.ACK, 0, P.pack_ack(P.FILE_UPLOAD, 0)),
                    (P.ACK, 0, P.pack_ack(P.FILE_UPLOAD, FILE_SIZE, file_hash))
                ]
                fake_sock = unittest.mock.MagicMock()

                # 2. Start the timer
                started = time.perf_counter()

                # 3. Execute the REAL client code (network is mocked, throttle is real)
                client.process_command(fake_sock, f"UPLOAD {filepath}", uid=1, limit_bps=LIMIT_BPS)

                # 4. Stop the timer and calculate speed
                elapsed = time.perf_counter() - started
                speed = FILE_SIZE / elapsed

                # 5. Reset mock side_effect for the next run
                mock_recv_packet.side_effect = None

                results.append({
                    "Run": run,
                    "Size_MB": FILE_SIZE / (1024*1024),
                    "Time_s": round(elapsed, 2),
                    "Speed_KBps": round(speed / 1024, 2),
                    "Limit_KBps": 500
                })

                self.assertLessEqual(speed, THRESHOLD_BPS,
                    f"Run {run}: Speed {speed/1024:.1f}KB/s exceeded threshold {THRESHOLD_BPS/1024:.1f}KB/s")
                print(f"[OK] Run {run} successful! Speed: {speed/1024:.1f}KB/s (Limit: 500KB/s)")

            from pathlib import Path
            docs_dir = Path(__file__).resolve().parents[1] / "docs" / "test-results"
            docs_dir.mkdir(parents=True, exist_ok=True)
            csv_file = docs_dir / "throttle.csv"

            # Save to CSV
            with open(csv_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Run", "Size_MB", "Time_s", "Speed_KBps", "Limit_KBps"])
                writer.writeheader()
                writer.writerows(results)
            print(f"[INFO] Results saved to {csv_file}")
        finally:
            os.remove(filepath)

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


class TestParallelThrottle(unittest.TestCase):
    def test_two_clients_throttled_independently(self):
        """Two simultaneous TokenBucket instances at 500 KB/s must each
        stay under 550 KB/s regardless of what the other client is doing.

        Each logical client owns its own TokenBucket — this test proves that
        two concurrent uploads do not share or interfere with each other's
        rate limiter. Both must stay within the +10% threshold.
        """
        import threading

        LIMIT_KBPS = 500
        LIMIT_BPS = LIMIT_KBPS * 1024
        THRESHOLD_BPS = LIMIT_BPS * 1.10  # +10% acceptance threshold
        FILE_SIZE = 2 * 1024 * 1024  # 2 MB
        CHUNK = 4096

        print(f"\n[INFO] Parallel throttle: running 2 clients simultaneously at {LIMIT_KBPS} KB/s each...")

        results: dict[int, float] = {}

        def run_client(client_id: int) -> None:
            bucket = TokenBucket(LIMIT_BPS)
            sent = 0
            started = time.perf_counter()
            while sent < FILE_SIZE:
                bucket.consume(CHUNK)
                sent += CHUNK
            elapsed = time.perf_counter() - started
            results[client_id] = FILE_SIZE / elapsed

        threads = [threading.Thread(target=run_client, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for client_id, speed in sorted(results.items()):
            kbps = speed / 1024
            print(f"[OK] Client {client_id + 1}: {kbps:.1f} KB/s (Limit: {LIMIT_KBPS} KB/s)")
            self.assertLessEqual(
                speed,
                THRESHOLD_BPS,
                f"Client {client_id + 1}: {kbps:.1f} KB/s exceeded threshold {THRESHOLD_BPS / 1024:.1f} KB/s",
            )

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
