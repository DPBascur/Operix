"""Authorized monitoring and revision management for the local RTSP lab."""
import atexit
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import socket
from urllib.parse import urlsplit
from threading import Lock, Thread
from time import time_ns
from uuid import uuid4

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.timezone import now
from django.utils.crypto import salted_hmac
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.events.models import Event
from apps.events.publication import event_publisher_environment
from config.access import CanAnalyze, request_role
from . import camera_registry
from .catalog import load_catalog, resolve_policy
from .models import AnalysisRunSnapshot, CameraRevision, CameraRun
from .sessions import (
    ROOT, active_perception, config_bytes, local_event_api_url, rule_snapshot,
)
from .validation import validate_spatial

TERMINAL = {"stopped", "error"}
ACTIVE = {"connecting", "transmitting", "analyzing", "no_signal", "reconnecting", "overloaded"}
_lock = Lock()
_processes = {}


class CameraConflict(APIException):
    status_code = 409
    default_detail = "La cámara está ocupada o se alcanzó la capacidad del laboratorio."


def run_dir(run_id):
    return Path(settings.MEDIA_ROOT) / "rtsp-lab" / str(run_id)


def last_run(camera_id, *, lock=False, calibration_sha256=None):
    query = CameraRun.objects.filter(camera_id=camera_id).order_by("-started_at")
    if calibration_sha256 is not None:
        query = query.filter(snapshot__configuration__calibration__sha256=calibration_sha256)
    return (query.select_for_update() if lock else query).first()


def remove_retired_preview(run):
    if not getattr(run, "managed", False) or run.active:
        return
    try:
        (run_dir(run.pk) / "preview.jpg").unlink(missing_ok=True)
    except OSError:
        # An in-flight response can hold the file open on Windows. Reaping or
        # reconciliation can retry without delaying run finalization.
        pass


def status_for(run):
    if run is None:
        return "stopped", {}, None
    folder = run_dir(run.pk)
    runtime = {}
    try:
        path = folder / "status.json"
        if path.stat().st_size <= 256 * 1024:
            runtime = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(runtime, dict):
            runtime = {}
    except (OSError, ValueError):
        pass
    metrics = runtime.get("metrics", run.metrics)
    if not isinstance(metrics, dict):
        metrics = {}
    state = runtime.get("status", runtime.get("state", "connecting"))
    state = {"starting": "connecting", "processing": "analyzing", "completed": "stopped"}.get(state, state)
    with _lock:
        process = _processes.get(run.pk)
    if not run.active:
        remove_retired_preview(run)
        return run.terminal_state, metrics, runtime
    exit_code = process.poll() if process is not None else None
    if process is None or exit_code is not None:
        # Compose uses one Django server. Restart terminates its workers and never welds epochs.
        state = state if state in TERMINAL else "error"
        if getattr(run, "playback", {}) and (process is None or exit_code != 0):
            state = "error"
        with transaction.atomic():
            if CameraRun.objects.filter(pk=run.pk, active=True).update(
                active=False, terminal_state=state, ended_at=now(), metrics=metrics,
            ):
                Event.objects.filter(analysis_run_id=run.pk, evidence_stage=Event.EvidenceStage.PENDING).update(
                    evidence_stage=Event.EvidenceStage.FINISHED,
                )
            else:
                run.refresh_from_db(fields=["terminal_state", "ended_at"])
                state = run.terminal_state
        with _lock:
            _processes.pop(run.pk, None)
        run.active = False
        run.terminal_state = state
        remove_retired_preview(run)
    elif state not in ACTIVE | TERMINAL:
        state = "connecting"
    return state, metrics, runtime


def default_document(camera):
    return {
        "schema_version": 1, "view_id": camera.id, "coordinate_system": "normalized",
        "zones": [{"zone_id": "frame", "name": "Encuadre completo", "purpose": "observation",
                   "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
        "rules": [
            {"rule_id": "lab_presence", "version": 1, "enabled": True,
             "parameters": {"kind": "zone_dwell", "zone_id": "frame", "class_name": "person",
                            "min_duration_s": 2.}},
        ],
    }


def latest_revision(camera):
    return CameraRevision.objects.filter(camera_id=camera.id).order_by("-revision").first()


def document_for(camera):
    revision = latest_revision(camera)
    return (revision.document, revision.revision) if revision else (default_document(camera), 0)


def spatial_capture_issue(camera, document, revision):
    if issue := calibration_issue(camera, document, None, {}):
        return issue
    if ((document["zones"] != default_document(camera)["zones"] or document.get("motion"))
            and (revision is None or revision.capture_signature != camera_capture_signature(camera))):
        return "Las zonas o el movimiento personalizado no están verificados para esta grabación."
    return None


def effective(camera, document, owner_id):
    rules, policy = resolve_policy(load_catalog(owner_id), profile=None, demo_source_id=None,
                                   source_sha256=None, camera_id=camera.id)
    if rules is not None:
        document = {**document, "rules": rules}
    return document, policy


def camera_json(request, camera):
    run = last_run(camera.id)
    state, metrics, runtime = status_for(run)
    document, revision = document_for(camera)
    event = Event.objects.filter(source__kind="lab", source__camera_id=camera.id).only(
        "id", "event_type", "occurred_at",
    ).first()
    _, policy = effective(camera, document, request.user.pk)
    active_snapshot = run.snapshot if run and run.active else None
    capture_camera = replace(camera, provenance=run.provenance) if active_snapshot else camera
    calibration_hash = (document.get("calibration") or {}).get("sha256")
    calibration_run, calibration_metrics = run, metrics
    if run and calibration_hash and (run.snapshot.configuration.get("calibration") or {}).get("sha256") != calibration_hash:
        # A newer uncalibrated run does not clear an invalidation of this revision.
        calibration_run = last_run(camera.id, calibration_sha256=calibration_hash)
        _, calibration_metrics, _ = status_for(calibration_run)
    preview = run_dir(run.pk) / "preview.jpg" if run else None
    if camera_registry.automatic(camera) and (state != "analyzing" or not recent_frame(runtime)):
        preview = None
    view_only = camera_registry.view_only(camera)
    if view_only:
        from .lab_control import CONTROL_ID, publisher_ack
        from .models import CameraLabControl

        control = CameraLabControl.objects.filter(pk=CONTROL_ID).first()
        playback = control.playback.get(camera.id, {}) if control else {}
        playlist = control.playlists.get(camera.id) if control else None
        assigned = bool(playlist.get("media_ids")) if playlist is not None else camera.provenance is not None
        if not control or not control.enabled or not control.cameras.get(camera.id, False):
            state = "stopped"
        elif not assigned:
            state = "available"
        elif playback.get("phase") == "finished":
            state = "stopped"
        elif playback.get("blocked"):
            state = "error"
        elif publisher_ack(camera.id, playback.get("token")) == "playing":
            state = "transmitting"
        else:
            state = "connecting"
        preview = None
    return {
        "id": camera.id, "name": camera.name, "description": camera.description,
        "kind": "lab", "automatic": camera_registry.automatic(camera), "view_only": view_only,
        "provenance": camera_registry.public_provenance(run.provenance if active_snapshot else camera.provenance),
        "profile": camera.profile,
        "expected_fps": camera.expected_fps, "width": camera.width, "height": camera.height,
        "configured_analysis_fps": None if view_only else camera.expected_fps, "configured_source_fps": camera.capture_fps,
        "status": state, "metrics": metrics, "configuration": document, "revision": revision,
        "calibration_requires_reconfirmation": bool(calibration_issue(capture_camera, document, calibration_run, calibration_metrics)),
        "policy": active_snapshot.policy if active_snapshot else policy,
        "effective_rules": active_snapshot.configuration.get("rules", []) if active_snapshot else None,
        "run_id": str(run.pk) if run else None,
        "playback": {key: value for key, value in getattr(run, "playback", {}).items() if key != "token"} or None,
        "preview_url": reverse("lab-camera-preview", args=[camera.id]) if preview and preview.is_file() else None,
        "last_frame_at": runtime.get("last_frame_at") if runtime else None,
        "last_error": (runtime.get("last_error") or runtime.get("termination_reason")) if runtime and state == "error" else None,
        "termination_reason": runtime.get("termination_reason") if runtime else None,
        "last_event": {"id": event.id, "event_type": event.event_type,
                       "occurred_at": event.occurred_at} if event else None,
    }


def recent_frame(runtime):
    timestamp = (runtime or {}).get("last_frame_at")
    try:
        return bool(timestamp and 0 <= (now() - parse_datetime(timestamp)).total_seconds() < 5)
    except (TypeError, ValueError):
        return False


def scheduler_lock():
    # Serializes start/config/stop against every camera, including across request threads.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [1782460449])


def camera_capture_signature(camera):
    source = urlsplit(camera.url)
    identity = [camera.id, source.hostname, source.port or 554, source.path, source.query,
                camera.width, camera.height, (camera.provenance or {}).get("sha256")]
    return salted_hmac("operix.camera-calibration", json.dumps(identity), algorithm="sha256").hexdigest()


def camera_worker_destination(camera):
    parsed = urlsplit(camera.url)
    if parsed.hostname != "mediamtx":
        return parsed.hostname, camera.url
    # Resolve only the fixed Docker DNS name and pin the worker to its IP.
    try:
        ip = socket.gethostbyname("mediamtx")
    except OSError:
        raise CameraConflict("El servidor RTSP interno no está accesible.") from None
    return ip, f"rtsp://{ip}:8554/{camera.id}"


def calibration_issue(camera, document, run, metrics):
    calibration = document.get("calibration")
    if not calibration:
        return None
    if (calibration.get("pattern_evidence") or {}).get("capture_signature") != camera_capture_signature(camera):
        return "Cambió la fuente o el encuadre configurado. Vuelva a calibrar la cámara."
    prior = (run.snapshot.configuration.get("calibration") or {}) if run else {}
    if (prior.get("sha256") == calibration.get("sha256")
            and (metrics.get("framing") or {}).get("state") == "INVALID"):
        return "El encuadre invalidó esta calibración. Confirme una nueva propuesta antes de volver a usarla."
    return None


def checked_document(camera, document):
    if not isinstance(document, dict) or document.get("view_id") != camera.id:
        raise ValidationError("La configuración debe pertenecer a esta cámara.")
    if "equipment_profile" in document:
        raise ValidationError("La categoría de equipo no se puede declarar para toda una cámara RTSP.")
    try:
        checked = validate_spatial(document, camera.spatial_key, ROOT)
    except ValueError as exc:
        raise ValidationError(str(exc)) from None
    calibration = checked.get("calibration")
    if calibration is not None:
        evidence = calibration.get("pattern_evidence")
        if not evidence:
            raise ValidationError("Confirme una propuesta de patrón para esta cámara.")
    return checked


class CameraInventoryView(APIView):
    permission_classes = [CanAnalyze]

    def get(self, request):
        return Response({
            "enabled": camera_registry.enabled(), "capacity": camera_registry.capacity(),
            "managed": camera_registry.managed(),
            "can_edit": request_role(request) in {"administrator", "safety_lead"},
            "cameras": [camera_json(request, camera) for camera in camera_registry.inventory().values()],
        })


class CameraView(APIView):
    permission_classes = [CanAnalyze]

    def camera(self, camera_id):
        camera = camera_registry.inventory().get(camera_id)
        if camera is None:
            raise Http404
        return camera


class CameraDetailView(CameraView):
    def get(self, request, camera_id):
        return Response(camera_json(request, self.camera(camera_id)))

    @transaction.atomic
    def put(self, request, camera_id):
        return self.save(request, self.camera(camera_id), request.data)

    def save(self, request, camera, body, *, pattern_confirmed=False, confirm_capture=None):
        camera_id = camera.id
        if not isinstance(body, dict) or set(body) != {"revision", "document"} or type(body["revision"]) is not int:
            raise ValidationError("Indique documento y revisión.")
        document = checked_document(camera, body["document"])
        scheduler_lock()
        run = last_run(camera_id, lock=True)
        status_for(run)
        if run is not None and run.active and confirm_capture is None:
            raise CameraConflict("Detenga el monitoreo antes de editar.")
        previous, revision = document_for(camera)
        if body["revision"] != revision:
            raise CameraConflict("Recupere la revisión vigente.")
        if confirm_capture is not None and (not pattern_confirmed or
                {k: v for k, v in body["document"].items() if k != "calibration"} !=
                {k: v for k, v in previous.items() if k != "calibration"}):
            raise CameraConflict("Mientras la cámara analiza solo se admite guardar la calibración confirmada.")
        calibration = document.get("calibration")
        prior_calibration = previous.get("calibration")
        if calibration and not pattern_confirmed and calibration != prior_calibration:
            raise ValidationError("Confirme una nueva propuesta de patrón para cambiar la calibración.")
        previous_rules = {rule["rule_id"]: rule for rule in previous["rules"]}
        versions = {}
        for item in CameraRevision.objects.filter(camera_id=camera_id).values_list("document", flat=True).iterator():
            for rule in item["rules"]:
                versions[rule["rule_id"]] = max(rule["version"], versions.get(rule["rule_id"], 0))
        for rule in document["rules"]:
            old = previous_rules.get(rule["rule_id"])
            changed = (not old or any(old[k] != rule[k] for k in ("enabled", "parameters"))
                       or previous["zones"] != document["zones"] or previous.get("motion") != document.get("motion")
                       or prior_calibration != calibration)
            version = max(versions.get(rule["rule_id"], 0), old["version"] if old else 0)
            rule["version"] = version + 1 if changed else old["version"]
        if confirm_capture is not None:
            confirm_capture()
        CameraRevision.objects.create(camera_id=camera_id, revision=revision + 1,
                                      document=document, updated_by=request.user,
                                      capture_signature=camera_capture_signature(camera) if camera.provenance else "")
        return Response(camera_json(request, camera))


class CameraStartView(CameraView):
    @transaction.atomic
    def post(self, request, camera_id):
        camera = self.camera(camera_id)
        if request.data not in ({}, None):
            raise ValidationError("La conexión se define en el registro del servidor.")
        if camera_registry.automatic(camera):
            raise CameraConflict("Esta cámara se controla desde el laboratorio automático.")
        start_camera(camera, request.user)
        data = camera_json(request, camera)
        return Response(data, status=202 if data["status"] != "error" else 503)


def playback_clock_id(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()[:32]


@transaction.atomic
def start_camera(camera, owner, *, managed=False, playback=None):
    try:
        perception = active_perception()
    except ValueError as error:
        raise CameraConflict(str(error)) from None
    camera_id = camera.id
    worker = ROOT / "engine/scripts/run_rtsp_lab.py"
    if not (camera.provenance and worker.is_file() and settings.EVENT_POST_ENABLED):
        raise CameraConflict("La fuente, su procedencia o el Motor aún no están habilitados.")
    inference_socket = os.environ.get("OPERIX_RTSP_INFERENCE_SOCKET")
    if inference_socket:
        if os.environ.get("OPERIX_DETECTOR_PROFILE") == "unified-v7":
            raise CameraConflict("UNIFIED V7 requiere un worker dedicado")
        try:
            if not hasattr(socket, "AF_UNIX"):
                raise OSError("AF_UNIX no está disponible")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                probe.settimeout(.25)
                probe.connect(inference_socket)
        except OSError:
            raise CameraConflict("El Motor de inferencia compartida aún no está disponible.") from None
    ip, url = camera_worker_destination(camera)
    scheduler_lock()
    active = 0
    for run in CameraRun.objects.filter(active=True).select_for_update():
        status_for(run)
        if run.active:
            if run.camera_id == camera_id:
                raise CameraConflict("Esta cámara ya tiene una ejecución.")
            active += 1
    if active >= camera_registry.capacity():
        raise CameraConflict()
    saved = latest_revision(camera)
    document = saved.document if saved else default_document(camera)
    revision = saved.revision if saved else 0
    document, policy = effective(camera, document, owner.pk)
    issue = spatial_capture_issue(camera, document, saved)
    if issue:
        # Keep the saved revision and policy for traceability. Freeze only safe geometry in this run.
        document = default_document(camera)
        document["zones"][0]["enabled"] = False
        document["rules"] = []
        if playback:
            playback = {**playback, "spatial_suspension_reason": issue}
    checked_document(camera, document)
    if calibration := document.get("calibration"):
        # A run with suspended spatial rules must not clear a prior framing invalidation.
        last = last_run(camera_id, calibration_sha256=calibration["sha256"])
        _, metrics, _ = status_for(last)
        if issue := calibration_issue(camera, document, last, metrics):
            raise CameraConflict(issue)
    run_id = uuid4()
    snapshot = rule_snapshot(document)
    stored = AnalysisRunSnapshot.objects.create(
        pk=run_id, owner=owner, source_sha256=camera.provenance["sha256"] if playback else camera.spatial_key,
        profile=camera.profile,
        spatial_revision=revision or None, configuration=document, config_sha256=snapshot["config_sha256"],
        policy=policy,
    )
    CameraRun.objects.create(snapshot=stored, camera_id=camera_id, provenance=camera.provenance,
                             managed=managed, playback=playback or {})
    folder = run_dir(run_id)
    folder.mkdir(parents=True, exist_ok=False)
    config_path = folder / "config.json"
    config_path.write_bytes(config_bytes(document))
    filename = camera.provenance["filename"] if managed else camera_id + ".mp4"
    source = {
        "kind": "lab", "camera_id": camera_id, "filename": filename,
        "video_sha256": camera.provenance["sha256"], "config_sha256": stored.config_sha256,
        "spatial_configuration": document, "timestamp_basis": "LAB_RECEPTION_UTC",
        "person_weights_sha256": perception["person"]["weights_sha256"],
        "forklift_weights_sha256": perception["forklift"]["weights_sha256"],
        "perception": perception,
        "session_id": str(run_id), "session_run": 1,
        **({"spatial_revision": revision} if revision else {}),
    }
    (folder / "context.json").write_text(json.dumps({
        "analysis_run_id": str(run_id), "analysis_started_at": now().isoformat(), "source": source,
    }), encoding="utf-8")
    env = event_publisher_environment()
    env.update(OPERIX_RTSP_URL=url, OPERIX_RTSP_ALLOWED_IP=ip, OPERIX_EVENT_API_BASE_URL=local_event_api_url(),
               OPERIX_MEDIA_ROOT=str(settings.MEDIA_ROOT),
               OPERIX_RTSP_LAB_CAMERA_ID=camera.id, OPERIX_WORKER_PARENT_PIPE="1")
    if managed:
        env["OPERIX_RTSP_LAB_MANAGED_PREVIEW"] = "1"
        if playback and os.environ.get("OPERIX_CAMERA_LAB_FRAME_CLOCK") == "1":
            env["OPERIX_RTSP_LAB_FRAME_CLOCK_ID"] = playback_clock_id(playback["token"])
    with _lock:
        try:
            process = subprocess.Popen([
                settings.OPERIX_ENGINE_PYTHON, str(worker), "--output", str(folder), "--config", str(config_path),
                "--fps", str(camera.expected_fps), "--source-fps", str(camera.capture_fps),
                "--width", str(camera.width), "--height", str(camera.height),
                "--person-weights", os.environ["OPERIX_PERSON_WEIGHTS"],
                "--forklift-weights", os.environ["OPERIX_FORKLIFT_WEIGHTS"],
            ], cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _processes[run_id] = process
            Thread(target=reap_run, args=(run_id, process), daemon=True).start()
            transaction.on_commit(lambda: confirm_worker_start(process))
        except (OSError, KeyError):
            CameraRun.objects.filter(pk=run_id).update(active=False, terminal_state="error", ended_at=now())
    return run_id


def stop_camera(run):
    status_for(run)
    if run is None or not run.active:
        return
    stop = run_dir(run.pk) / "stop"
    if not stop.exists():
        stop.touch()
        with _lock:
            process = _processes.get(run.pk)
        if process is not None:
            Thread(target=watch_process, args=(process, 20), daemon=True).start()


class CameraStopView(CameraView):
    @transaction.atomic
    def post(self, request, camera_id):
        camera = self.camera(camera_id)
        if camera_registry.automatic(camera):
            raise CameraConflict("Esta cámara se controla desde el laboratorio automático.")
        scheduler_lock()
        stop_camera(last_run(camera_id, lock=True))
        return Response(camera_json(request, camera), status=202)


class CameraPreviewView(CameraView):
    def get(self, request, camera_id):
        camera = self.camera(camera_id)
        run = last_run(camera_id)
        runtime = None
        if camera_registry.automatic(camera):
            state, _, runtime = status_for(run)
            if state != "analyzing" or not recent_frame(runtime):
                raise Http404
        try:
            file = (run_dir(run.pk) / "preview.jpg").open("rb") if run else None
        except FileNotFoundError:
            raise Http404 from None
        if file is None:
            raise Http404
        age_ms = None
        if (runtime or {}).get("metrics", {}).get("preview_clock_basis") == "local_receive_mtime":
            age_ms = (time_ns() - os.fstat(file.fileno()).st_mtime_ns) / 1e6
            if not 0 <= age_ms < 5000:
                file.close()
                raise Http404
        response = FileResponse(file, content_type="image/jpeg")
        response["Cache-Control"] = "private, no-store"
        if age_ms is not None:
            response["Server-Timing"] = f"preview-receive-age;dur={age_ms:.1f}"
        return response


def watch_process(process, seconds):
    try:
        process.wait(timeout=seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def confirm_worker_start(process):
    # La primera publicación requiere que el snapshot sea visible en otra conexión.
    try:
        process.stdin.write(b"\x01")
        process.stdin.flush()
    except (OSError, ValueError):
        pass  # El reaper recoge el proceso aunque haya terminado antes del commit.


def reap_run(run_id, process):
    watch_process(process, 1900)
    if process.stdin is not None:
        process.stdin.close()
    close_old_connections()
    try:
        run = CameraRun.objects.filter(pk=run_id).first()
        if run is not None:
            status_for(run)
    finally:
        with _lock:
            _processes.pop(run_id, None)
        close_old_connections()


@atexit.register
def stop_workers():
    with _lock:
        for run_id, process in _processes.items():
            if process.poll() is None:
                process.terminate()
