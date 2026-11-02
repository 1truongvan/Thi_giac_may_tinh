import cv2
import numpy as np
import os
from scipy.ndimage import gaussian_filter1d #
import pandas as pd
from .services.encoding import encode_for_web
from .services.errors import VideoProcessingError
def measure_shakiness(video_path): # Đo độ rung của video để điều chỉnh tham số ổn định
        cap = cv2.VideoCapture(video_path)

        ret, prev = cap.read()
        if not ret:
            cap.release()
            return None, None

        prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY) #Chuyển frame đầu tiên sang ảnh xám để giảm dữ liệu và dễ tính chuyển động

        motions = [] #Lưu trữ độ rung của từng frame để tính trung bình và độ lệch chuẩn

        while True:
            ret, frame = cap.read() 
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) 

            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray,
                None, 0.5, 3, 15, 3, 5, 1.2, 0
            ) #Tính toán trường chuyển động quang học giữa frame trước đó và frame hiện tại để ước lượng chuyển động của camera

            dx = np.mean(flow[..., 0])
            dy = np.mean(flow[..., 1])

            motion = np.sqrt(dx**2 + dy**2) #Tính độ rung tổng thể của frame hiện tại dựa trên chuyển động trung bình theo trục x và y
            motions.append(motion) #Lưu trữ độ rung của frame hiện tại

            prev_gray = gray #Cập nhật frame trước đó để so sánh với frame tiếp theo

        cap.release()

        if not motions or not np.isfinite(motions).all():
            return None, None
        return np.mean(motions), np.std(motions)
def stabilize_video(input_path, output_path, preview=True): #Ổn định video bằng cách ước lượng chuyển động giữa các frame,
        if os.path.exists(output_path):
            raise VideoProcessingError('Tệp đầu ra đã tồn tại; hệ thống không ghi đè dữ liệu cũ.')
        cap = cv2.VideoCapture(input_path)

        if not cap.isOpened():
            print("Cannot open video")
            return None

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)

        if fps <= 0 or fps > 60:
            fps = 30

        ret, prev = cap.read()
        if not ret:
            cap.release()
            return None

        prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
        transforms = []

        print(f"Total frames: {total_frames}")
        print("Estimating motion...")

        frame_idx = 1
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            try:
                warp = np.eye(2, 3, dtype=np.float32)
                _, warp = cv2.findTransformECC(
                    prev_gray,
                    gray,
                    warp,
                    cv2.MOTION_AFFINE,
                    (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 50, 1e-6)
                )
                dx = warp[0, 2]
                dy = warp[1, 2]
                da = np.arctan2(warp[1, 0], warp[0, 0])

            except Exception:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None,
                    0.5, 3, 15, 3, 5, 1.2, 0
                )
                dx = np.mean(flow[..., 0])
                dy = np.mean(flow[..., 1])
                da = 0

            transforms.append([dx, dy, da])
            prev_gray = gray
            frame_idx += 1

            print(f"Estimated: {frame_idx}/{total_frames}", end="\r")

        print()
        cap.release()

        if len(transforms) == 0:
            return None

        transforms = np.array(transforms)
        trajectory = np.cumsum(transforms, axis=0)

        motion_strength = np.mean(np.abs(transforms[:, :2]))

        if motion_strength > 5:
            sigma = 40
            crop_ratio = 0.12
        else:
            sigma = 20
            crop_ratio = 0.06

        print(f"Adaptive smoothing sigma={sigma}, crop={crop_ratio}")

        smoothed = np.copy(trajectory)
        for i in range(3):
            smoothed[:, i] = gaussian_filter1d(trajectory[:, i], sigma=sigma)

        diff = smoothed - trajectory
        transforms_smooth = transforms + diff

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            return None

        out = cv2.VideoWriter(
            output_path,
            cv2.VideoWriter_fourcc(*'mp4v'),
            fps,
            (w, h)
        )

        if not out.isOpened():
            cap.release()
            out.release()
            raise VideoProcessingError('OpenCV không mở được VideoWriter để ghi video đầu ra.')

        def fix_border(frame):
            h_, w_ = frame.shape[:2]
            y1 = int(crop_ratio * h_)
            y2 = int((1 - crop_ratio) * h_)
            x1 = int(crop_ratio * w_)
            x2 = int((1 - crop_ratio) * w_)

            crop = frame[y1:y2, x1:x2]
            return cv2.resize(crop, (w_, h_))

        print("Stabilizing...")

        ret, first_frame = cap.read()
        if not ret:
            cap.release()
            out.release()
            return None

        first_frame = fix_border(first_frame)
        cv2.putText(
            first_frame,
            "Frame: 1",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 255),
            2
        )
        if preview:
            cv2.imshow("Stabilizing Preview", first_frame)
        out.write(first_frame)

        if preview and cv2.waitKey(1) & 0xFF == 27:
            cap.release()
            out.release()
            cv2.destroyAllWindows()
            raise VideoProcessingError('Đã dừng xử lý bằng phím Esc. Video chưa hoàn thành; không trả kết quả thành công.')

        cancelled = False
        i = 0
        while True:
            ret, frame = cap.read()
            if not ret or i >= len(transforms_smooth):
                break

            dx, dy, da = transforms_smooth[i]

            dx = np.clip(dx, -50, 50)
            dy = np.clip(dy, -50, 50)
            da = np.clip(da, -0.3, 0.3)

            center = (w // 2, h // 2)

            m = cv2.getRotationMatrix2D(center, np.degrees(da), 1)
            m[0, 2] += dx
            m[1, 2] += dy

            stabilized = cv2.warpAffine(
                frame,
                m,
                (w, h),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REPLICATE
            )

            stabilized = fix_border(stabilized)

            if preview:
                preview_frame = stabilized.copy()
                cv2.putText(
                    preview_frame,
                    f"Frame: {i + 2}/{total_frames}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 255),
                    2
                )

                cv2.imshow("Stabilizing Preview", preview_frame)

            out.write(stabilized)
            print(f"Stabilized: {i + 2}/{total_frames}", end="\r")

            if preview and cv2.waitKey(1) & 0xFF == 27:
                print("\nStopped by user")
                cancelled = True
                break

            i += 1

        print()
        cap.release()
        out.release()
        if preview:
            cv2.destroyAllWindows()
        if cancelled:
            raise VideoProcessingError('Đã dừng xử lý bằng phím Esc. Video chưa hoàn thành; không trả kết quả thành công.')
        print("DONE:", output_path)

        return encode_for_web(output_path, crf=18, preset='slow')

def create_comparison_video(input_path, stabilized_path, output_path): #Tạo video so sánh giữa video gốc và video đã ổn định bằng cách ghép hai video lại với nhau và thêm chú thích
        if os.path.exists(output_path):
            raise VideoProcessingError('Tệp so sánh đã tồn tại; hệ thống không ghi đè dữ liệu cũ.')
        cap1 = cv2.VideoCapture(input_path)
        cap2 = cv2.VideoCapture(stabilized_path)

        if not cap1.isOpened() or not cap2.isOpened():
            cap1.release()
            cap2.release()
            return None

        w = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))

        fps = cap1.get(cv2.CAP_PROP_FPS)
        if fps <= 0 or fps > 60:
            fps = 30

        out = cv2.VideoWriter(
            output_path,
            cv2.VideoWriter_fourcc(*'mp4v'),
            fps,
            (w * 2, h)
        )

        if not out.isOpened():
            cap1.release()
            cap2.release()
            out.release()
            raise VideoProcessingError('OpenCV không mở được VideoWriter để ghi video so sánh.')

        frame_count = 0

        while True:
            ret1, f1 = cap1.read()
            ret2, f2 = cap2.read()

            if not ret1 or not ret2:
                break
            f1 = cv2.resize(f1, (w, h))
            f2 = cv2.resize(f2, (w, h))
            cv2.putText(f1, "Before", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.putText(f2, "After", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            combined = np.hstack((f1, f2))
            # line giữa
            cv2.line(combined, (w, 0), (w, h), (255, 255, 255), 2)
            out.write(combined)
            frame_count += 1
        cap1.release()
        cap2.release()
        out.release()

        if frame_count == 0:
            return None

        return encode_for_web(output_path, crf=23, preset='fast')
def evaluate_videos(input_videos):
    print("\n===== RESULT TABLE =====")
    print("Video | Mean Before | Std Before | Mean After | Std After")
    print("----------------------------------------------------------")

    for idx, input_path in enumerate(input_videos):
        print(f"\nProcessing Video {idx+1}...")

        stabilized_path = f"output_{idx+1}.mp4"

        final_output = stabilize_video(input_path, stabilized_path)

        if final_output is None:
            print(f"Video {idx+1} ERROR")
            continue

        # đo trước
        mean_before, std_before = measure_shakiness(input_path)

        # đo sau
        mean_after, std_after = measure_shakiness(final_output)

        # tránh None
        if mean_before is None: mean_before = 0
        if std_before is None: std_before = 0
        if mean_after is None: mean_after = 0
        if std_after is None: std_after = 0
        # in ra bảng
        print(f"{idx+1}     | {mean_before:.3f}       | {std_before:.3f}      | {mean_after:.3f}      | {std_after:.3f}")
