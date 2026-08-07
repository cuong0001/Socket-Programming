import time
import sys

class ProgressRenderer:
    # Refresh bar at most 10 times per second to avoid flickering
    MIN_INTERVAL = 0.1

    def __init__(self, filename, total, resumed_from=0):
        self.filename = filename
        self.total = total
        self.resumed_from = resumed_from
        self.current = resumed_from
        self.started = time.perf_counter()
        self._last = 0.0
        self._finished = False

    def update(self, done: int) -> None:
        if self._finished:
            return
        if done < self.current:
            return
        self.current = done

        now = time.perf_counter()

        # Do not update if interval is too short and transfer is not finished
        if now - self._last < self.MIN_INTERVAL and done < self.total:
            return

        self._last = now
        elapsed = now - self.started

        # Calculate speed based on bytes transferred in this session ONLY, ignoring resumed bytes
        this_session = done - self.resumed_from
        speed = (this_session / elapsed / 1024) if elapsed > 0 else 0

        pct = done / self.total * 100 if self.total > 0 else 100
        eta = ((self.total - done) / (this_session / elapsed)) if this_session > 0 and elapsed > 0 else 0

        filled = int(30 * done / self.total) if self.total > 0 else 30
        bar = "█" * filled + "░" * (30 - filled)

        # \r brings the cursor back to the start of the line to overwrite it
        print(f"\r{self.filename}: [{bar}] {pct:5.1f}% "
              f"({done:,}/{self.total:,}B) {speed:,.0f}KB/s ETA:{eta:.0f}s",
              end="", flush=True)

    def done(self) -> None:
        # Force a final render at 100% and print a newline to prevent overriding
        if not self._finished:
            self._finished = True
            self.update(self.total)
            print()
            
