"""Orchestrate one upload without changing the stabilization mathematics."""
import json
from pathlib import Path
import re
from time import perf_counter
from uuid import uuid4

from django.conf import settings

from .analysis import analyze_motion, chart_samples, std_reduction
from .encoding import probe_video, resolve_tools, validate_output
from .errors import ResultNotReady, VideoProcessingError


def validate_job_id(job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r'[0-9a-f]{32}', job_id):
        raise VideoProcessingError('Mã tác vụ video không hợp lệ.')
    return job_id


def process_upload(upload, *, job_id=None):
    from ..stabilizer import create_comparison_video, stabilize_video

    start = perf_counter()
    job_id = validate_job_id(job_id) if job_id is not None else uuid4().hex
    timings = {}

    def timed(label, function, *args, **kwargs):
        stage = perf_counter()
        value = function(*args, **kwargs)
        timings[label] = perf_counter() - stage
        return value

    _, probe = timed('tools_seconds', resolve_tools)
    if upload.size == 0:
        raise VideoProcessingError('Tệp video đang trống. Hãy chọn một video khác.')
    root = Path(settings.MEDIA_ROOT)
    for folder in ['input', 'output']:
        (root / folder).mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.name).suffix.lower()
    if suffix not in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.mpeg', '.mpg', '.wmv', '.3gp', '.mts', '.m2ts', '.ogv'}:
        suffix = '.video'
    input_path = root / 'input' / f'input_{job_id}{suffix}'
    output_path = root / 'output' / f'output_{job_id}.mp4'
    compare_path = root / 'output' / f'compare_{job_id}.mp4'
    stage = perf_counter()
    with input_path.open('xb') as stream:
        for chunk in upload.chunks():
            stream.write(chunk)
    timings['save_upload_seconds'] = perf_counter() - stage
    source = timed('input_validation_seconds', probe_video, input_path, probe=probe)
    if source['frame_count'] < 2:
        raise VideoProcessingError('Video cần ít nhất 2 frame để giảm rung.')
    if source['width'] % 2 or source['height'] % 2:
        raise VideoProcessingError('Chiều rộng và chiều cao video phải là số chẵn. Hệ thống giữ nguyên kích thước, không tự cắt thêm hoặc thêm viền.')
    before = timed('before_analysis_seconds', analyze_motion, input_path)
    if len(before['frames']) + 1 != source['frame_count']:
        raise VideoProcessingError('OpenCV và FFprobe đọc được số frame khác nhau trong video gốc.')
    result = timed('stabilize_and_encode_seconds', stabilize_video, str(input_path), str(output_path), preview=False)
    if not result:
        raise VideoProcessingError('Thuật toán không tạo được video đầu ra. Hãy kiểm tra tệp rồi thử lại.')
    expected = {**source, 'fps': source['fps'] if 0 < source['fps'] <= 60 else 30}
    output = timed('output_validation_seconds', validate_output, result, expected, probe=probe)
    after = timed('after_analysis_seconds', analyze_motion, result)
    if len(after['frames']) != len(before['frames']):
        raise VideoProcessingError('Số mẫu chuyển động trước/sau không khớp; không thể báo hoàn thành.')
    comparison_result = timed('comparison_and_encode_seconds', create_comparison_video, str(input_path), result, str(compare_path))
    if not comparison_result:
        raise VideoProcessingError('Không tạo được video so sánh hoàn chỉnh.')
    comparison = timed('comparison_validation_seconds', validate_output, comparison_result, {**expected, 'width': source['width'] * 2}, probe=probe)
    score = std_reduction(before['std'], after['std'])
    timings['total_processing_seconds'] = perf_counter() - start
    report = {
        'schema_version': 1, 'job_id': job_id, 'original_name': upload.name,
        'source': source, 'output': output, 'comparison': comparison,
        'before': before, 'after': after, 'std_reduction_percent': score,
        'timings': timings,
        'measurement_note': 'Mean dense image flow, not isolated camera shake or overall visual quality. Timings exclude network transfer and response rendering.',
    }
    sidecar = root / 'output' / f'analysis_{job_id}.json'
    with sidecar.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)

    return result_context(root, input_path, result, comparison_result, sidecar, report)


def result_context(root, input_path, result, comparison_result, sidecar, report):
    before, after = report['before'], report['after']

    def media_url(path):
        return settings.MEDIA_URL.rstrip('/') + '/' + Path(path).relative_to(root).as_posix()

    return {
        'input_video': media_url(input_path), 'output_video': media_url(result),
        'compare_video': media_url(comparison_result), 'analysis_url': media_url(sidecar),
        'before_mean': before['mean'], 'before_std': before['std'],
        'after_mean': after['mean'], 'after_std': after['std'], 'score': report['std_reduction_percent'],
        'processing_report': report,
        'chart_data': {'before': chart_samples(before), 'after': chart_samples(after), 'sample_count': len(before['frames'])},
    }


def load_result(job_id):
    """Recover one actual completed job, without rerunning OpenCV or encoding."""
    job_id = validate_job_id(job_id)
    root = Path(settings.MEDIA_ROOT)
    sidecar = root / 'output' / f'analysis_{job_id}.json'
    try:
        with sidecar.open(encoding='utf-8') as stream:
            report = json.load(stream)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        # A sidecar can briefly be observed while its initial write completes.
        raise ResultNotReady from exc
    if report.get('schema_version') != 1 or report.get('job_id') != job_id:
        raise VideoProcessingError('Dữ liệu kết quả không khớp mã tác vụ.')
    inputs = list((root / 'input').glob(f'input_{job_id}.*'))
    if len(inputs) != 1:
        raise VideoProcessingError('Không tìm thấy đúng video gốc của tác vụ này.')
    result = root / 'output' / f'output_{job_id}_fixed.mp4'
    comparison = root / 'output' / f'compare_{job_id}_fixed.mp4'
    for path, metadata in [(inputs[0], report['source']), (result, report['output']), (comparison, report['comparison'])]:
        if not path.is_file() or path.stat().st_size != metadata['size_bytes']:
            raise VideoProcessingError('Tệp của kết quả đã lưu bị thiếu hoặc đã thay đổi. Hệ thống không hiển thị kết quả không đầy đủ.')
    return result_context(root, inputs[0], result, comparison, sidecar, report)
