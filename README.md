# TopDev Auto Posting Tool

Công cụ tự động đăng tin tuyển dụng trên [dash.topdev.vn/jobs](https://dash.topdev.vn/jobs).

## Cấu trúc project

```
DevPost_Tool/
├── TopDev_AutoPost.ipynb   ← Notebook chính (chạy tại đây)
├── topdev_automation.py    ← Logic automation từng bước
├── topdev_helpers.py       ← Hàm tiện ích (log, đọc Excel)
├── data/
│   └── jd_data.xlsx        ← File JD (đặt file của bạn vào đây)
├── scripts/
│   └── create_sample.py    ← Tạo file Excel mẫu
└── guide.md                ← Hướng dẫn nghiệp vụ
```

## Cách sử dụng

### Bước 1 — Cài đặt (1 lần duy nhất)
Chạy **Cell 1** trong notebook để cài thư viện.

### Bước 2 — Chuẩn bị file JD
- Đặt file Excel vào thư mục `data/`
- File cần có các cột theo `guide.md`

Tạo file mẫu:
```bash
python scripts/create_sample.py
```

### Bước 3 — Chạy notebook
Mở `TopDev_AutoPost.ipynb` → chạy từng cell theo thứ tự:

| Cell | Mô tả |
|------|-------|
| 1 | Cài đặt thư viện |
| 2 | Config (đường dẫn file) |
| 3 | Đọc & xem trước JD |
| 4 | Đăng nhập TopDev |
| 5 | **Demo 1 tin đầu tiên** |
| 6 | Chạy tất cả các tin |
| 7 | Đóng trình duyệt |

## Cột Excel cần có

| Cột | Ví dụ |
|-----|-------|
| Job Title | Chuyên viên KHCN - Hà Nội |
| Job Category | Banking |
| Skills | Communication, Sales |
| Job Type | Full-time |
| Role | Individual Contributor |
| Level | Junior |
| Contract Type | Permanent |
| Tỉnh | Hà Nội |
| Job Detail | Mô tả vị trí... |
| Mô tả CV | Dòng 1\nDòng 2 (mỗi dòng = 1 responsibility) |
| Yêu cầu công việc | Yêu cầu 1\nYêu cầu 2 |
| LƯƠNG MIN | 9000000 |
| LƯƠNG MAX | 25000000 |