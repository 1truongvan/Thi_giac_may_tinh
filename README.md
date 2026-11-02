# Hệ thống ổn định video

## Cấu trúc sau khi tách

- `backend/config/`: cấu hình Django và chương trình Tkinter cũ `main.py`.
- `backend/video/`: app Django, thuật toán OpenCV, models và migrations cũ.
- `frontend/templates/`: Home, Workspace và các component dùng chung, kế thừa `base.html`.
- `frontend/static/`: CSS, JavaScript, SVG và ảnh minh họa từ video thật của dự án.
- `media/input/`, `media/output/`, `db.sqlite3`, `results.xlsx`: giữ ở gốc.

Các module Django vẫn có tên `config` và `video`; `manage.py` thêm `backend/`
vào đường dẫn import. Không chạy trực tiếp `backend/config/main.py` khi khởi động
web: đó là chương trình Tkinter độc lập từ source cũ.

## Chạy từ thư mục gốc

```powershell
python -m pip install -r requirements.txt
python manage.py check
python manage.py runserver
```

- `GET /`: Home navy/cyan theo bố cục ảnh Figma, nút Bắt đầu tới Workspace.
- `GET /workspace/`: kéo thả/chọn video, xem trước và bảng cấu hình tự động.
- `POST /workspace/`: xử lý video thật.
- `POST /`: giữ tương thích upload cũ, trả kết quả Workspace trực tiếp.

JavaScript gửi chính biểu mẫu Django bằng `fetch`, đọc HTML do backend trả về
và cập nhật phần kết quả ngay trong Workspace. Không thêm endpoint, giữ nguyên
phép tính giảm rung, không hiển thị phần trăm tiến trình. Khi JavaScript bị tắt, biểu mẫu
vẫn gửi POST theo cách truyền thống. Video không phát được trên trình duyệt vẫn
có liên kết tải MP4. Chi tiết triển khai và kiểm thử: [FRONTEND_REPORT.md](FRONTEND_REPORT.md).

## FFmpeg và FFprobe trên Windows

Dự án hiện có bản portable FFmpeg/FFprobe 9.0.2 trong `tools/ffmpeg/bin/`.
Archive đã được đối chiếu SHA-256 với bản phát hành của Gyan; không sửa PATH
toàn hệ thống. Binary và archive không được đưa vào Git.

Nếu sao chép source sang máy khác:

1. Tải bản Essentials ZIP tại [Gyan FFmpeg Builds](https://www.gyan.dev/ffmpeg/builds/).
2. Kiểm tra SHA-256 được công bố, giải nén rồi đặt `ffmpeg.exe` và `ffprobe.exe`
   trong `tools/ffmpeg/bin/`. Giữ giấy phép đi kèm khi phân phối binary.
3. Chạy `python manage.py check_video_tools` để kiểm tra công cụ và libx264.

Hoặc dùng công cụ đã cài ở thư mục riêng, trong PowerShell:

```powershell
$env:FFMPEG_BINARY = 'D:\ffmpeg\bin\ffmpeg.exe'
$env:FFPROBE_BINARY = 'D:\ffmpeg\bin\ffprobe.exe'
python manage.py check_video_tools
python manage.py runserver
```

Trong CMD:

```bat
set FFMPEG_BINARY=D:\ffmpeg\bin\ffmpeg.exe
set FFPROBE_BINARY=D:\ffmpeg\bin\ffprobe.exe
python manage.py runserver
```

Khởi động lại Django sau khi thay đổi biến môi trường. Hệ thống không tự đọc
file `.env`. Thứ tự tìm công cụ: cấu hình tường minh, bản portable của dự án,
sau đó PATH. Khi chỉ cấu hình FFmpeg, FFprobe có thể được tìm cạnh executable đó.
`VIDEO_TOOL_TIMEOUT` đặt giới hạn giây cho mỗi lệnh ngoài (mặc định 1800).

Nếu thiếu công cụ, không có libx264, lệnh lỗi hoặc video đầu ra không hợp lệ,
Workspace báo lỗi; không âm thầm trả MP4 `mp4v` làm kết quả thành công.

## Xử lý và phân tích

- Mã hóa MP4 H.264, yuv420p, faststart. Kiểm tra toàn bộ số frame giải mã, FPS,
  kích thước và codec trước khi trả kết quả. Giữ CRF/preset cũ: 18/slow cho đầu
  ra, 23/fast cho bản so sánh.
- Django gọi `stabilize_video(..., preview=False)`; không vá hàm OpenCV toàn cục.
  Chạy desktop vẫn có thể dùng `preview=True` (mặc định).
- ECC, Farneback, Gaussian, biến đổi hình học, tham số thích ứng và xử lý viền
  giữ nguyên. Chữ `Frame: 1` ở frame xuất đầu tiên cũng giữ nguyên.
- Tên file UUID và ghi độc quyền tránh ghi đè. Video gốc và trung gian đã tạo
  được giữ lại nếu bước xử lý tiếp theo thất bại.
- `media/output/analysis_<job_id>.json` chứa đầy đủ chuyển động theo frame,
  Mean/Std, metadata, mức giảm Std và thời gian máy chủ. JSON dùng số hữu hạn,
  không tạo dữ liệu khi phân tích thất bại. Không thêm model hoặc migration.
- Biểu đồ chỉ chọn tối đa 1500 mẫu thực mỗi chuỗi để hiển thị; JSON lưu toàn bộ.
  Chỉ số đo chuyển động ảnh trung bình, không tách riêng rung camera, lia máy
  hay chuyển động vật thể. Phần trăm giảm Std không phải cải thiện chất lượng tổng thể.
- Thời gian máy chủ gồm kiểm tra, lưu tệp, phân tích, ổn định/mã hóa và tạo bản
  so sánh; không gồm truyền tệp qua mạng, ghi JSON và dựng phản hồi HTML.

Nếu dùng máy chủ WSGI/ASGI từ gốc dự án, dùng
`backend.config.wsgi:application` hoặc `backend.config.asgi:application`.
Nếu đặt thư mục làm việc/Python path là `backend/`, vẫn dùng được
`config.wsgi:application` hoặc `config.asgi:application`.

## Kiểm thử

```powershell
python -B manage.py check
python -B manage.py test video --verbosity 2
```

Các bài kiểm thử không dùng database, không migrate và không ghi vào media gốc.
Bài kiểm thử tích hợp trích tối đa 12 frame từ video thật trong `media/input/`,
xử lý bằng thuật toán thật trong thư mục tạm, kiểm tra video gốc, video kết quả,
video so sánh và các số liệu. FFmpeg chạy thật; bài tích hợp sẽ thất bại nếu
luồng web gọi hàm cửa sổ OpenCV. Các fixture trong `backend/video/fixtures/`
ghi nhận phép tính/frame chuẩn của phiên bản cũ để kiểm tra bảo toàn thuật toán.

Kiểm thử trình duyệt trên Windows với Node 22 và Edge/Chrome đã cài:

```powershell
python -B tools/qa_server.py
```

Giữ terminal trên chạy, ở terminal thứ hai:

```powershell
node tools/browser_qa.mjs
$env:QA_BROWSER = 'chrome'
node tools/browser_qa.mjs
```

Máy chủ QA dùng cổng 8766, media tạm và thuật toán thật; không vá GUI hoặc ghi
vào media gốc. Báo cáo/ảnh lưu trong `_backups/processing_browser_qa/`.
Kết thúc QA bằng Ctrl+C; server ứng dụng thông thường vẫn chạy độc lập ở cổng 8000.

## Giới hạn hiện có

- Luồng xử lý vẫn đồng bộ; video dài hoặc độ phân giải lớn có thể mất nhiều thời gian.
- Cần chiều rộng/chiều cao chẵn để xuất yuv420p. Hệ thống báo lỗi thay vì tự
  sửa kích thước hoặc thay đổi nội dung frame. Video cần ít nhất hai frame hợp lệ.
- Chưa giữ âm thanh, chưa có API tiến trình hoặc tham số cấu hình từ người dùng.
- `db.sqlite3` ban đầu là file 0 byte. Sau khi sao lưu tại
  `_backups/before_migrate_20261102_223900/db.sqlite3`, đã áp dụng 18 migration
  mặc định của Django cho admin, auth, contenttypes và sessions. Không thay đổi
  models, migrations của app video hoặc dữ liệu video/Excel.

## Sao lưu

`_backups/before_split_20261102_222901/` lưu bản ZIP toàn bộ dự án trước khi
di chuyển, cả `.git`, manifest SHA-256, diff staged/unstaged và trạng thái Git.
Thư mục này bị loại khỏi Git để tránh commit bản sao dữ liệu lớn.
Không có commit hoặc thao tác thay đổi index Git trong quá trình tách.
