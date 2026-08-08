# Kịch bản video demo Phase 2 (5–8 phút)

Kịch bản này được thiết kế cho video dài khoảng **7 phút**, đáp ứng trực tiếp yêu cầu đề bài:

- truyền file cơ bản;
- tối thiểu ba client hoạt động đồng thời;
- ngắt kết nối giữa chừng và resume thành công;
- kiểm tra SHA-256 sau resume.

Ngoài phần bắt buộc, video còn cho thấy namespace riêng, stress 12 client, progress, throttle, `FILE_EXISTS` và `SERVER_BUSY`.

## 1. Chuẩn bị trước khi bấm quay

Thực hiện trước để thời gian tạo file và sắp xếp cửa sổ không tính vào video.

### Môi trường

Chạy tất cả lệnh từ:

```powershell
Set-Location "project/Phase 2"
```

Tạo dữ liệu mẫu:

```powershell
python testdata/make_testdata.py
```

Kiểm tra port 9000 chưa bị chương trình khác sử dụng. Nên quay trên một checkout sạch để `storage/` và `downloads/` không chứa dữ liệu từ lần demo trước.

### Chuẩn bị terminal

Mở sáu terminal và đặt tên:

1. `SERVER`
2. `ALICE`
3. `BOB`
4. `CAROL`
5. `STRESS / RESUME`
6. `CAPACITY`

Trong ba terminal Alice/Bob/Carol, dán sẵn các lệnh upload nhưng chưa nhấn Enter:

```powershell
# ALICE
python client.py 127.0.0.1 9000 --username video-alice --limit 500 "UPLOAD testdata/10mb.bin"

# BOB
python client.py 127.0.0.1 9000 --username video-bob --limit 500 "UPLOAD testdata/10mb.bin"

# CAROL
python client.py 127.0.0.1 9000 --username video-carol --limit 500 "UPLOAD testdata/10mb.bin"
```

Giới hạn 500 KB/s giúp mỗi upload 10 MiB kéo dài khoảng 20 giây, đủ để nhìn thấy cả ba client truyền đồng thời.

## 2. Timeline và lời thoại

## 0:00–0:35 — Giới thiệu hệ thống

### Hình ảnh

Mở nhanh `docs/architecture.md` và `docs/protocol.md`, chỉ vào packet header và sơ đồ kiến trúc.

### Lời thoại gợi ý

> Đây là hệ thống truyền file qua TCP sử dụng giao thức nhị phân tự định nghĩa. Mỗi packet có LENGTH, OPCODE, USER_ID và PAYLOAD, toàn bộ số nguyên dùng network byte order. Server dùng mô hình thread-per-client có semaphore giới hạn số kết nối. Mỗi username có namespace riêng và các thao tác file được bảo vệ bằng lock theo cặp username và filename.

Không đọc toàn bộ tài liệu; chỉ cho thấy packet header, opcode table và kiến trúc trong khoảng 30 giây.

## 0:35–0:55 — Khởi động server

### Terminal `SERVER`

```powershell
python server.py 9000 "" 10
```

### Lời thoại gợi ý

> Server đang lắng nghe tại port 9000 và cho phép tối đa 10 client hoạt động. Storage và log được tạo trong thư mục Phase 2. Mỗi client được xử lý bởi một worker thread riêng.

Chỉ vào các dòng `Storage dir`, `Log file` và `Max clients` nếu server in ra.

## 0:55–1:45 — Ba client truyền file đồng thời

### Thao tác

Lần lượt chuyển rất nhanh qua `ALICE`, `BOB`, `CAROL` và nhấn Enter cho ba lệnh đã dán sẵn. Khoảng cách giữa ba lần Enter nên dưới hai giây.

Sau đó chia màn hình hoặc chuyển nhanh giữa ba terminal để cho thấy cả ba progress bar đang tăng cùng lúc.

### Lời thoại gợi ý

> Bây giờ ba client Alice, Bob và Carol cùng upload file 10 MiB. Cả ba dùng cùng tên `10mb.bin`, nhưng không xung đột vì dữ liệu được lưu trong ba namespace khác nhau. Mỗi client có token bucket riêng ở giới hạn 500 KB/s, nên các progress bar tiến đồng thời thay vì bị serialize toàn hệ thống.

Chuyển sang `SERVER` khoảng 5 giây để cho thấy các dòng kết nối và transfer của ba client được ghi xen kẽ nhưng không chồng dòng.

Đợi cả ba client hiện:

```text
[OK] SHA256 Verification OK
100.0%
```

### Điểm cần nhìn thấy trong video

- ba username khác nhau;
- ba progress bar đang chạy trong cùng khoảng thời gian;
- cả ba đạt SHA-256 OK;
- progress kết thúc tại 100%.

## 1:45–2:25 — LIST và DOWNLOAD cơ bản

### Terminal `ALICE`

```powershell
python client.py 127.0.0.1 9000 --username video-alice "LIST"
python client.py 127.0.0.1 9000 --username video-alice "DOWNLOAD 10mb.bin"
```

### Terminal `BOB`

```powershell
python client.py 127.0.0.1 9000 --username video-bob "LIST"
```

### Lời thoại gợi ý

> LIST của Alice và Bob đều thấy `10mb.bin`, nhưng đây là hai file nằm trong hai thư mục user khác nhau. Alice tải file về bằng DOWNLOAD. Client nhận file theo chunk, kiểm tra offset và chỉ commit file sau khi SHA-256 khớp hoàn toàn.

Chỉ cần quay đến khi Alice hiện `SHA256 Verification OK` và 100%.

## 2:25–3:05 — Stress 12 client và bằng chứng R2.1

### Terminal `STRESS / RESUME`

```powershell
python tools/stress_clients.py --host 127.0.0.1 --port 9000 --clients 12 --rounds 20 --seed 2026
```

### Lời thoại gợi ý

> Đây là script stress có seed cố định 2026. Mỗi vòng khởi chạy 12 logical client, trong khi server chỉ có 10 slot nên script cũng kiểm tra cơ chế SERVER_BUSY và retry. Mỗi client thực hiện login, upload, list, download, kiểm tra SHA-256, delete và logout.

Chờ kết quả:

```text
[PASS] 240/240 clients; 1680 operations
```

Mở nhanh `docs/test-results/stress.json` hoặc `stress.csv`, chỉ vào:

- `clients = 12`;
- `rounds = 20`;
- `seed = 2026`;
- `successful_clients = 240`;
- `failed_clients = 0`.

## 3:05–3:20 — Dừng server để chuẩn bị resume demo

### Terminal `SERVER`

Nhấn:

```text
Ctrl+C
```

### Lời thoại gợi ý

> Phần resume demo sẽ tự khởi động một server riêng trên port 9000, nên tôi dừng server hiện tại trước.

Đợi server cũ kết thúc hoàn toàn rồi mới chạy bước tiếp theo.

## 3:20–4:35 — Ngắt giữa chừng, reconnect và resume

### Terminal `STRESS / RESUME`

```powershell
python tools/resume_demo.py
```

### Lời thoại gợi ý khi script chạy

> Script tạo một file ngẫu nhiên 20 MiB và tính SHA-256 của toàn bộ file. Nó kiểm tra hai trường hợp upload bị ngắt ở khoảng 37% và 73%, rồi kiểm tra download bị ngắt ở 50%. Mỗi lần, socket bị đóng cưỡng bức để mô phỏng mất mạng trước khi client reconnect và tiếp tục từ offset server hoặc file `.part` đã lưu.

Khi hiện:

```text
[DEMO] Upload connection killed at ... bytes (37.0% of 20.0MB)
[DEMO] Resuming upload from ... bytes...
[DEMO] Upload resume at 37% successful; SHA-256 verified.

[DEMO] Upload connection killed at ... bytes (73.0% of 20.0MB)
[DEMO] Resuming upload from ... bytes...
[DEMO] Upload resume at 73% successful; SHA-256 verified.
```

nói:

> Server giữ file `.part` và sidecar thay vì xóa dữ liệu đã nhận. Hai mốc khác nhau chứng minh resume không phụ thuộc vào một offset cố định.

Khi hiện:

```text
[DEMO] Download connection killed at 50.0% of 20.0MB
[DEMO] Resuming download from 10485760 bytes...
[DEMO] Download resume at 50% successful; SHA-256 verified.
```

nói:

> Khi upload, client reconnect bằng cùng username và metadata; server xác nhận staging tương thích và trả đúng offset của từng lần ngắt. Khi download, client giữ file `.part` 10 MiB và yêu cầu tiếp tục từ offset 10.485.760 byte, thay vì tải lại từ đầu.

Kết thúc phải quay rõ:

```text
100.0%
[OK] SHA256 Verification OK
[DEMO] Resume successful!
[DEMO] Server stopped.
[DEMO] Test file cleaned up.
```

### Lời thoại kết thúc phần resume

> Sau khi nhận đủ byte, server hash toàn bộ file upload, so sánh SHA-256 và chỉ atomic commit khi digest khớp. Client cũng xác minh SHA-256 của file download hoàn chỉnh. Các file tạm và server demo đều được cleanup.

## 4:35–5:05 — Bằng chứng throttle

Mở file `docs/test-results/throttle.csv`.

### Lời thoại gợi ý

> Throttle được đo ba lần với file 2 MiB và giới hạn 500 KB/s. Ba tốc độ đo trên release là 472,42; 471,15 và 471,55 KB/s. Tất cả đều thấp hơn limit 500 KB/s và thấp hơn ngưỡng chấp nhận của đề là limit cộng 10%, tức 550 KB/s.

Không cần chạy lại test throttle trong video nếu muốn tiết kiệm thời gian; CSV là artifact từ lần nghiệm thu release.

## 5:05–5:35 — Chính sách file trùng

### Terminal `SERVER`

Khởi động lại server:

```powershell
python server.py 9000 "" 3
```

### Terminal `ALICE`

```powershell
python client.py 127.0.0.1 9000 --username video-alice "UPLOAD testdata/10mb.bin"
```

Kết quả mong đợi:

```text
ERROR 112 / FILE_EXISTS
file exists -- DELETE first
```

### Lời thoại gợi ý

> File hoàn chỉnh đã tồn tại nên server từ chối bằng FILE_EXISTS và không ghi đè. Chính sách cập nhật là DELETE rõ ràng rồi mới UPLOAD lại, tránh để client khác đọc trúng file đang bị thay thế.

## 5:35–6:35 — SERVER_BUSY và server vẫn hoạt động

Mở ba session tương tác và giữ chúng không thoát.

### Terminal `ALICE`

```powershell
python client.py 127.0.0.1 9000 --username cap-alice
```

### Terminal `BOB`

```powershell
python client.py 127.0.0.1 9000 --username cap-bob
```

### Terminal `CAROL`

```powershell
python client.py 127.0.0.1 9000 --username cap-carol
```

Server đang dùng đủ 3/3 slot.

### Terminal `CAPACITY`

```powershell
python client.py 127.0.0.1 9000 --username overflow "LIST"
```

Kết quả mong đợi:

```text
ERROR 120 / SERVER_BUSY
server is full
```

Quay lại terminal `ALICE`, trong interactive prompt gõ:

```text
LIST
```

### Lời thoại gợi ý

> Kết nối vượt capacity nhận mã SERVER_BUSY có cấu trúc thay vì làm server crash. Các session cũ vẫn hoạt động; Alice vẫn gửi LIST bình thường. Khi một session logout, semaphore sẽ trả lại slot cho client mới.

## 6:35–7:05 — Tổng kết

### Hình ảnh

Mở bảng kết quả trong `docs/architecture.md` hoặc thư mục `docs/test-results/`.

### Lời thoại gợi ý

> Trên commit release, toàn bộ 69 test đều pass. Stress đạt 240 trên 240 client với 1.680 operations và không có failure. Hai lần upload resume ở 37% và 73%, cùng download resume ở 50%, đều tiếp tục đúng offset và có SHA-256 khớp. Throttle ba lần đều dưới giới hạn. Hệ thống đáp ứng concurrency, protocol framing, namespace, resume, progress, throttle và xử lý server đầy.

## 3. Dọn dẹp sau khi quay

Trong các client interactive, gõ:

```text
exit
```

Trong terminal server, nhấn:

```text
Ctrl+C
```

Không cần quay phần dọn dẹp nếu video đã đủ thời lượng.

## 4. Checklist trước khi xuất video

- [ ] Video dài từ 5 đến 8 phút.
- [ ] Có cảnh ba progress bar truyền đồng thời, không chỉ ba client đứng idle.
- [ ] Có ít nhất một UPLOAD, LIST và DOWNLOAD thành công.
- [ ] Có cảnh ngắt upload ở 37% và 73%, mỗi lần reconnect đúng offset.
- [ ] Có cảnh ngắt download ở 50%, resume từ offset 10.485.760 byte.
- [ ] Có cảnh SHA-256 OK sau từng lần upload/download resume.
- [ ] Có cảnh stress `240/240`, hoặc ít nhất artifact JSON/CSV rõ ràng.
- [ ] Có cảnh throttle CSV với ba lần đo.
- [ ] Có cảnh `FILE_EXISTS` và `SERVER_BUSY` nếu đủ thời gian.
- [ ] Không lộ token, mật khẩu, đường dẫn riêng tư không cần thiết hoặc cửa sổ chat cá nhân.
- [ ] Âm thanh rõ, terminal font đủ lớn, không cắt mất error/result line.

## 5. Phương án dự phòng khi quay

- Nếu ba upload kết thúc quá nhanh, luôn dùng `--limit 500` và file `10mb.bin`.
- Nếu `FILE_EXISTS` xuất hiện ngay ở lần upload đầu, đang dùng storage cũ; chuyển sang checkout sạch hoặc dùng username/filename mới.
- Nếu resume demo báo port đang bận, dừng server cũ và kiểm tra lại port 9000.
- Nếu demo live lỗi, giữ sẵn ảnh/chụp màn hình `stress.json`, `stress.csv`, `throttle.csv` và log của lần nghiệm thu release.
- Quay trên đúng commit release và ghi commit hash trong phần mô tả video.
