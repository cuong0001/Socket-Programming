import time

class TokenBucket:
    def __init__(self, rate_bps: int, capacity: int = None):
        if capacity is None:
            capacity = 4096  # Default capacity is 1 chunk
            
        self.rate = rate_bps
        self.capacity = capacity
        
        # CRITICAL: Tokens must start at 0. If initialized to full capacity, 
        # the initial burst will inflate the average speed above the 10% threshold.
        self.tokens = 0               
        self.last = time.perf_counter()

    def consume(self, n: int) -> None:
        if self.rate <= 0:
            return 

        # Called before sending each chunk. Sleeps if transferring too fast.
        now = time.perf_counter()
        
        # Refill tokens based on elapsed time, capped at capacity
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.rate)
        self.last = now
        self.tokens -= n
        
        # If bucket goes negative, we are too fast -> wait for new tokens
        if self.tokens < 0:
            time.sleep(-self.tokens / self.rate)
            self.tokens = 0
            self.last = time.perf_counter()

