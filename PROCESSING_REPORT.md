# Báo cáo giai đoạn 3 — Hoàn thiện xử lý video

## Sao lưu và phạm vi

Trước khi chỉnh sửa đã tạo `_backups/before_processing_20261102_232003/`:
ZIP source/dữ liệu, SHA-256, diff staged/unstaged và trạng thái Git. ZIP đã kiểm
tra CRC. Không commit hoặc thay đổi index Git của người dùng.

Giữ Home và bố cục Workspace. Bổ sung phân tích ở dưới Result. Không đổi
models, migrations, database, Excel, video cũ hoặc cơ chế POST upload tại `/`.

## Các thay đổi

- `backend/video/stabilizer.py`: tham số preview mặc định True cho desktop;
  Django gọi False; kiểm tra VideoWriter, không ghi đè file, không báo thành
  công khi hủy bằng Esc; thay lệnh shell bằng service mã hóa có kiểm chứng.
- `backend/video/services/encoding.py`: cấu hình Windows, phát hiện và kiểm tra
  FFmpeg/FFprobe/libx264; subprocess không qua shell, không hiện cửa sổ console;
  MP4 H.264/yuv420p/faststart; kiểm tra frame giải mã, FPS, kích thước, pixel
  format và vị trí moov. Lỗi công cụ, timeout, thiếu codec đều trả lỗi rõ ràng.
- `services/processing.py`: điều phối lưu file UUID bằng chế độ độc quyền,
  kiểm tra đầu vào, phân tích trước/sau, ổn định, tạo so sánh, kiểm tra đầu ra
  và ghi JSON đi kèm. Chỉ trả kết quả khi toàn bộ các bước bắt buộc đạt.
- `services/analysis.py`: cùng phương pháp Farneback/Mean/Std cũ, thêm chuỗi
  chuyển động thực từng frame; loại số liệu rỗng/NaN/Inf; Std sau bằng 0 là
  hợp lệ; Std trước bằng 0 trả trạng thái không xác định tỷ lệ.
- `views.py`: gọi service và đưa lỗi rõ ràng về template; POST `/` vẫn nhận
  upload như `/workspace/`. Không giả tiến trình, không thêm endpoint.
- `settings.py`: cấu hình FFMPEG_BINARY, FFPROBE_BINARY, VIDEO_TOOL_TIMEOUT.
- `management/commands/check_video_tools.py`: lệnh kiểm tra cấu hình công cụ.
- Frontend: component analysis, JavaScript biểu đồ không dùng CDN, CSS navy/cyan,
  tải JSON và hiển thị lỗi server cụ thể; giữ player, so sánh và tải MP4.
- Tests: kiểm thử bảo toàn thuật toán, công cụ, lỗi, UUID, JSON và H.264 thật.

## Bảo toàn thuật toán

Không thay đổi ECC, nhánh dự phòng Farneback, Gaussian, ngưỡng thích ứng,
sigma, crop_ratio, giới hạn dịch chuyển/góc, ma trận biến đổi hoặc xử lý viền.
Giữ chữ `Frame: 1` trong frame xuất đầu tiên. Desktop vẫn có preview tùy chọn.

Đối chiếu trên đoạn trích 12 frame từ video thật, kích thước 160×96:

- transforms, trajectory, smoothed, transforms_smooth: trùng chính xác.
- motion_strength, sigma, crop_ratio: trùng chính xác.
- SHA-256 của toàn bộ frame giải mã trước bước H.264: trùng chính xác.
- Hợp đồng AST của ECC, Farneback, Gaussian, phép biến đổi, hai nhánh thích ứng
  và hàm xử lý viền: không đổi so với source đã sao lưu.

Fixture chuẩn nhỏ trong `backend/video/fixtures/` được lấy từ phiên bản cũ,
không dùng để tạo kết quả hiển thị cho người dùng. H.264 là bước mã hóa có mất
mát; không tuyên bố pixel sau mã hóa H.264 giống bit-for-bit với MP4 trung gian.

## FFmpeg trên Windows

Đã đặt FFmpeg và FFprobe 9.0.2 portable trong `tools/ffmpeg/bin/`, có libx264.
Không thay đổi PATH hệ thống. Giữ LICENSE/README của bộ binary.

Nguồn: https://github.com/GyanD/codexffmpeg/releases/tag/9.0.2

SHA-256 archive đã kiểm chứng:
`60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`.

Binary/download nằm trong .gitignore. Máy khác cần cài/cấu hình theo README.
Không tự chuyển mã hoặc ghi đè các video cũ; chỉ upload mới dùng luồng mới.

## Kiểm thử

- Django check và `check_video_tools`: đạt.
- Toàn bộ 33 bài Django tests: đạt, không dùng database và không migrate.
- Cú pháp JavaScript: đạt.
- Edge: 18 kiểm tra đạt; Chrome: 18 kiểm tra đạt.
- Kiểm tra video kết quả mới và video so sánh mới giải mã được trong trình duyệt,
  Play/Pause trên chính video mới, tải MP4/JSON, 3 biểu đồ và metadata thực tế.
- Responsive Home/Workspace tại 320, 390, 768, 1024, 1440 px; Result mobile
  không tràn ngang. Không có ngoại lệ JS hoặc lỗi HTTP của trang/static/media.
- Máy chủ QA không vá các hàm cửa sổ OpenCV; luồng web dùng preview=False.
  Trong tests, các lệnh GUI gây AssertionError nếu bị gọi.
- Thiếu FFmpeg/FFprobe, file hỏng/rỗng, video 1 frame, NaN/Inf, timeout, mã hóa
  lỗi, VideoWriter thất bại, metadata không khớp, hủy desktop và ghi đè được kiểm tra.
- Bài kiểm thử UUID xử lý hai upload cùng tên và giữ cả hai bộ file độc lập.

Ảnh/báo cáo trình duyệt:
`_backups/processing_browser_qa/{edge,chrome}/`.

## Kiểm thử toàn bộ video 720×1280

Đã xử lý toàn bộ `media/input/input_1793635621.mp4`, không chỉ đoạn trích:

| Thuộc tính | Kết quả |
| --- | --- |
| Video đầu ra | H.264, yuv420p, faststart |
| Độ phân giải | 720×1280 |
| Frame / FPS | 152 frame / 30 fps |
| Video so sánh | H.264, 1440×1280, 152 frame / 30 fps |
| Mean trước → sau | 2.836949 → 1.687849 pixel/frame |
| Std trước → sau | 1.864431 → 1.389627 pixel/frame |
| Mức giảm Std | 25.47% |
| Thời gian máy chủ đo được | 192.691 giây |

Đây là phép đo của một video trên máy hiện tại; không phải cam kết chất lượng
hoặc tốc độ cho mọi video. Luồng vẫn xử lý đồng bộ. Báo cáo, JSON đầy đủ và
video đầu ra kiểm thử được giữ trong
`_backups/before_processing_20261102_232003/full_video/`.

## Bảo toàn dữ liệu

Đối chiếu manifest sau kiểm thử: toàn bộ 95 file dữ liệu cũ (media, SQLite,
Excel) giữ nguyên SHA-256; không thiếu file nào. Những source cũ ngoài phạm vi
chỉnh sửa đã cho phép cũng giữ nguyên. Home/CSS dùng chung không đổi.

JSON phân tích mới dùng schema_version 1; chứa toàn bộ mẫu chuyển động, thông
tin video và thời gian. Biểu đồ chọn tối đa 1500 mẫu thực, không nội suy thêm
dữ liệu vào JSON. Chuyển động ảnh trung bình không tách riêng rung camera,
lia máy hay vật thể chuyển động; mức giảm Std không phải chất lượng tổng thể.

## Giới hạn còn giữ nguyên

Chưa giữ âm thanh, chưa chạy hàng đợi nền hoặc phần trăm tiến trình. Video
cần ít nhất hai frame và kích thước chẵn để xuất yuv420p mà không tự thay đổi
nội dung khung hình. Video gốc có codec trình duyệt không hỗ trợ vẫn có thể
không xem trước được; bản H.264 mới và video so sánh được kiểm tra trước khi trả.
