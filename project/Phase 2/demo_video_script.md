# Kịch bản video demo Phase 2 (~9 phút, chia theo khối — không xen kẽ)

Bản này thay cho cách chia xen kẽ trước đây (mỗi người nói vài câu rồi đổi lượt liên tục). Ở đây mỗi người trình bày **trọn một khối liên tục ~3 phút**, đúng phần việc mình đã code, rồi mới bàn giao — dễ quay hơn (mỗi người có thể tự quay riêng khối của mình rồi ghép lại), dễ luyện tập hơn, và người xem theo dõi mạch lạc hơn vì không phải nhảy qua lại giữa các chủ đề.

Tổng thời lượng ước tính **~9 phút** (3 khối × ~3 phút), nhỉnh hơn mốc 5–8 phút gợi ý của đề một chút. Nếu cần rút ngắn, xem mục "Cách rút gọn nếu thiếu thời gian" ở cuối mỗi khối — không cắt phần nào ảnh hưởng tới 4 tiêu chí bắt buộc của đề:

- truyền file cơ bản;
- tối thiểu ba client hoạt động đồng thời;
- ngắt kết nối giữa chừng và resume thành công;
- kiểm tra SHA-256 sau resume.

## Phân công 3 khối

| Khối | Thời lượng | Người trình bày | Nội dung (đúng phần việc đã code) |
|---|---:|---|---|
| 1 | 0:00–3:00 | **Cường** | Kiến trúc server, namespace riêng, chính sách `FILE_EXISTS`, giới hạn `SERVER_BUSY` |
| 2 | 3:00–6:00 | **Bình** | Giao thức nhị phân (mini-RFC), stress test 12 client × 20 vòng |
| 3 | 6:00–9:00 | **Hưng** | Resume upload/download, progress + throttle, tổng kết |

Mỗi khối **tự khởi động server riêng** ở đầu khối (lệnh cụ thể ghi ngay dưới tiêu đề khối), nên 3 khối hoàn toàn độc lập: quay liền mạch trong một buổi hay mỗi người tự quay riêng rồi dựng nối lại đều được, không phụ thuộc trạng thái của khối trước.

## Chuẩn bị chung (trước khi bấm quay, không tính vào video)

```powershell
Set-Location "project/Phase 2"
python testdata/make_testdata.py
```

- Dùng checkout sạch (hoặc xoá `storage/`, `logs/`, `downloads/` trước khi quay) để namespace không lẫn dữ liệu từ lần chạy trước.
- Kiểm tra port 9000 chưa bị chương trình khác chiếm.
- Mỗi khối bên dưới đã ghi rõ tên terminal cần mở — mở sẵn và đặt tên trước khi quay để không mất thời gian giữa chừng.
- Font terminal đủ lớn, không để lộ đường dẫn/thông tin cá nhân không cần thiết.

---

# KHỐI 1 — CƯỜNG (0:00–3:00): Kiến trúc, namespace, FILE_EXISTS, SERVER_BUSY

**Terminal cần mở:** `SERVER`, `ALICE`, `BOB`, `CAROL`, `DAVE`, `OVERFLOW`.

### Lời mở đầu cho cả video (~20 giây)

> Xin chào, nhóm em gồm ba thành viên: Cường, Bình và Hưng, xin trình bày đồ án Phase 2 — hệ thống client/server truyền file qua giao thức nhị phân tự định nghĩa trên TCP. Video chia làm ba phần: em, Cường, sẽ trình bày kiến trúc server và cách xử lý nhiều user; sau đó Bình trình bày giao thức và bài test chịu tải; cuối cùng Hưng trình bày resume khi mất kết nối và giới hạn băng thông.

### 1. Kiến trúc server (~40 giây)

Mở nhanh `docs/architecture.md`, mục 1–3, trong lúc nói — không đọc nguyên văn, chỉ lướt qua các tiêu đề khi nhắc tới.

> Server dùng mô hình thread-per-client: mỗi kết nối được giao cho một thread riêng, vì code đọc/ghi socket và file vốn là blocking I/O, nên không cần viết lại theo asyncio. Số client đồng thời bị giới hạn bằng semaphore. Điểm quan trọng là server luôn `accept()` kết nối TCP trước, rồi mới kiểm tra còn chỗ hay không — nếu từ chối ngay ở tầng hệ điều hành, phía client sẽ không phân biệt được là "server đầy" hay "server đã chết". Mỗi username có một thư mục lưu trữ riêng, và các thao tác trên cùng một file được khoá theo cặp username-filename để tránh xung đột.

### 2. Khởi động server và namespace riêng (~50 giây)

**Terminal `SERVER`:**

```powershell
python server.py 9000 "" 4
```

> Em khởi động server ở port 9000, giới hạn tối đa 4 client cùng lúc — đặt thấp để một lát nữa dễ demo trường hợp server đầy. Server in ra thư mục storage, file log và số client tối đa ngay khi khởi động.

**Terminal `ALICE`:**

```powershell
python client.py 127.0.0.1 9000 --username alice "UPLOAD testdata/512b.bin"
python client.py 127.0.0.1 9000 --username alice "LIST"
```

**Terminal `BOB`:**

```powershell
python client.py 127.0.0.1 9000 --username bob "UPLOAD testdata/512b.bin"
python client.py 127.0.0.1 9000 --username bob "LIST"
```

> Alice và Bob cùng upload một file tên `512b.bin`, nhưng không hề xung đột — vì server lưu file theo namespace riêng của từng username. Lệnh LIST của Bob chỉ thấy file của Bob, không thấy file của Alice, dù hai người dùng chung một cái tên.

### 3. Chính sách file trùng — FILE_EXISTS (~25 giây)

**Terminal `ALICE`:**

```powershell
python client.py 127.0.0.1 9000 --username alice "UPLOAD testdata/512b.bin"
```

Kết quả mong đợi:

```text
ERROR 112 / FILE_EXISTS
file exists -- DELETE first
```

> Alice upload lại đúng file đã có — server từ chối ngay bằng lỗi FILE_EXISTS thay vì âm thầm ghi đè. Muốn thay file, client phải DELETE trước rồi mới upload lại; cách này tránh việc một client khác đang đọc dở file thì bị thay nội dung giữa chừng.

### 4. Giới hạn số client — SERVER_BUSY (~55 giây)

**Terminal `CAROL`:**

```powershell
python client.py 127.0.0.1 9000 --username carol
```

*(giữ phiên tương tác mở — đây là slot thứ 3/4)*

**Terminal `DAVE`:**

```powershell
python client.py 127.0.0.1 9000 --username dave
```

*(giữ phiên tương tác mở — đây là slot thứ 4/4, server đã đầy)*

**Terminal `OVERFLOW`:**

```powershell
python client.py 127.0.0.1 9000 --username overflow "LIST"
```

Kết quả mong đợi:

```text
ERROR 120 / SERVER_BUSY
server is full
```

> Bốn slot đã bị Alice, Bob, Carol và Dave chiếm hết. Kết nối thứ năm này nhận lỗi SERVER_BUSY có cấu trúc rõ ràng, thay vì bị treo hoặc làm server sập.

**Quay lại terminal `ALICE`, gõ `LIST`:**

```text
LIST
```

> Và quan trọng nhất: các session cũ hoàn toàn không bị ảnh hưởng — Alice vẫn gọi LIST bình thường. Khi một session logout, slot đó được trả lại ngay cho client tiếp theo.

### Bàn giao (~10 giây)

> Server đã xử lý đúng cả bốn tình huống: namespace riêng, file trùng, và vượt giới hạn kết nối mà không crash. Tiếp theo, Bình sẽ trình bày cấu trúc giao thức nhị phân và kết quả stress test nhiều client đồng thời.

*(Có thể dừng server bằng Ctrl+C ở đây nếu Bình tự quay khối riêng; nếu quay liền mạch, để nguyên — Khối 2 sẽ tự khởi động lại server theo cấu hình khác.)*

### Cách rút gọn nếu thiếu thời gian

Bỏ bước Carol/Dave giữ phiên tương tác thủ công (mỗi lệnh gõ tay mất thời gian) — thay bằng việc chỉ mở `docs/test-results/stress.json`/`.csv` ở phần sau và nói `SERVER_BUSY` đã được `tools/stress_clients.py` (Bình) xác nhận tự động qua 20 vòng. Giữ lại tối thiểu phần 2 (namespace) và phần 3 (FILE_EXISTS) vì đây là phần việc gắn trực tiếp với code của Cường.

---

# KHỐI 2 — BÌNH (3:00–6:00): Giao thức nhị phân, stress test đồng thời

**Terminal cần mở:** `SERVER`, `STRESS`.

### 1. Cấu trúc giao thức — mini-RFC (~60 giây)

Mở `docs/protocol.md`, mục "Packet framing" và bảng opcode.

> Toàn bộ giao tiếp giữa client và server đi qua một giao thức nhị phân tự định nghĩa trên TCP, mô tả đầy đủ trong file protocol.md. Mỗi gói tin có 4 phần: LENGTH 4 byte — độ dài phần còn lại của gói, không tính chính 4 byte này; OPCODE 2 byte xác định loại lệnh, ví dụ LOGIN, FILE_UPLOAD, FILE_DOWNLOAD, FILE_CHUNK, FILE_DELETE, ACK, ERROR; USER_ID 2 byte để server xác thực đúng người gửi; và cuối cùng là PAYLOAD có độ dài thay đổi tuỳ loại lệnh. Tất cả số nguyên đều dùng network byte order, tức big-endian. Vì TCP là luồng byte liên tục chứ không tự tách gói, phía nhận luôn phải đọc đủ số byte theo LENGTH khai báo trước khi xử lý — không được giả định một lần gửi tương ứng một lần nhận.

> Payload dữ liệu file luôn ở dạng byte thô, không bao giờ decode qua chuỗi văn bản, để không bị lỗi khi file chứa byte 0x00. Các mã lỗi cũng được chuẩn hoá thành số, ví dụ FILE_EXISTS là 112, SERVER_BUSY là 120, giúp client xử lý logic thay vì so khớp chuỗi.

*(Nếu còn thời gian, lướt nhanh qua bảng hex dump ví dụ trong file để người xem thấy gói tin thật trông như thế nào.)*

### 2. Khởi động lại server cho stress test (~10 giây)

**Terminal `SERVER`:**

```powershell
python server.py 9000
```

> Em khởi động lại server với cấu hình mặc định — tối đa 10 client cùng lúc, vì bài stress test sắp chạy sẽ mô phỏng 12 client, cố tình vượt quá capacity để kiểm tra luôn cả cơ chế SERVER_BUSY và retry.

### 3. Chạy stress test 12 client × 20 vòng (~60 giây)

**Terminal `STRESS`:**

```powershell
python tools/stress_clients.py --host 127.0.0.1 --port 9000 --clients 12 --rounds 20 --seed 2026
```

> Script này dùng seed cố định 2026 để kết quả có thể lặp lại giống hệt giữa các lần chạy. Mỗi vòng khởi tạo 12 client song song, mỗi client thực hiện đầy đủ chu trình: login, upload, list, download, kiểm tra lại SHA-256, delete rồi logout. Với 20 vòng, tổng cộng có 240 client và hàng nghìn thao tác được thực hiện.

Chờ dòng kết quả in ra (khoảng 10–12 giây):

```text
[PASS] 240/240 clients; 1680 operations; 11.24s
[INFO] JSON: docs/test-results/stress.json
[INFO] CSV : docs/test-results/stress.csv
```

> 240 trên 240 client thành công, 1680 thao tác, không có thao tác nào lỗi, chạy trong khoảng 11 giây.

### 4. Xem lại số liệu (~40 giây)

Mở nhanh `docs/test-results/stress.json`, chỉ vào các trường:

```text
"clients": 12, "rounds": 20, "seed": 2026,
"successful_clients": 240, "failed_clients": 0, "operations": 1680
```

> File JSON và CSV này được ghi lại tự động sau mỗi lần chạy, dùng làm bằng chứng nộp bài: cấu hình đúng 12 client, 20 vòng, seed 2026 để tái lập được, và không có client nào thất bại.

### Bàn giao (~10 giây)

> Hệ thống chịu tải tốt với nhiều client đồng thời. Tiếp theo, Hưng sẽ trình bày phần quan trọng nhất của đề bài: ngắt kết nối giữa chừng và resume đúng offset, kèm theo giới hạn băng thông truyền file.

### Cách rút gọn nếu thiếu thời gian

Nếu không muốn chờ stress test chạy trực tiếp trong video (~11 giây thực + thời gian server khởi động), có thể chỉ mở sẵn `docs/test-results/stress.json`/`.csv` từ lần chạy trước và nói kết quả, bỏ qua bước chạy lệnh trực tiếp — vẫn giữ nguyên phần giải thích giao thức ở mục 1 vì đó là nội dung bắt buộc của mini-RFC.

---

# KHỐI 3 — HƯNG (6:00–9:00): Resume upload/download, progress, throttle, tổng kết

**Terminal cần mở:** `SERVER`, `RESUME`.

### 1. Giới thiệu ngắn (~15 giây)

> Phần của em tập trung vào yêu cầu quan trọng nhất của đề: khi kết nối bị ngắt giữa chừng, client phải reconnect và tiếp tục đúng từ vị trí đã dừng, rồi xác minh lại bằng SHA-256 — không truyền lại từ đầu và không làm hỏng file.

### 2. Dừng server cũ, chạy demo resume (~90 giây)

**Terminal `SERVER`:** nhấn `Ctrl+C` để dừng server đang chạy từ Khối 2 — script bên dưới tự khởi động server riêng của nó trên port 9000.

**Terminal `RESUME`:**

```powershell
python tools/resume_demo.py
```

> Script tạo một file ngẫu nhiên 20 MiB, tính sẵn SHA-256 của toàn bộ file để đối chiếu ở cuối. Nó tự khởi động một server riêng, sau đó thực hiện lần lượt ba tình huống.

Khi màn hình hiện:

```text
[DEMO] === Phase 1: upload to 37%, then interrupt ===
[DEMO] Streaming from 0.0% to 37.0%...
[DEMO] Connection killed at 7,761,920 bytes (37.0% of 20.0MB)

[DEMO] === Phase 2: resume from 37%, upload to 73%, then interrupt ===
[DEMO] Server offset (before): 7,761,920 bytes (37.0%)
[DEMO] Streaming from 37.0% to 73.0%...
[DEMO] Connection killed at 15,310,848 bytes (73.0% of 20.0MB)

[DEMO] === Phase 3: resume from 73% to 100% via client.py ===
[DEMO] ✅ Two-interrupt upload resume successful! SHA-256 verified by server.
```

> Upload bị ngắt cưỡng bức ở 37 phần trăm để mô phỏng mất mạng giữa chừng — socket bị đóng đột ngột, không phải logout sạch. Server không xoá phần đã nhận mà giữ lại trong file tạm `.part` cùng một file sidecar ghi lại kích thước và SHA-256 kỳ vọng. Khi client kết nối lại, server đọc sidecar, xác nhận đây đúng là phần tiếp theo của cùng file, và trả lại chính xác offset 7.761.920 byte để client tiếp tục từ đó — không phải từ 0. Việc này lặp lại lần hai ở mốc 73 phần trăm để chứng minh cơ chế không phụ thuộc vào một offset cố định. Sau khi nhận đủ toàn bộ file, server tính lại SHA-256 và chỉ commit file khi khớp hoàn toàn với hash ban đầu.

Khi màn hình hiện:

```text
[DEMO] === Download Phase 1: download to 50%, then interrupt ===
[DEMO] Receiving from 0.0% to 50.0%...
[DEMO] Download killed at 10,485,760 bytes (50.0% of 20.0MB)

[DEMO] === Download Phase 2: resume from 50% to 100% via client.py ===
[DEMO] ✅ Download resume successful! SHA-256 verified by client.
```

> Tương tự ở chiều download: client giữ lại 10 MiB đã tải, và khi kết nối lại chỉ yêu cầu phần còn thiếu từ byte 10.485.760 trở đi. Sau khi ghép đủ file, client tự tính SHA-256 và so với hash server gửi kèm ACK ban đầu để xác nhận file toàn vẹn.

### 3. Progress bar và throttle (~50 giây)

Mở `docs/test-results/throttle.csv`.

> Trong lúc truyền, client hiển thị progress bar theo thời gian thực, tính tốc độ và ETA dựa trên số byte mới truyền trong phiên hiện tại — nếu đang resume, phần đã có sẵn từ trước không bị tính vào tốc độ, tránh hiện tốc độ ảo cao gấp nhiều lần lúc chỉ còn truyền vài phần trăm cuối. Băng thông bị giới hạn bằng thuật toán token bucket: token bắt đầu bằng 0 thay vì đầy ngay từ đầu, để không có một đợt burst ban đầu làm tốc độ trung bình cả file vượt ngưỡng cho phép.

```text
Run,Size_MB,Time_s,Speed_KBps,Limit_KBps
1,2.0,4.34,472.42,500
2,2.0,4.35,471.15,500
3,2.0,4.34,471.55,500
```

> Ba lần đo với giới hạn 500 KB/s cho tốc độ thực tế lần lượt là 472,42; 471,15 và 471,55 KB/s — đều thấp hơn giới hạn, và thấp hơn ngưỡng chấp nhận của đề là giới hạn cộng 10 phần trăm, tức 550 KB/s.

*(Không bắt buộc chạy lại throttle test trực tiếp trong video để tiết kiệm thời gian — CSV này là artifact đã đo từ commit release. Nếu muốn chạy lại trực tiếp: `python -m unittest discover -s tests -t tests -p test_throttle.py -v`, mất khoảng 13 giây.)*

### 4. Tổng kết toàn bộ video (~25 giây)

> Tổng kết lại: hệ thống hiện có 70 test đơn vị và tích hợp, toàn bộ đều pass. Stress test đạt 240 trên 240 client thành công với 1680 thao tác, không có lỗi nào. Resume upload đã kiểm chứng ở hai mốc ngắt 37 và 73 phần trăm, resume download ở mốc 50 phần trăm, cả hai đều tiếp tục đúng offset và khớp SHA-256 sau khi hoàn tất. Throttle giữ tốc độ dưới giới hạn cho phép qua ba lần đo liên tiếp. Cảm ơn thầy cô và các bạn đã theo dõi.

### Cách rút gọn nếu thiếu thời gian

Đây là phần bắt buộc của đề (resume + SHA-256), không nên cắt. Nếu cần rút bớt, bỏ phần chạy lại throttle test trực tiếp (mục 3 đã có sẵn lựa chọn chỉ xem CSV) và rút gọn câu tổng kết ở mục 4 xuống 2–3 câu.

---

## Dọn dẹp sau khi quay

Trong các client đang ở chế độ tương tác (Carol, Dave ở Khối 1), gõ:

```text
exit
```

Trong terminal server đang chạy, nhấn `Ctrl+C`.

## Checklist trước khi xuất video

- [ ] Tổng thời lượng khoảng 8–10 phút, chia rõ 3 khối liên tục theo người, không xen kẽ giữa chừng.
- [ ] Khối Cường: có LOGIN/UPLOAD/LIST thành công, namespace riêng giữa Alice và Bob, `FILE_EXISTS`, `SERVER_BUSY`, và cảnh chứng minh session cũ vẫn sống sau khi server đầy.
- [ ] Khối Bình: có giải thích packet header/opcode, và kết quả stress `240/240` (chạy trực tiếp hoặc mở JSON/CSV có sẵn).
- [ ] Khối Hưng: có cảnh ngắt upload ở 37% và 73%, ngắt download ở 50%, mỗi lần resume đúng offset và có dòng `SHA-256 verified`. Có throttle CSV ba lần đo. Có câu tổng kết ở cuối.
- [ ] Không lộ token, mật khẩu, đường dẫn cá nhân hay cửa sổ chat riêng tư.
- [ ] Âm thanh rõ, font terminal đủ lớn để đọc được output/error line.
- [ ] Ghi rõ commit hash đang quay trong mô tả video, để đối chiếu khi cần.

## Phương án dự phòng khi quay

- Nếu ba upload/stress kết thúc quá nhanh để quay kịp, dùng `--limit 500` với file `10mb.bin` thay vì file nhỏ.
- Nếu `FILE_EXISTS` không xuất hiện đúng lúc mong đợi, đang dùng lại `storage/` cũ còn sót dữ liệu — xoá `storage/`, `logs/`, `downloads/` rồi chạy lại từ đầu khối.
- Nếu server báo port 9000 đang bận, dừng hẳn tiến trình server cũ (kể cả server con mà `tools/resume_demo.py` tự khởi động) trước khi chạy lệnh tiếp theo.
- Nếu demo trực tiếp gặp lỗi không mong muốn giữa buổi quay, giữ sẵn ảnh chụp màn hình `stress.json`, `stress.csv`, `throttle.csv` và log của lần chạy nghiệm thu gần nhất để dùng thay thế.
