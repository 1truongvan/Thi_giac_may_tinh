"""Measurements of actual decoded video; never synthesis or quality claims."""
import math

import cv2
import numpy as np

from .errors import VideoProcessingError


def analyze_motion(path):
    cap = cv2.VideoCapture(str(path))
    motions, horizontal, vertical = [], [], []
    try:
        ret, prev = cap.read()
        if not ret:
            raise VideoProcessingError('OpenCV không đọc được video đầu vào.')
        prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Identical parameters and arithmetic to the original measurement.
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0,
            )
            dx = np.mean(flow[..., 0])
            dy = np.mean(flow[..., 1])
            motion = np.sqrt(dx**2 + dy**2)
            if not np.isfinite([dx, dy, motion]).all():
                raise VideoProcessingError('Không tính được số liệu chuyển động hữu hạn cho video này.')
            motions.append(motion)
            horizontal.append(float(dx))
            vertical.append(float(dy))
            prev_gray = gray
    finally:
        cap.release()
    if not motions:
        raise VideoProcessingError('Video cần ít nhất 2 frame đọc được để phân tích và giảm rung.')
    return {
        'method': 'Farneback: mean dense optical flow', 'units': 'pixel/frame',
        'mean': float(np.mean(motions)), 'std': float(np.std(motions)),
        'frames': list(range(2, len(motions) + 2)),
        'dx': horizontal, 'dy': vertical, 'magnitude': [float(value) for value in motions],
    }


def std_reduction(before_std, after_std):
    if not all(value is not None and math.isfinite(value) for value in [before_std, after_std]):
        return None
    if before_std <= 0 or after_std < 0:
        return None
    return round((before_std - after_std) / before_std * 100, 2)


def chart_samples(analysis, limit=1500):
    """Select actual samples for HTML; the sidecar JSON retains every sample."""
    count = len(analysis['frames'])
    indices = np.linspace(0, count - 1, min(count, limit), dtype=int).tolist()
    return {
        key: [analysis[key][index] for index in indices]
        for key in ['frames', 'dx', 'dy', 'magnitude']
    }
