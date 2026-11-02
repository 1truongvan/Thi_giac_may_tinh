"""Regression checks for the directory split, without touching project data.

Integration tests process a short extract from an existing input video using the
real algorithm and real FFmpeg. Desktop GUI calls fail the test if invoked.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import cv2

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import get_template
from django.test import Client, SimpleTestCase, override_settings
from django.urls import resolve, reverse

from video import views


class ProjectLayoutTests(SimpleTestCase):
    def test_database_and_media_still_point_to_project_root(self):
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(settings.BASE_DIR, root)
        self.assertEqual(Path(settings.DATABASES['default']['NAME']), root / 'db.sqlite3')
        self.assertEqual(settings.MEDIA_ROOT, root / 'media')

    def test_templates_are_loaded_from_frontend(self):
        for name in ['home.html', 'workspace.html']:
            self.assertEqual(
                Path(get_template(name).origin.name),
                settings.FRONTEND_DIR / 'templates' / name,
            )

    def test_frontend_static_discovery(self):
        with TemporaryDirectory(prefix='stabilizer_static_') as directory:
            asset = Path(directory) / 'probe.css'
            asset.write_text('body { color: navy; }', encoding='utf-8')
            with override_settings(STATICFILES_DIRS=[directory]):
                self.assertEqual(Path(finders.find('probe.css')), asset)
        self.assertIn(settings.FRONTEND_DIR / 'static', settings.STATICFILES_DIRS)

    def test_home_links_to_workspace(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/workspace/"')
        self.assertNotContains(response, '<video')

    def test_workspace_initial_state_has_upload_and_no_result(self):
        self.assertEqual(resolve('/workspace/').func, views.workspace)
        response = self.client.get(reverse('workspace'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="video"')
        self.assertIsNone(response.context['output_video'])
        self.assertNotContains(response, '<video')

    def test_post_without_file_keeps_legacy_behavior(self):
        for url in ['/', '/workspace/']:
            with self.subTest(url=url):
                response = self.client.post(url)
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.context['output_video'])

    def test_csrf_protection_remains_enabled(self):
        client = Client(enforce_csrf_checks=True)
        for url in ['/', '/workspace/']:
            self.assertEqual(client.post(url).status_code, 403)


class RealVideoUploadTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        sources = [settings.BASE_DIR / 'media/input/input_1775465623.mp4']
        sources = [source for source in sources if source.is_file()]
        if not sources:
            from unittest import SkipTest
            raise SkipTest('An existing real input video is required')
        with TemporaryDirectory(prefix='stabilizer_sample_') as directory:
            sample = Path(directory) / 'sample.mp4'
            cap = cv2.VideoCapture(str(sources[0]))
            writer = cv2.VideoWriter(
                str(sample), cv2.VideoWriter_fourcc(*'mp4v'), 24, (160, 96),
            )
            count = 0
            try:
                if not writer.isOpened():
                    raise RuntimeError('Cannot create MP4 regression sample')
                for _ in range(12):
                    ok, frame = cap.read()
                    if not ok:
                        break
                    writer.write(cv2.resize(frame, (160, 96)))
                    count += 1
            finally:
                cap.release()
                writer.release()
            if count < 2:
                raise RuntimeError('Existing input video has too few readable frames')
            cls.sample_bytes = sample.read_bytes()
            cls.frame_count = count

    def check_real_upload(self, url):
        with TemporaryDirectory(prefix='stabilizer_upload_') as directory:
            with override_settings(MEDIA_ROOT=Path(directory)), \
                    patch('cv2.imshow', side_effect=AssertionError('Desktop preview called')), \
                    patch('cv2.waitKey', side_effect=AssertionError('Desktop keyboard called')), \
                    patch('cv2.destroyAllWindows', side_effect=AssertionError('Desktop cleanup called')):
                response = self.client.post(url, {
                    'video': SimpleUploadedFile(
                        'real_sample.mp4', self.sample_bytes, content_type='video/mp4',
                    ),
                })
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, 'workspace.html')
                for key, width in [('input_video', 160), ('output_video', 160), ('compare_video', 320)]:
                    media_url = response.context[key]
                    self.assertTrue(media_url, key)
                    self.assertTrue(media_url.startswith(settings.MEDIA_URL))
                    path = Path(directory) / media_url.removeprefix(settings.MEDIA_URL)
                    self.assertTrue(path.is_file())
                    if key == 'input_video':
                        self.assertEqual(path.read_bytes(), self.sample_bytes)
                    cap = cv2.VideoCapture(str(path))
                    try:
                        self.assertTrue(cap.isOpened())
                        self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), self.frame_count)
                        self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), width)
                        self.assertTrue(cap.read()[0])
                    finally:
                        cap.release()
                for key in ['before_mean', 'before_std', 'after_mean', 'after_std']:
                    self.assertIsNotNone(response.context[key])
                self.assertContains(response, response.context['output_video'])
                self.assertContains(response, 'data-motion-chart="magnitude"')
                self.assertContains(response, 'data-motion-chart="dx"')
                self.assertContains(response, 'data-motion-chart="dy"')
                import json
                from video.services.encoding import has_faststart, probe_video
                report_path = Path(directory) / response.context['analysis_url'].removeprefix(settings.MEDIA_URL)
                report = json.loads(report_path.read_text(encoding='utf-8'))
                self.assertEqual(report['output']['codec'], 'h264')
                self.assertEqual(report['output']['pixel_format'], 'yuv420p')
                self.assertEqual(len(report['before']['frames']), self.frame_count - 1)
                self.assertEqual(len(report['after']['frames']), self.frame_count - 1)
                self.assertGreater(report['timings']['total_processing_seconds'], 0)
                for key in ['output_video', 'compare_video']:
                    path = Path(directory) / response.context[key].removeprefix(settings.MEDIA_URL)
                    self.assertTrue(has_faststart(path))
                    self.assertEqual(probe_video(path)['codec'], 'h264')

    def test_real_upload_to_workspace(self):
        self.check_real_upload('/workspace/')

    def test_legacy_root_upload_still_processes_video(self):
        self.check_real_upload('/')

    def test_existing_media_is_served(self):
        from django.views.static import serve
        from django.test import RequestFactory
        # URL patterns for development media are only installed with DEBUG=True.
        # Call the same serving view directly because Django's test runner sets
        # DEBUG=False, while ensuring the production media root stays unchanged.
        sample = sorted((settings.MEDIA_ROOT / 'input').glob('*.mp4'))[0]
        response = serve(
            RequestFactory().get(settings.MEDIA_URL + 'input/' + sample.name),
            'input/' + sample.name, document_root=settings.MEDIA_ROOT,
        )
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(int(response['Content-Length']), sample.stat().st_size)
        finally:
            response.close()


class FrontendPresentationTests(SimpleTestCase):
    def test_frontend_assets_can_be_found(self):
        for asset in [
            'css/site.css', 'css/workspace.css', 'js/site.js', 'js/workspace.js', 'js/analysis.js',
            'images/icons.svg', 'images/favicon.svg',
            'images/demo-before.jpg', 'images/demo-after.jpg',
        ]:
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset))

    def test_result_is_absent_until_backend_supplies_output(self):
        response = self.client.get('/workspace/')
        self.assertNotContains(response, 'data-result-player')
        self.assertNotContains(response, 'class="download-button"')
        self.assertContains(response, 'data-upload-form')
        self.assertContains(response, 'Tự động thích ứng')

    def test_zero_and_negative_measurements_are_not_hidden(self):
        # Template edge cases only; these fixtures are never served as results.
        template = get_template('components/result.html')
        context = {
            'output_video': '/media/output/test.mp4',
            'before_mean': 0.0, 'after_mean': 0.0,
            'before_std': 0.0, 'after_std': 0.0, 'score': 0.0,
        }
        zero = template.render(context)
        self.assertIn('0.0000', zero)
        self.assertNotIn('Không đủ dữ liệu', zero)
        negative = template.render({**context, 'score': -12.5})
        self.assertIn('score-negative', negative)
        self.assertIn('-12.50', negative)
        unavailable = template.render({**context, 'score': None})
        self.assertIn('Không đủ dữ liệu', unavailable)

    def test_home_uses_local_assets_and_real_example_posters(self):
        response = self.client.get('/')
        self.assertContains(response, 'Sửa Video Rung')
        self.assertContains(response, 'images/demo-before.jpg')
        self.assertContains(response, 'images/demo-after.jpg')
        self.assertContains(response, 'Khung hình trước / sau từ video thật')
        self.assertNotContains(response, 'cdn.jsdelivr.net')
        self.assertContains(response, 'id="faq"')
