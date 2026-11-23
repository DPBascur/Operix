"""Authorized, bounded access to the private MediaMTX HLS relay."""

import http.client
from http.cookies import CookieError, SimpleCookie
import os
import re
from threading import BoundedSemaphore
from urllib.parse import urlencode

from django.http import Http404, HttpResponse
from rest_framework.views import APIView

from config.access import CanAnalyze

from . import camera_registry


ASSET = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}\.(m3u8|mp4?)")
MIME = {"m3u8": "application/vnd.apple.mpegurl", "mp4": "video/mp4"}
LIMITS = {"m3u8": 128 * 1024, "mp4": 8 * 1024 * 1024}
# LL-HLS can hold a request while it waits for a part. Keep slots free for
# administration, events and worker publication on the same Django process.
RELAY_SLOTS = BoundedSemaphore(12)
RELAY_SESSIONS = {}
RELAY_SESSION = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def read_relay_session(headers):
    for value in headers.get_all("Set-Cookie", ()):
        cookie = SimpleCookie()
        try:
            cookie.load(value.split(";", 1)[0])
        except CookieError:
            continue
        session = cookie.get("hlsSession")
        if session and RELAY_SESSION.fullmatch(session.value):
            return session.value
    return None


def relay_reply(body=b"", *, status=200, content_type="text/plain"):
    response = HttpResponse(body, status=status, content_type=content_type)
    response["Cache-Control"] = "private, no-store"
    response["Cross-Origin-Resource-Policy"] = "same-origin"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class CameraLiveVideoView(APIView):
    permission_classes = [CanAnalyze]

    def get(self, request, camera_id, asset):
        match = ASSET.fullmatch(asset)
        if not match or os.environ.get("OPERIX_CAMERA_LAB_LIVE_ENABLED") != "1":
            raise Http404
        camera = camera_registry.inventory().get(camera_id)
        # Physical cameras may use private URLs and have no path on this relay.
        if camera is None or not camera_registry.automatic(camera):
            raise Http404
        extension = "m3u8" if match.group(1) == "m3u8" else "mp4"
        master = asset == "index.m3u8"
        # Complete the upstream cookie negotiation internally. The browser only
        # holds its Operix session and never receives a MediaMTX token or redirect.
        session = RELAY_SESSIONS.get(camera.id)
        if not master and not session:
            return relay_reply(status=503)
        headers = {"Cookie": "cookieCheck=1"}
        if not master:
            headers["Cookie"] += f"; hlsSession={session}"
        query = {}
        if master:
            query["cookieCheck"] = "1"
        if extension == "m3u8":
            for key in ("_HLS_msn", "_HLS_part"):
                value = request.query_params.get(key, "")
                if re.fullmatch(r"[0-9]{1,10}", value):
                    query[key] = value
            if request.query_params.get("_HLS_skip") in {"YES", "v2"}:
                query["_HLS_skip"] = request.query_params["_HLS_skip"]
        path = f"/{camera.id}/{asset}"
        if query:
            path += "?" + urlencode(query)

        if not RELAY_SLOTS.acquire(blocking=False):
            return relay_reply(status=503)
        relay = http.client.HTTPConnection("mediamtx", port=8888, timeout=4)
        try:
            relay.request("GET", path, headers=headers)
            with relay.getresponse() as upstream:
                if upstream.status == 404:
                    return relay_reply(status=404)
                if upstream.status != 200:
                    return relay_reply(status=503)
                body = upstream.read(LIMITS[extension] + 1)
                if len(body) > LIMITS[extension]:
                    return relay_reply(status=502)
                if master:
                    new_session = read_relay_session(upstream.headers)
                    if not new_session:
                        return relay_reply(status=503)
                    RELAY_SESSIONS[camera.id] = new_session
                return relay_reply(body, content_type=MIME[extension])
        except (OSError, http.client.HTTPException):
            return relay_reply(status=503)
        finally:
            relay.close()
            RELAY_SLOTS.release()
