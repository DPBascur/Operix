"""API de sesiones temporales sin persistencia de video ni eventos."""

from __future__ import annotations

import math
import json
import re
import subprocess

from django.conf import settings
from rest_framework.exceptions import PermissionDenied

from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .sessions import (
    PROFILES, create_demo_session, create_session, get_demo_video, get_session,
    profile_catalog, remove_session, start_session, stream_frames,
    local_event_api_url,
)


class ProfileListView(APIView):
    def get(self, request):
        return Response(profile_catalog())


class DemoSourceView(APIView):
    def get(self, request, profile, source_id):
        path = get_demo_video(profile, source_id)
        if path is None:
            return Response({"detail": "Fuente demo inexistente"}, status=404)
        return _video_response(request, path, path.name)


class SessionListView(APIView):
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        upload = request.FILES.get("video")
        profile = request.data.get("profile", "")
        demo_source_id = request.data.get("demo_source_id")
        try:
            if upload is not None and demo_source_id is None:
                session = create_session(upload, profile)
            elif upload is None and isinstance(demo_source_id, str):
                expected = next(
                    (
                        item["default_demo_video"]["id"]
                        for item in profile_catalog()
                        if item["id"] == profile and item["default_demo_video"] is not None
                    ),
                    None,
                )
                if demo_source_id != expected:
                    raise ValueError("La fuente demo no corresponde al perfil")
                session = create_demo_session(profile)
            else:
                raise ValueError("Seleccione un video o una fuente demo válida")
        except (ValueError, RuntimeError) as error:
            return Response({"detail": str(error)}, status=400)
        return Response(session.status(), status=status.HTTP_201_CREATED)


class SessionDetailView(APIView):
    def get(self, request, pk):
        session = get_session(pk)
        return Response(session.status()) if session else Response({"detail": "Sesión inexistente"}, status=404)

    def delete(self, request, pk):
        session = get_session(pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        remove_session(pk)
        return Response(status=204)


class SessionStopView(APIView):
    def post(self, request, pk):
        session = get_session(pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        session.status()
        try:
            session.stop()
        except ValueError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(session.status())


class SessionStartView(APIView):
    def post(self, request, pk):
        session = get_session(pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        try:
            start_session(session)
        except ValueError as error:
            return Response({"detail": str(error)}, status=409)
        except RuntimeError as error:
            return Response({"detail": str(error)}, status=400)
        except OSError:
            return Response({"detail": "No se pudieron preparar los archivos temporales del análisis. Revise espacio y permisos."}, status=400)
        return Response(session.status(), status=202)


class SessionPersistenceRetryView(APIView):
    """Solo reenvía snapshots existentes de esta sesión; no ejecuta inferencia."""

    def post(self, request, pk):
        if not settings.EVENT_POST_ENABLED:
            raise PermissionDenied("La publicación no está habilitada.")
        session = get_session(pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        with session._guard:
            if session.state not in {"completed", "error", "cancelled"} or session.outbox_directory is None:
                return Response({"detail": "Espere al término de un análisis con outbox."}, status=409)
            if session.process is not None and session.process.poll() is None:
                return Response({"detail": "El Motor sigue en ejecución."}, status=409)
            try:
                result = subprocess.run([
                    settings.OPERIX_ENGINE_PYTHON, "-B", "-m", "operix_engine.event_outbox",
                    str(session.outbox_directory), "--api-url", local_event_api_url(),
                ], capture_output=True, text=True, timeout=120)
                summary = json.loads(result.stdout)
                if (not isinstance(summary, dict) or summary.get("state") not in {"saved", "failed"}
                        or (result.returncode == 0) != (summary["state"] == "saved")
                        or any(type(summary.get(key)) is not int or summary[key] < 0 for key in ("candidates", "saved", "failed"))
                        or summary["saved"] + summary["failed"] != summary["candidates"]):
                    raise ValueError("Resumen inválido")
            except (OSError, ValueError, TypeError, RuntimeError, subprocess.TimeoutExpired):
                summary = {"state": "failed", "detail": "No se pudo reenviar el journal; se conserva para revisión."}
            target = session.outbox_directory / "replay-summary.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(summary), encoding="utf-8")
            temporary.replace(target)
        return Response(session.status())


class SessionZoneView(APIView):
    def put(self, request, pk):
        session = get_session(pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        if session.status()["state"] not in {"ready", "completed", "cancelled", "error"}:
            return Response({"detail": "La zona no puede editarse mientras se procesa"}, status=409)
        profile = request.data.get("profile", session.profile)
        if not isinstance(profile, str) or profile not in PROFILES:
            return Response({"detail": "Perfil de zona no válido"}, status=400)
        if "profile" not in request.data and "polygon" not in request.data:
            return Response({"detail": "Indique perfil o polígono"}, status=400)
        zone = (
            json.loads(PROFILES[profile].read_text(encoding="utf-8"))["zones"][0]
            if profile != session.profile else session.zone
        )
        polygon = request.data.get("polygon", zone["polygon"])
        if not isinstance(polygon, list) or not 3 <= len(polygon) <= 32:
            return Response({"detail": "Se requieren entre 3 y 32 vértices"}, status=400)
        for point in polygon:
            if not isinstance(point, list) or len(point) != 2 or any(
                type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
                for value in point
            ):
                return Response({"detail": "Vértices normalizados inválidos"}, status=400)
        with session._guard:
            if session.state not in {"ready", "completed", "cancelled", "error"}:
                return Response({"detail": "La zona no puede editarse mientras se procesa"}, status=409)
            session.profile = profile
            session.zone = {**zone, "polygon": polygon}
        return Response(session.status())


class SessionStreamView(APIView):
    def get(self, request, pk):
        session = get_session(pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        if session.process is None and session.status()["state"] == "ready":
            return Response({"detail": "Inicie la sesión antes de abrir el stream"}, status=409)
        response = StreamingHttpResponse(
            stream_frames(session), content_type="multipart/x-mixed-replace; boundary=frame",
        )
        response["Cache-Control"] = "no-store"
        response["X-Accel-Buffering"] = "no"
        return response


class SessionSourceView(APIView):
    def get(self, request, pk):
        session = get_session(pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        return _video_response(request, session.video_path, session.filename)


def _file_chunks(path, start, length):
    with path.open("rb") as source:
        source.seek(start)
        remaining = length
        while remaining > 0:
            block = source.read(min(256 * 1024, remaining))
            if not block:
                break
            remaining -= len(block)
            yield block


def _video_response(request, path, filename):
    if not path.is_file():
        return Response({"detail": "Video no disponible"}, status=404)
    size = path.stat().st_size
    header = request.headers.get("Range")
    if header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
        if not match or not any(match.groups()):
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            suffix = int(last)
            start, end = max(0, size - suffix), size - 1
        if start >= size or end < start or (not first and suffix == 0):
            response = HttpResponse(status=416)
            response["Content-Range"] = f"bytes */{size}"
            return response
        length = end - start + 1
        response = StreamingHttpResponse(
            _file_chunks(path, start, length), status=206, content_type="video/mp4",
        )
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(length)
    else:
        response = FileResponse(path.open("rb"), content_type="video/mp4")
        response["Content-Length"] = str(size)
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = "private, no-store"
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


class SessionResultView(APIView):
    def get(self, request, pk):
        session = get_session(pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        if session.status()["state"] != "completed":
            return Response({"detail": "El resultado aún no está disponible"}, status=409)
        path = session.directory / "annotated.mp4"
        if not path.is_file():
            return Response({"detail": "Resultado no disponible"}, status=404)
        return _video_response(request, path, "operix-annotated.mp4")
