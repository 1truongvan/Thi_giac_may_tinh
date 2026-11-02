"""Failure handling and preservation tests for production video processing."""
import ast
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2
import numpy as np
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from video.services.analysis import analyze_motion, chart_samples, std_reduction
from video.services.encoding import _run, encode_for_web, probe_video, resolve_tools, validate_output
from video.services.errors import VideoProcessingError
from video.services.processing import process_upload
from video.stabilizer import measure_shakiness, stabilize_video, create_comparison_video


class RealSampleCase(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        directory = TemporaryDirectory(prefix='steady_real_sample_')
        cls.addClassCleanup(directory.cleanup)
        cls.sample = Path(directory.name) / 'sample.mp4'
        # A fixed original source keeps the golden reference independent of
        # subsequently uploaded UUID filenames or failed uploads.
        source = settings.BASE_DIR / 'media/input/input_1775465623.mp4'
        capture = cv2.VideoCapture(str(source))
        writer = cv2.VideoWriter(str(cls.sample), cv2.VideoWriter_fourcc(*'mp4v'), 24, (160, 96))
        if not writer.isOpened():
            capture.release()
            raise RuntimeError('Cannot create regression sample')
        try:
            for _ in range(12):
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError('Source has fewer than 12 frames')
                writer.write(cv2.resize(frame, (160, 96)))
        finally:
            capture.release()
            writer.release()


class AnalysisTests(RealSampleCase):
    def test_zero_after_std_is_valid_and_zero_before_is_undefined(self):
        self.assertEqual(std_reduction(2, 0), 100.0)
        self.assertEqual(std_reduction(2, 3), -50.0)
        self.assertIsNone(std_reduction(0, 0))
        for before, after in [(None, 1), (1, float('nan')), (float('inf'), 0), (1, -1)]:
            self.assertIsNone(std_reduction(before, after))

    def test_single_frame_does_not_return_nan(self):
        with TemporaryDirectory(prefix='steady_single_') as directory:
            file = Path(directory) / 'single.mp4'
            writer = cv2.VideoWriter(str(file), cv2.VideoWriter_fourcc(*'mp4v'), 24, (160, 96))
            self.assertTrue(writer.isOpened())
            writer.write(np.zeros((96, 160, 3), dtype=np.uint8))
            writer.release()
            self.assertEqual(measure_shakiness(str(file)), (None, None))
            with self.assertRaises(VideoProcessingError):
                analyze_motion(file)

    def test_analysis_matches_original_measurement_on_real_video(self):
        sample = self.sample
        mean, std = measure_shakiness(str(sample))
        analysis = analyze_motion(sample)
        self.assertEqual(float(mean), analysis['mean'])
        self.assertEqual(float(std), analysis['std'])
        self.assertTrue(all(math.isfinite(x) for x in analysis['magnitude']))
        self.assertEqual(len(analysis['frames']), len(analysis['dx']))

    def test_downsampling_keeps_actual_samples_and_endpoints(self):
        original = {key: list(range(2000)) for key in ['frames', 'dx', 'dy', 'magnitude']}
        sampled = chart_samples(original)
        self.assertEqual(len(sampled['frames']), 1500)
        self.assertEqual(sampled['frames'][0], 0)
        self.assertEqual(sampled['frames'][-1], 1999)
        for frame, value in zip(sampled['frames'], sampled['dx']):
            self.assertEqual(value, original['dx'][frame])
        self.assertEqual(len(original['frames']), 2000)

    def test_nonfinite_flow_cannot_be_persisted_as_valid_analysis(self):
        with patch('video.services.analysis.cv2.calcOpticalFlowFarneback', return_value=np.full((96, 160, 2), np.nan, dtype=np.float32)):
            with self.assertRaises(VideoProcessingError):
                analyze_motion(self.sample)


class FailureTests(RealSampleCase):
    @override_settings(FFMPEG_BINARY='missing-steady-ffmpeg.exe', FFPROBE_BINARY='missing-steady-ffprobe.exe')
    def test_missing_tools_are_explicit_and_no_upload_is_saved(self):
        with TemporaryDirectory(prefix='steady_missing_') as directory, override_settings(MEDIA_ROOT=Path(directory)):
            response = self.client.post('/workspace/', {'video': SimpleUploadedFile('a.mp4', b'not empty')})
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.context['output_video'])
            self.assertContains(response, 'FFMPEG_BINARY')
            self.assertNotContains(response, 'data-result-player')
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_missing_probe_does_not_silently_succeed(self):
        encoder, _ = resolve_tools()
        with override_settings(FFMPEG_BINARY=encoder, FFPROBE_BINARY='missing-steady-probe.exe'):
            with self.assertRaises(VideoProcessingError):
                resolve_tools()

    def test_actual_corrupted_upload_has_error_and_no_result(self):
        with TemporaryDirectory(prefix='steady_broken_') as directory, override_settings(MEDIA_ROOT=Path(directory)):
            response = self.client.post('/workspace/', {'video': SimpleUploadedFile('broken.mp4', b'not a video')})
            self.assertTrue(response.context['error_message'])
            self.assertIsNone(response.context['output_video'])
            self.assertNotContains(response, 'data-result-player')
            self.assertEqual(len(list((Path(directory) / 'input').iterdir())), 1)

    def test_process_timeout_and_nonzero_exit_are_actionable(self):
        for exception in [subprocess.TimeoutExpired(['ffmpeg'], 1), subprocess.CalledProcessError(1, ['ffmpeg'], stderr='encoding failed')]:
            with self.subTest(exception=type(exception).__name__), patch('video.services.encoding.subprocess.run', side_effect=exception):
                with self.assertRaises(VideoProcessingError):
                    _run(['ffmpeg'])

    def test_empty_upload_is_rejected(self):
        with self.assertRaises(VideoProcessingError):
            process_upload(SimpleUploadedFile('empty.mp4', b''))

    def test_existing_output_is_never_overwritten(self):
        with TemporaryDirectory(prefix='steady_existing_') as directory:
            path = Path(directory) / 'old.mp4'
            path.write_bytes(b'keep old data')
            with self.assertRaises(VideoProcessingError):
                stabilize_video('unused', str(path), preview=False)
            with self.assertRaises(VideoProcessingError):
                create_comparison_video('unused', 'unused', str(path))
            self.assertEqual(path.read_bytes(), b'keep old data')

    def test_writer_failure_does_not_encode_or_succeed(self):
        sample = self.sample
        with TemporaryDirectory(prefix='steady_writer_') as directory, patch('video.stabilizer.cv2.VideoWriter') as writer, patch('video.stabilizer.encode_for_web') as encode:
            writer.return_value.isOpened.return_value = False
            with self.assertRaises(VideoProcessingError):
                stabilize_video(str(sample), str(Path(directory) / 'result.mp4'), preview=False)
            writer.return_value.release.assert_called_once()
            encode.assert_not_called()

    def test_comparison_writer_failure_does_not_encode(self):
        with TemporaryDirectory(prefix='steady_compare_writer_') as directory, patch('video.stabilizer.cv2.VideoWriter') as writer, patch('video.stabilizer.encode_for_web') as encode:
            writer.return_value.isOpened.return_value = False
            with self.assertRaises(VideoProcessingError):
                create_comparison_video(str(self.sample), str(self.sample), str(Path(directory) / 'compare.mp4'))
            writer.return_value.release.assert_called_once()
            encode.assert_not_called()

    def test_desktop_cancellation_does_not_report_partial_video_as_success(self):
        with TemporaryDirectory(prefix='steady_cancel_') as directory, patch('cv2.imshow'), patch('cv2.waitKey', return_value=27), patch('cv2.destroyAllWindows'), patch('video.stabilizer.encode_for_web') as encode:
            with self.assertRaises(VideoProcessingError):
                stabilize_video(str(self.sample), str(Path(directory) / 'result.mp4'), preview=True)
            encode.assert_not_called()

    def test_invalid_output_metadata_is_rejected(self):
        expected = {'width': 160, 'height': 96, 'frame_count': 12, 'fps': 24}
        valid = {**expected, 'codec': 'h264', 'pixel_format': 'yuv420p'}
        for field, value in [('codec', 'mpeg4'), ('pixel_format', 'yuv444p'), ('frame_count', 11), ('fps', 30), ('width', 158)]:
            with self.subTest(field=field), patch('video.services.encoding.probe_video', return_value={**valid, field: value}), patch('video.services.encoding.has_faststart', return_value=True):
                with self.assertRaises(VideoProcessingError):
                    validate_output('unused', expected)
        with patch('video.services.encoding.probe_video', return_value=valid), patch('video.services.encoding.has_faststart', return_value=False):
            with self.assertRaises(VideoProcessingError):
                validate_output('unused', expected)


class RealEncodingTests(RealSampleCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='steady_encoding_')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_actual_encoder_failure_preserves_existing_file(self):
        raw = self.root / 'test.mp4'
        raw.write_bytes(self.sample.read_bytes())
        fixed = self.root / 'test_fixed.mp4'
        fixed.write_bytes(b'existing data')
        with self.assertRaises(VideoProcessingError):
            encode_for_web(raw)
        self.assertEqual(fixed.read_bytes(), b'existing data')
        self.assertEqual(raw.read_bytes(), self.sample.read_bytes())

    def test_uuid_uploads_keep_both_inputs_results_and_json(self):
        with override_settings(MEDIA_ROOT=self.root):
            first = process_upload(SimpleUploadedFile('same.mp4', self.sample.read_bytes()))
            second = process_upload(SimpleUploadedFile('same.mp4', self.sample.read_bytes()))
        self.assertNotEqual(first['input_video'], second['input_video'])
        self.assertNotEqual(first['output_video'], second['output_video'])
        for result in [first, second]:
            for key in ['input_video', 'output_video', 'compare_video', 'analysis_url']:
                self.assertTrue((self.root / result[key].removeprefix(settings.MEDIA_URL)).is_file())
            report = json.loads((self.root / result['analysis_url'].removeprefix(settings.MEDIA_URL)).read_text(encoding='utf-8'))
            self.assertEqual(report['output']['frame_count'], 12)
            self.assertEqual(report['output']['fps'], 24)


class AlgorithmPreservationTests(RealSampleCase):
    def test_ecc_fallback_gaussian_transforms_and_both_adaptive_branches_are_unchanged(self):
        source = Path(__file__).parent / 'stabilizer.py'
        function = next(node for node in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(node, ast.FunctionDef) and node.name == 'stabilize_video')
        contract = json.loads((source.parent / 'fixtures/algorithm_contract.json').read_text(encoding='utf-8'))
        names = {'cv2.findTransformECC', 'cv2.calcOpticalFlowFarneback', 'gaussian_filter1d', 'np.cumsum', 'np.mean', 'np.abs', 'np.arctan2', 'np.clip', 'cv2.getRotationMatrix2D', 'np.degrees', 'cv2.warpAffine', 'cv2.resize'}
        self.assertEqual(contract['calls'], [ast.dump(node) for node in ast.walk(function) if isinstance(node, ast.Call) and ast.unparse(node.func) in names])
        self.assertEqual(contract['adaptive_branch'], next(ast.dump(node) for node in ast.walk(function) if isinstance(node, ast.If) and ast.unparse(node.test) == 'motion_strength > 5'))
        self.assertEqual(contract['border_function'], next(ast.dump(node) for node in ast.walk(function) if isinstance(node, ast.FunctionDef) and node.name == 'fix_border'))

    def test_core_arrays_and_pre_encoding_frames_match_original(self):
        reference = np.load(Path(__file__).parent / 'fixtures' / 'algorithm_baseline.npz')
        actual = {}

        def capture(frame, event, value):
            if event == 'return' and frame.f_code is stabilize_video.__code__:
                for key in ['transforms', 'trajectory', 'smoothed', 'transforms_smooth', 'motion_strength', 'sigma', 'crop_ratio']:
                    actual[key] = np.array(frame.f_locals[key], copy=True)

        previous_threads = cv2.getNumThreads()
        cv2.setNumThreads(1)
        previous_profile = sys.getprofile()
        try:
            with TemporaryDirectory(prefix='steady_math_regression_') as directory, \
                    patch('video.stabilizer.encode_for_web', side_effect=lambda p, **kwargs: p), \
                    patch('cv2.imshow', side_effect=AssertionError('Preview called')), \
                    patch('cv2.waitKey', side_effect=AssertionError('Keyboard called')), \
                    patch('cv2.destroyAllWindows', side_effect=AssertionError('Desktop called')):
                sys.setprofile(capture)
                try:
                    result = stabilize_video(str(self.sample), str(Path(directory) / 'result.mp4'), preview=False)
                finally:
                    sys.setprofile(previous_profile)
                cap = cv2.VideoCapture(result)
                digest = hashlib.sha256()
                count = 0
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        break
                    digest.update(frame.tobytes())
                    count += 1
                cap.release()
                self.assertEqual(count, 12)
                self.assertEqual(digest.hexdigest(), str(reference['decoded_sha256']))
        finally:
            cv2.setNumThreads(previous_threads)
        for key, value in actual.items():
            np.testing.assert_array_equal(value, reference[key], err_msg=key)
