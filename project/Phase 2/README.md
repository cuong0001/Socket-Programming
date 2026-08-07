# Phase 2 — Socket Programming (File Transfer Client/Server)

Server/client truyền file qua giao thức nhị phân tự định nghĩa (không dùng
FTP/HTTP), hỗ trợ nhiều user đồng thời, mỗi user một namespace lưu trữ
riêng, resume upload/download dở dang, giới hạn băng thông, và progress bar.

Hướng dẫn này giả định chạy trên máy sạch — clone repo mới, làm theo đúng
thứ tự bên dưới là chạy được, không cần đoán thêm gì.

## 1. Yêu cầu

- Python 3.10 trở lên (dùng cú pháp `str | None`, generic `tuple[...]` có sẵn từ 3.9+).
- Không cần cài package nào để **chạy server/client** — chỉ dùng thư viện chuẩn.
- Chạy **toàn bộ test suite** cần thêm `psutil` (chỉ `tests/test_churn.py` dùng, để đọc thread/handle count của server chạy ở process riêng).

## 2. Cài đặt

```bash
cd project/Phase\ 2

# Chỉ cần nếu muốn chạy full test suite (test_churn.py cần psutil):
pip install -r requirements-test.txt
```

## 3. Chạy server

```bash
python server.py <port> [host] [max_clients]
```

Ví dụ:

```bash
python server.py 9000                 # bind mọi interface, max_clients mặc định = 10
python server.py 9000 "" 4             # override max_clients (hữu ích khi demo SERVER_BUSY)
```

- `storage/` (dữ liệu user) và `logs/server.log` (log R1.4) được tạo trong **thư mục hiện tại** — luôn chạy từ `project/Phase 2/` để đúng layout, đường dẫn thật được in ra ngay khi server khởi động.
- Server tự in `[OK] Storage dir: ...` / `[OK] Max clients: N` khi sẵn sàng.
- Dừng sạch bằng `Ctrl+C` (đóng socket, ghi log DISCONNECT cho các session đang mở qua timeout tự nhiên — không cần force-kill).

## 4. Chạy client

```bash
python client.py <host> <port> --username <tên> [--limit <KBps>] ["<lệnh>"]
```

- Bỏ `["<lệnh>"]` → vào **chế độ tương tác**: gõ lệnh từng dòng, gõ `exit` để LOGOUT sạch và thoát.
- Truyền `["<lệnh>"]` → chạy **một lệnh rồi thoát**; exit code phản ánh đúng thành/bại (0 = thành công, 1 = lỗi) — dùng được trong script.
- `--limit N` giới hạn tốc độ upload/download ở N KB/s (0 = không giới hạn, mặc định).

| Lệnh | Cú pháp | Ghi chú |
|---|---|---|
| `UPLOAD` | `UPLOAD <đường dẫn file cục bộ>` | Tự tính SHA-256 trước khi gửi; tự resume nếu có `.part` tương thích trên server; từ chối nếu file đã tồn tại hoàn chỉnh (phải `DELETE` trước) |
| `DOWNLOAD` | `DOWNLOAD <tên file trên server>` | Lưu vào `downloads/` (tạo tự động); tự resume nếu trước đó tải dở |
| `DELETE` | `DELETE <tên file>` | Chỉ xoá được file trong namespace của username đang login |
| `LIST` | `LIST` | Liệt kê file trong namespace của user hiện tại |

Ví dụ:

```bash
# Một lệnh rồi thoát:
python client.py 127.0.0.1 9000 --username alice "UPLOAD testdata/512b.bin"
python client.py 127.0.0.1 9000 --username alice --limit 500 "UPLOAD testdata/10mb.bin"

# Chế độ tương tác:
python client.py 127.0.0.1 9000 --username alice
> LIST
> DOWNLOAD 512b.bin
> exit
```

File test mẫu (nhiều kích thước, kể cả byte `0x00` và file 150MB) được tạo bằng:

```bash
python testdata/make_testdata.py
```

## 5. Chạy test

```bash
cd project/Phase\ 2
pip install -r requirements-test.txt
python -m unittest discover -s tests -t tests -v
```

Kỳ vọng: **toàn bộ PASS** (66/66 tại thời điểm viết README này — xem `docs/ke_hoach_phase2.md` phần "Nhật ký triển khai" để biết số liệu mới nhất qua từng PR). Thời gian chạy toàn bộ suite khoảng 40s trên máy phát triển.

Chạy riêng các test đáng chú ý:

```bash
# 10 client đồng thời x 3 vòng (barrier-sync, seed cố định)
python -m unittest discover -s tests -t tests -p test_multi.py -v

# 500 vòng connect/LOGIN/LOGOUT, kiểm tra thread/handle không tăng tuyến tính
python -m unittest discover -s tests -t tests -p test_churn.py -v

# Throttle 500KB/s x 3 lần qua luồng client thật, xuất CSV vào docs/test-results/
python -m unittest discover -s tests -t tests -p test_throttle.py -v

# Capacity: client thứ (max_clients+1) nhận SERVER_BUSY, server không crash
python -m unittest discover -s tests -t tests -p test_server_busy.py -v

# Xác nhận FILE_BUSY không thể xảy ra qua giao thức thật (đọc docstring trong file để biết lý do)
python -m unittest discover -s tests -t tests -p test_file_busy.py -v
```

`test_multi.py` và `test_churn.py` nên chạy lại vài lần liên tiếp trước khi tin — race condition thường chỉ lộ ra không đều.

## 6. Demo

Kịch bản demo 5–8 phút, lệnh copy-paste theo từng terminal (đã rehearse thật bằng raw socket trước khi viết, không phải suy đoán từ code): xem [`demo_commands.txt`](demo_commands.txt).

## 7. Tài liệu khác

- [`docs/ke_hoach_phase2.md`](docs/ke_hoach_phase2.md) — kế hoạch triển khai gốc + nhật ký thực tế qua từng PR (task-based, không theo ngày).
- [`docs/report_cuong_server_lock_duplicate.md`](docs/report_cuong_server_lock_duplicate.md) — kiến trúc server, namespace/lock 2 lớp, duplicate-upload policy, vì sao `FILE_BUSY` không quan sát được qua protocol thật.

## 8. Kiến trúc tóm tắt

- **Thread-per-client**: mỗi kết nối được `server.py` giao cho một `threading.Thread(daemon=True)` riêng — phù hợp workload I/O-bound, không cần viết lại theo mô hình async.
- **Giới hạn tài nguyên 3 lớp**: capacity qua semaphore (`accept()` trước, kiểm tra slot sau — để phân biệt "server đầy" với "server chết"), một session/username qua `UserRegistry`, và idle timeout 30s để dọn session chết (crash/mất mạng không gửi FIN).
- **Namespace**: mỗi user một thư mục `storage/<username>/`, cách ly hoàn toàn — không cần kiểm tra quyền sở hữu từng file.
- **Validation 2 lớp** cho cả username lẫn filename: lớp 1 chặn ký tự nguy hiểm (`/`, `\`, `..`, `:`, tên thiết bị Windows), lớp 2 `os.path.realpath()` + kiểm tra containment thật — độc lập với lớp 1.
- **`FileLockRegistry`**: lock theo `(username, filename)`, tạo lazy, tự dọn khi không còn ai giữ tham chiếu (refcount).
- **Logging (R1.4)**: mỗi lệnh sinh đúng 1 dòng log (`logs/server.log`), kể cả các nhánh từ chối sớm.

Chi tiết đầy đủ + lý do thiết kế: xem `docs/report_cuong_server_lock_duplicate.md`.
