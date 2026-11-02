"""Isolated browser QA server: real processing, disposable media, no GUI patch."""
from pathlib import Path
import os
import sys
from tempfile import TemporaryDirectory
from socketserver import ThreadingMixIn
from wsgiref.simple_server import make_server, WSGIServer

import cv2


class ThreadedServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

project = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application

with TemporaryDirectory(prefix='steady_browser_qa_') as directory:
    source = settings.MEDIA_ROOT / 'input/input_1775465623.mp4'
    sample = Path(directory) / 'qa_sample.mp4'
    cap = cv2.VideoCapture(str(source))
    writer = cv2.VideoWriter(str(sample), cv2.VideoWriter_fourcc(*'mp4v'), 24, (160, 96))
    if not writer.isOpened():
        raise RuntimeError('Cannot create real-video QA extract')
    try:
        for _ in range(12):
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError('Real source video has fewer than 12 frames')
            writer.write(cv2.resize(frame, (160, 96)))
    finally:
        writer.release()
        cap.release()
    settings.MEDIA_ROOT = Path(directory)
    settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
    app = StaticFilesHandler(get_wsgi_application())
    with make_server('127.0.0.1', 8766, app, server_class=ThreadedServer) as server:
        print('QA_READY http://127.0.0.1:8766 (disposable media; real algorithm and FFmpeg)', flush=True)
        server.serve_forever()
