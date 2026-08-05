import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
SERVER_FILE = PROJECT_DIR / "server.py"
CLIENT_FILE = PROJECT_DIR / "client.py"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RunningServer:
    """Start the team's server in a temporary test directory."""

    def __init__(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.port = find_free_port()
        self.process = None

    def start(self) -> "RunningServer":
        self.process = subprocess.Popen(
            [sys.executable, str(SERVER_FILE), str(self.port)],
            cwd=self.work_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.time() + 5
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("Server kết thúc trước khi lắng nghe")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.1):
                    return self
            except OSError:
                time.sleep(0.05)

        raise RuntimeError("Server không lắng nghe sau 5 giây")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.temp_dir.cleanup()

    def run_client(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(CLIENT_FILE),
                "127.0.0.1",
                str(self.port),
                "--username",
                "alice",
                *arguments,
            ],
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
