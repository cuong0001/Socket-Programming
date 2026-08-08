# Lập trình Socket — Dịch vụ truyền file Giai đoạn 2

Kho mã nguồn này triển khai dịch vụ truyền file client/server qua TCP bằng thư viện chuẩn Python. Giai đoạn 2 hỗ trợ giao thức nhị phân có tiền tố độ dài, nhiều client đồng thời, namespace riêng theo user, resume, kiểm tra SHA-256, progress, giới hạn băng thông, mã lỗi có cấu trúc và xử lý server đầy.

Dự án cần chạy nằm trong [`project/Phase 2/`](project/Phase%202/). Xem [runbook](project/Phase%202/README.md) để cài đặt trên máy sạch, chạy server/client, chạy test và thực hiện demo 5–8 phút.

## Chạy nhanh

```powershell
Set-Location "project/Phase 2"
python server.py 9000
```

Trong terminal khác:

```powershell
Set-Location "project/Phase 2"
python testdata/make_testdata.py
python client.py 127.0.0.1 9000 --username alice "UPLOAD testdata/512b.bin"
python client.py 127.0.0.1 9000 --username alice "LIST"
```

Chạy test từ `project/Phase 2`:

```powershell
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -t tests -v
```

## Tài liệu

- [Runbook Giai đoạn 2](project/Phase%202/README.md)
- [Mini-RFC giao thức](project/Phase%202/docs/protocol.md)
- [Báo cáo kiến trúc và kiểm thử](project/Phase%202/docs/architecture.md)
- [Lệnh demo](project/Phase%202/demo_commands.txt)
