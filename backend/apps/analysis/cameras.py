"""Authorized monitoring and revision management for the local RTSP lab."""
import atexit
import json
import os
from pathlib import Path
import subprocess
import socket
from urllib.parse import urlsplit
from threading import Lock, Thread
from uuid import uuid4

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.http import FileResponse, Http404
from django.urls import reverse
from django.utils.timezone import now
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
    FORKLIFT_SHA256, PERSON_SHA256, ROOT, config_bytes, frozen_perception, local_event_api_url, rule_snapshot,
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


def last_run(camera_id, *, lock=False):
    query = CameraRun.objects.filter(camera_id=camera_id).order_by("-started_at")
    return (query.select_for_update() if lock else query).first()


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
        return run.terminal_state, metrics, runtime
    if process is None or process.poll() is not None:
        # Compose uses one Django server. Restart terminates its workers and never welds epochs.
        state = state if state in TERMINAL else "error"
        CameraRun.objects.filter(pk=run.pk, active=True).update(
            active=False, terminal_state=state, ended_at=now(), metrics=metrics,
        )
        with _lock:
            _processes.pop(run.pk, None)
        run.active = False
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


def document_for(camera):
    revision = CameraRevision.objects.filter(camera_id=camera.id).order_by("-revision").first()
    return (revision.document, revision.revision) if revision else (default_document(camera), 0)


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
    event = Event.objects.filter(analysis_run_id=run.pk).order_by("-created_at").first() if run else None
    _, policy = effective(camera, document, request.user.pk)
    preview = run_dir(run.pk) / "preview.jpg" if run else None
    return {
        "id": camera.id, "name": camera.name, "description": camera.description,
        "kind": "lab", "provenance": camera.provenance, "profile": camera.profile,
        "expected_fps": camera.expected_fps, "width": camera.width, "height": camera.height,
        "status": state, "metrics": metrics, "configuration": document, "revision": revision,
        "policy": policy, "run_id": str(run.pk) if run else None,
        "preview_url": reverse("lab-camera-preview", args=[camera.id]) if preview and preview.is_file() else None,
        "last_frame_at": runtime.get("last_frame_at") if runtime else None,
        "last_error": (runtime.get("last_error") or runtime.get("termination_reason")) if runtime and state == "error" else None,
        "last_event": {"id": event.id, "event_type": event.event_type,
                       "occurred_at": event.occurred_at} if event else None,
    }


def scheduler_lock():
    # Serializes start/config/stop against every camera, including across request threads.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [1782460449])


def checked_document(camera, document):
    if not isinstance(document, dict) or document.get("view_id") != camera.id:
        raise ValidationError("La configuración debe pertenecer a esta cámara.")
    if document.get("calibration") is not None:
        raise ValidationError("El laboratorio requiere referencias físicas verificadas antes de usar calibración.")
    try:
        return validate_spatial(document, camera.spatial_key, ROOT)
    except ValueError as exc:
        raise ValidationError(str(exc)) from None


class CameraInventoryView(APIView):
    permission_classes = [CanAnalyze]

    def get(self, request):
        return Response({
            "enabled": camera_registry.enabled(), "capacity": camera_registry.capacity(),
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
        camera = self.camera(camera_id)
        body = request.data
        if not isinstance(body, dict) or set(body) != {"revision", "document"} or type(body["revision"]) is not int:
            raise ValidationError("Indique documento y revisión.")
        document = checked_document(camera, body["document"])
        scheduler_lock()
        run = last_run(camera_id, lock=True)
        status_for(run)
        if run is not None and run.active:
            raise CameraConflict("Detenga el monitoreo antes de editar.")
        previous, revision = document_for(camera)
        if body["revision"] != revision:
            raise CameraConflict("Recupere la revisión vigente.")
        previous_rules = {rule["rule_id"]: rule for rule in previous["rules"]}
        versions = {}
        for item in CameraRevision.objects.filter(camera_id=camera_id).values_list("document", flat=True).iterator():
            for rule in item["rules"]:
                versions[rule["rule_id"]] = max(rule["version"], versions.get(rule["rule_id"], 0))
        for rule in document["rules"]:
            old = previous_rules.get(rule["rule_id"])
            changed = (not old or any(old[k] != rule[k] for k in ("enabled", "parameters"))
                       or previous["zones"] != document["zones"] or previous.get("motion") != document.get("motion"))
            version = max(versions.get(rule["rule_id"], 0), old["version"] if old else 0)
            rule["version"] = version + 1 if changed else old["version"]
        CameraRevision.objects.create(camera_id=camera_id, revision=revision + 1,
                                      document=document, updated_by=request.user)
        return Response(camera_json(request, camera))


class CameraStartView(CameraView):
    @transaction.atomic
    def post(self, request, camera_id):
        camera = self.camera(camera_id)
        if request.data not in ({}, None):
            raise ValidationError("La conexión se define en el registro del servidor.")
        worker = ROOT / "engine/scripts/run_rtsp_lab.py"
        if not (camera.provenance and worker.is_file() and settings.EVENT_POST_ENABLED):
            raise CameraConflict("La fuente, su procedencia o el Motor aún no están habilitados.")
        inference_socket = os.environ.get("OPERIX_RTSP_INFERENCE_SOCKET")
        if inference_socket:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(.25)
                    probe.connect(inference_socket)
            except OSError:
                raise CameraConflict("El Motor de inferencia compartida aún no está disponible.") from None
        try:
            parsed = urlsplit(camera.url)
            if parsed.hostname == "mediamtx":
                # Resolve only the fixed Docker DNS name and bind each worker to its IP.
                ip = socket.gethostbyname("mediamtx")
                url = f"rtsp://{ip}:8554/{camera_id}"
            else:
                ip, url = parsed.hostname, camera.url
        except (ValueError, OSError):
            raise CameraConflict("El servidor RTSP interno no está accesible.") from None
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
        document, revision = document_for(camera)
        document, policy = effective(camera, document, request.user.pk)
        checked_document(camera, document)
        run_id = uuid4()
        snapshot = rule_snapshot(document)
        stored = AnalysisRunSnapshot.objects.create(
            pk=run_id, owner=request.user, source_sha256=camera.spatial_key, profile=camera.profile,
            spatial_revision=revision or None, configuration=document, config_sha256=snapshot["config_sha256"],
            policy=policy,
        )
        CameraRun.objects.create(snapshot=stored, camera_id=camera_id, provenance=camera.provenance)
        folder = run_dir(run_id)
        folder.mkdir(parents=True, exist_ok=False)
        config_path = folder / "config.json"
        config_path.write_bytes(config_bytes(document))
        source = {
            "kind": "lab", "camera_id": camera_id, "filename": camera_id + ".mp4",
            "video_sha256": camera.provenance["sha256"], "config_sha256": stored.config_sha256,
            "spatial_configuration": document, "timestamp_basis": "LAB_RECEPTION_UTC",
            "person_weights_sha256": PERSON_SHA256, "forklift_weights_sha256": FORKLIFT_SHA256,
            "perception": frozen_perception(),
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
        with _lock:
            try:
                process = subprocess.Popen([
                    settings.OPERIX_ENGINE_PYTHON, str(worker), "--output", str(folder), "--config", str(config_path),
                    "--fps", str(camera.expected_fps), "--width", str(camera.width), "--height", str(camera.height),
                    "--person-weights", os.environ["OPERIX_PERSON_WEIGHTS"],
                    "--forklift-weights", os.environ["OPERIX_FORKLIFT_WEIGHTS"],
                ], cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _processes[run_id] = process
                Thread(target=reap_run, args=(run_id, process), daemon=True).start()
                transaction.on_commit(lambda: confirm_worker_start(process))
            except (OSError, KeyError):
                CameraRun.objects.filter(pk=run_id).update(active=False, terminal_state="error", ended_at=now())
        data = camera_json(request, camera)
        return Response(data, status=202 if data["status"] != "error" else 503)


class CameraStopView(CameraView):
    @transaction.atomic
    def post(self, request, camera_id):
        camera = self.camera(camera_id)
        scheduler_lock()
        run = last_run(camera_id, lock=True)
        status_for(run)
        if run is not None and run.active:
            stop = run_dir(run.pk) / "stop"
            if not stop.exists():
                stop.touch()
                with _lock:
                    process = _processes.get(run.pk)
                if process is not None:
                    Thread(target=watch_process, args=(process, 20), daemon=True).start()
        return Response(camera_json(request, camera), status=202)


class CameraPreviewView(CameraView):
    def get(self, request, camera_id):
        self.camera(camera_id)
        run = last_run(camera_id)
        try:
            file = (run_dir(run.pk) / "preview.jpg").open("rb") if run else None
        except FileNotFoundError:
            raise Http404 from None
        if file is None:
            raise Http404
        response = FileResponse(file, content_type="image/jpeg")
        response["Cache-Control"] = "private, no-store"
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
        run = CameraRun.objects.filter(pk=run_id, active=True).first()
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
