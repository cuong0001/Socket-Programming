import unittest
import time
import os
import sys

# Add parent directory to path to import rate_limit
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from rate_limit import TokenBucket

class TestThrottle(unittest.TestCase):
    def test_throttle_math(self):
        # Target speed: 500 KB/s
        LIMIT_BPS = 500 * 1024 
        
        # Test size: 2 MB (Will take roughly 4 seconds to complete)
        FILE_SIZE = 2 * 1024 * 1024 
        CHUNK = 4096
        
        bucket = TokenBucket(LIMIT_BPS)
        
        print(f"\n[INFO] Testing throttle. Simulating transfer of 2MB at 500KB/s...")
        started = time.perf_counter()
        sent = 0
        
        # Simulate sending chunks
        while sent < FILE_SIZE:
            bucket.consume(CHUNK)
            sent += CHUNK
            
        elapsed = time.perf_counter() - started
        speed = FILE_SIZE / elapsed
        
        # Assert that average speed does not exceed limit + 10%
        threshold = LIMIT_BPS * 1.10
        self.assertLessEqual(speed, threshold, 
            f"Speed {speed/1024:.1f}KB/s exceeded threshold {threshold/1024:.1f}KB/s")
        
        print(f"[OK] Throttle successful! Speed: {speed/1024:.1f}KB/s (Limit: 500KB/s)")

if __name__ == '__main__':
    unittest.main()
