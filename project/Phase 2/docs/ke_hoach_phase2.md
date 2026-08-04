# KẾ HOẠCH CHI TIẾT PHASE 2 — NHÓM 3 NGƯỜI
# (Cập nhật 01/08/2026 — tích hợp từ Phase2_Plan_Socket_Programming.docx)

Hệ Thống Truyền Nhận File Qua Socket TCP — Giai Đoạn 2: Đa Client & Giao Thức Tùy Chỉnh

**Lịch:** Tuần làm chính (**01/8 → 07/8**). Hạn nộp mục tiêu: **T6 07/8** (còn 2 ngày đệm 08–09/8).

**Điểm tối đa Phase 2:** 6,0 điểm (R2.1→R2.7)

**Trạng thái Phase 1:** ✅ **ĐÃ QUA CỔNG** — 22/22 test PASS. Code tại `project/`.

**Nguyên tắc bất di bất dịch:** KẾ THỪA code Phase 1, không viết lại. `recv_exact`, `read_frame`, `send_frame`, `logger.py` giữ nguyên.

---

## MỤC LỤC

- Trạng thái tiến độ (cập nhật liên tục)
- Phần 0: Tài sản Phase 1 còn dùng được
- Phần 1: Phân công & luật làm việc Phase 2
- Phần 2: Ngày 1–2 (01–02/8): Gói nhị phân + Session tách riêng
- Phần 3: Ngày 3 (03/8): Đa client + LOGIN + Namespace + Lock registry
- Phần 4: Ngày 4 (04/8): UPLOAD/DOWNLOAD theo gói nhị phân
- Phần 5: Ngày 5 (05/8): Resume transfer + Script 10 client
- Phần 6: Ngày 6 (06/8): Progress + Throttle + Server-full
- Phần 7: Ngày 7 (07/8): 🚪 Cổng Phase 2 + Báo cáo + Nộp
- Phần 8: Sai lầm kinh điển Phase 2
- Phụ lục A: Bảng opcode & payload format (mini-RFC)
- Phụ lục B: Ma trận kiểm thử & tiêu chí PASS định lượng

---

## TRẠNG THÁI TIẾN ĐỘ (cập nhật liên tục)

> Cập nhật thủ công mỗi khi merge PR. Không phải nghiệm thu chính thức (xem "✅ Nghiệm thu cuối Ngày X" trong từng phần) — đây chỉ để cả nhóm biết ai đang chờ ai.

### Theo file (khớp bảng Phần 0)

| File | Ai | Trạng thái trên `main` |
|---|---|---|
| `config.py` | Cường | ✅ Merged (qua PR #22) |
| `protocol.py` | Bình | ✅ Merged (PR #22) — có cả `pack_download`/`unpack_error` (thêm ngoài kế hoạch gốc, do review PR #20 phát hiện thiếu) |
| `session.py` | Cường | 🟡 Khung + state machine + LOGIN/FILE_LIST/LOGOUT chạy thật qua server. `handle_file_upload/download/delete/chunk` vẫn là stub `ERROR "not implemented yet"` — **Ngày 4, chưa làm** |
| `users.py` | Cường | ✅ Merged — `UserRegistry` (uid, `USERNAME_IN_USE`, semaphore `max_clients`) |
| `server.py` | Cường | ✅ Merged — accept loop threaded, LOGIN handshake thật, `storage/<username>/` tự tạo |
| `storage_service.py` | Cường | ❌ **Chưa tạo** — chặn `handle_file_upload` thật (cần `FileLockRegistry` + `validate_sidecar`/`write_sidecar`) |
| `client.py` | Hưng | ❌ Trên `main` vẫn là bản Phase 1 gốc (không LOGIN). Bản binary + `--username` đã có ở PR #21 nhưng **chưa merge** |
| `file_handler.py` | Hưng | ❌ Rỗng (0 dòng) trên `main`. Bản đầy đủ ở PR #19/#21, **chưa merge** — `session.py`'s Ngày 4 upload handler cần import từ file này |
| `resume.py` | Hưng | ❌ Chưa tồn tại trên `main`. Bản đầy đủ ở PR #19/#21, **chưa merge** |
| `tests/test_session.py` | Cường | ✅ Mới — test trực tiếp `Session` (không cần client.py), 6 case |
| `tests/test_errors.py` | Bình (kế hoạch gốc) | 🟡 Đã đánh dấu skip có lý do (làm tạm khi fix PR #20, đúng ra là việc Bình) — cần viết lại thật khi có client LOGIN + upload thật |
| `tests/test_roundtrip.py` | Bình | 🟡 Đã skip có lý do — cần "Adapt sang binary protocol" thật sự (Ngày 4, chưa làm) |
| `tests/test_multi.py`, `test_throttle.py`, `test_resume.py`, `test_churn.py` | Bình/Hưng/Cường | ❌ Chưa bắt đầu (Ngày 5–6) |

### Theo cổng ngày (✅/🟡/❌)

- **Ngày 0** — `config.py`: ✅ Xong
- **Ngày 1–2** — Session tách riêng: 🟡 `session.py`/`protocol.py` xong; `file_handler.py` (Hưng) chưa merge → chặn Ngày 4
- **Ngày 3** — Đa client + LOGIN + Namespace: 🟡 `users.py` + `server.py` threading/LOGIN xong; `storage_service.py` chưa làm → chặn Ngày 4
- **Ngày 4** — UPLOAD/DOWNLOAD nhị phân: ❌ Chưa bắt đầu. Việc của Cường (`handle_file_upload/download` thật trong `session.py`, xem mẫu code Phần 4) bị chặn bởi `storage_service.py` (tự làm) và `file_handler.py`/`resume.py` (chờ Hưng merge)
- **Ngày 5–7**: ❌ Chưa bắt đầu

### Đang chặn ai, việc gì (ưu tiên xử lý trước)

1. **Cường**: viết `storage_service.py` (`FileLockRegistry` + `StorageService`) — không phụ thuộc ai, làm ngay được.
2. **Hưng**: merge PR #19/#21 vào `main` (hoặc ít nhất `file_handler.py` + `resume.py` + `client.py`) — `session.py`'s Ngày 4 handler import thẳng từ `file_handler.py`, không có thì không viết tiếp được.
3. Sau khi cả hai xong: Cường viết `handle_file_upload`/`handle_file_download` thật theo mẫu Phần 4, rồi test round-trip thật với client của Hưng.

---

## PHẦN 0: TÀI SẢN PHASE 1 CÒN DÙNG ĐƯỢC

### Giữ nguyên, không sửa

| File | Trạng thái | Ghi chú |
|---|---|---|
| `common.py` | ✅ Hoàn chỉnh | `recv_exact`, `read_frame(prefix=4/8)`, `send_frame` — **KHÔNG CHẠM** |
| `logger.py` | ✅ Thread-safe sẵn | Đã có `threading.Lock` — **KHÔNG CHẠM** |
| `tests/test_framing.py` | ✅ Pass hết | Regression baseline — **22 test phải luôn xanh** |
| `tests/test_protocol.py` | ✅ 13 pass | Hex dump đúng đặc tả, golden vector phải tiếp tục PASS |
| `protocol.py` | ✅ Đầy đủ | `pack_packet`, `unpack_body`, `read_packet`, `pack_upload/chunk/ack` đã có |

### Cần sửa/bổ sung

| File | Việc cần làm | Ai | Ngày |
|---|---|---|---|
| `server.py` | Refactor → accept loop + semaphore + thread dispatch | Cường | Ngày 1–3 |
| `client.py` | Binary protocol + `--username`, progress, throttle, reconnect | Hưng | Ngày 1–4 |
| `file_handler.py` | Rỗng 0 dòng — gom code đọc/ghi/hash | Hưng | Ngày 1 |
| `protocol.py` | Thêm payload LOGIN/ERROR/checksum/download-info; sửa `pack_upload` thêm `sha256` | Bình | Ngày 1 |
| `tests/test_errors.py` | Đánh dấu `# TODO: sẽ flaky đa luồng`, sửa assertions | Bình | Ngày 3 |
| `tests/test_roundtrip.py` | Adapt sang binary protocol | Bình | Ngày 4 |

### Cần tạo mới

| File | Nội dung | Ai | Ngày |
|---|---|---|---|
| `config.py` | `ServerConfig`: host, port, max_clients, rate_kbps, chunk_size, storage/log path | Cường | Ngày 0 |
| `session.py` | Class `Session` với state machine 5 trạng thái + full opcode handler | Cường | Ngày 1–2 |
| `users.py` | `UserRegistry`: `username ↔ user_id`, semaphore, max_clients | Cường | Ngày 3 |
| `storage_service.py` | Path validation, per-user dir, `FileLockRegistry` | Cường | Ngày 3 |
| `resume.py` | Logic `.part` + `.part.json` sidecar + offset validation | Hưng | Ngày 5–6 |
| `tests/test_multi.py` | 10 client đồng thời — **bắt buộc theo đề (0,6đ)**, seed cố định | Bình | Ngày 5 |
| `tests/test_churn.py` | 500 connect/disconnect, đo thread/handle trước-sau | Cường | Ngày 5 |
| `tests/test_resume.py` | Kill giữa chừng ở 2 offset, resume, checksum | Hưng | Ngày 5–6 |
| `tests/test_throttle.py` | Đo tốc độ thực ≤ ngưỡng + 10%, 3 lần | Hưng | Ngày 6 |
| `tools/stress_clients.py` | 12 client, seed=2026, mix workload, JSON/CSV output | Bình | Ngày 9 |

---

## PHẦN 1: PHÂN CÔNG NHÓM & LUẬT LÀM VIỆC PHASE 2

### 1.1. Vai trò (gắn tên thật)

| Người | Phụ trách Phase 2 | File sở hữu | Điểm R |
|---|---|---|---|
| **Bình** | Protocol codec, error model, integration gate, CLI contract, đặc tả mini-RFC | `protocol.py`, `config.py`, `tests/`, `tools/stress_clients.py`, `docs/protocol.md` | R2.2 (1,0đ) + test toàn bộ |
| **Cường** | Server concurrency, session registry, namespace, lock, capacity, cleanup | `server.py`, `session.py`, `users.py`, `storage_service.py`, `logger.py` | R2.1 (1,5đ), R2.3 (0,5đ), R2.7 (0,5đ) |
| **Hưng** | Client Phase 2, resume hai chiều, progress, throttle | `client.py`, `file_handler.py`, `resume.py`, `rate_limit.py`, `progress.py` | R2.3 (0,5đ), R2.4 (1,0đ), R2.5 (0,5đ), R2.6 (0,5đ) |

**Quy tắc bằng chứng cá nhân** (phòng 1 người làm hết):
- Mỗi người: ≥ 2 PR code + 1 PR test + 1 phần báo cáo có tên owner + 1 lượt review PR người khác
- Demo: mỗi người nói ≥ 90 giây về phần sở hữu của mình và trả lời chéo phần người khác

> ⚠️ Cuối mỗi ngày: 20 phút knowledge-transfer — **cả 3 đều giải thích được** protocol, concurrency, resume, throttling.

### 1.2. Luật làm việc (5 luật)

1. **Họp 15 phút đầu ngày** — hôm qua xong gì, hôm nay làm gì, kẹt gì.
2. **Tích hợp cuối ngày**: 3 người chạy thử cùng nhau. Bug không được để qua đêm.
3. **`main` luôn chạy được.** Ai làm hỏng thì sửa ngay.
4. **Nghiệm thu cuối ngày là LỆNH CHẠY ĐƯỢC** — không phải cảm giác "chắc xong rồi".
5. **Thay đổi wire-protocol phải đủ 3 người đồng ý** — sửa vào `protocol.py` + `docs/protocol.md` ngay.

**Thứ tự merge PR theo dependency** (quan trọng — merge sai thứ tự gây conflict lớn):
```
protocol → server skeleton/login → storage/locks → transfer → resume → progress/throttle → stress/hardening
```

### 1.3. Cấu trúc thư mục Phase 2

```
phase2/
├── common.py            # ✅ GIỮ NGUYÊN
├── protocol.py          # Bình: nâng cấp thêm SHA-256 vào pack_upload
├── config.py            # Cường: [MỚI] ServerConfig
├── server.py            # Cường: accept loop + semaphore
├── session.py           # Cường: [MỚI] Session với state machine
├── users.py             # Cường: [MỚI] UserRegistry
├── storage_service.py   # Cường: [MỚI] path validation + FileLockRegistry
├── client.py            # Hưng: binary protocol + resume + progress
├── file_handler.py      # Hưng: chunk read/write + SHA-256 incremental
├── resume.py            # Hưng: [MỚI] .part + .part.json sidecar
├── rate_limit.py        # Hưng: [MỚI] TokenBucket
├── progress.py          # Hưng: [MỚI] progress renderer
├── logger.py            # ✅ GIỮ NGUYÊN
├── storage/
│   ├── alice/
│   └── bob/
├── downloads/
├── testdata/
├── tests/
│   ├── test_framing.py      # ✅ regression baseline
│   ├── test_protocol.py     # ✅ golden vectors
│   ├── test_roundtrip.py    # Bình: adapt sang binary
│   ├── test_errors.py       # Bình: sửa assertions đa luồng
│   ├── test_multi.py        # Bình: 10 client đồng thời
│   ├── test_churn.py        # Cường: 500 connect/disconnect
│   ├── test_resume.py       # Hưng: kill + resume 2 offset
│   └── test_throttle.py     # Hưng: đo tốc độ ≤ ngưỡng+10%
├── tools/
│   └── stress_clients.py    # Bình: 12 client, seed=2026, CSV
├── docs/
│   ├── protocol.md          # Bình: mini-RFC
│   └── test-results/        # Cả 3: CSV, log, ảnh
└── logs/
```

---

## PHẦN 2: NGÀY 1–2 (01–02/8): GIAO THỨC NHỊ PHÂN + SESSION TÁCH RIÊNG

### Ngày 1 — Thứ Bảy 01/8: `config.py` + `file_handler.py` + `session.py` khung + Nâng cấp `protocol.py`

#### 📌 Nhắc nhanh — Packet layout

```
[LENGTH:4B][OPCODE:2B][USER_ID:2B][PAYLOAD:N]
LENGTH = 2 + 2 + len(PAYLOAD)   ← KHÔNG tính 4 byte của chính LENGTH
Tất cả integer: big-endian (network byte order)
```

#### 🔨 LÀM

**Bình — Nâng cấp `protocol.py`:**

`FILE_UPLOAD` payload từ nay bao gồm SHA-256 của **toàn bộ file gốc**. Client tính trước rồi gửi kèm ngay từ đầu, server lưu vào sidecar để validate resume:

```python
# protocol.py — sửa pack_upload
def pack_upload(filename: str, total_size: int, offset: int = 0, sha256: bytes = b"") -> bytes:
    """
    Payload FILE_UPLOAD = name_len:2 + name + total_size:8 + offset:8 + sha256:32 (optional)
    sha256: bytes của SHA-256 toàn bộ file (32 bytes). Rỗng nếu không dùng.
    """
    total_size = _unsigned(total_size, 64, "total_size")
    offset = _unsigned(offset, 64, "offset")
    if sha256 and len(sha256) != 32:
        raise ValueError("sha256 must be exactly 32 bytes")
    return pack_filename(filename) + struct.pack("!QQ", total_size, offset) + sha256

def unpack_upload(payload: bytes) -> tuple[str, int, int, bytes]:
    """Trả (filename, total_size, offset, sha256_bytes). sha256_bytes có thể rỗng."""
    filename, off = unpack_text(payload)
    if len(payload) - off < 16:
        raise ValueError("Upload payload too short")
    total_size, next_offset = struct.unpack("!QQ", payload[off:off+16])
    sha256 = payload[off+16:off+48] if len(payload) >= off + 48 else b""
    return filename, total_size, next_offset, sha256
```

Thêm `pack_error(code: int, message: str) -> bytes`:

```python
def pack_error(code: int, message: str) -> bytes:
    encoded = message.encode("utf-8")
    return struct.pack("!HH", code, len(encoded)) + encoded
```

Cập nhật `pack_ack` hỗ trợ `optional_sha256`:

```python
def pack_ack(acked_opcode: int, next_offset: int, sha256: bytes = b"") -> bytes:
    return struct.pack("!HQ", acked_opcode, next_offset) + (sha256 if sha256 else b"")
```

**Bình — `config.py`:**

```python
# config.py
import os

class ServerConfig:
    def __init__(self):
        self.host = ""
        self.port = 9000
        self.max_clients = 10
        self.rate_kbps = 0          # 0 = không giới hạn
        self.chunk_size = 4096
        self.socket_timeout = 30.0  # giây
        self.storage_dir = os.path.join(os.getcwd(), "storage")
        self.log_file = os.path.join(os.getcwd(), "logs", "server.log")

    @classmethod
    def from_args(cls, args):
        """Parse từ argparse namespace."""
        cfg = cls()
        cfg.port = args.port
        cfg.max_clients = getattr(args, "max_clients", 10)
        cfg.rate_kbps = getattr(args, "rate_kbps", 0)
        return cfg
```

**Hưng — `file_handler.py`:**

```python
import hashlib, os

CHUNK_SIZE = 4096

def read_chunks(filepath, start_offset=0):
    """Yield (offset, data) từ start_offset đến hết file."""
    with open(filepath, "rb") as f:
        f.seek(start_offset)
        offset = start_offset
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            yield offset, chunk
            offset += len(chunk)

def sha256_file(filepath) -> bytes:
    """Trả bytes (32 byte) SHA-256 của toàn bộ file — không load vào RAM."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            hasher.update(chunk)
    return hasher.digest()   # bytes, không phải hexdigest

def sha256_incremental():
    return hashlib.sha256()
```

**Cường — `session.py` (khung với state machine):**

Session có **5 trạng thái** tường minh — ngăn nhận opcode sai trạng thái:

```python
import protocol as P
from enum import Enum, auto

class State(Enum):
    CONNECTED    = auto()   # chỉ nhận LOGIN
    AUTHENTICATED = auto()  # nhận LIST/UPLOAD/DOWNLOAD/DELETE/LOGOUT
    UPLOADING    = auto()   # chỉ nhận FILE_CHUNK đúng offset
    DOWNLOADING  = auto()   # server đang gửi FILE_CHUNK
    CLOSED       = auto()   # cleanup idempotent

# Opcode hợp lệ theo từng trạng thái
_ALLOWED = {
    State.CONNECTED:     {P.LOGIN},
    State.AUTHENTICATED: {P.FILE_LIST, P.FILE_UPLOAD, P.FILE_DOWNLOAD,
                          P.FILE_DELETE, P.LOGOUT},
    State.UPLOADING:     {P.FILE_CHUNK},
    State.DOWNLOADING:   set(),    # server chủ động gửi, không nhận thêm
}

class Session:
    def __init__(self, conn, addr, storage_dir, logger, user_id=0, username="",
                 file_lock_registry=None):
        self.conn = conn
        self.ip = addr[0]
        self.storage_dir = storage_dir
        self.logger = logger
        self.user_id = user_id
        self.username = username
        self.file_locks = file_lock_registry
        self.state = State.CONNECTED

    def send(self, opcode, payload=b""):
        self.conn.sendall(P.pack_packet(opcode, self.user_id, payload))

    def recv(self):
        return P.read_packet(self.conn)   # (opcode, user_id, payload)

    def serve(self):
        while self.state not in (State.CLOSED,):
            opcode, uid, payload = self.recv()

            # Kiểm tra state machine
            allowed = _ALLOWED.get(self.state, set())
            if opcode not in allowed:
                self.send(P.ERROR, P.pack_error(0x0103, f"opcode {opcode:#04x} not allowed in state {self.state.name}"))
                continue

            self.dispatch(opcode, payload)

    def dispatch(self, opcode, payload):
        handlers = {
            P.FILE_LIST:     self.handle_file_list,
            P.FILE_UPLOAD:   self.handle_file_upload,
            P.FILE_DOWNLOAD: self.handle_file_download,
            P.FILE_DELETE:   self.handle_file_delete,
            P.LOGOUT:        self.handle_logout,
            P.FILE_CHUNK:    self.handle_file_chunk,
        }
        h = handlers.get(opcode)
        if h:
            h(payload)
        else:
            self.send(P.ERROR, P.pack_error(0x0102, "unknown opcode"))

    def _safe_path(self, filename: str):
        """Trả đường dẫn tuyệt đối trong user_dir. None nếu không hợp lệ."""
        import os
        FORBIDDEN = ("/", "\\", "..", ":")
        if not filename or any(f in filename for f in FORBIDDEN):
            return None
        candidate = os.path.realpath(os.path.join(self.storage_dir, filename))
        root = os.path.realpath(self.storage_dir)
        if not (candidate == root or candidate.startswith(root + os.sep)):
            return None
        return candidate
```

#### ✅ Nghiệm thu cuối Ngày 1

- □ `python -m unittest tests.test_protocol` pass — golden vector vẫn byte-for-byte đúng
- □ `file_handler.py` import được, đọc 101 MB không tăng RAM
- □ `session.py` import được không lỗi
- □ `config.py` import được, `ServerConfig()` tạo được với defaults

---

### Ngày 2 — Chủ nhật 02/8: `storage_service.py` + Handler FILE_LIST + Tích hợp client↔server

#### 🔨 LÀM

**Cường — `storage_service.py` với `FileLockRegistry`:**

Lock theo `(username, filename)` — **không chỉ theo username**. 2 client cùng user upload cùng file đồng thời sẽ có 1 người chờ hoặc nhận `ERROR_FILE_BUSY`.

```python
# storage_service.py
import os, threading

class FileLockRegistry:
    """Lock theo (username, filename) với refcount và timeout."""

    def __init__(self):
        # Thứ tự lock BẮT BUỘC: registry_lock → file_lock (KHÔNG BAO GIỜ đảo)
        self._registry_lock = threading.Lock()
        self._file_locks: dict[tuple, threading.Lock] = {}
        self._refcounts: dict[tuple, int] = {}

    def acquire(self, username: str, filename: str, timeout: float = 5.0) -> bool:
        """Trả True nếu acquire thành công. False = timeout → gửi ERROR_FILE_BUSY."""
        key = (username, filename)
        with self._registry_lock:
            if key not in self._file_locks:
                self._file_locks[key] = threading.Lock()
                self._refcounts[key] = 0
            lock = self._file_locks[key]
            self._refcounts[key] += 1
        acquired = lock.acquire(timeout=timeout)
        if not acquired:
            with self._registry_lock:
                self._refcounts[key] -= 1
                if self._refcounts[key] == 0:
                    del self._file_locks[key], self._refcounts[key]
        return acquired

    def release(self, username: str, filename: str) -> None:
        key = (username, filename)
        with self._registry_lock:
            if key not in self._file_locks:
                return
            self._file_locks[key].release()
            self._refcounts[key] -= 1
            if self._refcounts[key] == 0:
                del self._file_locks[key], self._refcounts[key]


class StorageService:
    FORBIDDEN = ("/", "\\", "..", ":")

    def __init__(self, storage_root: str, lock_registry: FileLockRegistry):
        self.root = storage_root
        self.locks = lock_registry

    def user_dir(self, username: str) -> str:
        d = os.path.join(self.root, username)
        os.makedirs(d, exist_ok=True)
        return d

    def safe_path(self, username: str, filename: str) -> str | None:
        """Lớp 1: cấm ký tự. Lớp 2: realpath phải nằm trong user_dir."""
        if not filename or any(f in filename for f in self.FORBIDDEN):
            return None
        root = os.path.realpath(self.user_dir(username))
        candidate = os.path.realpath(os.path.join(root, filename))
        return candidate if (candidate == root or candidate.startswith(root + os.sep)) else None

    def list_files(self, username: str) -> list[tuple[str, int]]:
        d = self.user_dir(username)
        result = []
        for entry in sorted(os.listdir(d)):
            if entry.casefold().endswith(".part") or entry.endswith(".part.json"):
                continue
            path = os.path.join(d, entry)
            if os.path.isfile(path):
                result.append((entry, os.path.getsize(path)))
        return result
```

**Cường — handler FILE_LIST trong `session.py`:**

```python
def handle_file_list(self, payload):
    import protocol as P
    entries = self.storage.list_files(self.username)
    self.send(P.FILE_LIST_RESP, P.pack_file_list_response(entries))
    self.logger.command(self.ip, "FILE_LIST", f"OK {len(entries)}")
```

**Hưng — `client.py` wrapper binary + FILE_LIST:**

```python
import protocol as P, struct

def send_packet(sock, opcode, payload=b"", user_id=0):
    sock.sendall(P.pack_packet(opcode, user_id, payload))

def recv_packet(sock):
    return P.read_packet(sock)  # (opcode, user_id, payload)

# Ví dụ gọi FILE_LIST
send_packet(sock, P.FILE_LIST, user_id=uid)
op, uid, data = recv_packet(sock)
if op == P.FILE_LIST_RESP:
    for name, size in P.unpack_file_list_response(data):
        print(f"{size}\t{name}")
elif op == P.ERROR:
    code, msg = struct.unpack("!HH", data[:4]); print(f"ERR {code}: {data[4:].decode()}")
```

#### ✅ Nghiệm thu cuối Ngày 2

```bash
python server.py --port 9000 --max-clients 10
python client.py 127.0.0.1 9000 --username alice LIST
```

- □ Client nhận FILE_LIST_RESP, in đúng danh sách
- □ Server không crash khi nhận opcode lạ (trả ERROR, không exit)
- □ Session từ chối LIST khi ở trạng thái CONNECTED (chưa LOGIN)

---

## PHẦN 3: NGÀY 3 (03/8): ĐA CLIENT + LOGIN + NAMESPACE (R2.1 + R2.3)

### Ngày 3 — Thứ Hai 03/8: Thread-per-client + LOGIN/LOGOUT + semaphore

#### 📌 Nhắc nhanh — Thread-per-client

```python
while True:
    conn, addr = server.accept()
    t = threading.Thread(target=serve_client, args=(conn, addr), daemon=True)
    t.start()
```

**Câu giải thích cho báo cáo** (đề yêu cầu "nêu rõ lý do chọn"):  
*Chọn thread-per-client vì code Phase 1 đang blocking (socket và file I/O), kế thừa thay vì viết lại. Thread phù hợp I/O-bound workload; GIL được nhả khi chờ recv(). Giới hạn bằng semaphore loại bỏ nguy cơ tạo thread vô hạn. Ở quy mô ≤ 32 client, threading đơn giản hơn asyncio và không cần rewrite logic đồng bộ.*

> ⚠️ **Race condition fatal nhất:** `UserRegistry` được n thread đọc/ghi → **bọc TOÀN BỘ vào `with self._lock:`**. Không lock = mất 0,5đ R2.1.

#### 🔨 LÀM

**Cường — `users.py` với semaphore:**

```python
import threading

class UserRegistry:
    def __init__(self, max_clients: int = 10):
        self._lock = threading.Lock()
        self._semaphore = threading.Semaphore(max_clients)
        self._name_to_id: dict[str, int] = {}
        self._id_to_name: dict[int, str] = {}
        self._next_id = 1
        self.max_clients = max_clients

    def login(self, username: str) -> tuple[int | None, str]:
        """Trả (user_id, error). user_id=None nếu thất bại."""
        # Thử acquire semaphore (non-blocking)
        if not self._semaphore.acquire(blocking=False):
            return None, "server_full"
        with self._lock:
            if username in self._name_to_id:
                self._semaphore.release()
                return None, "username_taken"
            uid = self._next_id
            self._next_id += 1
            self._name_to_id[username] = uid
            self._id_to_name[uid] = username
            return uid, ""

    def logout(self, user_id: int) -> None:
        with self._lock:
            name = self._id_to_name.pop(user_id, None)
            if name:
                self._name_to_id.pop(name, None)
                self._semaphore.release()

    def count(self) -> int:
        with self._lock:
            return len(self._name_to_id)
```

**Cường — `server.py` accept loop + login flow:**

```python
import threading, socket, sys, os, argparse
import protocol as P
from config import ServerConfig
from users import UserRegistry
from storage_service import StorageService, FileLockRegistry
from session import Session
from logger import Logger

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="")
    p.add_argument("--port", type=int, default=9000)
    p.add_argument("--max-clients", type=int, default=10, dest="max_clients")
    p.add_argument("--rate-kbps", type=int, default=0, dest="rate_kbps")
    return p.parse_args()

def main():
    args = parse_args()
    cfg = ServerConfig.from_args(args)
    os.makedirs(cfg.storage_dir, exist_ok=True)
    logger = Logger(cfg.log_file)
    users = UserRegistry(max_clients=cfg.max_clients)
    file_locks = FileLockRegistry()
    storage = StorageService(cfg.storage_dir, file_locks)

    def serve_client(conn, addr):
        ip = addr[0]
        logger.connect(ip)
        uid = None
        try:
            conn.settimeout(cfg.socket_timeout)

            # Bước 1: nhận LOGIN trước tiên — state CONNECTED
            opcode, _, payload = P.read_packet(conn)
            if opcode != P.LOGIN:
                conn.sendall(P.pack_packet(P.ERROR, 0,
                             P.pack_error(0x0103, "must LOGIN first")))
                return

            username, _ = P.unpack_text(payload)
            uid, reason = users.login(username)
            if uid is None:
                code = 0x0078 if reason == "server_full" else 0x0069
                conn.sendall(P.pack_packet(P.ERROR, 0, P.pack_error(code, reason)))
                return

            conn.sendall(P.pack_packet(P.ACK, uid,
                         P.pack_ack(P.LOGIN, uid)))
            logger.command(ip, "LOGIN", f"user={username} id={uid}")

            # Bước 2: session đầy đủ — state AUTHENTICATED
            sess = Session(conn, addr, storage.user_dir(username),
                           logger, uid, username, file_lock_registry=file_locks)
            sess.storage = storage
            sess.state_transition_to_authenticated()
            sess.serve()

        except ConnectionError:
            pass
        except Exception as e:
            logger.error(ip, f"{type(e).__name__}: {e}")
        finally:
            if uid is not None:
                users.logout(uid)
            conn.close()
            logger.disconnect(ip)

    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((cfg.host, cfg.port))
    server_sock.listen(5)
    server_sock.settimeout(1.0)
    print(f"[OK] Server on {cfg.host or '0.0.0.0'}:{cfg.port} (max={cfg.max_clients})")
    try:
        while True:
            try:
                conn, addr = server_sock.accept()
            except socket.timeout:
                continue
            threading.Thread(target=serve_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down")
    finally:
        server_sock.close(); logger.close()

if __name__ == "__main__":
    main()
```

#### ✅ Nghiệm thu cuối Ngày 3

```bash
python server.py --port 9000
# 3 terminal riêng biệt
python client.py 127.0.0.1 9000 --username alice LIST
python client.py 127.0.0.1 9000 --username bob LIST
python client.py 127.0.0.1 9000 --username alice LIST   # → ERROR username taken
```

- □ 3 client song song — server sống
- □ alice không thấy file của bob
- □ 2 client cùng "alice" → client sau nhận ERROR rõ ràng
- □ Kill client → server sống, username được giải phóng (semaphore released)

---

## PHẦN 4: NGÀY 4 (04/8): UPLOAD/DOWNLOAD THEO GÓI NHỊ PHÂN (ngày tích hợp nặng nhất)

### Ngày 4 — Thứ Ba 04/8: FILE_UPLOAD / FILE_DOWNLOAD / FILE_DELETE

#### 📌 Nhắc nhanh — 5 bước upload + chính sách duplicate

```
C→S  FILE_UPLOAD(tên, total_size, offset=0, sha256_file)
S→C  ACK(acked=0x12, next_offset=server_has)   ← "server đang có bao nhiêu byte"
C→S  FILE_CHUNK(offset, data) × N
S→C  ACK(acked=0x14, next_offset=total_size, sha256)  ← chốt kèm SHA-256
```

**Chính sách duplicate (ghi vào báo cáo — 0,2đ R2.7):**
- File hoàn chỉnh đã tồn tại → **từ chối `ERROR_FILE_EXISTS`** (không ghi đè — đơn giản, chống race)
- Staging `.part` tương thích (cùng total_size + sha256) → **resume**
- Staging `.part` không tương thích → **xóa làm lại** (file khác trùng tên)

> Lý do từ chối thay vì ghi đè: nếu cho ghi đè, cần giữ lock suốt quá trình truyền để bảo vệ file cũ, phức tạp hơn rất nhiều. Nếu cần update file, client phải DELETE rồi UPLOAD.

#### 🔨 LÀM

**Cường — `session.py` handler FILE_UPLOAD:**

```python
def handle_file_upload(self, payload):
    import time, os
    from file_handler import CHUNK_SIZE, sha256_incremental
    import protocol as P

    filename, total_size, _, sha256_expected = P.unpack_upload(payload)
    path = self._safe_path(filename)
    if path is None:
        self.send(P.ERROR, P.pack_error(0x006E, "bad filename"))
        return

    part_path = path + ".part"
    sidecar_path = part_path + ".json"

    # Kiểm tra file hoàn chỉnh đã tồn tại
    if os.path.isfile(path):
        self.send(P.ERROR, P.pack_error(0x0070, "file exists — DELETE first"))
        return

    # Kiểm tra staging tương thích
    server_offset = 0
    if os.path.isfile(part_path):
        if not self.storage.validate_sidecar(self.username, filename, total_size, sha256_expected):
            # Staging không tương thích → xóa làm lại
            os.remove(part_path)
            if os.path.exists(sidecar_path):
                os.remove(sidecar_path)
        else:
            server_offset = os.path.getsize(part_path)

    # Lấy lock theo (username, filename)
    if not self.file_locks.acquire(self.username, filename, timeout=5.0):
        self.send(P.ERROR, P.pack_error(0x0078, "file busy, try again"))
        return

    try:
        self.send(P.ACK, P.pack_ack(P.FILE_UPLOAD, server_offset))

        # Ghi sidecar nếu chưa có
        if not os.path.isfile(sidecar_path):
            self.storage.write_sidecar(self.username, filename, total_size, sha256_expected)

        hasher = sha256_incremental()
        # Hash phần đã có trong .part (để checksum cuối đúng khi resume)
        if server_offset > 0:
            with open(part_path, "rb") as f:
                while data := f.read(CHUNK_SIZE):
                    hasher.update(data)

        received = server_offset
        started = time.perf_counter()
        self.state = State.UPLOADING

        with open(part_path, "ab") as f:
            while received < total_size:
                op, uid, chunk_payload = self.recv()
                if op == P.LOGOUT:
                    return   # client rút — giữ .part để resume sau
                if op != P.FILE_CHUNK:
                    raise ProtocolError(f"expected FILE_CHUNK got {op:#04x}")
                offset, data = P.unpack_chunk(chunk_payload)
                if offset != received:
                    raise ProtocolError(f"chunk offset {offset} != expected {received}")
                f.write(data)
                hasher.update(data)
                received += len(data)

        # Verify checksum
        actual_digest = hasher.digest()
        if sha256_expected and actual_digest != sha256_expected:
            # Checksum sai → cách ly staging, không commit
            os.rename(part_path, part_path + ".bad")
            self.send(P.ERROR, P.pack_error(0x0072, "checksum mismatch"))
            return

        # Commit nguyên tử
        os.replace(part_path, path)
        if os.path.exists(sidecar_path):
            os.remove(sidecar_path)

        duration = time.perf_counter() - started
        self.send(P.ACK, P.pack_ack(P.FILE_CHUNK, total_size, actual_digest))
        self.logger.transfer(self.ip, "UPLOAD", filename, total_size, duration, "SHA256-OK")
        self.state = State.AUTHENTICATED

    finally:
        self.file_locks.release(self.username, filename)
```

**Hưng — `client.py` UPLOAD/DOWNLOAD binary** (cùng flow với server).

**Bình — `tests/test_roundtrip_binary.py`:** upload từng file trong testdata (0 byte, 4096, 4097, 10 MB, file có byte 0x00) → download về → so từng byte.

#### ✅ Nghiệm thu cuối Ngày 4

```bash
python client.py 127.0.0.1 9000 --username alice UPLOAD testdata/medium_10mb.bin
python client.py 127.0.0.1 9000 --username alice LIST
python client.py 127.0.0.1 9000 --username alice DOWNLOAD medium_10mb.bin
# Upload lần 2 cùng tên → ERROR_FILE_EXISTS (không phải ghi đè)
python client.py 127.0.0.1 9000 --username alice UPLOAD testdata/medium_10mb.bin
```

- □ Round-trip đúng, checksum OK
- □ 3 client song song upload/download file khác nhau → không hỏng
- □ bob không tải được file alice (ERROR)
- □ Upload trùng tên → ERROR_FILE_EXISTS (chính sách rõ ràng)
- □ `python -m unittest tests.test_roundtrip_binary` pass

---

## PHẦN 5: NGÀY 5 (05/8): RESUME + SIDECAR + TEST 10 CLIENT (R2.4 + R2.1)

### Ngày 5 — Thứ Tư 05/8: Resume upload/download + test_multi + test_churn

#### 📌 Nhắc nhanh — Resume với sidecar

Resume không cần lệnh mới. Nhưng phải validate đúng file:

```python
# Luồng resume upload:
# 1. Client gửi FILE_UPLOAD(filename, total_size, offset=0, sha256_full_file)
# 2. Server tìm .part → validate sidecar (total_size + sha256 khớp?)
#    - Khớp → trả ACK với next_offset = size(.part)
#    - Không khớp → xóa .part, trả ACK với next_offset = 0
# 3. Client seek(server_offset) → gửi chunk từ đó
# 4. Server ghi tiếp vào .part (mode "ab")
# 5. Khi received == total_size → verify SHA-256 → commit
```

> ⚠️ **Đổi chính sách `.part` so với Phase 1:** Phase 1 XÓA `.part` khi lỗi kết nối. Phase 2 phải GIỮ `.part` để resume. Sửa `session.py` + cập nhật `test_errors.py`.

#### 🔨 LÀM

**Hưng — `resume.py` + sidecar:**

```python
# resume.py
import os, json, time

PART_SUFFIX = ".part"
SIDECAR_SUFFIX = ".part.json"


def sidecar_path(storage_dir, filename) -> str:
    return os.path.join(storage_dir, filename + SIDECAR_SUFFIX)


def write_sidecar(storage_dir, filename, total_size: int, sha256: bytes) -> None:
    """Ghi metadata để validate resume."""
    data = {
        "total_size": total_size,
        "expected_sha256": sha256.hex() if sha256 else "",
        "timestamp": time.time(),
        "protocol_version": 2,
    }
    with open(sidecar_path(storage_dir, filename), "w", encoding="utf-8") as f:
        json.dump(data, f)


def validate_sidecar(storage_dir, filename, total_size: int, sha256: bytes) -> bool:
    """
    Trả True nếu sidecar tồn tại và metadata khớp.
    Nếu không khớp → upload khác trùng tên → phải xóa staging làm lại.
    """
    try:
        with open(sidecar_path(storage_dir, filename), encoding="utf-8") as f:
            meta = json.load(f)
        size_ok = meta.get("total_size") == total_size
        hash_ok = (not sha256) or meta.get("expected_sha256") == sha256.hex()
        return size_ok and hash_ok
    except (OSError, KeyError, json.JSONDecodeError, ValueError):
        return False


def get_upload_offset(storage_dir, filename) -> int:
    """Offset server đang có — kích thước .part."""
    part = os.path.join(storage_dir, filename + PART_SUFFIX)
    return os.path.getsize(part) if os.path.exists(part) else 0


def get_download_offset(download_dir, filename) -> int:
    """Offset client đang có trong downloads/."""
    part = os.path.join(download_dir, filename + PART_SUFFIX)
    return os.path.getsize(part) if os.path.exists(part) else 0


def commit_download(download_dir, filename) -> None:
    """Rename .part → file thật (nguyên tử)."""
    os.replace(
        os.path.join(download_dir, filename + PART_SUFFIX),
        os.path.join(download_dir, filename),
    )


def cleanup_staging(storage_dir, filename) -> None:
    """Xóa .part và .part.json khi checksum lệch."""
    for suffix in (PART_SUFFIX, SIDECAR_SUFFIX):
        try:
            os.remove(os.path.join(storage_dir, filename + suffix))
        except OSError:
            pass
```

**Bình — `tests/test_multi.py` (bắt buộc 0,6đ, seed cố định):**

```python
import threading, socket, random, hashlib

SEED = 2026

def one_client(username, results, lock):
    try:
        sock = socket.create_connection(("127.0.0.1", 9002))
        # login → upload 2MB → LIST → download → verify checksum → logout
        # ... dùng helper functions
        results[username] = "OK"
    except Exception as e:
        results[username] = f"FAIL: {e}"
    finally:
        sock.close()

def test_10_concurrent():
    rng = random.Random(SEED)
    results = {}
    threads = [
        threading.Thread(target=one_client, args=(f"user{i}", results, threading.Lock()))
        for i in range(10)
    ]
    # Barrier để tất cả start đồng thời
    barrier = threading.Barrier(10)
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    failed = {k: v for k, v in results.items() if v != "OK"}
    assert not failed, f"Clients thất bại: {failed}"
    print(f"[OK] 10/10 clients hoàn thành")

# Chạy 3 lần liên tiếp để tìm race condition ẩn
if __name__ == "__main__":
    for i in range(3):
        test_10_concurrent()
        print(f"Pass lần {i+1}/3")
```

**Cường — `tests/test_churn.py` (0,4đ, đo handle/thread):**

```python
import socket, threading, psutil, os

def measure_resources():
    p = psutil.Process(os.getpid())
    return p.num_threads(), len(p.open_files())

def test_churn_no_leak():
    before_threads, before_files = measure_resources()

    # 500 vòng: connect → login → logout → close sạch
    for i in range(500):
        with socket.create_connection(("127.0.0.1", 9003)) as s:
            login(s, f"u{i % 5}"); logout(s)

    # 50 vòng: connect → đóng phũ (không login)
    for _ in range(50):
        socket.create_connection(("127.0.0.1", 9003)).close()

    import time; time.sleep(0.5)  # cho cleanup chạy
    after_threads, after_files = measure_resources()

    # Tài nguyên không tăng tuyến tính
    assert after_threads <= before_threads + 2, f"Thread leak: {before_threads} → {after_threads}"
    assert after_files <= before_files + 5, f"File handle leak: {before_files} → {after_files}"
    print(f"[OK] Threads: {before_threads}→{after_threads}, Files: {before_files}→{after_files}")
```

**Hưng — `tests/test_resume.py`** (kill ở 2 offset khác nhau — 37% và 73%):

```python
import subprocess, time, os
from file_handler import sha256_file

def test_resume_at_offset(kill_after_sec: float, label: str):
    server = subprocess.Popen(["python", "server.py", "--port", "9004"])
    time.sleep(0.5)

    p1 = subprocess.Popen(["python", "client.py", "127.0.0.1", "9004",
                            "--username", "tester", "UPLOAD", "testdata/large_100mb.bin"])
    time.sleep(kill_after_sec)
    p1.kill(); time.sleep(0.3)

    # Xác nhận .part tồn tại và > 0
    parts = [f for f in os.listdir("storage/tester") if f.endswith(".part") and not f.endswith(".json")]
    assert parts, f"[{label}] Không có .part"
    part_size = os.path.getsize(f"storage/tester/{parts[0]}")
    print(f"[{label}] Server đã nhận {part_size:,} bytes")

    # Resume — chỉ truyền phần còn lại
    p2 = subprocess.Popen(["python", "client.py", "127.0.0.1", "9004",
                            "--username", "tester", "UPLOAD", "testdata/large_100mb.bin"])
    p2.wait(timeout=120)

    final = "storage/tester/large_100mb.bin"
    assert os.path.isfile(final), f"[{label}] File không tồn tại sau resume"
    assert sha256_file(final) == sha256_file("testdata/large_100mb.bin"), f"[{label}] MISMATCH"
    print(f"[{label}] OK — resume + checksum khớp")
    server.kill()

if __name__ == "__main__":
    test_resume_at_offset(1.0, "offset ~37%")   # ~1s ≈ 37MB với 37 MB/s
    test_resume_at_offset(2.0, "offset ~73%")   # ~2s ≈ 73MB
```

#### ✅ Nghiệm thu cuối Ngày 5

- □ `python tests/test_resume.py` — 2 offset PASS, offset > 0, checksum OK — **chụp màn hình**
- □ `python -m unittest tests.test_multi` — 10/10 OK **× 3 lần liên tiếp** (race trốn)
- □ `python tests/test_churn.py` — thread/file handle không tăng tuyến tính

---

## PHẦN 6: NGÀY 6 (06/8): PROGRESS + THROTTLE + SERVER-FULL (R2.5 + R2.6 + R2.7)

### Ngày 6 — Thứ Năm 06/8: Hoàn thiện UX và kiểm soát tài nguyên

#### 🔨 LÀM

**Hưng — `progress.py` (R2.5 — 0,5đ):**

```python
# progress.py
import time, sys

class ProgressRenderer:
    """Hiển thị % dựa trên byte đã ACK, refresh tối đa 10 Hz."""
    MIN_INTERVAL = 0.1   # giây

    def __init__(self, filename, total, resumed_from=0):
        self.filename = filename
        self.total = total
        self.resumed_from = resumed_from
        self.started = time.perf_counter()
        self._last = 0.0

    def update(self, done: int) -> None:
        now = time.perf_counter()
        if now - self._last < self.MIN_INTERVAL and done < self.total:
            return
        self._last = now
        elapsed = now - self.started
        this_session = done - self.resumed_from
        speed = (this_session / elapsed / 1024) if elapsed > 0 else 0
        pct = done / self.total * 100 if self.total > 0 else 100
        eta = ((self.total - done) / (this_session / elapsed)) if this_session > 0 and elapsed > 0 else 0
        filled = int(30 * done / self.total) if self.total > 0 else 30
        bar = "█" * filled + "░" * (30 - filled)
        print(f"\r{self.filename}: [{bar}] {pct:5.1f}% "
              f"({done:,}/{self.total:,}B) {speed:,.0f}KB/s ETA:{eta:.0f}s",
              end="", flush=True)

    def done(self) -> None:
        self.update(self.total)
        print()  # dòng trống sau bar
```

> ⚠️ `speed` chỉ tính byte gửi lần này (`done - resumed_from`). Nếu tính `total/time` sẽ ra tốc độ ảo ×10 khi resume 10% cuối.

**Hưng — `rate_limit.py` (R2.6 — 0,5đ):**

> ⚠️ **Bucket khởi đầu RỖNG, capacity = 1 chunk.** Bucket đầy kiểu sách giáo khoa cho không 1 giây băng thông đầu → tốc độ trung bình cả file vượt ~11% ngưỡng → **rớt tiêu chí 10%**.

```python
# rate_limit.py
import time

class TokenBucket:
    def __init__(self, rate_bps: int, capacity: int = None):
        if capacity is None:
            capacity = 4096            # 1 chunk = capacity
        self.rate = rate_bps
        self.capacity = capacity
        self.tokens = 0               # RỖNG — không phải capacity!
        self.last = time.perf_counter()

    def consume(self, n: int) -> None:
        """Gọi trước mỗi chunk. Sẽ sleep nếu cần."""
        now = time.perf_counter()
        self.tokens = min(self.capacity,
                          self.tokens + (now - self.last) * self.rate)
        self.last = now
        self.tokens -= n
        if self.tokens < 0:
            time.sleep(-self.tokens / self.rate)
            self.tokens = 0
```

**Cường — Server full đúng cách (R2.7 — 0,3đ):**

```python
# Trong serve_client() — PHẢI accept() trước, kiểm tra sau, gửi ERROR, đóng
# Không từ chối tầng OS — client phải phân biệt "server đầy" vs "server chết"
# Đã xử lý qua semaphore.acquire(blocking=False) trong UserRegistry.login()
# → Nếu semaphore = 0: trả ERROR_SERVER_BUSY (0x0078) → đóng socket
```

**Hưng — `tests/test_throttle.py` (đo nghiêm túc, 3 lần):**

```python
def test_throttle_limit():
    LIMIT_BPS = 500 * 1024   # 500 KB/s
    FILE_SIZE = 20 * 1024 * 1024   # 20 MB — đủ lớn để đo chính xác

    speeds = []
    for _ in range(3):
        started = time.perf_counter()
        upload_with_rate(sock, "testdata/large_20mb.bin", rate=LIMIT_BPS)
        elapsed = time.perf_counter() - started
        speed = FILE_SIZE / elapsed
        speeds.append(speed)
        assert speed <= LIMIT_BPS * 1.10, (
            f"Vượt ngưỡng: {speed/1024:.1f}KB/s > {LIMIT_BPS*1.1/1024:.1f}KB/s"
        )

    print(f"[OK] 3 lần đo: {[f'{s/1024:.0f}KB/s' for s in speeds]}")
    # Ghi CSV
    with open("docs/test-results/throttle.csv", "a") as f:
        f.write(f"{LIMIT_BPS},{','.join(str(s) for s in speeds)}\n")
```

#### ✅ Nghiệm thu cuối Ngày 6

- □ Progress bar mượt, % không lùi, in 100% sau checksum + rename, speed tính từ byte gửi lần này
- □ `python tests/test_throttle.py` — 3 lần đo ≤ ngưỡng + 10%
- □ Client thứ (max+1) nhận ERROR "server is full", server không crash, 10 client cũ tiếp tục
- □ 2 client throttle song song: tổng thời gian ≈ thời gian 1 client (bucket riêng nhau)

---

## PHẦN 7: NGÀY 7 (07/8): 🚪 CỔNG PHASE 2 + BÁO CÁO + NỘP

### Checklist cổng Phase 2 (trên máy "sạch" — clone repo mới, làm theo README từ đầu)

| # | Kiểm tra | Owner | Kết quả |
|---|---|---|---|
| □ | `python -m unittest discover -s tests -v` — **22 test Phase 1 + toàn bộ Phase 2 PASS** | Bình | |
| □ | `python tools/stress_clients.py --clients 12 --rounds 20 --seed 2026` — JSON/CSV output | Bình | |
| □ | `python tests/test_multi.py` — 10/10 OK × **3 lần liên tiếp** | Bình | |
| □ | `python tests/test_resume.py` — kill ở 37% + 73%, resume đúng offset, checksum OK | Hưng | |
| □ | `python tests/test_churn.py` — 500 vòng, handle/thread không tăng | Cường | |
| □ | `python tests/test_throttle.py` — ≤ ngưỡng + 10%, 3 lần, CSV saved | Hưng | |
| □ | Client thứ (max+1) nhận ERROR_SERVER_BUSY, server không crash | Cường | |
| □ | bob không đụng được file alice — NOT_FOUND | Cường | |
| □ | 2 client cùng alice upload cùng file → 1 người FILE_BUSY | Cường | |
| □ | Upload trùng tên file hoàn chỉnh → ERROR_FILE_EXISTS | Cường | |
| □ | `python -m unittest tests.test_protocol` — golden vector khớp byte-for-byte | Bình | |
| □ | `DOWNLOAD ../secret` → ERROR, không crash | Bình | |

### Báo cáo Phase 2 — nội dung bắt buộc

| Mục | Nội dung | Owner |
|---|---|---|
| Kiến trúc | Thread-per-client, lý do chọn, sơ đồ | Cường |
| Mini-RFC | Bảng opcode, payload format, error code, state machine, hex dump | Bình |
| Namespace + Lock | `storage/<username>/`, 2 lớp validation, FileLockRegistry, thứ tự lock | Cường |
| Resume | Sidecar `.part.json`, offset handshake, hash prefix, commit | Hưng |
| Progress + Throttle | TokenBucket khởi đầu rỗng, công thức speed, ETA | Hưng |
| Duplicate policy | 3 trường hợp rõ ràng | Cường |
| Test results | Bảng số liệu: 10 client, throttle CSV, resume 2 offset | Bình tổng hợp |

### Kịch bản demo (5–8 phút)

| Thời gian | Nội dung | Người demo |
|---|---|---|
| 0:00–0:45 | Kiến trúc + packet header, chỉ nhanh hex dump | Bình |
| 0:45–2:10 | Khởi server, LOGIN 3 user, namespace riêng, upload/download song song | Cường |
| 2:10–3:20 | Chạy stress 10-12 client, chỉ log/summary PASS | Bình + Cường |
| 3:20–5:20 | Upload file lớn, ngắt giữa chừng, reconnect, resume đúng offset + checksum | Hưng |
| 5:20–6:20 | Progress bar + throttle 500 KB/s, chỉ kết quả ≤ 550 KB/s | Hưng |
| 6:20–7:10 | Max client + 1 → ERROR; upload trùng tên → ERROR; 2 client cùng file → FILE_BUSY | Cường |
| 7:10–8:00 | Rubric map + Q&A | Cả nhóm |

**Phương án dự phòng demo:** file test nằm sẵn, lệnh copy-paste trong `demo_commands.txt`, terminal đặt tên Alice/Bob/Server, video dự phòng quay trên đúng release commit. Không phụ thuộc Internet.

---

## PHẦN 8: SAI LẦM KINH ĐIỂN PHASE 2

❌ **1. Race condition trên UserRegistry.** Không lock → mất 0,5đ R2.1. Dùng semaphore cho capacity + Lock cho map.

❌ **2. Token bucket khởi đầu đầy.** Bucket đầy → tốc độ trung bình cả file vượt ~11% → rớt R2.6. **Khởi đầu `tokens = 0`**, capacity = 1 chunk.

❌ **3. Xóa `.part` khi lỗi kết nối.** Phase 2 phải GIỮ `.part` để resume. Chỉ xóa khi checksum sai (cách ly `.bad`). Sửa `session.py` + cập nhật `test_errors.py`.

❌ **4. Không validate sidecar khi resume.** Nếu chỉ dùng `getsize(.part)`, upload `photo.jpg` 10MB dở, sau upload `photo.jpg` 500KB → server đọc offset 6MB cho file 500KB → **file hỏng**. Phải validate `total_size + sha256` từ sidecar.

❌ **5. Quên `finally: conn.close()`.** `test_churn.py` sẽ lộ — server cạn tài nguyên sau 100 vòng.

❌ **6. Hash chỉ phần resume, bỏ prefix.** Nếu server đã có 6 MB, hasher phải "bơm" 6 MB đó trước → không thì checksum cuối chỉ hash phần mới → MISMATCH dù dữ liệu đúng.

❌ **7. Progress tính speed từ byte 0 khi resume.** Chỉ tính `(done - resumed_from) / time` — tránh tốc độ ảo gấp 10 lần khi resume 10% cuối.

❌ **8. Từ chối server-full ở tầng OS.** Phải `accept()` rồi mới gửi ERROR — client phải phân biệt "server đầy" vs "server chết".

❌ **9. test_multi pass 1 lần là đủ.** Race condition ẩn — chạy **3 lần liên tiếp** không trượt mới tin. Dùng seed cố định để reproduce.

❌ **10. Giữ registry lock khi I/O.** Thứ tự lock BẮT BUỘC: `registry_lock → file_lock`. Không bao giờ đảo. Không giữ registry lock trong lúc đọc/ghi file → deadlock.

❌ **11. Binary data qua hàm chuỗi.** File chứa byte 0x00 → `decode()` raises `UnicodeDecodeError`. Payload file là `bytes` từ đầu đến cuối. Đề bài cảnh báo nguyên văn điều này.

❌ **12. `FILE_UPLOAD` payload thiếu SHA-256.** Nếu không gửi hash từ đầu, sidecar không có expected hash → không validate được resume → phải chấp nhận mọi file trùng tên làm resume.

---

## PHỤ LỤC A: ĐẶC TẢ GIAO THỨC MINI-RFC (R2.2 — 0,5đ)

### Cấu trúc gói tin

```
 0               1               2               3
 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7 0 1 2 3 4 5 6 7
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           LENGTH (4B)                          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          OPCODE (2B)          |         USER_ID (2B)          |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                        PAYLOAD (biến đổi)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

LENGTH = 2 + 2 + len(PAYLOAD)   ← KHÔNG tính 4 byte của chính LENGTH
Tất cả integer: network byte order (big-endian).
USER_ID = 0 trước LOGIN; sau LOGIN phải khớp session.
```

### Bảng Opcode

| Opcode | Hex | Chiều | Payload format |
|---|---|---|---|
| LOGIN | 0x01 | C→S | `name_len:2` + `username:utf8` |
| LOGOUT | 0x02 | C→S | rỗng |
| FILE_LIST | 0x10 | C→S | rỗng |
| FILE_LIST_RESP | 0x11 | S→C | `count:4` + N×(`name_len:2` + `name` + `size:8`) |
| **FILE_UPLOAD** | 0x12 | C→S | `name_len:2` + `name` + `total_size:8` + `offset:8` + **`sha256:32`** |
| FILE_DOWNLOAD | 0x13 | C→S | `name_len:2` + `name` + `req_offset:8` |
| FILE_CHUNK | 0x14 | C↔S | `offset:8` + `data:biến đổi` |
| FILE_DELETE | 0x15 | C→S | `name_len:2` + `name` |
| **ACK** | 0x20 | S→C | `acked_opcode:2` + `next_offset:8` + **`sha256:32` (optional)** |
| ERROR | 0xFF | S→C | `error_code:2` + `msg_len:2` + `message:utf8` |

### Bảng Error Code

| Code | Hex | Tên | Khi dùng |
|---|---|---|---|
| 100 | 0x0064 | MALFORMED | Packet không parse được |
| 101 | 0x0065 | UNKNOWN_OPCODE | Opcode không nhận ra |
| 102 | 0x0066 | INVALID_USERNAME | Tên user không hợp lệ |
| 103 | 0x0067 | NOT_LOGGED_IN | Opcode không được phép ở trạng thái hiện tại |
| 104 | 0x0068 | USER_ID_MISMATCH | user_id trong packet khác session |
| 105 | 0x0069 | USERNAME_IN_USE | Username đang online |
| 110 | 0x006E | INVALID_FILENAME | Tên file không hợp lệ / path traversal |
| 111 | 0x006F | NOT_FOUND | File không tồn tại |
| 112 | 0x0070 | FILE_EXISTS | File hoàn chỉnh đã tồn tại (dùng DELETE trước) |
| 113 | 0x0071 | OFFSET_MISMATCH | Chunk offset sai |
| 114 | 0x0072 | CHECKSUM_MISMATCH | SHA-256 không khớp |
| 115 | 0x0073 | RESUME_CONFLICT | Sidecar không khớp (total_size hoặc sha256 khác) |
| 120 | 0x0078 | SERVER_BUSY | Quá max client |
| 121 | 0x0079 | FILE_BUSY | Lock timeout |
| 130 | 0x0082 | INTERNAL_ERROR | Lỗi server (đã log, không lộ path) |

### State machine Session

```
CONNECTED ──LOGIN──→ AUTHENTICATED ──FILE_UPLOAD──→ UPLOADING
                           │                             │
                     FILE_DOWNLOAD                   FILE_CHUNK(×N)
                           │                             │
                      DOWNLOADING              received==total_size
                           │                     + checksum OK
                    server gửi                         │
                    FILE_CHUNK(×N)                 AUTHENTICATED
                    ACK cuối                       (os.replace)
                           │
                        LOGOUT → CLOSED (cleanup idempotent)

Opcode sai trạng thái → ERROR_NOT_LOGGED_IN hoặc ERROR_MALFORMED (không đóng kết nối)
```

### Ví dụ hex dump — FILE_UPLOAD (data.bin, 10.000.000 byte, offset=0, user_id=7)

```
00 00 00 3E  ← LENGTH = 62 (= 2+2+58 — KHÔNG tính 4 byte này)
00 12        ← OPCODE = FILE_UPLOAD (0x12)
00 07        ← USER_ID = 7
00 08        ← filename_len = 8
64 61 74 61 2E 62 69 6E  ← "data.bin" (ASCII)
00 00 00 00 00 98 96 80  ← total_size = 10,000,000
00 00 00 00 00 00 00 00  ← offset = 0
<32 bytes SHA-256 của toàn bộ file>
```

Kiểm chứng: payload = 2+8+8+8+32 = 58 → LENGTH = 2+2+58 = 62 = 0x3E ✓

---

## PHỤ LỤC B: MA TRẬN KIỂM THỬ & TIÊU CHÍ PASS ĐỊNH LƯỢNG

| Scenario | Rubric | Cách tự động hóa | Ngưỡng PASS |
|---|---|---|---|
| 12 client mixed workload | R2.1 | Barrier khởi chạy đồng thời, watchdog timeout 120s | 100% operation PASS, hash đúng, không timeout/deadlock |
| 500 connect/disconnect | R2.1 | Loop, đo thread/handle trước-sau | Thread/file ≤ baseline + 2/5; server sống |
| Fragment/coalesce packet | R2.2 | Fake socket 1 byte/lần + ghép 3 packet | Đọc đúng 3 packet; oversize bị từ chối |
| Alice/Bob same filename | R2.3 | 2 user upload `report.bin` hash khác; list/download chéo | Mỗi user chỉ thấy bản mình; cross-access NOT_FOUND |
| 2 session cùng user, cùng file | R2.3/R2.7 | 2 thread cùng alice upload `big.bin` | 1 lock, 1 FILE_BUSY; file cuối không hỏng |
| Resume upload ở 37% và 73% | R2.4 | Subprocess kill sau N giây | Bytes gửi lại ≤ remainder + 1 chunk; SHA-256 đúng |
| Resume download ở 37% và 73% | R2.4 | Đóng client sau N byte, giữ .part | Chunk đầu đúng offset; hash cuối đúng |
| Progress accuracy | R2.5 | Inject callback ghi danh sách percent/bytes | 0≤p≤100; không giảm; kết thúc 100% |
| 500 KB/s/client × 3 lần | R2.6 | File 20 MB, đo byte/time | Mỗi lần ≤ 550 KB/s; CSV saved |
| Max client + 1 | R2.7 | Giữ max session, kết nối thêm 1 | ERROR_SERVER_BUSY; session cũ không bị rớt |
| Checksum corruption | R2.4 + regression | Corrupt 1 byte staging trước finalize | CHECKSUM_MISMATCH; file không promote; server sống |

### Lệnh acceptance chuẩn (README phải khớp chính xác)

```bash
# Regression + unit/integration
python -m unittest discover -s tests -v

# Interface Phase 2
python server.py --host 0.0.0.0 --port 9000 --max-clients 10 --rate-kbps 500
python client.py 127.0.0.1 9000 --username alice LIST
python client.py 127.0.0.1 9000 --username alice UPLOAD testdata/large_100mb.bin

# Stress test (bắt buộc theo R2.1)
python tools/stress_clients.py --host 127.0.0.1 --port 9000 --clients 12 --rounds 20 --seed 2026
```

---

*Tài liệu liên quan:*
- [ke_hoach_chi_tiet.md](file:///C:/Users/cuong/Downloads/HK3/MẠNG%20MÁY%20TÍNH/ĐỒ%20ÁN/Socket_Programming/docs/ke_hoach_chi_tiet.md) — Phase 1 plan
- [notes.md](file:///C:/Users/cuong/Downloads/HK3/MẠNG%20MÁY%20TÍNH/ĐỒ%20ÁN/test/notes.md) — trạng thái Phase 1 & chuẩn bị Phase 2
- [assignment_text.txt](file:///C:/Users/cuong/Downloads/HK3/MẠNG%20MÁY%20TÍNH/ĐỒ%20ÁN/test/assignment_text.txt) — đề bài gốc
- [Phase2_Plan_Socket_Programming.docx](file:///C:/Users/cuong/Downloads/Phase2_Plan_Socket_Programming.docx) — nguồn tham khảo chính
