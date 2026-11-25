"""Persistent intent and bounded reconciliation for the private RTSP publishers."""

from dataclasses import replace
from functools import lru_cache
import hashlib
import json
import logging
import os
from pathlib import Path
import socket
import stat
from threading import Thread
from time import sleep, time
from uuid import uuid4

from django.contrib.admin.models import CHANGE, LogEntry
from django.db import close_old_connections, transaction
from django.utils.timezone import now
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from config.access import request_role, user_role
from . import camera_registry
from .cameras import (
    CameraConflict, camera_json, last_run, recent_frame, scheduler_lock,
    start_camera, stop_camera, status_for,
)
from .models import CameraLabControl, CameraRun


logger = logging.getLogger(__name__)
CONTROL_ID = 1
MAX_RETRY_SECONDS = 30
MAX_RETRY_ATTEMPTS = 6
STABLE_PLAYBACK_SECONDS = 30
RECONCILE_SECONDS = .5
SLOTS = camera_registry.SLOTS
MAX_MEDIA_BYTES = 100 * 1024**3
MAX_PLAYLIST_ITEMS = 64
LEASE_SECONDS = 12
START_SECONDS = 60
# Short clips can end while a dedicated model is still loading. Longer
# recordings retain the low-latency publisher-first handoff.
PREWARM_CLIP_SECONDS = 30
# The engine has a hard 1,800-second ceiling. Leave time to detect EOF and drain.
MAX_CLIP_SECONDS = 1740
DURATION_LIMIT = f"El medio requiere una duración verificada de hasta {MAX_CLIP_SECONDS} segundos. Retírelo o divídalo en clips autorizados."
DURATION_EXCEEDED = "El medio alcanzó el límite del Motor. Verifique su duración real y retírelo o divídalo en clips autorizados."


class LabAdministrator(BasePermission):
    def has_permission(self, request, view):
        return request_role(request) == "administrator"


class MediaRejected(ValueError):
    """A media validation error safe to report to administrators."""


def candidates(inventory=None):
    inventory = camera_registry.inventory() if inventory is None else inventory
    return {id_: item for id_, item in inventory.items() if camera_registry.automatic(item)}


def intent(control, inventory):
    if not control:
        return {}
    return {id_: control.cameras.get(id_, id_ != camera_registry.THIRD_SLOT) for id_ in inventory}


def marker(id_):
    if id_ not in SLOTS:
        raise ValueError("Slot inválido")
    return Path(os.environ["OPERIX_CAMERA_LAB_CONTROL_DIR"]) / (id_ + ".lease")


def ack_path(id_):
    if id_ not in SLOTS:
        raise ValueError("Slot inválido")
    return Path(os.environ["OPERIX_CAMERA_LAB_ACK_DIR"]) / id_ / "status"


def file_identity(stat_result):
    return (stat_result.st_dev, stat_result.st_ino, stat_result.st_size,
            stat_result.st_mtime_ns, stat_result.st_ctime_ns)


@lru_cache(maxsize=128)
def checked_hash(path, identity):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        opened_identity = file_identity(opened)
        # Windows reports different ctime semantics for the path and the open handle.
        if not stat.S_ISREG(opened.st_mode) or opened_identity[:4] != identity[:4]:
            raise MediaRejected("El archivo cambió durante la verificación.")
        digest = hashlib.sha256()
        remaining = opened.st_size
        while remaining:
            chunk = stream.read(min(1024**2, remaining))
            if not chunk:
                raise MediaRejected("El archivo cambió durante la verificación.")
            digest.update(chunk)
            remaining -= len(chunk)
        if (stream.read(1) or file_identity(os.fstat(stream.fileno())) != opened_identity
                or file_identity(path.lstat()) != identity):
            raise MediaRejected("El archivo cambió durante la verificación.")
        return digest.hexdigest()


def media_eligible(source, capture_fps):
    name, digest, fps = source.get("filename"), source.get("sha256"), source.get("fps")
    license_ = source.get("license")
    synthetic_test = (os.environ.get("OPERIX_CAMERA_LAB_ALLOW_SYNTHETIC") == "1"
                      and source.get("footage") == "synthetic validation video")
    return (isinstance(name, str) and camera_registry.MEDIA_FILENAME.fullmatch(name)
            and isinstance(digest, str) and camera_registry.SHA256.fullmatch(digest)
            and (source.get("real") is True or synthetic_test) and isinstance(license_, str) and bool(license_.strip())
            and type(fps) in (int, float) and capture_fps <= fps <= 240)


def supported_duration(source):
    duration = source.get("duration_s")
    return type(duration) in (int, float) and 0 < duration <= MAX_CLIP_SECONDS


def media_file(camera):
    source = camera.provenance or {}
    if not media_eligible(source, camera.capture_fps):
        raise MediaRejected("El archivo carece de procedencia autorizada o su FPS es inferior al de captura configurado.")
    if not supported_duration(source):
        raise MediaRejected(DURATION_LIMIT)
    return registered_media_file(source)


def registered_media_file(source):
    name, digest = source["filename"], source["sha256"]
    root = Path(os.environ["OPERIX_CAMERA_LAB_MANIFEST"]).resolve().parent
    path = root / name
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or not 0 < details.st_size <= MAX_MEDIA_BYTES:
        raise MediaRejected("El archivo autorizado no está disponible.")
    return path, digest, file_identity(details)


def camera_at_playlist_start(camera):
    """A stopped managed camera starts from its first assigned recording."""
    if not camera_registry.automatic(camera):
        return camera
    control = CameraLabControl.objects.filter(pk=CONTROL_ID).first()
    catalog, defaults = camera_registry.media_registry()
    playlists = configured_playlists(control, {camera.id: camera}, defaults)
    ids = playlists[camera.id]["media_ids"]
    source = catalog.get(ids[0]) if ids else None
    return replace(camera, provenance={**source, "media_id": ids[0]} if source else None)


def approved_media(camera):
    # PATCH verifies before taking the scheduler lock. During reconciliation
    # the publisher hashes its opened descriptor before reporting frame output.
    path, digest, identity = media_file(camera)
    if checked_hash(path, identity) != digest:
        raise MediaRejected("El archivo autorizado no coincide con el inventario.")
    return path.name, digest


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


def publisher_ack(id_, token):
    try:
        with ack_path(id_).open("rb") as stream:
            age = time() - os.fstat(stream.fileno()).st_mtime
            fields = stream.read(128).decode("ascii").split()
        if len(fields) == 2 and fields[0] == token:
            state = fields[1]
            if state in {"eof", "failed", "expired"} or (0 <= age < LEASE_SECONDS and state in {"idle", "playing"}):
                return state
    except (KeyError, OSError, UnicodeError):
        pass
    return None


def configured_playlists(control, inventory, defaults):
    saved = control.playlists if control else {}
    return {id_: saved.get(id_, {"media_ids": [defaults[id_]] if id_ in defaults else [], "repeat": True})
            for id_ in inventory}


def playlist_signature(playlist, catalog):
    sources = [(id_, catalog.get(id_)) for id_ in playlist["media_ids"]]
    return hashlib.sha256(json.dumps([sources, playlist["repeat"]], sort_keys=True).encode()).hexdigest()


def valid_playlist_position(progress, playlist):
    position = progress.get("position")
    return type(position) is int and 0 <= position < len(playlist["media_ids"])


def new_attempt(signature, position=0, cycle=0, last=None, *, failures=0):
    delay = min(MAX_RETRY_SECONDS, 2 ** (failures - 1)) if failures else 0
    return {"signature": signature, "position": position, "cycle": cycle, "last_transition": last,
            "phase": "idle", "token": uuid4().hex, "retry_at": time() + delay if delay else 0,
            "failures": failures}


def release_to_attempt(id_, signature, position=0, cycle=0, last=None, *, failures=0):
    attempt = new_attempt(signature, position, cycle, last, failures=failures)
    update_lease(id_, (attempt["token"], "idle"))
    return attempt


def next_item(playlist, position, cycle):
    if position + 1 < len(playlist["media_ids"]):
        return position + 1, cycle
    if playlist["repeat"]:
        return 0, cycle + 1
    return None


def breadcrumb(outcome, reason, playback=None):
    data = playback or {}
    return {"outcome": outcome, "reason": reason, "at": now().isoformat(),
            **{key: data[key] for key in ("media_id", "source_sha256", "position", "cycle") if key in data}}


def drain(run, transition):
    if run.active:
        if run.playback and "stop_requested" not in run.playback:
            run.playback = {**run.playback, "stop_requested": transition}
            run.save(update_fields=["playback"])
        stop_camera(run)


def seal_playback(run, state, runtime):
    if not run.playback:
        return None
    if "transition" not in run.playback:
        requested = run.playback.get("stop_requested")
        if requested and state == "stopped" and (runtime or {}).get("termination_reason") == "OPERATOR_STOP":
            transition = requested
        else:
            reason = ("duration_exceeded" if (runtime or {}).get("termination_reason") == "TIME_LIMIT"
                      else "worker_drain_failed" if requested else "worker_exited")
            transition = breadcrumb("interrupted", reason, run.playback)
        run.playback = {**run.playback, "transition": transition}
        run.save(update_fields=["playback"])
    return run.playback["transition"]


def reconcile_slot(id_, camera, playlist, catalog, progress, run, owner):
    state, metrics, runtime = status_for(run)
    if run and not run.managed and run.active:
        update_lease(id_, None)
        return {}
    if playlist is None or not playlist["media_ids"]:
        update_lease(id_, None)
        if run and run.managed:
            if run.active:
                drain(run, breadcrumb("expected", "disabled", run.playback))
            else:
                seal_playback(run, state, runtime)
        return {}

    view_only = camera_registry.view_only(camera)
    if view_only and run and run.active:
        drain(run, breadcrumb("expected", "view_only", run.playback))
        return progress
    signature = playlist_signature(playlist, catalog)
    stale = progress.get("signature") != signature or not valid_playlist_position(progress, playlist)
    if run and run.active and (stale or run.playback.get("token") != progress.get("token")):
        # Keep the prior publisher unchanged during the drain, if its lease still exists.
        try:
            previous = marker(id_).read_text(encoding="ascii").split()
            if (len(previous) == 4 and previous[0] == run.playback.get("token") and previous[1] == "play"
                    and previous[2:] == [run.provenance.get("filename"), run.provenance.get("sha256")]):
                update_lease(id_, previous)
        except (OSError, UnicodeError):
            pass
        drain(run, breadcrumb("expected", "playlist_changed", run.playback))
        return progress

    transition = seal_playback(run, state, runtime) if run and run.managed and not run.active else None
    if stale:
        return release_to_attempt(id_, signature, last=transition or progress.get("last_transition"))
    if progress["phase"] in {"finished", "duration_blocked"}:
        return progress
    token, position = progress["token"], progress["position"]
    media_id = playlist["media_ids"][position]
    source = catalog.get(media_id) or {}
    selected = replace(camera, provenance={**source, "media_id": media_id})
    playback = {"token": token, "media_id": media_id, "source_sha256": source.get("sha256"),
                "position": position, "cycle": progress["cycle"]}
    ack = publisher_ack(id_, token)
    failures = progress.get("failures", 0)
    if view_only and progress.get("view_started"):
        if ack == "eof":
            transition = breadcrumb("expected", "media_eof", playback)
            upcoming = next_item(playlist, position, progress["cycle"])
            if upcoming is not None:
                return release_to_attempt(id_, signature, *upcoming, transition)
            update_lease(id_, None)
            return {**progress, "phase": "finished", "last_transition": transition}
        if ack != "playing":
            transition = breadcrumb("interrupted", "publisher_interrupted", playback)
            return release_to_attempt(id_, signature, position, progress["cycle"], transition,
                                      failures=min(failures + 1, MAX_RETRY_ATTEMPTS))
    if not view_only and run and run.playback.get("token") == token:
        if run.active:
            if run.playback.get("stop_requested"):
                if pending := progress.get("pending"):
                    update_lease(id_, (pending["token"], "idle"))
                stop_camera(run)
            elif progress["phase"] in {"warming", "launching"}:
                phase = progress["phase"]
                if time() - progress["launch_at"] >= START_SECONDS or ack in {"failed", "expired", "eof"}:
                    update_lease(id_, None)
                    reason = "worker_startup_timeout" if phase == "warming" else "publisher_startup_failed"
                    drain(run, breadcrumb("interrupted", reason, playback))
                elif phase == "warming" and (runtime or {}).get("capture_ready") is not True:
                    update_lease(id_, (token, "idle"))
                else:
                    try:
                        path, digest, _ = media_file(selected)
                    except (KeyError, OSError, ValueError):
                        update_lease(id_, None)
                        drain(run, breadcrumb("interrupted", "media_unavailable", playback))
                    else:
                        update_lease(id_, (token, "play", path.name, digest))
                        if phase == "warming":
                            progress = {**progress, "phase": "launching", "launch_at": time()}
                        elif ack == "playing":
                            progress = {**progress, "phase": "play"}
            elif ack == "eof" and (metrics.get("frames_processed") or 0) > 0:
                eof = breadcrumb("expected", "media_eof", playback)
                drain(run, eof)
                upcoming = next_item(playlist, position, progress["cycle"])
                if upcoming is not None:
                    # EOF closed the old publisher. Acknowledge the next lease while
                    # the old worker drains, but do not publish until it has exited.
                    pending = release_to_attempt(id_, signature, *upcoming, eof)
                    progress = {**progress, "pending": pending}
            elif ack != "playing":
                reason = "no_frames_analyzed" if ack == "eof" else "publisher_interrupted"
                drain(run, breadcrumb("interrupted", reason, playback))
            else:
                try:
                    path, digest, _ = media_file(selected)
                except (KeyError, OSError, ValueError):
                    update_lease(id_, None)
                    drain(run, breadcrumb("interrupted", "media_unavailable", playback))
                else:
                    update_lease(id_, (token, "play", path.name, digest))
                    if failures and (metrics.get("frames_processed") or 0) >= camera.expected_fps * STABLE_PLAYBACK_SECONDS:
                        progress = {**progress, "failures": 0}
            return progress

        if transition["reason"] == "media_eof" and transition["outcome"] == "expected":
            upcoming = next_item(playlist, position, progress["cycle"])
            if upcoming is not None:
                return progress.get("pending") or release_to_attempt(id_, signature, *upcoming, transition)
            update_lease(id_, None)
            return {**progress, "phase": "finished", "last_transition": transition}
        if transition["reason"] == "duration_exceeded":
            update_lease(id_, None)
            return {**progress, "phase": "duration_blocked", "blocked": DURATION_EXCEEDED,
                    "last_transition": transition}
        return release_to_attempt(id_, signature, position, progress["cycle"], transition,
                                  failures=min(failures + 1, MAX_RETRY_ATTEMPTS))

    if media_eligible(source, selected.capture_fps) and not supported_duration(source):
        update_lease(id_, None)
        if progress.get("blocked") != DURATION_LIMIT:
            progress = {**progress, "last_transition": breadcrumb("interrupted", "unsupported_duration", playback)}
        return {**progress, "phase": "duration_blocked", "blocked": DURATION_LIMIT}
    if progress["phase"] == "idle":
        update_lease(id_, (token, "idle"))
        if time() >= progress["retry_at"] and ack == "idle" and not rtsp_ready(id_):
            progress = {**progress, "phase": "play", "launch_at": time(), "blocked": None}
        else:
            return {**progress, "blocked": None}

    failure = None
    try:
        path, digest, _ = media_file(selected)
        media = path.name, digest
    except (KeyError, OSError, ValueError):
        failure = "media_unavailable"
    if ack in {"eof", "failed", "expired"}:
        failure = "publisher_ended_before_worker"
    prewarm = not view_only and supported_duration(source) and source["duration_s"] <= PREWARM_CLIP_SECONDS
    if not failure and view_only and ack == "playing":
        update_lease(id_, (token, "play", *media))
        return {**progress, "view_started": True,
                "failures": 0 if time() - progress["launch_at"] >= STABLE_PLAYBACK_SECONDS else failures}
    startup_ready = (ack == "idle" and not rtsp_ready(id_)) if prewarm else (ack == "playing" and rtsp_ready(id_))
    if not failure and not view_only and startup_ready:
        try:
            start_camera(selected, owner, managed=True, playback=playback)
        except (CameraConflict, ValidationError):
            pass
        else:
            if prewarm:
                return {**progress, "phase": "warming", "launch_at": time()}
            update_lease(id_, (token, "play", *media))
            return progress
    if failure or time() - progress["launch_at"] >= START_SECONDS:
        update_lease(id_, None)
        transition = breadcrumb("interrupted", failure or "startup_timeout", playback)
        return release_to_attempt(id_, signature, position, progress["cycle"], transition,
                                  failures=min(failures + 1, MAX_RETRY_ATTEMPTS))
    if not prewarm:
        update_lease(id_, (token, "play", *media))
    return progress


@transaction.atomic
def reconcile():
    scheduler_lock()
    control = CameraLabControl.objects.select_related("updated_by").filter(pk=CONTROL_ID).first()
    authorized = bool(control and control.enabled and control.updated_by and user_role(control.updated_by) == "administrator")
    registry = camera_registry.media_registry()
    inventory = candidates(camera_registry.inventory(registry))
    catalog, defaults = registry
    desired = intent(control, inventory) if authorized else {}
    playlists = configured_playlists(control, inventory, defaults)
    progress = control.playback if control else {}
    updated = {}
    for id_ in (SLOTS if camera_registry.third_slot_enabled() or camera_registry.THIRD_SLOT in progress else SLOTS[:2]):
        slot = reconcile_slot(id_, inventory.get(id_), playlists[id_] if desired.get(id_) else None,
                              catalog, progress.get(id_, {}), last_run(id_, lock=True),
                              control.updated_by if authorized else None)
        if slot:
            updated[id_] = slot
    if control and updated != progress:
        control.playback = updated
        control.save(update_fields=["playback"])


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
            sleep(RECONCILE_SECONDS)

    Thread(target=loop, daemon=True, name="operix-camera-lab").start()


def describe(request):
    available = camera_registry.managed()
    registry = camera_registry.media_registry()
    inventory = candidates(camera_registry.inventory(registry))
    catalog, defaults = registry
    control = CameraLabControl.objects.filter(pk=CONTROL_ID).select_related("updated_by").first() if available else None
    enabled = bool(control and control.enabled)
    desired = intent(control, inventory)
    playlists = configured_playlists(control, inventory, defaults)
    rows, publishers = [], {}
    rtsp = available and rtsp_ready()
    for id_, camera in inventory.items():
        row = camera_json(request, camera)
        live = rtsp and rtsp_ready(id_)
        slot_enabled = desired.get(id_, id_ != camera_registry.THIRD_SLOT)
        publishers[id_] = "publishing" if live else "idle"
        detail = None
        playlist = playlists[id_]
        progress = (control.playback.get(id_, {}) if control else {})
        if progress.get("signature") != playlist_signature(playlist, catalog) or not valid_playlist_position(progress, playlist):
            progress = {}
        position = progress.get("position", 0)
        media_ids = playlist["media_ids"]
        finished = progress.get("phase") == "finished"
        if enabled and slot_enabled and media_ids and not finished:
            try:
                media_file(replace(camera, provenance=catalog.get(media_ids[position])))
                if progress.get("blocked"):
                    publishers[id_] = "error"
                    detail = progress["blocked"]
                elif not live:
                    publishers[id_] = "starting" if rtsp else "error"
            except MediaRejected as error:
                publishers[id_] = "error"
                detail = str(error)
            except (OSError, KeyError, ValueError):
                publishers[id_] = "error"
                detail = "Compruebe el archivo, la licencia, la huella y la cadencia del inventario."
        transitions = [item for item in (progress.get("last_transition"), (row["playback"] or {}).get("transition")) if item]
        rows.append({**row, "enabled": slot_enabled, "problem": detail, "playlist_finished": finished,
                     "playlist_blocked": bool(progress.get("blocked")),
                     "playlist_position": position if enabled and slot_enabled and media_ids else None,
                     "last_transition": max(transitions, key=lambda item: item.get("at", ""), default=None)})
    selected = [row for row in rows if row["enabled"] and playlists[row["id"]]["media_ids"]]
    pending = [row for row in selected if not row["playlist_finished"]]
    active = [row for row in pending if (row["status"] == "analyzing" or (row.get("view_only") and row["status"] == "transmitting")) and publishers[row["id"]] == "publishing"
              and (row.get("view_only") or recent_frame(row))]
    if not enabled:
        running = CameraRun.objects.filter(active=True, managed=True).exists() or "publishing" in publishers.values()
        state = "stopping" if running else "disabled"
    elif selected and not pending:
        state = "finished"
    elif pending and len(active) == len(pending):
        state = "active"
    elif (not selected or not rtsp or active or any(row["status"] in {"error", "reconnecting", "overloaded"}
          or publishers[row["id"]] == "error" for row in pending)):
        state = "partial"
    else:
        state = "starting"
    return {"available": available, "enabled": enabled, "status": state,
            "capacity": min(3 if camera_registry.third_slot_enabled() else 2, camera_registry.capacity()), "cameras": rows,
            "publisher": publishers, "mediamtx": "ready" if rtsp else "unavailable",
            "catalog": [{"id": media_id, **{key: source[key] for key in
                         ("filename", "title", "duration_s", "fps", "scenario", "footage", "author", "license", "sha256")}}
                        for media_id, source in catalog.items()
                        if supported_duration(source)
                        and any(media_eligible(source, camera.capture_fps) for camera in inventory.values())],
            "playlists": playlists,
            "updated_by": control.updated_by.get_username() if control and control.updated_by_id else None}


def checked_playlists(updates, inventory, catalog):
    if not isinstance(updates, dict) or updates.keys() - inventory.keys():
        raise ValidationError("Identificador de cámara inválido.")
    for id_, playlist in updates.items():
        if not isinstance(playlist, dict) or playlist.keys() != {"media_ids", "repeat"}:
            raise ValidationError("Indique los identificadores de medios y si se repite la lista.")
        ids = playlist["media_ids"]
        if (type(playlist["repeat"]) is not bool or not isinstance(ids, list) or len(ids) > MAX_PLAYLIST_ITEMS
                or any(not isinstance(media_id, str) or media_id not in catalog for media_id in ids)):
            raise ValidationError("Lista de medios inválida.")
        for media_id in set(ids):
            try:
                approved_media(replace(inventory[id_], provenance=catalog[media_id]))
            except MediaRejected as error:
                raise ValidationError(str(error)) from None
            except (KeyError, OSError, ValueError):
                raise ValidationError("La lista contiene un medio no autorizado para esta cámara.") from None
    return updates


class CameraLabControlView(APIView):
    permission_classes = [LabAdministrator]

    def get(self, request):
        return Response(describe(request))

    def patch(self, request):
        if not camera_registry.managed():
            raise CameraConflict("El despliegue no incluye el supervisor virtual.")
        body = request.data
        if not isinstance(body, dict) or not body or body.keys() - {"enabled", "cameras", "playlists"}:
            raise ValidationError("Envíe el estado del laboratorio, los estados por cámara o las listas de reproducción.")
        registry = camera_registry.media_registry()
        inventory = candidates(camera_registry.inventory(registry))
        updates = body.get("cameras", {})
        if (not isinstance(updates, dict) or updates.keys() - inventory.keys()
                or any(type(value) is not bool for value in updates.values())
                or ("enabled" in body and type(body["enabled"]) is not bool)):
            raise ValidationError("Estado o identificador de cámara inválido.")
        playlists = checked_playlists(body.get("playlists", {}), inventory, registry[0])
        with transaction.atomic():
            scheduler_lock()
            control, _ = CameraLabControl.objects.get_or_create(pk=CONTROL_ID)
            enabled = body.get("enabled", control.enabled)
            if enabled and not control.enabled:
                control.playback = {}
            for id_, active in updates.items():
                if active and control.cameras.get(id_) is False:
                    control.playback.pop(id_, None)
            control.cameras = {**control.cameras, **updates}
            control.playlists = {**control.playlists, **playlists}
            control.enabled = enabled
            control.updated_by = request.user
            control.save()
            LogEntry.objects.log_actions(user_id=request.user.pk, queryset=[control], action_flag=CHANGE,
                                         change_message=json.dumps({"enabled": control.enabled, "cameras": updates,
                                                                    "playlists": playlists}))
        return Response(describe(request), status=202)
