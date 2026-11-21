"""Calibration is an explicit review action on a server-owned source."""

import base64
import binascii
from datetime import timedelta
import hashlib
import json
import math
import os
import subprocess
from threading import BoundedSemaphore

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.http import Http404
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .cameras import (CameraConflict, CameraDetailView, CameraView, camera_capture_signature,
                      camera_worker_destination, document_for, last_run, status_for)
from .models import CameraRevision
from .sessions import RESTARTABLE, ROOT
from .sources import latest_spatial
from .spatial import SpatialConfigurationView
from .views import AnalysisView


_capture_slot = BoundedSemaphore(1)
_SIGNING_SALT = "operix.ground-calibration.proposal.v1"
_PROPOSAL_AGE_S = 600


def _proposal_input(body):
    if (not isinstance(body, dict) or set(body) != {"revision", "layout"}
            or type(body["revision"]) is not int or body["revision"] < 0
            or not isinstance(body["layout"], dict)):
        raise ValidationError("Indique revisión, disposición y cómo midió las referencias del suelo.")
    layout = body["layout"]
    if (set(layout) != {"dictionary", "markers", "provenance"}
            or layout["dictionary"] != "DICT_4X4_50"
            or not isinstance(layout["provenance"], str) or not 1 <= len(layout["provenance"].strip()) <= 250
            or not isinstance(layout["markers"], list) or not 3 <= len(layout["markers"]) <= 8):
        raise ValidationError("Declare de tres a ocho marcadores ArUco medidos y su procedencia.")
    markers = []
    for marker in layout["markers"]:
        if (not isinstance(marker, dict) or set(marker) != {"id", "x_m", "y_m", "size_m", "rotation_deg"}
                or type(marker["id"]) is not int or not 0 <= marker["id"] < 50
                or any(type(marker[key]) not in (int, float) or not -10000 <= marker[key] <= 10000
                       for key in ("x_m", "y_m", "size_m", "rotation_deg"))
                or not .01 <= marker["size_m"] <= 20 or not -360 <= marker["rotation_deg"] <= 360):
            raise ValidationError("Revise las coordenadas, el tamaño y el giro medidos de cada marcador.")
        angle = math.radians(marker["rotation_deg"])
        c, s = math.cos(angle), math.sin(angle)
        x, y, side = marker["x_m"], marker["y_m"], marker["size_m"]
        markers.append({"id": marker["id"], "corners_m": [
            [x + side * (dx*c - dy*s), y + side * (dx*s + dy*c)]
            for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1))
        ]})
    if len({marker["id"] for marker in markers}) != len(markers):
        raise ValidationError("Use un ID diferente para cada marcador.")
    return body["revision"], {"dictionary": layout["dictionary"], "markers": markers,
                              "ground_plane_confirmed": True}, layout["provenance"].strip()


def _detect(layout, capture, env=None):
    try:
        payload = json.dumps({"layout": layout, **capture}, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        raise ValidationError("Disposición del patrón inválida.") from None
    if len(payload) > 8192:
        raise ValidationError("La disposición del patrón excede el tamaño permitido.")
    if not _capture_slot.acquire(blocking=False):
        raise CameraConflict("Hay otra captura de calibración en curso. Vuelva a intentar.")
    try:
        process = subprocess.run(
            [settings.OPERIX_ENGINE_PYTHON, "-B", str(ROOT / "engine/scripts/propose_calibration.py"), "propose"],
            input=payload, capture_output=True, encoding="utf-8", timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", **(env or {})},
        )
        if process.returncode or len(process.stdout) > 768_000:
            raise ValueError
        report = json.loads(process.stdout)
        if not isinstance(report, dict):
            raise ValueError
        return report
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise ValidationError("No se pudo leer la fuente o evaluar el patrón. Revise la señal, la resolución y las referencias.") from None
    finally:
        _capture_slot.release()


def _reply(request, binding, revision, layout, provenance, result):
    encoded = result.pop("preview_jpeg", None)
    preview = None
    if isinstance(encoded, str) and len(encoded) <= 720_000:
        try:
            candidate = base64.b64decode(encoded, validate=True)
            if candidate.startswith(b"\xff\xd8\xff"):
                preview = candidate
        except (ValueError, binascii.Error):
            pass
    quality = result.get("quality", {})
    report = {
        "status": result.get("status", "invalid"), "reasons": result.get("reasons", []),
        "usable_polygon": result.get("footprint", []), "grid": result.get("grid", []),
        "expires_at": (now() + timedelta(seconds=_PROPOSAL_AGE_S)).isoformat(),
        "references": [{"id": int(key), "corners": corners}
                       for key, corners in result.get("marker_corners", {}).items()],
        "quality": {"reprojection_error_px": quality.get("max_reprojection_error_px"),
                    "coverage_ratio": result.get("coverage"),
                    "temporal_error_px": quality.get("max_marker_deviation_px"),
                    "condition_number": quality.get("homography_condition"),
                    "sensitivity_m": quality.get("one_pixel_sensitivity_m")},
    }
    if preview:
        report["preview_url"] = "data:image/jpeg;base64," + encoded
    if report["status"] != "candidate" or not preview or not result.get("reference_marker_corners"):
        status = "requires_review" if report["status"] == "candidate" else report["status"]
        return Response({**report, "proposal_id": None, "status": status}, headers={"Cache-Control": "no-store"})
    calibration = {
        "image_points": result["image_points"], "ground_points_m": result["ground_points_m"],
        "pattern_evidence": {
            "dictionary": layout["dictionary"], "layout": layout, "provenance": provenance,
            "width": result["width"], "height": result["height"], "marker_corners": result["reference_marker_corners"],
            "quality": result["quality"], "capture_signature": binding[-1],
            "image_transform": "native_frame",
            "preview_sha256": hashlib.sha256(preview).hexdigest(),
        },
    }
    token = signing.dumps({"owner": request.user.pk, "binding": binding, "revision": revision,
                           "calibration": calibration}, salt=_SIGNING_SALT, compress=True)
    return Response({**report, "proposal_id": token}, headers={"Cache-Control": "no-store"})


def _confirm(request, binding, revision, version, source):
    body = request.data
    consent = {"proposal_id", "revision", "ground_confirmed", "zones_reviewed", "control"}
    if (not isinstance(body, dict) or set(body) != consent or not isinstance(body["proposal_id"], str)
            or len(body["proposal_id"]) > 24_000 or type(body["revision"]) is not int
            or body["ground_confirmed"] is not True or body["zones_reviewed"] is not True
            or not isinstance(body["control"], dict)
            or set(body["control"]) != {"image_points", "distance_m", "tolerance_m", "provenance"}):
        raise ValidationError("Confirme el plano del suelo, revise las zonas e indique una medida de comprobación.")
    try:
        proposal = signing.loads(body["proposal_id"], salt=_SIGNING_SALT, max_age=_PROPOSAL_AGE_S)
    except signing.BadSignature:
        raise ValidationError("La propuesta expiró o es inválida. Capture una nueva.") from None
    if proposal["owner"] != request.user.pk or proposal["binding"] != binding:
        raise ValidationError("La propuesta pertenece a otra fuente o cambió el encuadre configurado.")
    if proposal["revision"] != revision or body["revision"] != revision:
        raise CameraConflict("La configuración cambió. Capture una propuesta para la revisión actual.")
    calibration = proposal["calibration"]
    calibration["pattern_evidence"]["control"] = body["control"]
    return {**calibration, "source_sha256": source, "version": version, "status": "valid", "units": "m",
            "calibrated_at": now().isoformat(), "zones_reviewed": True}


def _live_source(camera):
    ip, url = camera_worker_destination(camera)
    return {
        "OPERIX_RTSP_URL": url, "OPERIX_RTSP_ALLOWED_IP": ip,
        "OPENCV_FFMPEG_CAPTURE_OPTIONS": "rtsp_transport;tcp|probesize;65536|analyzeduration;250000",
    }


class CameraCalibrationView(CameraView):
    confirm = False

    def post(self, request, camera_id):
        camera = self.camera(camera_id)
        run = last_run(camera_id)
        status_for(run)
        if run is not None and run.active:
            raise CameraConflict("Detenga el monitoreo antes de calibrar.")
        document, revision = document_for(camera)
        binding = ["camera", camera.id, camera_capture_signature(camera)]
        if self.confirm:
            with transaction.atomic():
                previous = CameraRevision.objects.filter(camera_id=camera.id).values_list("document", flat=True)
                version = max(((doc.get("calibration") or {}).get("version", 0) for doc in previous), default=0) + 1
                calibration = _confirm(request, binding, revision, version, camera.spatial_key)
                return CameraDetailView().save(request, camera, {
                    "document": {**document, "calibration": calibration}, "revision": revision,
                }, pattern_confirmed=True)
        requested, layout, provenance = _proposal_input(request.data)
        if requested != revision:
            raise CameraConflict("Recupere la revisión vigente antes de capturar.")
        report = _detect(layout, {"width": camera.width, "height": camera.height}, _live_source(camera))
        return _reply(request, binding, revision, layout, provenance, report)


class SessionCalibrationView(AnalysisView):
    confirm = False

    def post(self, request, pk):
        session = self.owned_session(request, pk)
        if session is None or session.owner_id != request.user.pk:
            raise Http404
        with session._guard:
            if session._closed or session.state not in RESTARTABLE or (session.process and session.process.poll() is None):
                raise CameraConflict("Detenga el análisis antes de calibrar.")
            saved = latest_spatial(request.user.pk, session.source_sha256)
            revision = saved.revision if saved else 0
            document = saved.document if saved else session.operational_config()
            if not document["zones"] or any(len(zone["polygon"]) < 3 for zone in document["zones"]):
                raise CameraConflict("Crea y aplica una zona válida antes de calibrar el video.")
            binding = ["session", str(session.id), session.source_sha256]
            if self.confirm:
                calibration = _confirm(request, binding, revision, 1, session.source_sha256)
                return SpatialConfigurationView().save(request, session, {
                    "document": {**document, "calibration": calibration}, "revision": revision,
                }, pattern_confirmed=True)
            requested, layout, provenance = _proposal_input(request.data)
            if requested != revision:
                raise CameraConflict("Recupere la revisión vigente antes de capturar.")
            report = _detect(layout, {"video_path": str(session.video_path)})
            return _reply(request, binding, revision, layout, provenance, report)
