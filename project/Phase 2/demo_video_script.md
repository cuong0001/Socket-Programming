# Kịch bản video demo Phase 2 — quay theo lô, dựng theo dòng thời gian

Video hoàn chỉnh dài khoảng **7 phút**, giữ nguyên mạch kể xen kẽ giữa ba người (Cường → Bình → Cường → Bình → Hưng → Bình → Hưng → Cường) vì mạch này bám sát trình tự tự nhiên của một phiên làm việc thật: dựng server → truyền file → chịu tải → mất kết nối → giới hạn → server đầy → tổng kết.

Nhưng **cách quay thì không xen kẽ**. Mỗi người quay gọn toàn bộ shot của mình trong một buổi, rồi khâu dựng ghép lại theo đúng thứ tự ở mục 1. Nhờ vậy không ai phải chờ ai, và mỗi người chỉ cần dựng đúng một lần môi trường máy của mình.

Tài liệu gồm 3 phần chính:

- **Mục 1–3**: bảng shot list (thứ tự dựng), nguyên tắc câu nối, chuẩn bị chung.
- **Mục 4–6**: gói quay riêng của từng người — mỗi shot có đủ *trạng thái cần dựng trước*, *thao tác trên màn hình*, *lời thoại đầy đủ*, *câu nối*.
- **Mục 7–9**: hướng dẫn dựng, checklist, phương án dự phòng.

Video đáp ứng trực tiếp 4 yêu cầu bắt buộc của đề: truyền file cơ bản; tối thiểu ba client đồng thời; ngắt kết nối giữa chừng và resume thành công; kiểm tra SHA-256 sau resume. Ngoài ra còn có namespace riêng, stress 12 client, progress, throttle, `FILE_EXISTS` và `SERVER_BUSY`.

---

## 1. Shot list — thứ tự dựng cuối cùng

| # | Thời lượng | Mã shot | Người quay | Nội dung |
|---:|---|:---:|---|---|
| 1 | 0:00–0:35 | **C1** | Cường | Mở đầu + giới thiệu kiến trúc và giao thức |
| 2 | 0:35–0:55 | **C2** | Cường | Khởi động server |
| 3 | 0:55–1:45 | **B1** | Bình | Ba client upload đồng thời |
| 4 | 1:45–2:25 | **C3** | Cường | LIST và DOWNLOAD cơ bản |
| 5 | 2:25–3:05 | **B2** | Bình | Stress 12 client × 20 vòng |
| 6 | 3:05–3:20 | **H1** | Hưng | Dừng server, chuẩn bị resume |
| 7 | 3:20–4:35 | **H2** | Hưng | Ngắt giữa chừng và resume (37% / 73% / 50%) |
| 8 | 4:35–5:05 | **B3** | Bình | Bằng chứng throttle |
| 9 | 5:05–5:35 | **B4** | Bình | Chính sách file trùng — `FILE_EXISTS` |
| 10 | 5:35–6:20 | **H3** | Hưng | `SERVER_BUSY` khi vượt capacity |
| 11 | 6:20–6:35 | **C4** | Cường | Session cũ vẫn hoạt động bình thường |
| 12 | 6:35–7:05 | **C5** | Cường | Tổng kết |

**Tổng số shot theo người:** Cường 5 shot (~2 phút 20), Bình 4 shot (~2 phút 30), Hưng 3 shot (~2 phút 15).

---

## 2. Nguyên tắc câu nối — đọc kỹ trước khi quay

Đây là phần dễ hỏng nhất khi quay theo lô: nếu ai cũng chỉ quay đúng phần kỹ thuật của mình rồi cắt phựt, video ghép lại sẽ giật cục như 12 đoạn rời rạc dán vào nhau.

Quy ước để tránh điều đó — **mỗi shot có 2 mối nối**:

1. **Câu nối vào** — mở đầu shot, thường bắt đầu bằng "Cảm ơn *tên người trước*…" rồi nhắc lại một ý ngắn của shot trước.
2. **Câu nối ra** — kết thúc shot, gọi tên người tiếp theo và nói trước họ sắp làm gì.

Ba lưu ý bắt buộc:

- **Vẫn phải đọc câu nối dù người kia không có mặt.** Lúc quay, người trước/người sau không ngồi cạnh — cứ đọc bình thường như đang nói với họ. Khi ghép lại nó sẽ khớp.
- **Chừa 1 giây im lặng ở đầu và cuối mỗi shot.** Đừng nói ngay khi vừa bấm quay và đừng tắt máy ngay khi vừa dứt câu — khâu dựng cần khoảng đệm để cắt sạch, không cụt tiếng.
- **Giữ nguyên tên gọi trong câu nối.** Nếu shot trước nói "Bình sẽ trình bày stress test" thì shot sau phải đúng là stress test của Bình. Nếu ai đổi nội dung shot của mình, phải báo hai người kề bên sửa câu nối theo.

Trong các mục 4–6, câu nối vào/ra đã được viết sẵn và đánh dấu 🔗. Phần thoại kỹ thuật đánh dấu 🎙️.

---

## 3. Chuẩn bị chung — cả ba người đều làm trước khi quay

Làm hết những việc dưới đây **trước khi bấm nút quay**, để thời gian tạo file và sắp xếp cửa sổ không lọt vào video.

```powershell
Set-Location "project/Phase 2"
python testdata/make_testdata.py
```

Checklist môi trường:

- [ ] Quay trên checkout sạch, hoặc xoá `storage/`, `logs/`, `downloads/` trước khi bắt đầu — nếu còn dữ liệu cũ, `FILE_EXISTS` sẽ nổ sai lúc và namespace hiển thị lộn xộn.
- [ ] Port 9000 chưa bị chương trình nào chiếm.
- [ ] Font terminal phóng to đủ để đọc được dòng lỗi và dòng kết quả khi xem video.
- [ ] Đóng hết cửa sổ chat, email, tab cá nhân — không để lọt vào khung hình.
- [ ] Ghi lại commit hash đang quay (`git log --oneline -1`) để ghi vào mô tả video.
- [ ] Mic thử trước một đoạn 10 giây, nghe lại xem có tiếng ồn nền không.

Đặt tên các terminal theo vai trò ngay từ đầu — trong video người xem sẽ nhận ra ngay đâu là server, đâu là client nào:

`SERVER` · `ALICE` · `BOB` · `CAROL` · `STRESS / RESUME` · `CAPACITY`

---

# 4. GÓI QUAY CỦA CƯỜNG — 5 shot (C1, C2, C3, C4, C5)

## Dựng môi trường cho cả buổi quay của Cường

Cường quay các shot ở nhiều mốc thời gian khác nhau của video, nên trạng thái server/storage mỗi shot mỗi khác. Trình tự dưới đây đã sắp xếp để **quay tuần tự từ C1 đến C5 mà chỉ phải dựng lại trạng thái đúng hai lần**.

```powershell
Set-Location "project/Phase 2"
# Xoá sạch dữ liệu cũ trước khi bắt đầu
Remove-Item -Recurse -Force storage, logs, downloads -ErrorAction SilentlyContinue
python testdata/make_testdata.py
```

---

## Shot C1 — Mở đầu + giới thiệu kiến trúc *(0:00–0:35, ~35 giây)*

**Trạng thái cần có:** không cần server, không cần dữ liệu. Quay lúc nào cũng được.

### Chuẩn bị màn hình (làm trước, chưa quay)

Đây là shot duy nhất không có terminal, nên phải chuẩn bị kỹ hơn — nếu vừa quay vừa mò tìm mục thì video sẽ rất lộ.

1. Mở VS Code, **chỉ mở đúng 2 file**: `docs/protocol.md` và `docs/architecture.md`. Đóng hết tab khác để thanh tab không rối.
2. Với **từng file**, bật chế độ xem đã render: `Ctrl+Shift+V`. Bản render có khung nền cho sơ đồ và bảng có kẻ ô, nhìn chuyên nghiệp hơn hẳn markdown thô đầy dấu `#` và `|`.
3. Ẩn thanh bên trái: `Ctrl+B` — lấy thêm chỗ cho nội dung.
4. Phóng to chữ: `Ctrl+=` khoảng 3–4 lần. **Quay thử 10 giây rồi mở lại trên điện thoại xem** — nếu đọc không nổi thì phóng thêm. Chữ nhỏ là lỗi hay gặp nhất khi quay màn hình.
5. Cuộn sẵn từng tab tới đúng vị trí (xem bảng bên dưới), rồi **không chạm vào nữa** cho tới lúc quay.
6. Chuyển tab bằng `Ctrl+Tab`, đừng dùng chuột bấm lên thanh tab — đỡ rung hình.

> 💡 Nếu nhánh `docs/protocol-vi` đã merge thì `protocol.md` đã là tiếng Việt. Nên merge **trước khi quay**, để video tiếng Việt không chiếu tài liệu tiếng Anh.

### Storyboard — chỉ vào đâu, lúc nào

| Đoạn | Đang nói câu nào | Màn hình | Thao tác chuột |
|---|---|---|---|
| **1** (~10 giây) | Từ *"Xin chào thầy cô…"* đến *"…giao thức nhị phân do nhóm tự định nghĩa."* | `protocol.md` — để ở **đầu file**, thấy tiêu đề *"Giao thức truyền file Giai đoạn 2 (Mini-RFC)"* | **Không chỉ gì cả.** Đây là đoạn chào, để yên màn hình. |
| **2** (~15 giây) | Từ *"Mỗi gói tin gồm bốn phần…"* đến *"…network byte order."* | `protocol.md` — mục **"2. Khung gói tin (framing)"**, hiện rõ sơ đồ ASCII | Bôi đen **lần lượt 4 ô** trong sơ đồ, đúng theo thứ tự đang đọc: `LENGTH:u32` → `OPCODE:u16` → `USER_ID:u16` → `PAYLOAD` |
| **3** (~10 giây) | Từ *"Về phía server…"* đến hết | `Ctrl+Tab` sang `architecture.md` — chỉnh zoom sao cho **thấy đồng thời cả 3 tiêu đề** mục 1, 2, 3 | Bôi đen lần lượt 3 tiêu đề: *"1. Kiến trúc thread-per-client"* → *"2. Namespace và an toàn đường dẫn"* → *"3. FileLockRegistry"* |

### Ba mẹo quan trọng

**Bôi đen chứ đừng rê chuột.** Con trỏ chuột trong video rất nhỏ, người xem gần như không thấy nó ở đâu. Kéo chuột bôi đen tạo một vùng sáng rõ ràng, nhìn là biết ngay đang nói tới chỗ nào. Bôi xong đoạn nào thì bấm chuột ra chỗ trống để bỏ chọn rồi bôi đoạn tiếp theo.

**Đoạn 3 hạn chế cuộn.** Ba mục 1, 2, 3 của `architecture.md` nằm gần nhau (cách nhau chưa tới 20 dòng nguồn), nên thường chỉ cần hạ zoom một nấc là cả ba tiêu đề cùng nằm trên một màn hình — khi đó chỉ việc bôi đen lần lượt, không cần chạm bánh xe chuột. Nếu ở mức zoom đọc được mà vẫn không đủ chỗ, thì **cuộn đúng một lần, thật chậm và đều** từ mục 1 xuống mục 3 trong lúc nói, chứ đừng nhảy giật ba lần — người xem sẽ không kịp đọc gì.

**Câu "network byte order" không cần chỉ vào đâu.** Nó nằm ở mục 1 của `protocol.md`, cuộn ngược lên rồi cuộn xuống lại chỉ tổ rối hình. Cứ nói bình thường trong lúc màn hình vẫn đang ở sơ đồ.

🎙️ **Lời thoại:**

> Xin chào thầy cô. Nhóm em gồm ba thành viên là Cường, Bình và Hưng, xin trình bày đồ án Phase 2 — hệ thống client-server truyền file qua TCP, sử dụng một giao thức nhị phân do nhóm tự định nghĩa.
>
> Mỗi gói tin gồm bốn phần: LENGTH bốn byte cho biết độ dài phần còn lại, OPCODE hai byte xác định loại lệnh, USER_ID hai byte để server biết ai đang gửi, và cuối cùng là PAYLOAD có độ dài thay đổi. Tất cả số nguyên đều dùng network byte order.
>
> Về phía server, nhóm em chọn mô hình thread-per-client, giới hạn số kết nối đồng thời bằng semaphore. Mỗi username có một thư mục lưu trữ riêng, và các thao tác trên cùng một file được khoá theo cặp username và filename.

🔗 **Câu nối ra:**

> Trước tiên, em khởi động server để cả nhóm bắt đầu phần demo.

---

## Shot C2 — Khởi động server *(0:35–0:55, ~20 giây)*

**Trạng thái cần có:** `storage/` và `logs/` đã xoá sạch (đã làm ở bước dựng môi trường).

**Thao tác — terminal `SERVER`:**

```powershell
python server.py 9000 "" 10
```

Sau khi server in ra, trỏ chuột lần lượt vào ba dòng `Storage dir`, `Log file`, `Max clients`.

🎙️ **Lời thoại:**

> Server đang lắng nghe ở port 9000 và cho phép tối đa 10 client hoạt động cùng lúc. Ngay khi khởi động, server in ra thư mục lưu trữ, đường dẫn file log và giới hạn số client — mọi thao tác trong phần demo sau đây đều được ghi lại đầy đủ trong file log này. Mỗi kết nối đi vào sẽ được giao cho một worker thread riêng để xử lý.

🔗 **Câu nối ra:**

> Server đã sẵn sàng. Bình sẽ trình bày kịch bản ba client truyền file đồng thời.

> ⚠️ **Giữ nguyên server này chạy** — shot C3 ngay sau đây cần nó.

---

## Shot C3 — LIST và DOWNLOAD cơ bản *(1:45–2:25, ~40 giây)*

**Trạng thái cần dựng trước khi quay:** trong video, shot này đứng *sau* phần Bình cho ba client upload. Nghĩa là trước khi bấm quay, Cường phải tự chạy ba lệnh upload đó **ngoài khung hình** để dữ liệu tồn tại:

```powershell
# Chạy trước, KHÔNG quay — chỉ để tạo dữ liệu
python client.py 127.0.0.1 9000 --username video-alice --limit 500 "UPLOAD testdata/10mb.bin"
python client.py 127.0.0.1 9000 --username video-bob   --limit 500 "UPLOAD testdata/10mb.bin"
python client.py 127.0.0.1 9000 --username video-carol --limit 500 "UPLOAD testdata/10mb.bin"
```

Chờ cả ba xong (mỗi lệnh ~20 giây), xoá màn hình terminal cho sạch, rồi mới bắt đầu quay.

**Thao tác — terminal `ALICE`:**

```powershell
python client.py 127.0.0.1 9000 --username video-alice "LIST"
python client.py 127.0.0.1 9000 --username video-alice "DOWNLOAD 10mb.bin"
```

**Thao tác — terminal `BOB`:**

```powershell
python client.py 127.0.0.1 9000 --username video-bob "LIST"
```

🔗 **Câu nối vào:**

> Cảm ơn Bình. Em sẽ dùng luôn chính dữ liệu mà ba client vừa tải lên.

🎙️ **Lời thoại:**

> Đầu tiên là LIST của Alice — thấy đúng một file `10mb.bin`. LIST của Bob cũng thấy một file tên `10mb.bin`. Nhưng đây là hai file hoàn toàn khác nhau, nằm ở hai thư mục user riêng biệt, chứ không phải cùng một file dùng chung — đó chính là ý nghĩa của namespace riêng theo username.
>
> Bây giờ Alice tải file của mình về bằng lệnh DOWNLOAD. Client nhận file theo từng chunk, kiểm tra offset của mỗi chunk có đúng thứ tự không, và chỉ ghi ra file hoàn chỉnh sau khi SHA-256 khớp đúng với hash mà server đã gửi kèm từ đầu.

*(Chờ tới khi hiện `SHA256 Verification OK` và `100.0%`)*

> SHA-256 khớp, tiến trình đạt 100 phần trăm. Vòng truyền file cơ bản gồm upload, list và download đã hoạt động đầy đủ.

🔗 **Câu nối ra:**

> Đó là luồng cơ bản với vài client. Tiếp theo, Bình sẽ đẩy hệ thống lên mức chịu tải cao hơn nhiều.

---

## Shot C4 — Session cũ vẫn hoạt động *(6:20–6:35, ~15 giây)*

**Trạng thái cần dựng trước khi quay:** shot này nằm ngay sau phần Hưng demo `SERVER_BUSY`. Cường phải tự dựng lại đúng bối cảnh đó:

```powershell
# 1. Dừng server 10-slot đang chạy (Ctrl+C ở terminal SERVER)
# 2. Khởi động lại với đúng 3 slot
python server.py 9000 "" 3
```

Sau đó mở **ba** terminal, mỗi terminal một phiên tương tác và **giữ nguyên, không gõ `exit`**:

```powershell
# Terminal ALICE
python client.py 127.0.0.1 9000 --username cap-alice
# Terminal BOB
python client.py 127.0.0.1 9000 --username cap-bob
# Terminal CAROL
python client.py 127.0.0.1 9000 --username cap-carol
```

Ba phiên này chiếm đủ 3/3 slot. Bây giờ mới bấm quay, và quay ở terminal `ALICE`.

**Thao tác:** trong prompt tương tác của `cap-alice`, gõ:

```text
LIST
```

🔗 **Câu nối vào:**

> Cảm ơn Hưng. Em quay lại phiên của Alice — phiên này đã mở từ trước và vẫn đang giữ slot của mình.

🎙️ **Lời thoại:**

> Alice vẫn gửi được lệnh LIST và nhận kết quả bình thường. Việc server từ chối một kết nối mới hoàn toàn không ảnh hưởng gì tới các phiên đang chạy. Và khi một phiên logout, semaphore sẽ trả slot đó lại ngay cho client tiếp theo.

---

## Shot C5 — Tổng kết *(6:35–7:05, ~30 giây)*

**Trạng thái cần có:** không cần server. Chỉ cần mở sẵn thư mục `docs/test-results/` và file `docs/architecture.md`.

**Trên màn hình:** mở thư mục `docs/test-results/` cho thấy `stress.json`, `stress.csv`, `throttle.csv`; hoặc cuộn tới bảng kết quả trong `docs/architecture.md`.

> ⚠️ **Kiểm tra lại con số test ngay trước khi quay.** Con số bên dưới là 70, đo trên commit `03116b3`. Mỗi PR mới merge đều có thể làm nó thay đổi. Chạy lại và đọc đúng con số thật:
>
> ```powershell
> python -m unittest discover -s tests -t tests
> ```

🎙️ **Lời thoại:**

> Tổng kết lại toàn bộ phần demo. Trên commit nghiệm thu, toàn bộ 70 test đơn vị và tích hợp đều pass. Stress test đạt 240 trên 240 client với 1.680 thao tác và không có lỗi nào. Resume upload đã được kiểm chứng ở hai mốc ngắt là 37 và 73 phần trăm, resume download ở mốc 50 phần trăm — tất cả đều tiếp tục đúng offset và khớp SHA-256 sau khi hoàn tất. Giới hạn băng thông giữ được dưới ngưỡng qua cả ba lần đo.
>
> Như vậy hệ thống đã đáp ứng đầy đủ các yêu cầu của đề: nhiều client đồng thời, giao thức nhị phân có framing rõ ràng, namespace riêng theo user, resume sau khi mất kết nối, hiển thị tiến trình, giới hạn băng thông, và xử lý đúng khi server đầy.
>
> Nhóm em xin cảm ơn thầy cô và các bạn đã theo dõi.

---

# 5. GÓI QUAY CỦA BÌNH — 4 shot (B1, B2, B3, B4)

## Dựng môi trường cho cả buổi quay của Bình

```powershell
Set-Location "project/Phase 2"
Remove-Item -Recurse -Force storage, logs, downloads -ErrorAction SilentlyContinue
python testdata/make_testdata.py
```

Khởi động server **ngoài khung hình** (shot khởi động server là của Cường, Bình không quay lại):

```powershell
python server.py 9000 "" 10
```

Trong ba terminal `ALICE`, `BOB`, `CAROL`, **dán sẵn lệnh nhưng chưa nhấn Enter**:

```powershell
# ALICE
python client.py 127.0.0.1 9000 --username video-alice --limit 500 "UPLOAD testdata/10mb.bin"
# BOB
python client.py 127.0.0.1 9000 --username video-bob --limit 500 "UPLOAD testdata/10mb.bin"
# CAROL
python client.py 127.0.0.1 9000 --username video-carol --limit 500 "UPLOAD testdata/10mb.bin"
```

Giới hạn 500 KB/s làm mỗi lượt upload 10 MiB kéo dài khoảng 20 giây — vừa đủ để thấy rõ ba thanh tiến trình chạy song song.

---

## Shot B1 — Ba client upload đồng thời *(0:55–1:45, ~50 giây)*

**Trạng thái cần có:** server 10 slot đang chạy, ba lệnh đã dán sẵn chưa Enter, `storage/` sạch.

**Thao tác:**

1. Chuyển thật nhanh qua ba terminal `ALICE` → `BOB` → `CAROL`, nhấn Enter từng cái. **Khoảng cách giữa ba lần Enter phải dưới 2 giây** — nếu chậm, ba thanh tiến trình sẽ không chồng lấn nhau và mất ý nghĩa "đồng thời".
2. Chia màn hình hoặc chuyển qua lại giữa ba terminal để thấy cả ba thanh tiến trình cùng tăng.
3. Chuyển sang terminal `SERVER` khoảng 5 giây.
4. Chờ cả ba client hiện `SHA256 Verification OK` và `100.0%`.

🔗 **Câu nối vào:**

> Cảm ơn Cường. Server đã sẵn sàng, bây giờ em cho ba client cùng làm việc một lúc.

🎙️ **Lời thoại:**

> Ba client Alice, Bob và Carol cùng upload một file 10 MiB lên server. Cả ba dùng chung một tên file là `10mb.bin`, nhưng hoàn toàn không xung đột với nhau, vì server lưu chúng vào ba namespace riêng theo username.
>
> Em giới hạn mỗi client ở 500 KB/s để mỗi lượt truyền kéo dài đủ lâu — như vậy mình nhìn thấy rõ ba thanh tiến trình đang cùng tiến song song, chứ không phải server xử lý xong client này rồi mới tới client kia.

*(Chuyển sang terminal `SERVER`)*

> Bên phía server, log của cả ba phiên truyền được ghi xen kẽ nhau theo thời gian thực, nhưng không có dòng nào bị chồng lên dòng nào — vì logger dùng chung một khoá cho mỗi lần ghi.

*(Chờ cả ba client kết thúc)*

> Cả ba client đều báo SHA-256 Verification OK và tiến trình kết thúc ở 100 phần trăm.

🔗 **Câu nối ra:**

> Ba lượt truyền đã hoàn tất độc lập với nhau. Cường sẽ dùng chính dữ liệu này để minh hoạ hai lệnh LIST và DOWNLOAD.

---

## Shot B2 — Stress 12 client × 20 vòng *(2:25–3:05, ~40 giây)*

**Trạng thái cần có:** server 10 slot vẫn đang chạy (giữ nguyên từ B1).

**Thao tác — terminal `STRESS / RESUME`:**

```powershell
python tools/stress_clients.py --host 127.0.0.1 --port 9000 --clients 12 --rounds 20 --seed 2026
```

Chờ khoảng 11 giây tới khi hiện dòng `[PASS]`. Sau đó mở nhanh `docs/test-results/stress.json`, trỏ vào các trường `clients`, `rounds`, `seed`, `successful_clients`, `failed_clients`.

🔗 **Câu nối vào:**

> Đúng vậy. Sau khi luồng cơ bản đã chạy tốt, em đẩy hệ thống lên mức chịu tải cao hơn hẳn.

🎙️ **Lời thoại:**

> Đây là script stress dùng seed cố định 2026, để kết quả có thể lặp lại y hệt ở những lần chạy sau chứ không phụ thuộc may rủi. Mỗi vòng khởi tạo 12 client chạy song song, trong khi server chỉ có 10 slot — nhóm em cố ý cho vượt quá, để kiểm tra luôn cả cơ chế `SERVER_BUSY` và retry. Mỗi client chạy đủ một chu trình: login, upload, list, download, đối chiếu lại SHA-256, delete, rồi logout. Hai mươi vòng như vậy là tổng cộng 240 lượt client.

*(Chờ kết quả `[PASS] 240/240 clients; 1680 operations; ~11s`)*

> Kết quả: 240 trên 240 client thành công, 1.680 thao tác, không có lượt nào thất bại, chạy hết khoảng 11 giây.

*(Mở `stress.json`)*

> Toàn bộ số liệu được ghi tự động ra file JSON và CSV trong thư mục `test-results` — gồm cấu hình 12 client, 20 vòng, seed 2026, và quan trọng nhất là `failed_clients` bằng 0. Đây là bằng chứng định lượng cho yêu cầu nhiều client hoạt động đồng thời.

🔗 **Câu nối ra:**

> Hệ thống chịu tải ổn định. Tiếp theo, Hưng sẽ trình bày phần quan trọng nhất của đề bài: mất kết nối giữa chừng và resume.

---

## Shot B3 — Bằng chứng throttle *(4:35–5:05, ~30 giây)*

**Trạng thái cần có:** không cần server. Chỉ cần mở file `docs/test-results/throttle.csv`.

**Thao tác:** mở `docs/test-results/throttle.csv`, phóng to cho đọc rõ cột `Speed_KBps` và `Limit_KBps`.

🔗 **Câu nối vào:**

> Cảm ơn Hưng. Ngoài resume, đề bài còn yêu cầu giới hạn được băng thông truyền — em trình bày phần đo này.

🎙️ **Lời thoại:**

> Giới hạn băng thông được đo ba lần liên tiếp, mỗi lần upload một file 2 MiB với giới hạn đặt ở 500 KB/s. Tốc độ thực tế đo được lần lượt là 472,42 — 471,15 — và 471,55 KB/s. Cả ba lần đều nằm dưới giới hạn 500, và thấp hơn khá xa so với ngưỡng chấp nhận của đề bài là giới hạn cộng thêm 10 phần trăm, tức 550 KB/s.
>
> Sở dĩ giữ được ổn định như vậy là vì token bucket của nhóm em khởi tạo với số token bằng 0 thay vì đầy sẵn. Nếu để đầy sẵn, client sẽ có một đợt truyền dồn ở ngay đầu file, và đợt dồn đó kéo tốc độ trung bình của cả file vượt lên trên giới hạn cho phép.

🔗 **Câu nối ra:**

> Còn một tình huống nữa cũng liên quan tới việc ghi dữ liệu, là khi client upload trùng tên với một file đã có sẵn trên server.

---

## Shot B4 — Chính sách file trùng `FILE_EXISTS` *(5:05–5:35, ~30 giây)*

**Trạng thái cần có:** trong `storage/video-alice/` phải đã có sẵn `10mb.bin` (đã có từ shot B1). Cần khởi động lại server với 3 slot:

```powershell
# Dừng server 10-slot (Ctrl+C), rồi:
python server.py 9000 "" 3
```

**Thao tác — terminal `ALICE`:**

```powershell
python client.py 127.0.0.1 9000 --username video-alice "UPLOAD testdata/10mb.bin"
```

Kết quả mong đợi:

```text
[ERROR] Server rejected upload (112): file exists -- DELETE first
```

🎙️ **Lời thoại:**

> Em khởi động lại server, lần này giới hạn chỉ 3 client, để chuẩn bị luôn cho phần kiểm tra capacity ngay sau đây. Bây giờ Alice thử upload lại đúng file `10mb.bin` mà chính Alice đã upload thành công lúc nãy.

*(Chờ dòng lỗi hiện ra)*

> Server từ chối ngay lập tức bằng lỗi 112, `FILE_EXISTS`, và tuyệt đối không ghi đè lên file cũ. Chính sách của nhóm em là: muốn thay file thì phải DELETE tường minh rồi mới UPLOAD lại. Làm như vậy sẽ không xảy ra trường hợp một client khác đang đọc dở file thì nội dung bị thay ngay giữa chừng.

🔗 **Câu nối ra:**

> Server hiện đang giới hạn đúng 3 slot. Hưng sẽ lấp đầy cả ba slot đó để kiểm tra xem hệ thống xử lý thế nào khi server đầy.

---

# 6. GÓI QUAY CỦA HƯNG — 3 shot (H1, H2, H3)

## Dựng môi trường cho cả buổi quay của Hưng

```powershell
Set-Location "project/Phase 2"
Remove-Item -Recurse -Force storage, logs, downloads -ErrorAction SilentlyContinue
python testdata/make_testdata.py
```

Khởi động một server **ngoài khung hình** — shot H1 cần có sẵn một server đang chạy để dừng nó:

```powershell
python server.py 9000 "" 10
```

---

## Shot H1 — Dừng server, chuẩn bị resume *(3:05–3:20, ~15 giây)*

**Trạng thái cần có:** một server đang chạy ở port 9000.

**Thao tác — terminal `SERVER`:** nhấn `Ctrl+C`, chờ tới khi tiến trình thoát hẳn.

🔗 **Câu nối vào:**

> Cảm ơn Bình. Phần demo resume của em dùng một script riêng, và script này sẽ tự khởi động server của nó trên port 9000.

🎙️ **Lời thoại:**

> Nên trước tiên em dừng server hiện tại lại, để tránh hai tiến trình cùng tranh một port.

*(Chờ server thoát hẳn)*

> Server đã dừng hoàn toàn.

---

## Shot H2 — Ngắt giữa chừng và resume *(3:20–4:35, ~75 giây)*

**Trạng thái cần có:** port 9000 đang rảnh (đã dừng ở H1). Script tự lo phần còn lại.

**Thao tác — terminal `STRESS / RESUME`:**

```powershell
python tools/resume_demo.py
```

Script chạy khoảng 30–40 giây. Lời thoại dưới đây chia theo từng mốc output — nói đúng lúc màn hình hiện ra khối tương ứng.

🎙️ **Mở đầu, ngay khi script bắt đầu chạy:**

> Script tạo một file ngẫu nhiên 20 MiB và tính sẵn SHA-256 của toàn bộ file để đối chiếu ở cuối. Nó sẽ lần lượt kiểm tra ba tình huống mất kết nối khác nhau.

*(Khi hiện Phase 1 và Phase 2 của upload)*

```text
[DEMO] === Phase 1: upload to 37%, then interrupt ===
[DEMO] Connection killed at 7,761,920 bytes (37.0% of 20.0MB)

[DEMO] === Phase 2: resume from 37%, upload to 73%, then interrupt ===
[DEMO] Server offset (before): 7,761,920 bytes (37.0%)
[DEMO] Connection killed at 15,310,848 bytes (73.0% of 20.0MB)

[DEMO] === Phase 3: resume from 73% to 100% via client.py ===
[DEMO] ✅ Two-interrupt upload resume successful! SHA-256 verified by server.
```

🎙️ **Lời thoại:**

> Upload bị ngắt cưỡng bức ở mốc 37 phần trăm — socket bị đóng đột ngột để mô phỏng mất mạng thật, chứ không phải logout sạch sẽ.
>
> Server không xoá phần dữ liệu đã nhận, mà giữ lại trong một file tạm đuôi `.part`, kèm theo một file sidecar ghi kích thước và SHA-256 kỳ vọng của file gốc. Khi client kết nối lại, server đọc sidecar này, xác nhận đúng là phần tiếp theo của cùng một file, rồi trả về chính xác offset 7 triệu 761 nghìn 920 byte để client truyền tiếp từ đó — chứ không bắt đầu lại từ số không.
>
> Kịch bản được lặp lại lần thứ hai ở mốc 73 phần trăm. Hai mốc khác nhau chứng minh cơ chế resume không phụ thuộc vào một vị trí cố định nào cả.

*(Khi hiện phần download)*

```text
[DEMO] === Download Phase 1: download to 50%, then interrupt ===
[DEMO] Download killed at 10,485,760 bytes (50.0% of 20.0MB)

[DEMO] === Download Phase 2: resume from 50% to 100% via client.py ===
[DEMO] ✅ Download resume successful! SHA-256 verified by client.
```

🎙️ **Lời thoại:**

> Ở chiều ngược lại, download bị ngắt ở mốc 50 phần trăm. Lần này client mới là bên giữ dữ liệu dở — nó giữ lại 10 MiB đã tải trong file `.part` của mình, và khi kết nối lại thì chỉ yêu cầu phần còn thiếu, bắt đầu từ byte 10 triệu 485 nghìn 760, thay vì tải lại toàn bộ từ đầu.

*(Khi script kết thúc, quay rõ các dòng cuối)*

🎙️ **Lời thoại kết:**

> Sau khi nhận đủ toàn bộ file, server băm lại SHA-256 của cả file và chỉ commit khi digest khớp hoàn toàn — nếu sai, file hỏng sẽ bị cách ly ra riêng chứ không ghi đè lên dữ liệu tốt. Phía download thì client tự băm và đối chiếu với hash mà server đã gửi kèm từ đầu. Cả hai chiều đều báo SHA-256 verified. File tạm và server demo cũng được dọn dẹp tự động.

🔗 **Câu nối ra:**

> Resume ở cả hai chiều đều khớp SHA-256. Bình sẽ trình bày tiếp phần đo giới hạn băng thông và chính sách xử lý file trùng tên.

---

## Shot H3 — `SERVER_BUSY` khi vượt capacity *(5:35–6:20, ~45 giây)*

**Trạng thái cần dựng trước khi quay:** cần một server chỉ có 3 slot.

```powershell
python server.py 9000 "" 3
```

**Thao tác:** mở ba phiên tương tác, giữ nguyên không thoát.

```powershell
# Terminal ALICE
python client.py 127.0.0.1 9000 --username cap-alice
# Terminal BOB
python client.py 127.0.0.1 9000 --username cap-bob
# Terminal CAROL
python client.py 127.0.0.1 9000 --username cap-carol
```

Sau đó, terminal `CAPACITY`:

```powershell
python client.py 127.0.0.1 9000 --username overflow "LIST"
```

Kết quả mong đợi (đã kiểm chứng bằng lệnh thật, không phải phỏng đoán):

```text
[OK] Connected to 127.0.0.1:9000
[ERROR] LOGIN failed (120): server is full
[INFO] Connection closed
```

Client thoát với exit code 1 — script bên ngoài phát hiện được lỗi này qua exit code chứ không cần đọc chuỗi.

🔗 **Câu nối vào:**

> Cảm ơn Bình. Server đang giới hạn 3 slot, em sẽ mở đúng ba phiên tương tác và giữ nguyên, không thoát ra.

🎙️ **Lời thoại:**

*(Sau khi ba phiên đã mở)*

> Ba phiên này đang chiếm đủ ba trên ba slot của server. Bây giờ em thử kết nối thêm một client thứ tư.

*(Sau khi lỗi hiện ra)*

> Kết nối thứ tư nhận về lỗi 120, `SERVER_BUSY`, kèm thông báo "server is full".
>
> Có một chi tiết thiết kế đáng chú ý ở đây: server vẫn `accept` kết nối TCP trước, rồi mới trả về lỗi này. Nếu từ chối ngay ở tầng hệ điều hành, thì phía client sẽ không phân biệt được là server đang đầy hay server đã chết hẳn — cả hai trường hợp đều chỉ thấy kết nối bị từ chối. Cách làm hiện tại cho client biết chính xác lý do. Và quan trọng là server hoàn toàn không crash, cũng không treo.

🔗 **Câu nối ra:**

> Server đã từ chối đúng kết nối vượt giới hạn. Cường sẽ kiểm tra lại một phiên cũ, để chứng minh các client đang kết nối không hề bị ảnh hưởng.

---

# 7. Hướng dẫn dựng

1. **Gom file.** Mỗi người nộp các file quay đặt tên đúng theo mã shot: `C1.mp4`, `C2.mp4`, `C3.mp4`, `C4.mp4`, `C5.mp4`, `B1.mp4`…, `H1.mp4`…
2. **Ghép theo đúng thứ tự bảng ở mục 1** — thứ tự này *không* trùng với thứ tự từng người quay:

   ```
   C1 → C2 → B1 → C3 → B2 → H1 → H2 → B3 → B4 → H3 → C4 → C5
   ```

3. **Cắt khoảng đệm.** Xén phần im lặng thừa ở đầu/cuối mỗi shot, nhưng **chừa lại khoảng 0,3–0,5 giây** giữa hai shot — cắt sát quá sẽ nghe như bị nuốt chữ.
4. **Kiểm tra mối nối.** Nghe lại từng chỗ chuyển người: câu nối ra của shot trước phải khớp nội dung với shot sau. Nếu ai đó lỡ đọc sai tên hoặc sai nội dung sắp tới, quay lại riêng đúng câu đó rồi chèn vào.
5. **Cân âm lượng.** Ba người quay ba máy khác nhau nên mức âm gần như chắc chắn lệch. Chuẩn hoá về cùng một mức trước khi xuất.
6. **Chèn tên người nói.** Nên thêm một dòng chữ nhỏ ở góc mỗi khi đổi người (ví dụ "Cường — kiến trúc"), giúp người chấm theo dõi được ai phụ trách phần nào.
7. **Kiểm tra tổng thời lượng** nằm trong 5–8 phút trước khi xuất bản.

---

# 8. Checklist trước khi xuất video

**Nội dung bắt buộc theo đề:**

- [ ] Có cảnh ba thanh tiến trình chạy đồng thời (B1) — không phải ba client đứng yên.
- [ ] Có ít nhất một UPLOAD, một LIST và một DOWNLOAD thành công (B1, C3).
- [ ] Có cảnh ngắt upload ở 37% và 73%, mỗi lần reconnect đúng offset (H2).
- [ ] Có cảnh ngắt download ở 50%, resume từ byte 10.485.760 (H2).
- [ ] Có cảnh `SHA256 Verification OK` sau mỗi lần resume (H2).

**Nội dung mở rộng:**

- [ ] Stress `240/240` hoặc artifact JSON/CSV rõ ràng (B2).
- [ ] Throttle CSV đủ ba lần đo (B3).
- [ ] `FILE_EXISTS` (B4) và `SERVER_BUSY` (H3).
- [ ] Cảnh chứng minh session cũ vẫn sống sau khi server từ chối client mới (C4).

**Kỹ thuật:**

- [ ] Tổng thời lượng 5–8 phút.
- [ ] Các mối nối giữa shot nghe liền mạch, không cụt tiếng, không lặp ý.
- [ ] Âm lượng ba người đã cân bằng.
- [ ] Font terminal đủ lớn, không cắt mất dòng lỗi hay dòng kết quả.
- [ ] Không lộ token, mật khẩu, đường dẫn cá nhân, cửa sổ chat riêng.
- [ ] Ghi commit hash đang quay trong phần mô tả video.

---

# 9. Phương án dự phòng khi quay

| Sự cố | Cách xử lý |
|---|---|
| Ba upload kết thúc quá nhanh, không kịp quay cảnh song song | Luôn dùng `--limit 500` với file `10mb.bin`. Nếu vẫn nhanh, hạ xuống `--limit 200`. |
| `FILE_EXISTS` nổ ngay ở lần upload đầu tiên (B1) | Đang dùng lại `storage/` cũ còn dữ liệu. Xoá `storage/`, `logs/`, `downloads/` rồi quay lại từ đầu gói. |
| `resume_demo.py` báo port đang bận | Còn tiến trình server cũ chưa thoát hẳn — kể cả server con do chính script khởi động ở lần chạy trước. Kiểm tra và tắt hết tiến trình Python đang giữ port 9000. |
| Stress test báo có client failed | Chạy lại một lần nữa; nếu vẫn lỗi, kiểm tra xem có server nào khác đang chiếm port 9000 không. Không quay đè lên kết quả lỗi. |
| Lỡ đọc sai một câu ở giữa shot | Không cần quay lại cả shot — dừng, im lặng 2 giây, đọc lại nguyên câu đó, khâu dựng sẽ cắt bỏ đoạn hỏng. |
| Demo trực tiếp lỗi ngay lúc quay, không sửa kịp | Dùng ảnh chụp màn hình `stress.json`, `stress.csv`, `throttle.csv` và log của lần nghiệm thu gần nhất để thay thế, kèm lời giải thích. |
