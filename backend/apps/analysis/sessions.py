"""Registro local acotado; el Motor corre aislado en su propio Python."""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

from .preview import PreviewClock


ROOT = Path(__file__).resolve().parents[3]
PROFILES = {
    "A": ROOT / "engine/config/examples/desktop-zone-dwell.json",
    "B": ROOT / "engine/config/examples/warehouse-nearmiss-zone-dwell.json",
    "C": ROOT / "engine/config/examples/warehouse-box-pickup-zone-dwell.json",
}
PROFILE_NAMES = {
    "A": "Warehouse fire",
    "B": "Forklift / human",
    "C": "Box pickup",
}
PROFILE_DEMO_SETTINGS = {
    "A": ("warehouse_fire", "OPERIX_DEMO_VIDEO_A"),
    "B": ("forklift_human_nearmiss", "OPERIX_DEMO_VIDEO_B"),
    "C": ("warehouse_box_pickup", "OPERIX_DEMO_VIDEO_C"),
}
PERSON_SHA256 = "21766a9dc664fac06da3b0b457e0449f25e1696acbf8e7e39993c4b42282083f"
FORKLIFT_SHA256 = "1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6"
TERMINAL = {"completed", "cancelled", "error"}
RESTARTABLE = TERMINAL | {"ready"}
_sessions: dict[uuid.UUID, "AnalysisSession"] = {}
_lock = threading.RLock()
logger = logging.getLogger(__name__)


def local_event_api_url():
    value = settings.OPERIX_EVENT_API_BASE_URL
    parsed = urlparse(value)
    if (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise RuntimeError("La publicación web requiere una URL de API local sin credenciales")
    return value


@dataclass
class AnalysisSession:
    id: uuid.UUID
    directory: Path
    filename: str
    profile: str
    video_path: Path
    source_sha256: str
    source_bytes: int
    source_kind: str
    demo_source_id: str | None
    zone: dict
    state: str = "ready"
    process: subprocess.Popen | None = None
    run: int = 0
    active_config: dict | None = None
    result_config: dict | None = None
    last_access: float = field(default_factory=time.monotonic)
    _guard: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _cleanup_timer: threading.Timer | None = field(default=None, repr=False)
    preview_clock: PreviewClock = field(default_factory=PreviewClock, repr=False)
    failure_detail: str | None = None
    outbox_directory: Path | None = None
    analysis_run_id: str | None = None

    def touch(self) -> None:
        self.last_access = time.monotonic()

    def status(self) -> dict:
        with self._guard:
            self.touch()
            payload = {
                "id": str(self.id), "state": self.state,
                "filename": self.filename, "profile": self.profile,
                "source_sha256": self.source_sha256, "source_bytes": self.source_bytes,
                "source_kind": self.source_kind, "demo_source_id": self.demo_source_id,
                "zone": self.zone, "frame": 0, "total": None,
                "percent": None, "fps": None, "person_detections": 0,
                "forklift_detections": 0, "person_tracks": 0, "forklift_tracks": 0,
                "run": self.run, "result": None,
                "analysis_run_id": self.analysis_run_id,
                "persistence": {"state": "pending" if self.outbox_directory else "disabled",
                                "candidates": 0, "saved": 0, "failed": 0},
                # Solo candidatos del último frame comunicado por IPC; no es un histórico.
                "candidates": [],
            }
            path = self.directory / "status.json"
            if path.exists() and self.state in {"preparing", "processing", "completed", "error"}:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    payload.update(data)
                    if self.state in {"preparing", "processing"}:
                        self.state = data["state"]
                except (OSError, json.JSONDecodeError, KeyError):
                    pass
            if self.process is not None and self.process.poll() is not None and self.state not in TERMINAL:
                self.state = "error"
                self.failure_detail = "El Motor terminó antes de completar el análisis. Puede volver a intentarlo."
                payload.update(state="error", detail=self.failure_detail)
            if self.process is not None and self.process.poll() not in (None, 0) and self.state == "completed":
                self.state = "error"
                self.failure_detail = "El proceso del Motor terminó con error; no se confirma una ejecución completa."
            if self.state == "completed":
                result = self.directory / "annotated.mp4"
                if result.is_file() and self.active_config is not None:
                    self.result_config = {
                        **self.active_config,
                        "source_fps": payload.get("source_fps"),
                        "frames": payload.get("frame"),
                        "width": payload.get("width"),
                        "height": payload.get("height"),
                        "video": payload.get("result_video"),
                    }
                else:
                    self.state = "error"
                    payload["detail"] = "No se generó un resultado reproducible."
            payload["result"] = self.result_config if self.state == "completed" else None
            if self.outbox_directory and (self.state in {"error", "cancelled"} or
                    (self.state in TERMINAL and payload["persistence"]["state"] == "pending")):
                payload["persistence"] = {"state": "failed", "detail": "El análisis terminó sin confirmar la persistencia; revise el journal."}
            if self.outbox_directory and (self.outbox_directory / "replay-summary.json").is_file():
                try:
                    payload["persistence"] = json.loads((self.outbox_directory / "replay-summary.json").read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    payload["persistence"] = {"state": "failed", "detail": "No se pudo verificar la persistencia."}
            payload["pending_changes"] = bool(
                self.result_config and
                (self.profile != self.result_config["profile"] or self.zone != self.result_config["zone"])
            )
            payload["state"] = self.state
            if self.failure_detail is not None:
                payload["detail"] = self.failure_detail
            clock = self.preview_clock
            enabled = payload.get("preview_sample_fps") is not None
            # El reloj sigue avanzando aunque el navegador cierre/reabra MJPEG.
            # Sin consumidor inicial, el resultado completo no espera un stream inexistente.
            if enabled and clock.started_at is not None and payload.get("preview_latest_frame") is not None:
                clock.select(
                    now=time.monotonic(), source_fps=payload["source_fps"],
                    sample_fps=payload["preview_sample_fps"], latest=payload["preview_latest_frame"],
                    total=payload.get("total") or payload["frame"], completed=self.state == "completed",
                )
            payload["preview"] = {
                "pending": enabled and not clock.finished and (
                    self.state in {"preparing", "processing"} or
                    (self.state == "completed" and clock.started_at is not None)
                ),
                "frame_index": clock.frame_index,
                "source_timestamp": (
                    clock.frame_index / payload["source_fps"]
                    if clock.frame_index is not None and payload.get("source_fps") else None
                ),
                "playback_rate": 1,
            }
            return payload

    def schedule_cleanup(self) -> None:
        with self._guard:
            if self._cleanup_timer is not None:
                return
            self._schedule_after(settings.OPERIX_ANALYSIS_RETENTION_SECONDS)

    def _schedule_after(self, seconds: float) -> None:
        timer = threading.Timer(seconds, lambda: expire_session(self.id))
        timer.daemon = True
        self._cleanup_timer = timer
        timer.start()

    def stop(self) -> None:
        with self._guard:
            if self.state not in {"preparing", "processing"}:
                raise ValueError("No hay un análisis en curso para detener")
            self.state = "cancelled"
            process = self.process
            run = self.run
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        with self._guard:
            if self.process is not process or self.run != run:
                return  # Otro inicio ya posee la sesión; nunca limpiar sus salidas.
            self.process = None
            self.result_config = None
            for filename in ("status.json", "frame.jpg", "annotated.partial.mp4", "annotated.mp4", "error.log"):
                (self.directory / filename).unlink(missing_ok=True)
            shutil.rmtree(self.directory / "preview", ignore_errors=True)
            self.preview_clock = PreviewClock()
        self.schedule_cleanup()

    def close(self) -> None:
        with self._guard:
            process = self.process
            self.process = None
            if self.state in {"preparing", "processing"}:
                self.state = "cancelled"
            if self._cleanup_timer is not None:
                self._cleanup_timer.cancel()
                self._cleanup_timer = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _demo_path(profile: str) -> tuple[str, Path] | None:
    if profile not in PROFILE_DEMO_SETTINGS:
        raise ValueError("Perfil de zona no válido")
    source_id, setting_name = PROFILE_DEMO_SETTINGS[profile]
    raw_path = str(getattr(settings, setting_name, "")).strip()
    if not raw_path:
        return None
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        return None
    return source_id, path


def profile_catalog() -> list[dict]:
    result = []
    for profile in PROFILES:
        demo = _demo_path(profile)
        result.append({
            "id": profile,
            "display_name": PROFILE_NAMES[profile],
            "default_demo_video": None if demo is None else {
                "id": demo[0],
                "filename": demo[1].name,
                "bytes": demo[1].stat().st_size,
            },
        })
    return result


def get_demo_video(profile: str, source_id: str) -> Path | None:
    demo = _demo_path(profile)
    if demo is None or demo[0] != source_id:
        return None
    return demo[1]


def _clean_filename(value: object) -> str:
    filename = str(value).replace("\\", "/").split("/")[-1]
    return "".join(char for char in filename if char.isprintable())[:120]


def _validate_video_file(path: Path, filename: str, size: int) -> None:
    extension = path.suffix.lower()
    if extension not in {".mp4", ".mov", ".avi"}:
        raise ValueError("Se admite video MP4, MOV o AVI")
    if size > settings.OPERIX_ANALYSIS_MAX_UPLOAD_BYTES:
        raise ValueError("El video supera el tamaño máximo configurado")
    with path.open("rb") as source:
        first = source.read(16)
    header_ok = first[:4] == b"RIFF" if extension == ".avi" else first[4:8] == b"ftyp"
    if not header_ok:
        raise ValueError(f"{filename} no tiene una cabecera de video reconocible")


def _register_session(
    *, profile: str, filename: str, video_path: Path, source_sha256: str,
    source_bytes: int, source_kind: str, demo_source_id: str | None,
    directory: Path,
) -> AnalysisSession:
    zone = json.loads(PROFILES[profile].read_text(encoding="utf-8"))["zones"][0]
    session = AnalysisSession(
        uuid.uuid4(), directory, filename, profile, video_path, source_sha256,
        source_bytes, source_kind, demo_source_id, zone,
    )
    with _lock:
        if len(_sessions) >= settings.OPERIX_ANALYSIS_MAX_SESSIONS:
            raise RuntimeError("Se alcanzó el límite de análisis simultáneos")
        _sessions[session.id] = session
    session.schedule_cleanup()
    return session


def create_session(upload, profile: str) -> AnalysisSession:
    if profile not in PROFILES:
        raise ValueError("Perfil de zona no válido")
    filename = _clean_filename(upload.name)
    extension = Path(filename).suffix.lower()
    if upload.size > settings.OPERIX_ANALYSIS_MAX_UPLOAD_BYTES:
        raise ValueError("El video supera el tamaño máximo configurado")
    first = upload.read(16)
    upload.seek(0)
    header_ok = first[:4] == b"RIFF" if extension == ".avi" else first[4:8] == b"ftyp"
    if not header_ok:
        raise ValueError("El archivo no tiene una cabecera de video reconocible")
    directory = Path(tempfile.mkdtemp(prefix="operix-analysis-"))
    try:
        video_path = directory / f"input{extension}"
        digest = hashlib.sha256()
        with video_path.open("wb") as destination:
            count = 0
            for chunk in upload.chunks():
                count += len(chunk)
                if count > settings.OPERIX_ANALYSIS_MAX_UPLOAD_BYTES:
                    raise ValueError("El video supera el tamaño máximo configurado")
                destination.write(chunk)
                digest.update(chunk)
        _validate_video_file(video_path, filename, count)
        return _register_session(
            profile=profile, filename=filename, video_path=video_path,
            source_sha256=digest.hexdigest(), source_bytes=count,
            source_kind="manual", demo_source_id=None, directory=directory,
        )
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def create_demo_session(profile: str) -> AnalysisSession:
    demo = _demo_path(profile)
    if demo is None:
        raise ValueError("El perfil no tiene un video demo disponible")
    source_id, video_path = demo
    filename = _clean_filename(video_path.name)
    source_bytes = video_path.stat().st_size
    _validate_video_file(video_path, filename, source_bytes)
    digest = hashlib.sha256()
    with video_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    directory = Path(tempfile.mkdtemp(prefix="operix-analysis-"))
    try:
        return _register_session(
            profile=profile, filename=filename, video_path=video_path,
            source_sha256=digest.hexdigest(), source_bytes=source_bytes,
            source_kind="demo", demo_source_id=source_id, directory=directory,
        )
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def get_session(session_id: uuid.UUID) -> AnalysisSession | None:
    with _lock:
        return _sessions.get(session_id)


def remove_session(session_id: uuid.UUID) -> None:
    with _lock:
        session = _sessions.pop(session_id, None)
    if session is None:
        return
    session.close()
    try:
        shutil.rmtree(session.directory)
    except FileNotFoundError:
        return
    except OSError:
        # Windows puede mantener abierto el MP4 durante una respuesta Range.
        threading.Thread(
            target=_remove_directory_when_released,
            args=(session.directory,),
            name=f"analysis-cleanup-{session.id}",
            daemon=True,
        ).start()


def _remove_directory_when_released(directory: Path) -> None:
    for _ in range(60):
        time.sleep(0.5)
        try:
            shutil.rmtree(directory)
            return
        except FileNotFoundError:
            return
        except OSError:
            continue
    logger.warning("No se pudo liberar el directorio temporal de una sesión de análisis")


def close_all_sessions() -> None:
    """Cierre normal de esta instancia de API; no inspecciona procesos ajenos."""
    with _lock:
        identities = tuple(_sessions)
    for identity in identities:
        try:
            remove_session(identity)
        except OSError:
            logger.exception("No se pudo liberar una sesión al cerrar la API")


def expire_session(session_id: uuid.UUID) -> None:
    session = get_session(session_id)
    if session is None:
        return
    with session._guard:
        session._cleanup_timer = None
        idle = time.monotonic() - session.last_access
        if session.state in {"preparing", "processing"}:
            session._schedule_after(settings.OPERIX_ANALYSIS_RETENTION_SECONDS)
            return
        if idle < settings.OPERIX_ANALYSIS_RETENTION_SECONDS:
            session._schedule_after(settings.OPERIX_ANALYSIS_RETENTION_SECONDS - idle)
            return
    remove_session(session_id)


def _clear_run_outputs(session: AnalysisSession) -> None:
    shutil.rmtree(session.directory / "preview", ignore_errors=True)
    session.preview_clock = PreviewClock()
    for filename in (
        "status.json", "frame.jpg", "annotated.partial.mp4", "annotated.mp4",
        "error.log", "polygon.json", "run_config.json",
    ):
        (session.directory / filename).unlink(missing_ok=True)


def start_session(session: AnalysisSession) -> None:
    # Política local explícita: una inferencia GPU a la vez, sin cola distribuida.
    # El lock cubre comprobación + Popen para dos solicitudes simultáneas.
    with _lock:
        for other in _sessions.values():
            if other is not session and other.process is not None and other.process.poll() is None:
                raise ValueError("Ya hay otro análisis en curso. Espere a que termine o deténgalo.")
        _start_session(session)


def _start_session(session: AnalysisSession) -> None:
    with session._guard:
        if session.state not in RESTARTABLE or (
            session.process is not None and session.process.poll() is None
        ):
            raise ValueError("Espere a que termine el análisis actual")
        python = Path(settings.OPERIX_ENGINE_PYTHON)
        person = Path(settings.OPERIX_PERSON_WEIGHTS) if settings.OPERIX_PERSON_WEIGHTS else None
        forklift = Path(settings.OPERIX_FORKLIFT_WEIGHTS) if settings.OPERIX_FORKLIFT_WEIGHTS else None
        if not python.is_file() or person is None or not person.is_file() or forklift is None or not forklift.is_file():
            raise RuntimeError("Configure OPERIX_ENGINE_PYTHON y los pesos person/forklift fuera de Git")
        _clear_run_outputs(session)
        session.run += 1
        session.result_config = None
        session.failure_detail = None
        session.active_config = {
            "profile": session.profile,
            "zone": json.loads(json.dumps(session.zone)),
            "source_video": session.filename,
            "source_sha256": session.source_sha256,
            "person_model_sha256": PERSON_SHA256,
            "forklift_model_sha256": FORKLIFT_SHA256,
            "person": {"imgsz": 640, "confidence": 0.10, "nms_iou": 0.70},
            "forklift": {"imgsz": 640, "confidence": 0.45, "nms_iou": 0.55},
            "tracker": "ByteTrack independiente por clase",
            "run": session.run,
        }
        (session.directory / "run_config.json").write_text(
            json.dumps(session.active_config, ensure_ascii=False), encoding="utf-8",
        )
        polygon_path = session.directory / "polygon.json"
        polygon_path.write_text(json.dumps(session.zone["polygon"]), encoding="utf-8")
        command = [
            str(python), str(ROOT / "engine/scripts/stream_dual_perception.py"),
            "--session-dir", str(session.directory), "--video", str(session.video_path),
            "--config", str(PROFILES[session.profile]), "--polygon", str(polygon_path),
            "--person-weights", str(person), "--person-sha256", PERSON_SHA256,
            "--forklift-weights", str(forklift), "--forklift-sha256", FORKLIFT_SHA256,
        ]
        session.outbox_directory = None
        session.analysis_run_id = str(uuid.uuid5(session.id, str(session.run)))
        if settings.EVENT_POST_ENABLED:
            api_url = local_event_api_url()
            actual = json.loads(PROFILES[session.profile].read_text(encoding="utf-8"))
            actual["zones"] = [json.loads(json.dumps(session.zone))]
            snapshot = json.dumps(actual, sort_keys=True).encode()
            config_path = session.directory / "operational_config.json"
            config_path.write_bytes(snapshot)
            command[command.index("--config") + 1] = str(config_path)
            session.outbox_directory = Path(settings.MEDIA_ROOT) / "analysis-events" / session.analysis_run_id
            session.outbox_directory.mkdir(parents=True, exist_ok=False)
            source = {"filename": session.filename, "kind": session.source_kind,
                      "video_sha256": session.source_sha256,
                      "config_sha256": hashlib.sha256(snapshot).hexdigest(),
                      "person_weights_sha256": PERSON_SHA256, "forklift_weights_sha256": FORKLIFT_SHA256,
                      "timestamp_basis": "ANALYSIS_START_PROXY_NOT_RECORDING_TIME",
                      "session_id": str(session.id), "session_run": session.run}
            context_path = session.outbox_directory / "context.json"
            context_path.write_text(json.dumps({"analysis_run_id": session.analysis_run_id,
                "analysis_started_at": datetime.now(timezone.utc).isoformat(), "source": source,
                "api_url": api_url}), encoding="utf-8")
            session.active_config.update(analysis_run_id=session.analysis_run_id, source=source,
                                         event_retention="MANUAL_RETENTION")
            command.extend(["--event-context", str(context_path)])
        (session.directory / "run_config.json").write_text(
            json.dumps(session.active_config, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["YOLO_CONFIG_DIR"] = str(session.directory)
        session.state = "preparing"
        session.touch()
        try:
            session.process = subprocess.Popen(
                command, cwd=ROOT / "engine", env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except OSError:
            session.state = "error"
            session.failure_detail = "No se pudo iniciar el Motor. Revise la configuración local e inténtelo de nuevo."
            logger.exception("No se pudo iniciar el proceso del Motor")
            raise RuntimeError(session.failure_detail) from None

    process = session.process

    def watch() -> None:
        try:
            process.wait(timeout=settings.OPERIX_ANALYSIS_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            with session._guard:
                if session.process is not process:
                    return
                session.state = "error"
                session.failure_detail = "El análisis superó el tiempo máximo. Puede volver a intentarlo."
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        with session._guard:
            if session.process is not process:
                return
            session.status()
            if session.state not in TERMINAL:
                session.state = "error"
            if session.state != "completed":
                (session.directory / "annotated.partial.mp4").unlink(missing_ok=True)
                (session.directory / "annotated.mp4").unlink(missing_ok=True)
            session.process = None
        session.schedule_cleanup()

    threading.Thread(target=watch, name=f"analysis-{session.id}", daemon=True).start()


def stream_frames(session: AnalysisSession):
    last_frame = None
    run = session.run
    while True:
        status = session.status()
        if session.run != run or status["state"] in {"cancelled", "error", "ready"}:
            break
        if status.get("preview_sample_fps") is not None:
            latest = status.get("preview_latest_frame")
            if latest is not None:
                with session._guard:
                    index = session.preview_clock.select(
                        now=time.monotonic(), source_fps=status["source_fps"],
                        sample_fps=status["preview_sample_fps"], latest=latest,
                        total=status.get("total") or status["frame"],
                        completed=status["state"] == "completed",
                    )
                    finished = session.preview_clock.finished
                if index != last_frame:
                    try:
                        frame = (session.directory / "preview" / f"{index:09d}.jpg").read_bytes()
                    except OSError:
                        pass
                    else:
                        last_frame = index
                        yield (
                            b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                            + str(len(frame)).encode()
                            + f"\r\nX-Frame-Index: {index}\r\nX-Source-Timestamp: {index / status['source_fps']:.6f}"
                              f"\r\nX-Latest-Processed-Frame: {status['frame'] - 1}\r\n\r\n".encode()
                            + frame + b"\r\n"
                        )
                if finished:
                    break
            time.sleep(0.01)  # Solo el consumidor HTTP espera; nunca el Motor.
            continue
        frame_path = session.directory / "frame.jpg"
        if frame_path.exists():
            try:
                stamp = frame_path.stat().st_mtime_ns
                if stamp != last_frame:
                    frame = frame_path.read_bytes()
                    last_frame = stamp
                    yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
            except OSError:
                pass
        if status["state"] in TERMINAL:
            break
        time.sleep(0.06)


atexit.register(close_all_sessions)
