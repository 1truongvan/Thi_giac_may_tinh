class VideoProcessingError(Exception):
    """An actionable processing failure that may be shown to the user."""


class ResultNotReady(Exception):
    """No complete analysis sidecar exists yet for the requested job."""
