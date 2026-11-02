"""Strict, shell-free FFmpeg encoding and FFprobe validation."""
import json
import logging
import math
import os
from fractions import Fraction
from pathlib import Path
import shutil
import struct
import subprocess

from django.conf import settings

from .errors import VideoProcessingError

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _setting(name, default):
    return getattr(settings, name, default) if settings.configured else os.environ.get(name, default)


def _run(arguments):
    try:
        return subprocess.run(
            [str(arg) for arg in arguments], check=True, capture_output=True,
            text=True, encoding='utf-8', errors='replace',
            timeout=int(_setting('VIDEO_TOOL_TIMEOUT', 1800)),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
    except subprocess.TimeoutExpired as exc:
        raise VideoProcessingError('Công cụ video vượt thời gian cho phép. Hãy thử video ngắn hơn.') from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        logger.warning('Video tool failed: %s', getattr(exc, 'stderr', str(exc)))
        raise VideoProcessingError('FFmpeg/FFprobe không hoàn tất xử lý. Kiểm tra tệp video và cấu hình công cụ trên máy chủ.') from exc


def resolve_tools():
    executable = '.exe' if os.name == 'nt' else ''
    local = PROJECT_ROOT / 'tools' / 'ffmpeg' / 'bin'
    encoder = str(_setting('FFMPEG_BINARY', '') or os.environ.get('FFMPEG_BINARY', '') or (local / ('ffmpeg' + executable) if (local / ('ffmpeg' + executable)).is_file() else 'ffmpeg'))
    encoder = shutil.which(encoder)
    configured_probe = _setting('FFPROBE_BINARY', '') or os.environ.get('FFPROBE_BINARY', '')
    sibling = Path(encoder).parent / ('ffprobe' + executable) if encoder else None
    probe = shutil.which(str(configured_probe or (sibling if sibling and sibling.is_file() else 'ffprobe')))
    if not encoder or not probe:
        raise VideoProcessingError(
            'Không tìm thấy FFmpeg hoặc FFprobe. Cài FFmpeg Essentials cho Windows, '
            'đặt ffmpeg.exe và ffprobe.exe trong tools/ffmpeg/bin, hoặc cấu hình '
            'FFMPEG_BINARY và FFPROBE_BINARY rồi khởi động lại Django. Xem README.md.'
        )
    _run([encoder, '-version'])
    _run([probe, '-version'])
    if 'libx264' not in _run([encoder, '-hide_banner', '-encoders']).stdout:
        raise VideoProcessingError('Bản FFmpeg này không hỗ trợ libx264. Hãy cài bản có bộ mã hóa H.264 libx264.')
    return encoder, probe


def probe_video(path, *, probe=None):
    if not probe:
        _, probe = resolve_tools()
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise VideoProcessingError('Tệp video không tồn tại hoặc không có dữ liệu.')
    result = _run([
        probe, '-v', 'error', '-select_streams', 'v:0', '-count_frames',
        '-show_streams', '-show_format', '-of', 'json', path,
    ])
    try:
        data = json.loads(result.stdout)
        stream = data['streams'][0]
        count = int(stream['nb_read_frames'])
        width, height = int(stream['width']), int(stream['height'])
        fps = float(Fraction(stream.get('avg_frame_rate', '0/1')))
        declared = stream.get('nb_frames')
        if declared and declared != 'N/A' and int(declared) != count:
            raise VideoProcessingError('Số frame giải mã không khớp thông tin video; tệp có thể bị thiếu hoặc hỏng.')
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise VideoProcessingError('Không đọc được đầy đủ thông tin hoặc các frame của video.') from exc
    if result.stderr.strip() or count < 1 or width < 1 or height < 1 or not math.isfinite(fps):
        raise VideoProcessingError('Video bị lỗi, không có frame hợp lệ hoặc thông tin FPS không hợp lệ.')
    return {
        'codec': stream.get('codec_name'), 'pixel_format': stream.get('pix_fmt'),
        'width': width, 'height': height, 'fps': fps, 'frame_count': count,
        'duration_seconds': count / fps if fps > 0 else None,
        'size_bytes': path.stat().st_size,
    }


def has_faststart(path):
    """Inspect top-level MP4 boxes without loading video payload into memory."""
    locations = {}
    with Path(path).open('rb') as stream:
        end = Path(path).stat().st_size
        position = 0
        while position + 8 <= end:
            stream.seek(position)
            size, kind = struct.unpack('>I4s', stream.read(8))
            header = 8
            if size == 1:
                raw = stream.read(8)
                if len(raw) != 8:
                    return False
                size, header = struct.unpack('>Q', raw)[0], 16
            if size == 0:
                size = end - position
            if size < header or position + size > end:
                return False
            locations[kind] = position
            position += size
    return b'moov' in locations and b'mdat' in locations and locations[b'moov'] < locations[b'mdat']


def validate_output(path, expected, *, probe=None, browser=True):
    actual = probe_video(path, probe=probe)
    for key in ['width', 'height', 'frame_count']:
        if actual[key] != expected[key]:
            raise VideoProcessingError(f'Video đầu ra không hợp lệ: {key} không khớp với kết quả cần xuất.')
    if not math.isclose(actual['fps'], expected['fps'], rel_tol=1e-4, abs_tol=0.01):
        raise VideoProcessingError('FPS video đầu ra không khớp với quá trình xử lý.')
    if browser:
        if actual['codec'] != 'h264' or actual['pixel_format'] != 'yuv420p' or not has_faststart(path):
            raise VideoProcessingError('Video đầu ra chưa đạt yêu cầu H.264, yuv420p và faststart.')
    return actual


def encode_for_web(path, *, crf=18, preset='slow'):
    encoder, probe = resolve_tools()
    source = probe_video(path, probe=probe)
    if source['width'] % 2 or source['height'] % 2:
        raise VideoProcessingError('Kích thước khung hình phải là số chẵn để xuất yuv420p; hệ thống không tự đổi kích thước video.')
    output = Path(path).with_name(Path(path).stem + '_fixed.mp4')
    _run([
        encoder, '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
        '-i', path, '-map', '0:v:0', '-an', '-c:v', 'libx264',
        '-crf', str(crf), '-preset', preset, '-pix_fmt', 'yuv420p',
        '-fps_mode', 'passthrough', '-movflags', '+faststart', output,
    ])
    validate_output(output, source, probe=probe)
    return str(output)
