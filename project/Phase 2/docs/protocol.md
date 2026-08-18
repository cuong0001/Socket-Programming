# Giao thức truyền file Giai đoạn 2 (Mini-RFC)

Trạng thái: đã được hiện thực bởi `protocol.py`, `client.py`, `server.py` và
`session.py`.

## 1. Phạm vi và quy ước

Giao thức này chạy trên nền TCP, cung cấp các chức năng: đăng nhập, namespace
file riêng theo từng user, upload/download nhị phân, resume dựa trên offset,
kiểm tra checksum, xóa file, và trả lỗi có cấu trúc. TCP là một luồng byte
liên tục, nên mọi gói tin ở tầng ứng dụng đều mang một tiền tố độ dài. Phía
nhận bắt buộc phải dùng `recv_exact`/`read_packet`; không được giả định rằng
một lần `send` sẽ tương ứng với đúng một lần `recv`.

Toàn bộ các trường số nguyên đều không dấu và dùng thứ tự byte mạng
(big-endian). Kích thước và offset được tính theo byte. Giá trị SHA-256 là 32
byte digest **thô**, không phải chuỗi hex dạng văn bản. Dữ liệu file nhị phân
không bao giờ được decode thành văn bản và có thể chứa byte `0x00`.

Ký hiệu:

- `u16`, `u32`, `u64`: số nguyên không dấu 2, 4 và 8 byte.
- `text`: `byte_length:u16 + chuỗi byte UTF-8`.
- `sha256`: đúng 32 byte thô khi có mặt.
- `data`: chuỗi byte nhị phân bất kỳ.

## 2. Khung gói tin (framing)

Mọi gói tin đều có bố cục sau:

```text
  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                         LENGTH:u32                            |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |          OPCODE:u16           |          USER_ID:u16          |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |                     PAYLOAD (độ dài thay đổi) ...             |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

`LENGTH` đếm toàn bộ số byte đứng **sau** trường length 4 byte:

```text
LENGTH = 2 (opcode) + 2 (user_id) + độ dài payload
```

Do đó, một gói tin có payload rỗng sẽ mang `LENGTH=4` và chiếm 8 byte trên
đường truyền. Phần hiện thực từ chối mọi phần thân lớn hơn 1 MiB. Mỗi khối dữ
liệu file trong client và server hiện tại có kích thước 4096 byte.

Trước khi đăng nhập, client gửi `USER_ID=0`. Một phản hồi LOGIN thành công sẽ
cấp cho client một ID khác 0. Mọi gói tin client gửi sau đó đều phải mang đúng
ID này; nếu không khớp sẽ nhận lỗi `USER_ID_MISMATCH`.

## 3. Bảng opcode

| Tên | Hex | Chiều | Payload |
|---|---:|---|---|
| `LOGIN` | `0x01` | C -> S | `username:text` |
| `LOGOUT` | `0x02` | C -> S | rỗng |
| `FILE_LIST` | `0x10` | C -> S | rỗng |
| `FILE_LIST_RESP` | `0x11` | S -> C | `count:u32 + danh sách entry` |
| `FILE_UPLOAD` | `0x12` | C -> S | metadata upload |
| `FILE_DOWNLOAD` | `0x13` | C -> S | metadata download |
| `FILE_CHUNK` | `0x14` | C <-> S | `offset:u64 + data` |
| `FILE_DELETE` | `0x15` | C -> S | `filename:text` |
| `ACK` | `0x20` | S -> C | gói xác nhận |
| `ERROR` | `0xFF` | S -> C | lỗi có cấu trúc |

Các opcode không xác định sẽ nhận lỗi `UNKNOWN_OPCODE` trong trường hợp trạng
thái phiên hiện tại vẫn có thể tiếp tục an toàn.

## 4. Định dạng payload

### 4.1 LOGIN và tên file

`LOGIN` dùng một chuỗi username UTF-8 có tiền tố độ dài:

```text
name_length:u16 + username:name_length byte
```

`FILE_DELETE` dùng đúng cách biểu diễn này cho tên file. Server từ chối các
trường hợp: tên rỗng, UTF-8 không hợp lệ, ký tự phân tách đường dẫn, `..`, ký
tự phân tách ổ đĩa, dấu chấm/khoảng trắng ở cuối tên, và tên thiết bị của
Windows.

### 4.2 FILE_LIST_RESP

```text
count:u32
lặp lại count lần:
    name_length:u16
    filename:name_length byte
    size:u64
```

Phản hồi chỉ chứa các file **đã hoàn chỉnh** trong thư mục lưu trữ của user
đang đăng nhập. Các file sidecar staging, file dở dang và file bị cách ly đều
được ẩn đi.

### 4.3 FILE_UPLOAD

```text
name_length:u16
filename:name_length byte
total_size:u64
proposed_offset:u64
sha256:32 byte (tùy chọn với gói tin đời cũ; bắt buộc với client Giai đoạn 2)
```

Client hiện tại luôn đề xuất offset bằng 0 và gửi kèm SHA-256 của toàn bộ
file. Server mới là bên quyết định điểm resume thực tế, dựa trên file `.part`
tương thích và file sidecar của nó, rồi trả vị trí đó về trong một gói ACK.
Cả `proposed_offset` lẫn offset do server chọn đều không được vượt quá
`total_size`.

### 4.4 FILE_DOWNLOAD

```text
name_length:u16
filename:name_length byte
requested_offset:u64
```

Offset ở đây chính là kích thước file `.part` cục bộ đã được client xác thực.
Server từ chối nếu offset vượt quá kích thước của file hoàn chỉnh.

### 4.5 FILE_CHUNK

```text
offset:u64
data:phần byte payload còn lại
```

Các khối dữ liệu phải đến đúng vị trí offset kế tiếp mà phía nhận đang chờ.
Với chiều upload, một khối không được phép vượt quá `total_size` mà gói
FILE_UPLOAD đã khai báo. Phía nhận ghi và băm `data` ở dạng byte thô.

### 4.6 ACK

```text
acked_opcode:u16
next_offset:u64
sha256:32 byte (tùy chọn)
```

Phía nhận bắt buộc phải kiểm tra `acked_opcode` có khớp với thao tác mình đang
chờ hay không. Ý nghĩa của `next_offset` thay đổi tùy theo từng thao tác:

| Thao tác được xác nhận | Ý nghĩa của `next_offset` | SHA-256 |
|---|---|---|
| `LOGIN` | user ID được cấp | không có |
| `FILE_UPLOAD` (gói đầu) | vị trí resume phía server | không có |
| `FILE_UPLOAD` (gói cuối) | tổng kích thước đã hoàn tất | digest của server |
| `FILE_DOWNLOAD` | tổng kích thước file | digest của server |
| `FILE_DELETE` | bằng 0 | không có |
| `LOGOUT` | bằng 0 | không có |

### 4.7 ERROR

```text
error_code:u16
message_length:u16
message:message_length byte UTF-8
```

Trường `message_length` lưu **số byte**, không phải số ký tự Unicode.

## 5. Bảng mã lỗi

| Thập phân | Hex | Tên | Ý nghĩa |
|---:|---:|---|---|
| 100 | `0x0064` | `MALFORMED` | Không phân tích được gói tin hoặc payload |
| 101 | `0x0065` | `UNKNOWN_OPCODE` | Opcode chưa được hiện thực |
| 102 | `0x0066` | `INVALID_USERNAME` | Username không hợp lệ hoặc không an toàn |
| 103 | `0x0067` | `NOT_LOGGED_IN` | Phải LOGIN trước |
| 104 | `0x0068` | `USER_ID_MISMATCH` | ID trong gói tin khác với ID của phiên |
| 105 | `0x0069` | `USERNAME_IN_USE` | Username đã có một phiên đang hoạt động |
| 110 | `0x006E` | `INVALID_FILENAME` | Tên file không hợp lệ hoặc không an toàn |
| 111 | `0x006F` | `NOT_FOUND` | File hoàn chỉnh không tồn tại |
| 112 | `0x0070` | `FILE_EXISTS` | File đích của upload đã tồn tại |
| 113 | `0x0071` | `OFFSET_MISMATCH` | Offset của khối dữ liệu hoặc của resume không hợp lệ |
| 114 | `0x0072` | `CHECKSUM_MISMATCH` | SHA-256 cuối cùng không khớp |
| 115 | `0x0073` | `RESUME_CONFLICT` | Metadata resume không tương thích |
| 120 | `0x0078` | `SERVER_BUSY` | Đã đạt giới hạn số client hoạt động tối đa |
| 121 | `0x0079` | `FILE_BUSY` | Không lấy được khóa file |
| 130 | `0x0082` | `INTERNAL_ERROR` | Lỗi nội bộ của server, đã được ghi log |

Phần lớn các lỗi ngữ nghĩa vẫn để kết nối tiếp tục dùng được. Riêng trường hợp
frame bị cắt cụt hoặc mất kết nối TCP thì không thể khôi phục, vì lúc đó không
còn xác định được ranh giới gói tin nữa; phía đối tác sẽ kết nối lại từ đầu.

## 6. Máy trạng thái phiên

```text
CONNECTED --LOGIN--> AUTHENTICATED

AUTHENTICATED --FILE_UPLOAD--> UPLOADING --FILE_CHUNK x N--> AUTHENTICATED
AUTHENTICATED --FILE_DOWNLOAD--> DOWNLOADING --FILE_CHUNK x N--> AUTHENTICATED
AUTHENTICATED --FILE_LIST / FILE_DELETE--> AUTHENTICATED
AUTHENTICATED --LOGOUT--> CLOSED
```

Trước khi xác thực, server chỉ chấp nhận duy nhất LOGIN. Ở trạng thái
`AUTHENTICATED`, server chấp nhận LIST, UPLOAD, DOWNLOAD, DELETE và LOGOUT.
Trong lúc đang upload, chỉ luồng FILE_CHUNK đúng như dự kiến (hoặc LOGOUT) mới
hợp lệ. Với download thì server là bên chủ động đẩy dữ liệu; client nhận cho
tới khi đủ số byte mà gói ACK mở đầu đã thông báo.

## 7. Trình tự các thao tác

### 7.1 Đăng nhập

```text
C -> S  LOGIN(user_id=0, username)
S -> C  ACK(acked_opcode=LOGIN, next_offset=user_id_được_cấp)
```

Client dùng ID được cấp này cho toàn bộ các gói tin về sau.

### 7.2 Upload và resume upload

```text
C -> S  FILE_UPLOAD(filename, total_size, offset=0, full_sha256)
S -> C  ACK(FILE_UPLOAD, server_offset)
C -> S  FILE_CHUNK(server_offset, data) x N
S -> C  ACK(FILE_UPLOAD, total_size, actual_sha256)
```

Nếu kết nối bị đứt, server giữ lại file `.part` cùng file `.part.json`. Ở lần
FILE_UPLOAD kế tiếp cho cùng cặp username/filename, server đối chiếu
`total_size` và SHA-256 với nội dung sidecar. Nếu file staging tương thích,
quá trình truyền tiếp tục từ đúng kích thước byte hiện tại của nó; nếu không
tương thích, staging sẽ bị xóa bỏ thay vì trộn lẫn với dữ liệu của một file
nguồn khác. File hoàn chỉnh chỉ được chuyển sang trạng thái chính thức một
cách nguyên tử **sau khi** digest toàn file khớp.

Nếu tên file đó đã hoàn chỉnh từ trước, server trả về `FILE_EXISTS`; chính
sách cập nhật tường minh là DELETE trước rồi mới UPLOAD lại.

### 7.3 Download và resume download

```text
C -> S  FILE_DOWNLOAD(filename, local_part_size)
S -> C  ACK(FILE_DOWNLOAD, total_size, full_sha256)
S -> C  FILE_CHUNK(local_part_size, data) x N
```

Chiều download **không có** gói ACK kết thúc. Client đã biết sẵn `total_size`
và digest kỳ vọng ngay từ gói ACK mở đầu. Sau khi nhận đúng số byte đó, client
băm toàn bộ file `.part` và chỉ đổi tên nó một cách nguyên tử khi digest khớp.
Nếu sidecar không khớp, client xóa staging cục bộ và phải gửi yêu cầu mới.

### 7.4 Xóa file và đăng xuất

```text
C -> S  FILE_DELETE(filename)
S -> C  ACK(FILE_DELETE, 0) | ERROR(...)

C -> S  LOGOUT
S -> C  ACK(LOGOUT, 0)
```

## 8. Gói tin upload mẫu chuẩn (golden vector)

Đây là vector chuẩn được `tests/test_protocol.py` kiểm tra đối chiếu từng
byte, với các tham số:

- opcode `FILE_UPLOAD` (`0x0012`)
- user ID `7`
- tên file `data.bin`
- tổng kích thước `10.000.000` (`0x0000000000989680`)
- offset đề xuất `0`
- 32 byte SHA-256, mỗi byte đều là `0x11`

```text
00 00 00 3E  00 12  00 07
00 08  64 61 74 61 2E 62 69 6E
00 00 00 00 00 98 96 80
00 00 00 00 00 00 00 00
11 11 11 11 11 11 11 11
11 11 11 11 11 11 11 11
11 11 11 11 11 11 11 11
11 11 11 11 11 11 11 11
```

Phần thân gói tin gồm 62 byte (`0x3E`): 4 byte cho opcode và user ID, 10 byte
cho tên file đã mã hóa, 16 byte cho kích thước và offset, cùng 32 byte digest.
Gói tin hoàn chỉnh chiếm 66 byte nếu tính cả tiền tố độ dài 4 byte.

## 9. Các lệnh kiểm chứng

Chạy từ thư mục `project/Phase 2`:

```powershell
python -m unittest tests.test_protocol -v
python -m unittest discover -s tests -t tests -p test_framing.py -v
python -m unittest discover -s tests -t tests -p test_stress_clients.py -v
```

Khi đã có một server đang lắng nghe ở port 9000:

```powershell
python tools/stress_clients.py --host 127.0.0.1 --port 9000 --clients 12 --rounds 20 --seed 2026
```

Lệnh stress sẽ ghi ra `docs/test-results/stress.json` và
`docs/test-results/stress.csv`, đồng thời thoát với mã khác 0 nếu có bất kỳ
logical client nào thất bại.
