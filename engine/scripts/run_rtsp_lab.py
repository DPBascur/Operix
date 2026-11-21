"""Motor continuo para una fuente RTSP interna autorizada por el Backend."""

import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from functools import cached_property
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
from threading import Event, Thread
from time import perf_counter as monotonic
from urllib.parse import urlsplit
from uuid import UUID

import cv2
import numpy as np
import torch

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.dual_perception import ClassPerceptionChannel, DualPerception, PerceptionFrame
from operix_engine.event_publishing import (
    EventContext, HttpEventSink, event_candidate_payload, publish_document_with_retries,
)
from operix_engine.operational_config import load_operational_config
from operix_engine.rtsp_inference import InferenceBusy, InferenceClient, InferenceError, InferenceTimeout
from operix_engine.rtsp_lab_clips import ClipStore, JpegRing
from operix_engine.rtsp_pilot import Capture, Epoch
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.video_event_pipeline import _visible_tracks
from operix_engine.visualization import OpenCvRenderer, TrajectoryAccumulator, VisualizationConfig
from run_rtsp_pilot import FORKLIFT_SHA, PERSON_SHA, Reader, checked_file, detector
from stream_dual_perception import _write_atomic


MAX_SECONDS = 1800
MAX_EVENTS = 20
MAX_PENDING = 3
PREVIEW_INTERVAL = .1
STATUS_INTERVAL = 1
PNG_LIMIT = 2 * 1024 * 1024
POST_LIMIT = 2 * 1024 * 1024
INFERENCE_STALL_SECONDS = 5


def utc_now():
    return datetime.now(timezone.utc)


def authorized_url(env):
    url = env.get("OPERIX_RTSP_URL", "")
    parsed = urlsplit(url)
    allowed = ipaddress.ip_address(env.get("OPERIX_RTSP_ALLOWED_IP", ""))
    if (parsed.scheme != "rtsp" or not parsed.hostname or ipaddress.ip_address(parsed.hostname) != allowed
            or not parsed.path.startswith("/") or parsed.fragment or parsed.port == 0
            or any(ord(char) <= 32 or ord(char) == 127 for char in url)):
        raise ValueError("Fuente fuera de la autorización RTSP")
    return url


def load_context(output, config_path):
    document = json.loads((output / "context.json").read_text(encoding="utf-8"))
    source = document["source"]
    if (source["kind"] != "lab" or source["timestamp_basis"] != "LAB_RECEPTION_UTC"
            or any(not re.fullmatch(r"[0-9a-fA-F]{64}", source[key])
                   for key in ("video_sha256", "config_sha256"))):
        raise ValueError("Identidad de fuente lab inválida")
    snapshot = config_path.read_bytes()
    config = load_operational_config(config_path)
    if (config_path.read_bytes() != snapshot
            or hashlib.sha256(snapshot).hexdigest() != source["config_sha256"].lower()):
        raise ValueError("La configuración no coincide con el contexto")
    if config.calibration or (config.motion and config.motion.unit == "m"):
        raise ValueError("RTSP lab requiere configuración de imagen sin calibración ligada a un archivo")
    context = EventContext(UUID(document["analysis_run_id"]), config.view_id,
                           datetime.fromisoformat(document["analysis_started_at"]), source)
    return context, config


def reception_payload(candidate, context, received_at, processed_at, pts, uses_pts):
    source = {**context.source, "capture": {
        "received_at": received_at.isoformat(), "processed_at": processed_at.isoformat(),
        "source_pts_s": pts, "time_basis": "source_pts" if uses_pts else "local_arrival",
    }}
    # El candidato conserva el reloj de la época, mientras occurred_at documenta la recepción UTC.
    return event_candidate_payload(candidate, replace(
        context, recording_started_at=received_at - timedelta(seconds=candidate.timestamp_s), source=source,
    ))


class WorkerStatus:
    def __init__(self, args):
        self.args = args
        self.started = monotonic()
        self.last_update = -math.inf
        self.state = None
        self.run_id = None
        self.inference_mode = "dedicated"
        self.capture = None
        self.epochs = Counter()
        self.received = deque(maxlen=600)
        self.completed = deque(maxlen=600)
        self.connection = 0
        self.timings = {name: deque(maxlen=600) for name in (
            "arrival_to_result", "queue_age", "inference", "rules", "jpeg",
            "png", "publication", "clip", "arrival_to_publication", "inference_request",
            "inference_queue", "person_batch", "forklift_batch",
        )}
        self.metrics = Counter({key: 0 for key in (
            "frames_processed", "candidates", "events_submitted", "events_published", "events_duplicate",
            "events_failed", "events_skipped_quota", "events_skipped_backpressure", "clips_saved",
            "clips_existing", "clips_unavailable", "clips_disk_limit", "clips_failed",
            "evidence_saved", "evidence_failed",
        )})
        self.preview_frame = None
        self.last_frame_at = None
        self.last_frame_received = None
        self.epoch = 0
        self.inference_drops = Counter()
        self.inference_batch_sizes = Counter()

    def capture_trace(self, kind, connection, timestamp, **_fields):
        # Capture invoca el callback con el bloqueo de ready.
        if kind == "open":
            self.connection = connection
        elif kind == "decoded":
            self.received.append((timestamp, connection))

    def write(self, state, reason=None):
        now = monotonic()
        if reason is None and state == self.state and now - self.last_update < STATUS_INTERVAL:
            return
        elapsed = now - self.started
        capture_counts = {}
        decoded_recently = 0
        arrivals = []
        queue_depth = queue_peak = 0
        if self.capture is not None:
            with self.capture.ready:
                capture_counts = dict(self.capture.counts)
                received = [(timestamp, connection) for timestamp, connection in self.received
                            if now - 5 <= timestamp <= now]
                arrivals = [timestamp for timestamp, connection in received if connection == self.connection]
                decoded_recently = len(received)
                queue_depth = len(self.capture.queue)
                queue_peak = self.capture.depth
        received_fps = 0.0
        if len(arrivals) >= 2 and now - arrivals[-1] <= .5 and arrivals[-1] > arrivals[0]:
            received_fps = round((len(arrivals) - 1) / (arrivals[-1] - arrivals[0]), 2)
        timing_metrics = {}
        for name, values in self.timings.items():
            ordered = sorted(values)
            timing_metrics[f"{name}_ms"] = round(values[-1], 2) if values else None
            for quantile in (.50, .95):
                timing_metrics[f"p{int(quantile * 100)}_{name}_ms"] = (
                    round(ordered[math.ceil(quantile * len(ordered)) - 1], 2) if ordered else None
                )
        results_recently = sum(now - 5 <= timestamp <= now for timestamp, _ in self.completed)
        covered = None
        if decoded_recently:
            completed_from_recent_frames = sum(now - 5 <= received <= now for _, received in self.completed)
            covered = min(1., completed_from_recent_frames / decoded_recently)
        api_state = {"starting": "connecting", "processing": "analyzing", "completed": "stopped"}.get(state, state)
        error_message = None
        if state == "error":
            error_message = (
                "El Motor compartido dejó de responder. Vuelva a iniciar cuando esté disponible."
                if reason == "INFERENCE_UNAVAILABLE" else "El Motor RTSP lab no pudo continuar."
            )
        document = {
            "state": state, "status": api_state, "updated_at": utc_now().isoformat(), "termination_reason": reason,
            "last_frame_at": self.last_frame_at,
            "last_error": error_message,
            "analysis_run_id": self.run_id,
            "metrics": {
                **self.metrics, **timing_metrics, "elapsed_s": round(elapsed, 3), "received_fps": received_fps,
                "source_fps": self.args.fps if math.isfinite(self.args.fps) else None,
                "analysis_fps": round(self.metrics["frames_processed"] / max(elapsed, 1e-9), 2),
                "analysis_fps_5s": round(results_recently / 5, 2),
                "observed_fraction_5s": round(covered, 4) if covered is not None else None,
                "queue_depth": queue_depth, "max_queue_depth": queue_peak,
                "last_frame_age_ms": (round((now - self.last_frame_received) * 1000, 2)
                                      if self.last_frame_received is not None else None),
                "frames_dropped": (sum(self.inference_drops.values())
                                   + sum(value for key, value in capture_counts.items() if key.endswith("_drop"))),
                "frames_inference_dropped": sum(self.inference_drops.values()),
                "inference_drops": dict(self.inference_drops),
                "inference_batch_sizes": dict(self.inference_batch_sizes),
                "inference_mode": self.inference_mode,
                "width": self.args.width, "height": self.args.height, "capture": capture_counts,
                "epoch": self.epoch, "epochs": dict(self.epochs), "preview_frame": self.preview_frame,
                "event_limit": MAX_EVENTS,
            },
        }
        _write_atomic(self.args.output / "status.json", json.dumps(document, allow_nan=False).encode("utf-8"))
        self.last_update, self.state = now, state


class LabPipeline:
    def __init__(self, config, args, *, infer_remotely=False):
        person = forklift = None
        if not infer_remotely:
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA no disponible")
            checked_file(args.person_weights, PERSON_SHA, "PERSON")
            checked_file(args.forklift_weights, FORKLIFT_SHA, "FORKLIFT")
            person = detector(args.person_weights, .10, .70)
            forklift = detector(args.forklift_weights, .45, .55)
        self.perception = DualPerception(
            person=ClassPerceptionChannel("person", person, ByteTracker(ByteTrackConfig())),
            forklift=ClassPerceptionChannel("forklift", forklift, ByteTracker(ByteTrackConfig())),
        )
        if not infer_remotely:
            self.perception.process(np.zeros((args.height, args.width, 3), dtype=np.uint8),
                                    synchronize=torch.cuda.synchronize)
        self.analyzer = SpatiotemporalAnalyzer(
            width=args.width, height=args.height, fps=args.fps, zones=config.zones,
            proximity_roles=config.proximity_roles, motion=config.motion, observe_occupants=config.observe_occupants,
        )
        self.rules = RuleEngine(config)
        self.zones = tuple(zone for zone in config.zones if zone.enabled)
        visual = VisualizationConfig(max_trajectory_points=60, inactive_retention_frames=30, relations=config.relations)
        self.renderer = OpenCvRenderer(visual)
        self.histories = {name: TrajectoryAccumulator(visual) for name in ("person", "forklift")}
        self.dimensions = args.width, args.height

    def reset(self, epoch):
        self.perception.person.reset()
        self.perception.forklift.reset()
        self.analyzer.reset(epoch=epoch)
        self.rules.reset()
        for history in self.histories.values():
            history.reset()

    def process(self, frame, timestamp, *, detected=None, inference_ms=None):
        if detected is None:
            observed, timing = self.perception.process(frame.image, synchronize=torch.cuda.synchronize)
            inference_ms = (timing.person_inference_s + timing.forklift_inference_s) * 1000
        else:
            observed = PerceptionFrame(detected.person, detected.forklift,
                                       self.perception.person.track(detected.person),
                                       self.perception.forklift.track(detected.forklift))
        rules_started = monotonic()
        tracks, _, _ = _visible_tracks(observed.person_tracks + observed.forklift_tracks, *self.dimensions)
        spatial = self.analyzer.update(frame.index, tracks, timestamp_s=timestamp)
        result = self.rules.evaluate(spatial)
        rules_ms = (monotonic() - rules_started) * 1000
        annotated = frame.image
        occupied = []
        boxes = [track.bounding_box for track in tracks]
        active_zones = {item.zone_id for item in result.candidates}
        for zone in self.zones:
            annotated = self.renderer.render_zone(
                annotated, zone, event=zone.zone_id in active_zones, occupied=occupied, object_boxes=boxes,
            )
        for name, history in self.histories.items():
            class_tracks = getattr(observed, f"{name}_tracks")
            annotated = self.renderer.render_tracks(
                annotated, class_tracks, history.update(frame.index, class_tracks), occupied=occupied, object_boxes=boxes,
            )
        annotated = self.renderer.render_proximity(annotated, spatial, result, metric_expected=False, occupied=occupied)
        return annotated, result.candidates, inference_ms, rules_ms


def evidence_png(image):
    height, width = image.shape[:2]
    scale = min(1.0, 960 / max(height, width))
    while True:
        sample = image if scale == 1 else cv2.resize(
            image, (max(1, round(width * scale)), max(1, round(height * scale))), interpolation=cv2.INTER_AREA,
        )
        encoded, png = cv2.imencode(".png", sample, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        if not encoded:
            raise RuntimeError("La codificación PNG falló")
        if png.nbytes <= PNG_LIMIT:
            return png.tobytes()
        scale *= .75


@dataclass
class EventImage:
    image: np.ndarray | None

    @cached_property
    def encoded(self):
        started = monotonic()
        try:
            png = evidence_png(self.image)
        except (RuntimeError, cv2.error):
            png = None
        self.image = None
        return png, (monotonic() - started) * 1000


@dataclass
class PendingEvent:
    payload: dict
    image: EventImage
    frames: list
    last_index: int
    post_bytes: int = 0


class EventPublisher:
    def __init__(self, sink, clips, executor, metrics, fps, timings=None):
        self.sink, self.clips, self.executor, self.metrics = sink, clips, executor, metrics
        self.pending = set()
        self.waiting = []
        self.post_frames = math.floor(fps)
        self.timings = timings

    def _publish(self, job):
        was_encoded = "encoded" in vars(job.image)
        png, png_ms = job.image.encoded
        timings = {} if was_encoded else {"png": png_ms}
        if png is None:
            return {"events_failed": 1, "evidence_failed": 1}, timings
        started = monotonic()
        result, _ = publish_document_with_retries(self.sink, job.payload, png, max_attempts=2)
        timings["publication"] = (monotonic() - started) * 1000
        counters = {f"events_{result.status}": 1}
        counters["evidence_saved" if result.status in {"published", "duplicate"} else "evidence_failed"] = 1
        if result.event_id:
            arrival = datetime.fromisoformat(job.payload["source"]["capture"]["received_at"])
            timings["arrival_to_publication"] = max(0., (utc_now() - arrival).total_seconds() * 1000)
            started = monotonic()
            try:
                clip_status = self.clips.save(result.event_id, job.payload, job.frames)
            except (OSError, RuntimeError, ValueError, cv2.error):
                clip_status = "failed"
            counters[f"clips_{clip_status}"] = 1
            timings["clip"] = (monotonic() - started) * 1000
        return counters, timings

    def _dispatch(self, job):
        self.pending.add(self.executor.submit(self._publish, job))

    def advance(self, index, data):
        remaining = []
        for job in self.waiting:
            if job.post_bytes + len(data) > POST_LIMIT:
                self._dispatch(job)
                continue
            job.frames.append((index, data))
            job.post_bytes += len(data)
            if index >= job.last_index:
                self._dispatch(job)
            else:
                remaining.append(job)
        self.waiting = remaining

    def flush(self):
        for job in self.waiting:
            self._dispatch(job)
        self.waiting.clear()

    def collect(self, *, drain=False):
        for future in tuple(self.pending):
            if drain or future.done():
                self.pending.remove(future)
                counts, timings = future.result()
                self.metrics.update(counts)
                if self.timings is not None:
                    for name, elapsed in timings.items():
                        self.timings[name].append(elapsed)

    def submit(self, candidates, context, received_at, processed_at, frame, epoch, ring, annotated):
        self.metrics["candidates"] += len(candidates)
        image = None
        for candidate in candidates:
            if self.metrics["events_submitted"] >= MAX_EVENTS:
                self.metrics["events_skipped_quota"] += 1
            elif len(self.pending) + len(self.waiting) >= MAX_PENDING:
                self.metrics["events_skipped_backpressure"] += 1
            else:
                payload = reception_payload(candidate, context, received_at, processed_at, frame.pts, epoch.uses_pts)
                if image is None:
                    image = EventImage(annotated.copy())
                job = PendingEvent(payload, image, list(ring.snapshot()), frame.index + self.post_frames)
                if self.post_frames and job.frames:
                    self.waiting.append(job)
                else:
                    self._dispatch(job)
                self.metrics["events_submitted"] += 1


def run(args, status, stop_reason):
    if not (0 < args.seconds <= MAX_SECONDS and 0 < args.fps <= 60
            and 0 < args.width <= 1920 and 0 < args.height <= 1080):
        raise ValueError("Límites de sesión inválidos")
    if reason := stop_reason():
        return reason
    url = authorized_url(os.environ)
    if not os.environ.get("OPERIX_EVENT_PUBLISH_TOKEN", "").strip():
        raise ValueError("Falta la autorización de publicación")
    sink = HttpEventSink(os.environ["OPERIX_EVENT_API_BASE_URL"], timeout_s=1, local_only=True)
    context, config = load_context(args.output, args.config)
    status.run_id = str(context.analysis_run_id)
    media_root = Path(__file__).resolve().parents[2] / "backend" / os.environ.get("OPERIX_MEDIA_ROOT", "media")
    clips = ClipStore(media_root.resolve(), args.fps)
    if reason := stop_reason():
        return reason
    inference_socket = os.environ.get("OPERIX_RTSP_INFERENCE_SOCKET")
    inference = None
    if inference_socket:
        inference = InferenceClient(inference_socket, camera_id=context.source["camera_id"], run_id=status.run_id)
        status.inference_mode = "shared"
    pipeline = LabPipeline(config, args, infer_remotely=inference is not None)
    if reason := stop_reason():
        return reason
    epoch, ring = Epoch(args.fps), JpegRing(args.fps)
    last_frame = last_preview = -math.inf
    failures_at_frame = 0
    inference_stalled_since = None
    capture = Capture(lambda: Reader(url, args.fps, pipeline.dimensions), fps=args.fps, trace=status.capture_trace)
    status.capture = capture
    status.write("connecting")
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="rtsp-event") as executor:
        publisher = EventPublisher(sink, clips, executor, status.metrics, args.fps, status.timings)
        try:
            with capture:
                while not (reason := stop_reason()):
                    frame = capture.next()
                    if reason := stop_reason():
                        break
                    now = monotonic()
                    publisher.collect()
                    with capture.ready:
                        failures = capture.counts["open_failure"] + capture.counts["read_failure"]
                    if frame is None:
                        if not capture.thread.is_alive():
                            raise RuntimeError("El lector RTSP terminó inesperadamente")
                        if failures > failures_at_frame or (epoch.number and now - last_frame > .5):
                            publisher.flush()
                            status.write("reconnecting")
                        else:
                            status.write("overloaded" if inference_stalled_since is not None
                                         else "processing" if epoch.number else "connecting")
                        continue
                    selected_at = monotonic()
                    received_at = utc_now() - timedelta(seconds=max(0, selected_at - frame.received))
                    status.timings["queue_age"].append(max(0, selected_at - frame.received) * 1000)
                    detected = None
                    if inference is not None:
                        try:
                            detected = inference.infer(
                                frame.image, epoch=epoch.number + int(epoch.discontinuity(frame) is not None),
                                frame_index=frame.index, deadline=frame.received + capture.max_age,
                            )
                        except InferenceBusy:
                            status.inference_drops["busy"] += 1
                        except InferenceTimeout:
                            status.inference_drops["deadline"] += 1
                        except InferenceError:
                            status.inference_drops["failed"] += 1
                            raise
                        if reason := stop_reason():
                            if detected is not None:
                                status.inference_drops["shutdown"] += 1
                            break
                        obsolete = not capture.is_current(frame)
                        if detected is None or obsolete:
                            if detected is not None:
                                status.inference_drops["disconnect"] += 1
                            if obsolete:
                                inference_stalled_since = None
                                status.write("reconnecting")
                            else:
                                if inference_stalled_since is None:
                                    inference_stalled_since = selected_at
                                if monotonic() - inference_stalled_since >= INFERENCE_STALL_SECONDS:
                                    raise InferenceError("La inferencia dejó de producir resultados")
                                status.write("overloaded")
                            continue
                        inference_stalled_since = None
                        request_ms = (monotonic() - selected_at) * 1000
                        status.timings["inference_request"].append(request_ms)
                        status.timings["inference_queue"].append(detected.wait_ms)
                        status.timings["person_batch"].append(detected.person_ms)
                        status.timings["forklift_batch"].append(detected.forklift_ms)
                        # Cuenta resultados por tamaño de lote en esta cámara, no lotes globales.
                        status.inference_batch_sizes[detected.batch_size] += 1
                    epoch_reason, timestamp = epoch.advance(frame)
                    if epoch_reason:
                        publisher.flush()
                        pipeline.reset(epoch.number)
                        ring.clear()
                        status.epoch = epoch.number
                        status.epochs[epoch_reason] += 1
                    if detected is None:
                        annotated, candidates, inference_ms, rules_ms = pipeline.process(frame, timestamp)
                    else:
                        annotated, candidates, inference_ms, rules_ms = pipeline.process(
                            frame, timestamp, detected=detected,
                            inference_ms=detected.person_ms + detected.forklift_ms,
                        )
                    completed = monotonic()
                    status.completed.append((completed, frame.received))
                    status.timings["arrival_to_result"].append((completed - frame.received) * 1000)
                    status.timings["inference"].append(inference_ms)
                    status.timings["rules"].append(rules_ms)
                    processed_at = max(received_at, utc_now())
                    status.metrics["frames_processed"] += 1
                    status.last_frame_at = received_at.isoformat()
                    status.last_frame_received = frame.received
                    last_frame = now
                    failures_at_frame = failures
                    preview_due = now - last_preview >= PREVIEW_INTERVAL or epoch_reason is not None
                    keep_context = status.metrics["events_submitted"] < MAX_EVENTS
                    if preview_due or keep_context or publisher.waiting:
                        encoding = monotonic()
                        encoded, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        status.timings["jpeg"].append((monotonic() - encoding) * 1000)
                        if not encoded:
                            raise RuntimeError("La codificación JPEG falló")
                        data = jpeg.tobytes()
                        publisher.advance(frame.index, data)
                        if keep_context:
                            ring.append(frame.index, data)
                        if preview_due:
                            _write_atomic(args.output / "preview.jpg", data)
                            last_preview, status.preview_frame = now, frame.index
                    publisher.submit(candidates, context, received_at, processed_at, frame, epoch, ring, annotated)
                    if keep_context and status.metrics["events_submitted"] == MAX_EVENTS:
                        ring.clear()
                    status.write("processing")
        finally:
            publisher.flush()
            publisher.collect(drain=True)
    return reason


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("output", "config", "person-weights", "forklift-weights"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--seconds", type=float, default=MAX_SECONDS)
    args = parser.parse_args()
    if not args.output.is_dir():
        parser.error("--output debe ser un directorio existente")

    status = WorkerStatus(args)
    interrupted = False
    parent_closed = Event()
    snapshot_committed = Event()

    def interrupt(*_):
        nonlocal interrupted
        interrupted = True

    def stop_reason():
        if (args.output / "stop").is_file():
            return "OPERATOR_STOP"
        if interrupted:
            return "SIGNAL"
        if parent_closed.is_set():
            return "PARENT_EXIT"
        if monotonic() - status.started >= args.seconds:
            return "TIME_LIMIT"
        return None

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    supervised = os.environ.get("OPERIX_WORKER_PARENT_PIPE") == "1"
    if supervised:
        def watch_parent():
            try:
                descriptor = sys.stdin.fileno()
                if os.read(descriptor, 1) == b"\x01":
                    snapshot_committed.set()
                    os.read(descriptor, 1)
            finally:
                parent_closed.set()

        Thread(target=watch_parent, name="rtsp-parent", daemon=True).start()
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|probesize;65536|analyzeduration;250000"
    try:
        status.write("starting")
        if supervised:
            ready_deadline = monotonic() + 10
            while not snapshot_committed.wait(.05):
                if reason := stop_reason():
                    status.write("stopped", reason)
                    return 0
                if monotonic() >= ready_deadline:
                    status.write("error", "SNAPSHOT_NOT_COMMITTED")
                    return 1
        # El stderr nativo de FFmpeg puede incluir la URI con credenciales.
        with open(os.devnull, "w") as sink, redirect_stderr(sink):
            previous = os.dup(2)
            try:
                os.dup2(sink.fileno(), 2)
                reason = run(args, status, stop_reason)
            finally:
                os.dup2(previous, 2)
                os.close(previous)
        status.write("completed" if reason == "TIME_LIMIT" else "stopped", reason)
        return 0
    except Exception as error:
        reason = "INFERENCE_UNAVAILABLE" if isinstance(error, InferenceError) else "WORKER_FAILURE"
        status.write("error", reason)
        print("El Motor RTSP lab no pudo continuar.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
