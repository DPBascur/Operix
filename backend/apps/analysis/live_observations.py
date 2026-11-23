"""Expose the current worker's bounded, read-only overlay observations."""

import json
import os
from time import time_ns

from django.http import Http404
from rest_framework.views import APIView

from config.access import CanAnalyze

from . import camera_registry
from .cameras import last_run, playback_clock_id, run_dir
from .live_video import relay_reply


MAX_BYTES = 512 * 1024
MAX_AGE_NS = 1_500_000_000


class CameraLiveObservationsView(APIView):
    permission_classes = [CanAnalyze]

    def get(self, request, camera_id):
        camera = camera_registry.inventory().get(camera_id)
        if (camera is None or not camera_registry.automatic(camera)
                or os.environ.get("OPERIX_CAMERA_LAB_LIVE_ENABLED") != "1"):
            raise Http404
        run = last_run(camera.id)
        if run is None or not run.active or not run.managed:
            return relay_reply(status=204)
        try:
            with (run_dir(run.pk) / "overlay.json").open("rb") as stream:
                age = time_ns() - os.fstat(stream.fileno()).st_mtime_ns
                if not 0 <= age < MAX_AGE_NS:
                    return relay_reply(status=204)
                body = stream.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                return relay_reply(status=204)
            observations = json.loads(body)
        except (OSError, ValueError, RecursionError):
            return relay_reply(status=204)
        if (not isinstance(observations, dict) or observations.get("run_id") != str(run.pk)
                or not isinstance(observations.get("items"), list) or len(observations["items"]) > 64):
            return relay_reply(status=204)
        if os.environ.get("OPERIX_CAMERA_LAB_FRAME_CLOCK") == "1":
            token = run.playback.get("token")
            if not token or observations.get("stream_id") != playback_clock_id(token):
                return relay_reply(status=204)
        after = request.query_params.get("after", "")
        if (request.query_params.get("run_id") == observations["run_id"]
                and after.isascii() and after.isdigit() and len(after) <= 12):
            index = int(after)
            observations["items"] = [item for item in observations["items"]
                                     if isinstance(item, dict) and type(item.get("index")) is int and item["index"] > index]
            body = json.dumps(observations, separators=(",", ":")).encode("utf-8")
        return relay_reply(body, content_type="application/json")
