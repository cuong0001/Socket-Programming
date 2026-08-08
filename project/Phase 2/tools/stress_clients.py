"""Deterministic mixed-workload stress runner for the Phase 2 server.

The server must already be running. Each logical client owns a separate
username but deliberately uses the same filename, proving that per-user
namespaces do not interfere. A client performs this complete workflow:

    LOGIN -> cleanup -> UPLOAD -> LIST -> DOWNLOAD -> SHA-256 -> DELETE -> LOGOUT

The default 12 clients begin each round together. The server intentionally
allows only 10 active sessions by default, so clients rejected with
SERVER_BUSY retry until a slot is released. All other protocol errors fail the
run. Results are written as machine-readable JSON and one-row-per-client CSV.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import protocol as P
from session import ErrorCode


CHUNK_SIZE = 4096
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "docs" / "test-results"

# Windows may select a legacy console codepage. Output paths can contain
# non-ASCII characters, so keep subprocess capture and redirected logs valid.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


class StressFailure(RuntimeError):
    """A protocol or data-integrity failure in one logical client."""


@dataclass(frozen=True)
class StressConfig:
    host: str = "127.0.0.1"
    port: int = 9000
    clients: int = 12
    rounds: int = 20
    seed: int = 2026
    payload_kb: int = 32
    timeout: float = 120.0
    output_dir: Path = DEFAULT_OUTPUT_DIR


@dataclass
class ClientResult:
    round: int
    client: int
    username: str
    success: bool
    login_attempts: int
    operations: int
    bytes_uploaded: int
    bytes_downloaded: int
    elapsed_seconds: float
    error: str = ""


def _read_ack(sock: socket.socket, expected_opcode: int) -> tuple[int, bytes]:
    opcode, _uid, payload = P.read_packet(sock)
    if opcode == P.ERROR:
        code, message = P.unpack_error(payload)
        raise StressFailure(f"ERROR {code}: {message}")
    if opcode != P.ACK:
        raise StressFailure(f"expected ACK, got opcode {opcode:#06x}")

    acked_opcode, next_offset, digest = P.unpack_ack(payload)
    if acked_opcode != expected_opcode:
        raise StressFailure(
            f"expected ACK for {expected_opcode:#06x}, got {acked_opcode:#06x}"
        )
    return next_offset, digest


def _connect_and_login(
    config: StressConfig,
    username: str,
    deadline: float,
) -> tuple[socket.socket, int, int]:
    """Connect and log in, retrying only the expected capacity rejection."""
    attempts = 0
    last_error = "server did not accept the client before the deadline"

    while time.monotonic() < deadline:
        attempts += 1
        remaining = max(0.1, deadline - time.monotonic())
        sock = None
        try:
            sock = socket.create_connection(
                (config.host, config.port), timeout=min(5.0, remaining)
            )
            sock.settimeout(min(10.0, remaining))
            sock.sendall(P.pack_packet(P.LOGIN, 0, P.pack_text(username)))
            opcode, uid, payload = P.read_packet(sock)

            if opcode == P.ACK:
                acked_opcode, acked_uid, _digest = P.unpack_ack(payload)
                if acked_opcode != P.LOGIN or acked_uid != uid or uid == 0:
                    raise StressFailure("LOGIN ACK contains inconsistent user data")
                connected = sock
                sock = None
                return connected, uid, attempts

            if opcode != P.ERROR:
                raise StressFailure(f"expected LOGIN ACK, got opcode {opcode:#06x}")

            code, message = P.unpack_error(payload)
            if code != ErrorCode.SERVER_BUSY:
                raise StressFailure(f"LOGIN failed with ERROR {code}: {message}")
            last_error = f"SERVER_BUSY after {attempts} login attempts"
        except (ConnectionError, OSError, socket.timeout) as exc:
            last_error = f"connection attempt failed: {exc}"
        finally:
            if sock is not None:
                sock.close()

        time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))

    raise StressFailure(last_error)


def _delete_if_present(sock: socket.socket, uid: int, filename: str) -> None:
    """Make repeated stress runs idempotent without hiding real errors."""
    sock.sendall(
        P.pack_packet(P.FILE_DELETE, uid, P.pack_filename(filename))
    )
    opcode, _uid, payload = P.read_packet(sock)
    if opcode == P.ACK:
        acked_opcode, _next_offset, _digest = P.unpack_ack(payload)
        if acked_opcode != P.FILE_DELETE:
            raise StressFailure("cleanup received an ACK for the wrong opcode")
        return
    if opcode == P.ERROR:
        code, message = P.unpack_error(payload)
        if code == ErrorCode.NOT_FOUND:
            return
        raise StressFailure(f"cleanup failed with ERROR {code}: {message}")
    raise StressFailure(f"cleanup expected ACK or ERROR, got {opcode:#06x}")


def _upload(
    sock: socket.socket,
    uid: int,
    filename: str,
    data: bytes,
) -> bytes:
    digest = hashlib.sha256(data).digest()
    request = P.pack_upload(filename, len(data), 0, digest)
    sock.sendall(P.pack_packet(P.FILE_UPLOAD, uid, request))
    offset, _digest = _read_ack(sock, P.FILE_UPLOAD)
    if not 0 <= offset <= len(data):
        raise StressFailure(f"server returned invalid upload offset {offset}")

    for chunk_offset in range(offset, len(data), CHUNK_SIZE):
        chunk = data[chunk_offset : chunk_offset + CHUNK_SIZE]
        sock.sendall(
            P.pack_packet(
                P.FILE_CHUNK,
                uid,
                P.pack_chunk(chunk_offset, chunk),
            )
        )

    final_offset, server_digest = _read_ack(sock, P.FILE_UPLOAD)
    if final_offset != len(data):
        raise StressFailure(
            f"upload completed at {final_offset}, expected {len(data)}"
        )
    if server_digest != digest:
        raise StressFailure("server upload checksum does not match the source")
    return digest


def _assert_listing(
    sock: socket.socket,
    uid: int,
    filename: str,
    expected_size: int,
) -> None:
    sock.sendall(P.pack_packet(P.FILE_LIST, uid))
    opcode, _uid, payload = P.read_packet(sock)
    if opcode == P.ERROR:
        code, message = P.unpack_error(payload)
        raise StressFailure(f"FILE_LIST failed with ERROR {code}: {message}")
    if opcode != P.FILE_LIST_RESP:
        raise StressFailure(f"expected FILE_LIST_RESP, got {opcode:#06x}")

    entries = P.unpack_file_list_response(payload)
    if entries != [(filename, expected_size)]:
        raise StressFailure(f"namespace listing is not isolated: {entries!r}")


def _download(
    sock: socket.socket,
    uid: int,
    filename: str,
    expected_digest: bytes,
) -> bytes:
    sock.sendall(
        P.pack_packet(P.FILE_DOWNLOAD, uid, P.pack_download(filename, 0))
    )
    total_size, advertised_digest = _read_ack(sock, P.FILE_DOWNLOAD)
    if advertised_digest != expected_digest:
        raise StressFailure("download ACK advertises the wrong checksum")

    received = bytearray()
    while len(received) < total_size:
        opcode, _uid, payload = P.read_packet(sock)
        if opcode == P.ERROR:
            code, message = P.unpack_error(payload)
            raise StressFailure(f"download failed with ERROR {code}: {message}")
        if opcode != P.FILE_CHUNK:
            raise StressFailure(f"expected FILE_CHUNK, got {opcode:#06x}")
        offset, chunk = P.unpack_chunk(payload)
        if offset != len(received):
            raise StressFailure(
                f"download offset {offset} does not match {len(received)}"
            )
        if len(received) + len(chunk) > total_size:
            raise StressFailure("download exceeded its advertised size")
        received.extend(chunk)

    downloaded = bytes(received)
    if hashlib.sha256(downloaded).digest() != expected_digest:
        raise StressFailure("downloaded data failed SHA-256 verification")
    return downloaded


def _delete(sock: socket.socket, uid: int, filename: str) -> None:
    sock.sendall(
        P.pack_packet(P.FILE_DELETE, uid, P.pack_filename(filename))
    )
    _read_ack(sock, P.FILE_DELETE)


def _logout(sock: socket.socket, uid: int) -> None:
    sock.sendall(P.pack_packet(P.LOGOUT, uid))
    _read_ack(sock, P.LOGOUT)


def _run_client(
    config: StressConfig,
    round_number: int,
    client_number: int,
    start_barrier: threading.Barrier,
    deadline: float,
) -> ClientResult:
    started = time.perf_counter()
    username = f"stress-r{round_number}-c{client_number}"
    filename = "shared-name.bin"
    data_seed = config.seed + round_number * config.clients + client_number
    data = random.Random(data_seed).randbytes(config.payload_kb * 1024 + 17)
    attempts = 0
    sock = None

    try:
        start_barrier.wait(timeout=min(10.0, config.timeout))
        sock, uid, attempts = _connect_and_login(config, username, deadline)
        _delete_if_present(sock, uid, filename)
        digest = _upload(sock, uid, filename, data)
        _assert_listing(sock, uid, filename, len(data))
        downloaded = _download(sock, uid, filename, digest)
        if downloaded != data:
            raise StressFailure("downloaded bytes differ from uploaded bytes")
        _delete(sock, uid, filename)
        _logout(sock, uid)
        return ClientResult(
            round=round_number,
            client=client_number,
            username=username,
            success=True,
            login_attempts=attempts,
            operations=7,
            bytes_uploaded=len(data),
            bytes_downloaded=len(downloaded),
            elapsed_seconds=time.perf_counter() - started,
        )
    except Exception as exc:
        return ClientResult(
            round=round_number,
            client=client_number,
            username=username,
            success=False,
            login_attempts=attempts,
            operations=0,
            bytes_uploaded=0,
            bytes_downloaded=0,
            elapsed_seconds=time.perf_counter() - started,
            error=f"{type(exc).__name__}: {exc}",
        )
    finally:
        if sock is not None:
            sock.close()


def run_stress(config: StressConfig) -> dict:
    if config.clients <= 0:
        raise ValueError("clients must be greater than zero")
    if config.rounds <= 0:
        raise ValueError("rounds must be greater than zero")
    if config.payload_kb <= 0:
        raise ValueError("payload_kb must be greater than zero")
    if config.timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    started = time.perf_counter()
    deadline = time.monotonic() + config.timeout
    results: list[ClientResult] = []

    for round_number in range(1, config.rounds + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        barrier = threading.Barrier(config.clients)
        with ThreadPoolExecutor(max_workers=config.clients) as executor:
            futures = [
                executor.submit(
                    _run_client,
                    config,
                    round_number,
                    client_number,
                    barrier,
                    deadline,
                )
                for client_number in range(1, config.clients + 1)
            ]
            try:
                for future in as_completed(futures, timeout=remaining):
                    results.append(future.result())
            except TimeoutError:
                for future in futures:
                    if not future.done():
                        future.cancel()

        if time.monotonic() >= deadline:
            break

    expected_clients = config.clients * config.rounds
    completed_keys = {(result.round, result.client) for result in results}
    for round_number in range(1, config.rounds + 1):
        for client_number in range(1, config.clients + 1):
            if (round_number, client_number) not in completed_keys:
                results.append(
                    ClientResult(
                        round=round_number,
                        client=client_number,
                        username=f"stress-r{round_number}-c{client_number}",
                        success=False,
                        login_attempts=0,
                        operations=0,
                        bytes_uploaded=0,
                        bytes_downloaded=0,
                        elapsed_seconds=0.0,
                        error="watchdog timeout",
                    )
                )

    results.sort(key=lambda result: (result.round, result.client))
    successful = sum(result.success for result in results)
    elapsed = time.perf_counter() - started
    uploaded = sum(result.bytes_uploaded for result in results)
    downloaded = sum(result.bytes_downloaded for result in results)
    operations = sum(result.operations for result in results)
    failures = [asdict(result) for result in results if not result.success]

    return {
        "schema_version": 1,
        "config": {
            **asdict(config),
            "output_dir": str(config.output_dir),
        },
        "summary": {
            "expected_clients": expected_clients,
            "successful_clients": successful,
            "failed_clients": expected_clients - successful,
            "operations": operations,
            "bytes_uploaded": uploaded,
            "bytes_downloaded": downloaded,
            "elapsed_seconds": elapsed,
            "throughput_kbps": (
                ((uploaded + downloaded) / 1024) / elapsed if elapsed > 0 else 0.0
            ),
            "passed": successful == expected_clients,
        },
        "failures": failures,
        "clients": [asdict(result) for result in results],
    }


def write_report(report: dict, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "stress.json"
    csv_path = output_dir / "stress.csv"

    with json_path.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")

    fieldnames = list(ClientResult.__dataclass_fields__)
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(report["clients"])

    return json_path, csv_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic concurrent Phase 2 client workloads"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--clients", type=int, default=12)
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--payload-kb", type=int, default=32)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = StressConfig(
        host=args.host,
        port=args.port,
        clients=args.clients,
        rounds=args.rounds,
        seed=args.seed,
        payload_kb=args.payload_kb,
        timeout=args.timeout,
        output_dir=args.output_dir,
    )

    try:
        report = run_stress(config)
        json_path, csv_path = write_report(report, config.output_dir)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] Stress run could not start: {exc}", file=sys.stderr)
        return 2

    summary = report["summary"]
    status = "PASS" if summary["passed"] else "FAIL"
    print(
        f"[{status}] {summary['successful_clients']}/"
        f"{summary['expected_clients']} clients; "
        f"{summary['operations']} operations; "
        f"{summary['elapsed_seconds']:.2f}s"
    )
    print(f"[INFO] JSON: {json_path}")
    print(f"[INFO] CSV : {csv_path}")

    for failure in report["failures"][:10]:
        print(
            f"[ERROR] round {failure['round']} client {failure['client']}: "
            f"{failure['error']}",
            file=sys.stderr,
        )
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
