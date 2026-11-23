"""Persistent intent and bounded reconciliation for the two private RTSP publishers."""

from functools import lru_cache
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import socket
from threading import Thread
from time import sleep

from django.contrib.admin.models import CHANGE, LogEntry
from django.db import close_old_connections, transaction
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from config.access import request_role, user_role
from . import camera_registry
from .cameras import CameraConflict, camera_json, last_run, recent_frame, scheduler_lock, start_camera, stop_camera, status_for
from .models import CameraLabControl, CameraRun


logger = logging.getLogger(__name__)
CONTROL_ID = 1
RETRY_SECONDS = 30
SLOTS = ("lab-cam-01", "lab-cam-02")
MAX_MEDIA_BYTES = 100 * 1024**3


class LabAdministrator(BasePermission):
    def has_permission(self, request, view):
        return request_role(request) == "administrator"


def candidates(inventory=None):
    inventory = camera_registry.inventory() if inventory is None else inventory
    return {id_: item for id_, item in inventory.items() if camera_registry.automatic(item)}


def intent(control, inventory):
    if not control:
        return {}
    return {id_: control.cameras.get(id_, True) for id_ in inventory}


def marker(id_):
    if id_ not in SLOTS:
        raise ValueError("Slot inválido")
    return Path(os.environ["OPERIX_CAMERA_LAB_CONTROL_DIR"]) / (id_ + ".lease")


@lru_cache(maxsize=8)
def checked_hash(path, size, modified, inode):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def approved_media(camera):
    source = camera.provenance or {}
    name, digest, fps = source.get("filename"), source.get("sha256"), source.get("fps")
    if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,126}\.mp4", name)
            or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
            or source.get("real") is not True or not source.get("license")
            or type(fps) not in (int, float) or not camera.expected_fps <= fps <= 240):
        raise ValueError("El archivo carece de procedencia autorizada o su FPS es inferior al perfil.")
    root = Path(os.environ["OPERIX_CAMERA_LAB_MANIFEST"]).resolve().parent
    path = root / name
    if path.is_symlink() or not path.is_file():
        raise ValueError("El archivo autorizado no está disponible.")
    details = path.stat()
    if (not 0 < details.st_size <= MAX_MEDIA_BYTES
            or checked_hash(path, details.st_size, details.st_mtime_ns, details.st_ino) != digest):
        raise ValueError("El archivo autorizado no coincide con el inventario.")
    return name, digest


def rtsp_ready(id_=None):
    # The target and paths are fixed by the Compose network. No redirects or
    # network destinations from a request/manifest are accepted.
    if id_ is not None and id_ not in SLOTS:
        return False
    uri = "rtsp://mediamtx:8554" + (f"/{id_}" if id_ else "/")
    method = "DESCRIBE" if id_ else "OPTIONS"
    try:
        with socket.create_connection(("mediamtx", 8554), timeout=.35) as peer:
            peer.sendall(f"{method} {uri} RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\n\r\n".encode("ascii"))
            with peer.makefile("rb") as response:
                return response.readline(96).startswith(b"RTSP/1.0 200 ")
    except OSError:
        return False


def update_lease(id_, media):
    lease = marker(id_)
    if media is None:
        lease.unlink(missing_ok=True)
        return
    data = " ".join(media) + "\n"
    scratch = lease.with_suffix(".tmp")
    scratch.write_text(data, encoding="ascii")
    scratch.chmod(0o644)
    scratch.replace(lease)


def issued_lease(id_, media):
    try:
        return marker(id_).read_text(encoding="ascii").split() == list(media)
    except (OSError, UnicodeError):
        return False


@transaction.atomic
def reconcile():
    scheduler_lock()
    control = CameraLabControl.objects.select_related("updated_by").filter(pk=CONTROL_ID).first()
    authorized = bool(control and control.enabled and control.updated_by and user_role(control.updated_by) == "administrator")
    inventory = candidates()
    desired = intent(control, inventory) if authorized else {}
    for id_ in SLOTS:
        camera = inventory.get(id_)
        run = last_run(id_, lock=True)
        state, _, _ = status_for(run)
        # A legacy/manual process in a camera slot remains under its original control.
        if not desired.get(id_) or (run and run.active and not run.managed):
            update_lease(id_, None)
            if run and run.managed:
                stop_camera(run)
            continue
        try:
            media = approved_media(camera)
        except (KeyError, OSError, ValueError):
            update_lease(id_, None)
            if run and run.managed:
                stop_camera(run)
            continue
        if run and run.active:
            if run.provenance.get("sha256") != media[1]:
                update_lease(id_, None)
                stop_camera(run)
            else:
                update_lease(id_, media)
            continue
        if run and run.provenance.get("sha256") != media[1] and not issued_lease(id_, media):
            # Wait for the old publisher to release the slot before authorizing
            # a different file. A new worker must not see it under the new hash.
            update_lease(id_, None if rtsp_ready(id_) else media)
            continue
        update_lease(id_, media)
        if run and state == "error" and (now() - (run.ended_at or run.started_at)).total_seconds() < RETRY_SECONDS:
            continue
        if rtsp_ready(id_):
            try:
                start_camera(camera, control.updated_by, managed=True)
            except (CameraConflict, ValidationError):
                # Capacity or invalid spatial setup is shown as partial. The
                # intent is retained and reconciliation retries after recovery.
                pass


def start_reconciler():
    if not camera_registry.managed():
        return

    def loop():
        while True:
            close_old_connections()
            try:
                reconcile()
            except Exception:
                logger.exception("No se pudo reconciliar el laboratorio virtual")
            finally:
                close_old_connections()
            sleep(2.0)

    Thread(target=loop, daemon=True, name="operix-camera-lab").start()


def describe(request):
    available = camera_registry.managed()
    inventory = candidates()
    control = CameraLabControl.objects.filter(pk=CONTROL_ID).select_related("updated_by").first() if available else None
    enabled = bool(control and control.enabled)
    desired = intent(control, inventory)
    rows, publishers = [], {}
    rtsp = available and rtsp_ready()
    for id_, camera in inventory.items():
        row = camera_json(request, camera)
        live = rtsp and rtsp_ready(id_)
        slot_enabled = desired.get(id_, True)
        publishers[id_] = "publishing" if live else "idle"
        detail = None
        if enabled and slot_enabled:
            try:
                approved_media(camera)
                if not live:
                    publishers[id_] = "starting" if rtsp else "error"
            except (ValueError, OSError, KeyError):
                publishers[id_] = "error"
                detail = "Compruebe el archivo, la licencia, la huella y la cadencia del inventario."
        rows.append({**row, "enabled": slot_enabled, "problem": detail})
    selected = [row for row in rows if row["enabled"]]
    active = [row for row in selected if row["status"] == "analyzing" and publishers[row["id"]] == "publishing"
              and recent_frame(row)]
    if not enabled:
        running = CameraRun.objects.filter(active=True, managed=True).exists() or "publishing" in publishers.values()
        state = "stopping" if running else "disabled"
    elif selected and len(active) == len(selected):
        state = "active"
    elif (not selected or not rtsp or active or any(row["status"] in {"error", "reconnecting", "overloaded"}
          or publishers[row["id"]] == "error" for row in selected)):
        state = "partial"
    else:
        state = "starting"
    return {"available": available, "enabled": enabled, "status": state,
            "capacity": min(2, camera_registry.capacity()), "cameras": rows,
            "publisher": publishers, "mediamtx": "ready" if rtsp else "unavailable",
            "updated_by": control.updated_by.get_username() if control and control.updated_by_id else None}


class CameraLabControlView(APIView):
    permission_classes = [LabAdministrator]

    def get(self, request):
        return Response(describe(request))

    @transaction.atomic
    def patch(self, request):
        if not camera_registry.managed():
            raise CameraConflict("El despliegue no incluye el supervisor virtual.")
        body = request.data
        if not isinstance(body, dict) or not body or body.keys() - {"enabled", "cameras"}:
            raise ValidationError("Envíe el estado global o los estados por cámara.")
        updates = body.get("cameras", {})
        if (not isinstance(updates, dict) or updates.keys() - candidates().keys()
                or any(type(value) is not bool for value in updates.values())
                or ("enabled" in body and type(body["enabled"]) is not bool)):
            raise ValidationError("Estado o identificador de cámara inválido.")
        scheduler_lock()
        control, _ = CameraLabControl.objects.get_or_create(pk=CONTROL_ID)
        control.cameras = {**control.cameras, **updates}
        control.enabled = body.get("enabled", control.enabled)
        control.updated_by = request.user
        control.save()
        LogEntry.objects.log_actions(user_id=request.user.pk, queryset=[control], action_flag=CHANGE,
                                     change_message=json.dumps({"enabled": control.enabled, "cameras": updates}))
        return Response(describe(request), status=202)
