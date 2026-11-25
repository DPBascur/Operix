"""Read-only playback and thumbnails for the administrator's authorized catalog."""

import os
from pathlib import Path
import subprocess
from tempfile import NamedTemporaryFile
from threading import BoundedSemaphore

from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from .camera_registry import media_registry
from .lab_control import LabAdministrator, checked_hash, media_eligible, registered_media_file, supported_duration
from .views import _video_response


_thumbnail_slots = BoundedSemaphore(2)


class LabMediaView(APIView):
    permission_classes = [LabAdministrator]
    thumbnail = False

    def get(self, request, media_id):
        source = media_registry()[0].get(media_id, {})
        if not source.get("real") or not media_eligible(source, 1) or not supported_duration(source):
            raise Http404
        try:
            path, digest, identity = registered_media_file(source)
            if checked_hash(path, identity) != digest:
                raise Http404
        except (OSError, ValueError, KeyError) as error:
            raise Http404 from error
        if not self.thumbnail:
            return _video_response(request, path, path.name)
        cache = Path(settings.MEDIA_ROOT) / "lab-thumbnails-v1"
        cached = cache / f"{digest}.jpg"
        try:
            if not cached.is_file():
                if not _thumbnail_slots.acquire(timeout=3):
                    return Response(status=503, headers={"Retry-After": "2"})
                try:
                    cache.mkdir(parents=True, exist_ok=True)
                    with NamedTemporaryFile(dir=cache, suffix=".jpg", delete=False) as temporary:
                        output = Path(temporary.name)
                    try:
                        subprocess.run([
                            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                            "-ss", str(min(30, source["duration_s"] * .18)), "-protocol_whitelist", "file",
                            "-f", "mov", "-threads", "1", "-i", str(path), "-t", "3",
                            "-map", "0:v:0", "-filter_threads", "1",
                            "-vf", "fps=4,scale=320:180:force_original_aspect_ratio=decrease,"
                                   "pad=320:180:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                                   "signalstats,metadata=select:key=lavfi.signalstats.YAVG:"
                                   "value=28:function=greater,thumbnail=8",
                            "-frames:v", "1", "-threads", "1", str(output),
                        ], check=True, timeout=12, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if not output.stat().st_size:
                            raise Http404
                        os.replace(output, cached)
                    finally:
                        output.unlink(missing_ok=True)
                finally:
                    _thumbnail_slots.release()
            response = FileResponse(cached.open("rb"), content_type="image/jpeg")
        except (OSError, subprocess.SubprocessError) as error:
            raise Http404 from error
        response["Cache-Control"] = "private, no-store"
        return response
