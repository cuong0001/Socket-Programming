# Báo cáo kiến trúc và kiểm chứng Giai đoạn 2

Báo cáo này trình bày phần việc của Cường: kiến trúc server đồng thời, namespace riêng, file lock, logging, giới hạn số client, chính sách file trùng và bằng chứng kiểm thử.

## 1. Kiến trúc thread-per-client

Server kế thừa mô hình socket và file I/O blocking. Mỗi kết nối được giao cho một daemon thread riêng, giúp state machine của từng session độc lập và không cần viết lại toàn bộ chương trình bằng `asyncio`.

Semaphore giới hạn số client hoạt động. Server `accept()` kết nối TCP trước rồi mới giữ slot; nếu hết chỗ, server trả `SERVER_BUSY` để client phân biệt server đầy với server không hoạt động. Cleanup trong `finally` giải phóng username, socket và semaphore. Socket timeout dọn các peer chết không gửi FIN.

## 2. Namespace và an toàn đường dẫn

Mỗi username có thư mục `storage/<username>/`. Hai user có thể upload cùng tên file mà không xung đột.

Hệ thống dùng hai lớp bảo vệ:

1. Validator từ chối tên rỗng, ký tự không in được, `/`, `\`, `..`, `:`, dấu chấm/khoảng trắng cuối tên, tên thiết bị Windows và hậu tố staging nội bộ.
2. Real-path containment dùng `os.path.realpath()` và xác nhận đường dẫn vẫn nằm trong storage root.

Lớp thứ hai vẫn bảo vệ hệ thống nếu một caller tương lai bỏ qua validator.

## 3. FileLockRegistry

Lock được quản lý theo `(username, filename)`. Các file độc lập vẫn chạy song song, còn thao tác trên cùng file được serialize. Entry được tạo lazy, có refcount và bị xóa khi không còn tham chiếu, kể cả trường hợp acquire timeout.

Registry lock chỉ được giữ trong thời gian tra cứu/cập nhật dictionary, không giữ trong lúc network hoặc file I/O.

### Vì sao FILE_BUSY không quan sát được qua protocol hiện tại

Protocol có mã `FILE_BUSY`, nhưng `UserRegistry` chỉ cho phép một session hoạt động cho mỗi username. Kết nối thứ hai cùng username nhận `USERNAME_IN_USE` ở bước LOGIN trước khi có thể tranh cùng `(username, filename)` lock.

`tests/test_file_busy.py` ghi lại invariant này bằng hai kết nối thật. Nếu chính sách username thay đổi, test sẽ báo rằng cần bổ sung integration test `FILE_BUSY` thật.

## 4. Logging

Một logger dùng chung ghi ra stdout và `logs/server.log`. `threading.Lock` ngăn các worker ghi chồng dòng.

Mỗi command hoặc kết quả transfer tạo đúng một record, kể cả nhánh từ chối sớm. Field do client điều khiển được sanitize để không chèn dòng log giả. Thời gian transfer dùng `time.perf_counter()` để đo elapsed time và tốc độ chính xác.

```text
[2026-07-23 10:30:15] | 127.0.0.1 | CONNECT
[2026-07-23 10:30:16] | 127.0.0.1 | UPLOAD | data.bin | 10485760B | 6.201s | 1650.4KB/s | SHA256-OK
[2026-07-23 10:30:17] | 127.0.0.1 | UPLOAD | broken.bin | 17B/100000B | 0.004s | 4.1KB/s | ABORTED
[2026-07-23 10:30:20] | 127.0.0.1 | DISCONNECT
```

## 5. Chính sách file trùng và resume

| Trạng thái hiện có | Hành vi | Lý do |
|---|---|---|
| File hoàn chỉnh tồn tại | Trả `FILE_EXISTS`, không sửa file | Không ghi đè ngầm hoặc để reader thấy file dở. |
| `.part` và sidecar tương thích | Resume từ kích thước staging hiện tại | Total size và SHA-256 xác định đúng file nguồn. |
| Metadata staging không tương thích | Xóa staging cũ, bắt đầu offset 0 | File khác trùng tên không được nối vào dữ liệu cũ. |

Sidecar lưu total size và SHA-256 dự kiến. Chỉ kích thước file không đủ để xác định một transfer có thể resume. Server chỉ commit atomically sau khi digest khớp; checksum mismatch bị quarantine và ẩn khỏi LIST.

## 6. SERVER_BUSY

Giới hạn client được cấu hình qua CLI:

```powershell
python server.py 9000 "" 4
```

Khi bốn session đang hoạt động, kết nối thứ năm nhận `0x0078 SERVER_BUSY`. Sau khi một session giải phóng slot, client mới kết nối được bình thường. Các client cũ vẫn được phục vụ trong lúc server từ chối kết nối dư.

## 7. Kết quả kiểm thử

```powershell
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -t tests -v
```

Nghiệm thu cuối được chạy trên commit tích hợp `f156061` (Windows, Python 3.14 trong môi trường kiểm tra): **69/69 test pass trong 51,309 giây**. Đây là kết quả của một revision duy nhất sau khi merge phần stress/mini-RFC, runbook/report và client acceptance.

| Bằng chứng | Kịch bản | Kết quả mong đợi |
|---|---|---|
| `test_multi.py` | 10 client đồng thời, ba vòng, cùng filename khác username | Không xung đột namespace hoặc dữ liệu. |
| `tools/stress_clients.py` | 12 client, 20 vòng, seed 2026 | 240/240 client pass; 1.680 operations; 0 failure; 11,24 giây; xuất JSON/CSV. |
| `test_churn.py` | 500 vòng connect/LOGIN/LOGOUT | Thread/handle quay gần baseline. |
| `test_server_busy.py` | Kết nối vượt capacity rồi giải phóng slot | Client dư nhận `SERVER_BUSY`; kết nối sau đó thành công. |
| `test_file_busy.py` | Kết nối thứ hai dùng username đang hoạt động | Nhận `USERNAME_IN_USE`, giải thích vì sao `FILE_BUSY` không reachable. |
| `test_storage_service.py` | Cleanup lock và containment | Entry được dọn; username escape bị chặn. |
| `test_throttle.py` | Ba upload 2 MiB ở 500 KB/s | 472,42 / 471,15 / 471,55 KB/s; đều dưới limit 500 KB/s và ngưỡng +10%; lưu CSV. |
| `tools/resume_demo.py` | Lần lượt ngắt upload 20 MiB ở 37% và 73%, sau đó ngắt download ở 50% | Cả ba kịch bản đều reconnect đúng offset; đạt 100%; SHA-256 khớp; cleanup thành công. |

Artifact được lưu tại:

- `docs/test-results/stress.json`: cấu hình, summary, failure list và kết quả từng logical client.
- `docs/test-results/stress.csv`: 240 dòng kết quả client để xử lý bằng bảng tính.
- `docs/test-results/throttle.csv`: ba lần đo tốc độ thực tế.

## 8. Kịch bản demo

File [`../demo_video_script.md`](../demo_video_script.md) chứa timeline, lời thoại và lệnh quay video 5–8 phút: ba client truyền đồng thời, namespace, stress, resume đúng offset, SHA-256, throttle, file trùng và `SERVER_BUSY`.

## 9. Kết luận

Thiết kế sử dụng thread-per-client có giới hạn, một session cho mỗi username, thư mục riêng, lock hẹp theo file và atomic commit sau SHA-256. Các lựa chọn này đáp ứng yêu cầu concurrency mà không làm phức tạp code blocking hiện có.
