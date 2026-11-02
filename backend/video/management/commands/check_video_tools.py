from django.core.management.base import BaseCommand, CommandError

from video.services.encoding import resolve_tools
from video.services.errors import VideoProcessingError


class Command(BaseCommand):
    help = 'Verify FFmpeg, FFprobe and the H.264 libx264 encoder.'

    def handle(self, *args, **options):
        try:
            encoder, probe = resolve_tools()
        except VideoProcessingError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS('FFmpeg / FFprobe / libx264: OK'))
        self.stdout.write(f'FFmpeg: {encoder}')
        self.stdout.write(f'FFprobe: {probe}')
