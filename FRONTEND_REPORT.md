# Báo cáo giai đoạn frontend

Đã triển khai tại dự án Django cục bộ, không xuất bản lên dịch vụ hosting.

## 1. Kiểm tra và bảo toàn

Đọc lại template, views, các đường dẫn và tests hiện tại. Sao lưu source,
database và Excel trong `_backups/before_frontend_20261102_224148/` trước khi sửa.
Manifest SHA-256 ghi nhận toàn bộ media, database, Excel, views và stabilizer.
Không thay đổi views, URLs, settings, models, migrations hoặc `stabilizer.py`.
File backend duy nhất được bổ sung nội dung trong giai đoạn này là `video/tests.py`.

## 2. Home

- Hero “Sửa Video Rung”, nút Bắt đầu dẫn đến `/workspace/`.
- Navy gần đen, cyan, bố cục hero hai cột, card bước xử lý, feature grid, FAQ,
  CTA và footer dựa trên ảnh tham chiếu.
- Không dùng logo khách hàng, đánh giá, số liệu hoặc công cụ chưa có.
- Ảnh trước/sau lấy ở frame 30 của `input_1776156541.mp4` và
  `output_1776156541_fixed.mp4`. Đây là ảnh minh họa tĩnh từ dữ liệu thật,
  không dùng làm kết quả cho video người dùng vừa tải lên.
- Dùng font hệ thống hỗ trợ tiếng Việt, không phụ thuộc CDN hoặc font bên ngoài.

Files: `frontend/templates/home.html`, `base.html`, component header/footer/icon,
`frontend/static/css/site.css`, `js/site.js`, `images/`.

Kiểm tra ở bước này: Django check và 7 bài kiểm thử cấu trúc/đường dẫn đạt.

## 3. Workspace và upload

- Sidebar, header, video gốc bên trái và cấu hình bên phải trên desktop.
- Chọn tệp/kéo thả, xem trước bằng URL tạm từ tệp người dùng đã chọn.
- Chỉ hiển thị chế độ tự động và xử lý viền thực tế; không thêm tham số không
  được backend sử dụng. Hiển thị rõ chưa giữ âm thanh và xử lý trên máy chủ.
- Trạng thái chờ, sẵn sàng, đang tải lên/xử lý; không giả phần trăm.
- CSRF được gửi bằng trường ẩn có sẵn trong FormData, giữ POST `/` tương thích.
- Lỗi HTTP, mất kết nối, tệp sai và không có kết quả đều cho phép chọn lại/thử lại.

Files: `workspace.html`, component sidebar, `css/workspace.css`, `js/workspace.js`.

Kiểm tra ở bước này: cả 10 bài kiểm thử cũ và kiểm tra cú pháp JavaScript đạt.

## 4. Kết quả

- Thêm khung video đã giảm rung bên dưới, giữ video gốc để so sánh.
- Player có điều khiển trình duyệt và nút Play/Pause, tải MP4, Bắt đầu lại.
- Bảng mean/std và mức thay đổi lấy nguyên context từ backend; hiển thị đúng
  giá trị 0, giá trị âm và trạng thái không đủ dữ liệu.
- Có phần mở rộng video so sánh ghép đôi khi backend thực sự trả về đường dẫn.
- Không có khung kết quả khi mới mở Workspace hoặc khi xử lý thất bại.
- Khi codec không phát được, ẩn trình phát lỗi, thông báo và giữ liên kết tải tệp.

Files: component `player.html`, `result.html`, CSS/JS Workspace.

Kiểm tra: upload một đoạn 12 frame trích từ video thật, xử lý bằng OpenCV thật,
kiểm tra video gốc, video kết quả, video so sánh và tải xuống.

## 5. Kiểm tra cuối

- `python -B manage.py check`: đạt.
- `python -B manage.py test video`: 14 bài kiểm thử đạt.
- `node --check` cho cả hai file JavaScript: đạt.
- Edge headless: 15 kiểm tra đạt, không có ngoại lệ JavaScript hoặc lỗi HTTP
  của trang, static và media trong các luồng đã kiểm tra.
- Home và Workspace không tràn ngang tại 320, 390, 768, 1024 và 1440 px.
- Kiểm tra menu mobile, chọn file, kéo thả, trạng thái đang xử lý, kết quả trong
  cùng URL, tải MP4, lỗi/thử lại, fallback codec và Play/Pause.
- Mọi upload kiểm thử ghi vào MEDIA_ROOT tạm, không ghi vào media gốc.
- Trong kiểm thử, chỉ tắt các lệnh hiển thị cửa sổ OpenCV; thuật toán chạy thật.

Ảnh chụp desktop/mobile và `browser-report.json` được lưu tại
`_backups/before_frontend_20261102_224148/`.

## Giới hạn giữ nguyên

Máy hiện chưa có FFmpeg trong PATH. Video mới được xuất bằng nhánh dự phòng
MP4 `mp4v`; chưa bảo đảm phát trực tiếp trên mọi trình duyệt. Giao diện có
fallback tải tệp. Kiểm tra Play/Pause dùng riêng một MP4 H.264 có sẵn của dự án;
không thay thế video kết quả của luồng upload bằng tệp này.

Thuật toán vẫn mở preview desktop và xử lý đồng bộ theo code cũ. Không sửa
các giới hạn này trong giai đoạn frontend vì người dùng yêu cầu hỏi trước
khi thay đổi logic backend hoặc thuật toán.
