"""API de sesiones temporales sin persistencia de video ni eventos."""

from __future__ import annotations

import math
import json
import re
import subprocess
from collections.abc import Mapping

from django.conf import settings
from rest_framework.exceptions import PermissionDenied

from django.http import FileResponse, HttpResponse, StreamingHttpResponse
from rest_framework import status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from config.access import CanAnalyze, request_role
from apps.events.publication import event_publisher_environment

from .sessions import (
    PROFILES, create_demo_session, create_session, get_demo_video, get_session,
    profile_catalog, read_profile, remove_session, start_session, stream_frames,
    local_event_api_url,
)


class AnalysisView(APIView):
    permission_classes = [CanAnalyze]

    def owned_session(self, request, pk):
        session = get_session(pk)
        if session and (request_role(request) == "administrator" or session.owner_id == request.user.pk):
            return session
        return None


class ProfileListView(AnalysisView):
    def get(self, request):
        return Response(profile_catalog())


class DemoSourceView(AnalysisView):
    def get(self, request, profile, source_id):
        try:
            path = get_demo_video(profile, source_id)
        except ValueError:
            return Response({"detail": "Perfil de zona no válido"}, status=400)
        if path is None:
            return Response({"detail": "Fuente demo inexistente"}, status=404)
        return _video_response(request, path, path.name)


class SessionListView(AnalysisView):
    parser_classes = [MultiPartParser, JSONParser]

    def post(self, request):
        if not isinstance(request.data, Mapping):
            return Response({"detail": "Se requiere un objeto con los parámetros del video"}, status=400)
        upload = request.FILES.get("video")
        profile = request.data.get("profile", "")
        if not isinstance(profile, str) or profile not in PROFILES:
            return Response({"detail": "Perfil de zona no válido"}, status=400)
        demo_source_id = request.data.get("demo_source_id")
        try:
            if upload is not None and demo_source_id is None:
                session = create_session(upload, profile, owner_id=request.user.pk)
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
                session = create_demo_session(profile, owner_id=request.user.pk)
            else:
                raise ValueError("Seleccione un video o una fuente demo válida")
        except (ValueError, RuntimeError) as error:
            return Response({"detail": str(error)}, status=400)
        except OSError:
            return Response({"detail": "No se pudo acceder al video o al almacenamiento temporal"}, status=400)
        return Response(session.status(), status=status.HTTP_201_CREATED)


class SessionDetailView(AnalysisView):
    def get(self, request, pk):
        session = self.owned_session(request, pk)
        return Response(session.status()) if session else Response({"detail": "Sesión inexistente"}, status=404)

    def delete(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        remove_session(pk)
        return Response(status=204)


class SessionStopView(AnalysisView):
    def post(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        session.status()
        try:
            session.stop()
        except ValueError as error:
            return Response({"detail": str(error)}, status=409)
        return Response(session.status())


class SessionStartView(AnalysisView):
    def post(self, request, pk):
        session = self.owned_session(request, pk)
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


class SessionPersistenceRetryView(AnalysisView):
    """Solo reenvía snapshots existentes de esta sesión; no ejecuta inferencia."""

    def post(self, request, pk):
        if not settings.EVENT_POST_ENABLED:
            raise PermissionDenied("La publicación no está habilitada.")
        session = self.owned_session(request, pk)
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
                ], capture_output=True, text=True, timeout=120, env=event_publisher_environment())
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


class SessionZoneView(AnalysisView):
    def put(self, request, pk):
        if not isinstance(request.data, Mapping):
            return Response({"detail": "Se requiere un objeto con perfil o polígono"}, status=400)
        session = self.owned_session(request, pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        if session.spatial_revision:
            return Response({"detail":"Edite las zonas desde la configuración espacial versionada."}, status=409)
        if session.status()["state"] not in {"ready", "completed", "cancelled", "error"}:
            return Response({"detail": "La zona no puede editarse mientras se procesa"}, status=409)
        profile = request.data.get("profile")
        if "profile" in request.data and (not isinstance(profile, str) or profile not in PROFILES):
            return Response({"detail": "Perfil de zona no válido"}, status=400)
        if "profile" not in request.data and "polygon" not in request.data:
            return Response({"detail": "Indique perfil o polígono"}, status=400)
        if "polygon" in request.data:
            polygon = request.data["polygon"]
            if not isinstance(polygon, list) or not 3 <= len(polygon) <= 32:
                return Response({"detail": "Se requieren entre 3 y 32 vértices"}, status=400)
            for point in polygon:
                if not isinstance(point, list) or len(point) != 2 or any(
                    type(value) not in (int, float) or not 0 <= value <= 1 or not math.isfinite(value)
                    for value in point
                ):
                    return Response({"detail": "Vértices normalizados inválidos"}, status=400)
            try:
                valid = _motor_accepts_polygon(polygon)
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                return Response({"detail": "El validador de geometría del Motor no está disponible"}, status=503)
            if not valid:
                return Response({"detail": "El polígono debe tener área y lados sin cruces ni solapamientos"}, status=400)
        with session._guard:
            if session._closed or session.state not in {"ready", "completed", "cancelled", "error"}:
                return Response({"detail": "La zona no puede editarse mientras se procesa"}, status=409)
            if session.source_kind == "demo" and profile is not None and profile != session.profile:
                return Response({"detail": "Seleccione la fuente demo correspondiente al perfil"}, status=409)
            if profile is not None and profile != session.profile:
                try:
                    profile_config = read_profile(profile)
                except (OSError, ValueError, KeyError):
                    return Response({"detail": "No se pudo leer la configuración del perfil"}, status=503)
                session.profile = profile
                session.profile_config = profile_config
            if "polygon" in request.data:
                session.zone = {**session.zone, "polygon": polygon}
        return Response(session.status())


def _motor_accepts_polygon(polygon):
    # El Backend nativo y el Motor pueden usar entornos Python distintos.
    validator = """
import json
import sys
from operix_engine.operational_config import Zone
from operix_engine.zone_geometry import NormalizedPoint, point_in_zone

try:
    point_in_zone(NormalizedPoint(0, 0), Zone("session", "Sesión", json.load(sys.stdin)))
except ValueError:
    print("invalid")
else:
    print("valid")
"""
    result = subprocess.run(
        [settings.OPERIX_ENGINE_PYTHON, "-B", "-c", validator],
        input=json.dumps(polygon), capture_output=True, text=True, timeout=5,
    )
    outcome = result.stdout.strip()
    if result.returncode or outcome not in {"valid", "invalid"}:
        raise RuntimeError("No se pudo validar la geometría")
    return outcome == "valid"


class SessionStreamView(AnalysisView):
    def get(self, request, pk):
        session = self.owned_session(request, pk)
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


class SessionSourceView(AnalysisView):
    def get(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        return _video_response(request, session.video_path, session.filename)


class _FileRange:
    def __init__(self, source, start, length):
        self.source = source
        self.source.seek(start)
        self.remaining = length

    def __iter__(self):
        while self.remaining:
            block = self.source.read(min(256 * 1024, self.remaining))
            if not block:
                break
            self.remaining -= len(block)
            yield block

    def close(self):
        self.source.close()


def _video_response(request, path, filename):
    if not path.is_file():
        return Response({"detail": "Video no disponible"}, status=404)
    size = path.stat().st_size
    header = request.headers.get("Range")
    if header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", header)
        if (not match or not any(match.groups())
                or any(len(value) > 20 for value in match.groups())):
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
            _FileRange(path.open("rb"), start, length), status=206, content_type="video/mp4",
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


class SessionResultView(AnalysisView):
    def get(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None:
            return Response({"detail": "Sesión inexistente"}, status=404)
        runs = request.query_params.getlist("run")
        if runs and (len(runs) != 1 or not re.fullmatch(r"[1-9][0-9]{0,19}", runs[0])):
            return Response({"detail": "Identificador de ejecución inválido"}, status=400)
        with session._guard:
            if session._closed or (runs and int(runs[0]) != session.run):
                return Response({"detail": "Ejecución inexistente para esta sesión"}, status=404)
            if session.status()["state"] != "completed":
                return Response({"detail": "El resultado aún no está disponible"}, status=409)
            return _video_response(request, session.directory / "annotated.mp4", "operix-annotated.mp4")
