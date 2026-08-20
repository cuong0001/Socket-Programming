# Giai đoạn 2 — Client và Server truyền file

Đây là dịch vụ truyền file qua TCP với giao thức nhị phân tự định nghĩa, hỗ trợ nhiều client đồng thời, namespace riêng theo username, resume upload/download, kiểm tra SHA-256, progress, giới hạn băng thông, mã lỗi có cấu trúc và `SERVER_BUSY`.

## Yêu cầu và cài đặt

- Python 3.10 trở lên.
- Chạy client/server chỉ cần thư viện chuẩn Python.
- Full test suite cần `psutil` cho bài kiểm tra churn.

```powershell
Set-Location "project/Phase 2"
python -m pip install -r requirements-test.txt
```

Luôn chạy lệnh từ thư mục này để `storage/` và `logs/` được tạo đúng vị trí.

## Chạy server

```text
python server.py <port> [host] [max_clients]
```

```powershell
python server.py 9000
python server.py 9000 "" 4
```

Mặc định server cho phép 10 client hoạt động. Dùng `max_clients=4` khi demo `SERVER_BUSY`. Dừng server bằng `Ctrl+C`.

## Chạy client

```text
python client.py <host> <port> --username <name> [--limit <KBps>] [command]
```

Không truyền command để vào chế độ tương tác; gõ `exit` để logout. Khi truyền một command, client trả exit code 0 nếu thành công và 1 nếu lỗi.

| Lệnh | Ví dụ | Ý nghĩa |
|---|---|---|
| `LIST` | `LIST` | Liệt kê file trong namespace của user hiện tại. |
| `UPLOAD` | `UPLOAD testdata/512b.bin` | Upload, kiểm tra SHA-256 và resume staging tương thích. |
| `DOWNLOAD` | `DOWNLOAD 512b.bin` | Download vào `downloads/`, hỗ trợ resume. |
| `DELETE` | `DELETE 512b.bin` | Xóa file trong namespace hiện tại. |

```powershell
python testdata/make_testdata.py
python client.py 127.0.0.1 9000 --username alice "UPLOAD testdata/512b.bin"
python client.py 127.0.0.1 9000 --username alice "LIST"
python client.py 127.0.0.1 9000 --username alice --limit 500 "UPLOAD testdata/10mb.bin"
python client.py 127.0.0.1 9000 --username alice "DOWNLOAD 512b.bin"
python client.py 127.0.0.1 9000 --username alice "DELETE 512b.bin"
```

## Chạy test

```powershell
python -m unittest discover -s tests -t tests -v
```

Các test quan trọng:

```powershell
python -m unittest discover -s tests -t tests -p test_multi.py -v
python -m unittest discover -s tests -t tests -p test_churn.py -v
python -m unittest discover -s tests -t tests -p test_server_busy.py -v
python -m unittest discover -s tests -t tests -p test_file_busy.py -v
python -m unittest discover -s tests -t tests -p test_throttle.py -v
python -m unittest discover -s tests -t tests -p test_stress_clients.py -v
```

`test_throttle.py` chạy ba lần upload 2 MiB và ghi `docs/test-results/throttle.csv`. Stress runner ghi JSON/CSV vào `docs/test-results/`.

## Kiến trúc tóm tắt

- **Thread-per-client:** mỗi socket được xử lý bởi một daemon thread; semaphore giới hạn số client.
- **Namespace:** file nằm trong `storage/<username>/`; validator và real-path containment chặn path traversal.
- **Lock:** `FileLockRegistry` khóa theo `(username, filename)` và dọn entry không còn tham chiếu.
- **Logging:** logger dùng chung, thread-safe, ghi command/transfer vào `logs/server.log` và stdout, kể cả nhánh lỗi.
- **SERVER_BUSY:** khi hết slot, server trả mã lỗi có cấu trúc mà không crash; slot được giải phóng khi session kết thúc.

Xem [`docs/protocol.md`](docs/protocol.md) và [`docs/architecture.md`](docs/architecture.md) để biết chi tiết.

## Nghiệm thu release

Kết quả test/stress/throttle dưới đây được đo trên commit tích hợp `f156061`. Kịch bản resume được cập nhật theo commit merge PR #31 `8eccdca`:

```text
Full suite: 70/70 tests pass
Stress: 240/240 client pass, 1.680 operations, 0 failure
Resume: upload ngắt ở 37% và 73%; download ngắt ở 50%; mỗi lần reconnect đúng offset và SHA-256 OK
Throttle: 472,42 / 471,15 / 471,55 KB/s với limit 500 KB/s
```

Chạy stress (server phải đang lắng nghe ở port 9000):

```powershell
python tools/stress_clients.py --host 127.0.0.1 --port 9000 --clients 12 --rounds 20 --seed 2026
```

Chạy resume demo khi port 9000 đang rảnh:

```powershell
python tools/resume_demo.py
```

Artifact định lượng nằm trong [`docs/test-results/`](docs/test-results/).

## Demo

Làm theo [`demo_video_script.md`](demo_video_script.md) để quay video 5–8 phút, gồm ba client truyền đồng thời, upload/download cơ bản, stress, resume sau khi ngắt giữa chừng, SHA-256, throttle, file trùng và `SERVER_BUSY`.
