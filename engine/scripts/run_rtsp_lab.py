"""Motor continuo para una fuente RTSP interna autorizada por el Backend."""

import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import signal
import sys
from time import perf_counter as monotonic
from urllib.parse import urlsplit
from uuid import UUID

import cv2
import numpy as np
import torch

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.dual_perception import ClassPerceptionChannel, DualPerception
from operix_engine.event_publishing import (
    EventContext, HttpEventSink, event_candidate_payload, publish_document_with_retries,
)
from operix_engine.operational_config import load_operational_config
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
        self.capture = None
        self.epochs = Counter()
        self.received = deque(maxlen=600)
        self.timings = {name: deque(maxlen=600) for name in ("arrival_to_result", "inference", "rules")}
        self.metrics = Counter({key: 0 for key in (
            "frames_processed", "candidates", "events_submitted", "events_published", "events_duplicate",
            "events_failed", "events_skipped_quota", "events_skipped_backpressure", "clips_saved",
            "clips_existing", "clips_unavailable", "clips_disk_limit", "clips_failed",
            "evidence_saved", "evidence_failed",
        )})
        self.preview_frame = None
        self.last_frame_at = None
        self.epoch = 0

    def capture_trace(self, kind, _connection, timestamp, **_fields):
        # Capture invoca el callback con el bloqueo de ready.
        if kind == "open":
            self.received.clear()
        elif kind == "decoded":
            self.received.append(timestamp)

    def write(self, state, reason=None):
        now = monotonic()
        if reason is None and state == self.state and now - self.last_update < STATUS_INTERVAL:
            return
        elapsed = now - self.started
        capture_counts = {}
        arrivals = []
        if self.capture is not None:
            with self.capture.ready:
                capture_counts = dict(self.capture.counts)
                arrivals = [timestamp for timestamp in self.received if now - 5 <= timestamp <= now]
        received_fps = 0.0
        if len(arrivals) >= 2 and now - arrivals[-1] <= .5 and arrivals[-1] > arrivals[0]:
            received_fps = round((len(arrivals) - 1) / (arrivals[-1] - arrivals[0]), 2)
        timing_metrics = {}
        for name, values in self.timings.items():
            timing_metrics[f"{name}_ms"] = round(values[-1], 2) if values else None
            timing_metrics[f"p95_{name}_ms"] = round(sorted(values)[math.ceil(.95 * len(values)) - 1], 2) if values else None
        api_state = {"starting": "connecting", "processing": "analyzing", "completed": "stopped"}.get(state, state)
        document = {
            "state": state, "status": api_state, "updated_at": utc_now().isoformat(), "termination_reason": reason,
            "last_frame_at": self.last_frame_at,
            "last_error": "El Motor RTSP lab no pudo continuar." if state == "error" else None,
            "analysis_run_id": self.run_id,
            "metrics": {
                **self.metrics, **timing_metrics, "elapsed_s": round(elapsed, 3), "received_fps": received_fps,
                "source_fps": self.args.fps if math.isfinite(self.args.fps) else None,
                "analysis_fps": round(self.metrics["frames_processed"] / max(elapsed, 1e-9), 2),
                "frames_dropped": sum(value for key, value in capture_counts.items() if key.endswith("_drop")),
                "width": self.args.width, "height": self.args.height, "capture": capture_counts,
                "epoch": self.epoch, "epochs": dict(self.epochs), "preview_frame": self.preview_frame,
                "event_limit": MAX_EVENTS,
            },
        }
        _write_atomic(self.args.output / "status.json", json.dumps(document, allow_nan=False).encode("utf-8"))
        self.last_update, self.state = now, state


class LabPipeline:
    def __init__(self, config, args):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA no disponible")
        checked_file(args.person_weights, PERSON_SHA, "PERSON")
        checked_file(args.forklift_weights, FORKLIFT_SHA, "FORKLIFT")
        self.perception = DualPerception(
            person=ClassPerceptionChannel("person", detector(args.person_weights, .10, .70),
                                          ByteTracker(ByteTrackConfig())),
            forklift=ClassPerceptionChannel("forklift", detector(args.forklift_weights, .45, .55),
                                            ByteTracker(ByteTrackConfig())),
        )
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

    def process(self, frame, timestamp):
        observed, timing = self.perception.process(frame.image, synchronize=torch.cuda.synchronize)
        inference_ms = (timing.person_inference_s + timing.forklift_inference_s) * 1000
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
class PendingEvent:
    payload: dict
    png: bytes
    frames: list
    last_index: int
    post_bytes: int = 0


class EventPublisher:
    def __init__(self, sink, clips, executor, metrics, fps):
        self.sink, self.clips, self.executor, self.metrics = sink, clips, executor, metrics
        self.pending = set()
        self.waiting = []
        self.post_frames = math.floor(fps)

    def _publish(self, job):
        result, _ = publish_document_with_retries(self.sink, job.payload, job.png, max_attempts=2)
        counters = {f"events_{result.status}": 1}
        counters["evidence_saved" if result.status in {"published", "duplicate"} else "evidence_failed"] = 1
        if result.event_id:
            try:
                clip_status = self.clips.save(result.event_id, job.payload, job.frames)
            except (OSError, RuntimeError, ValueError, cv2.error):
                clip_status = "failed"
            counters[f"clips_{clip_status}"] = 1
        return counters

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
                self.metrics.update(future.result())

    def submit(self, candidates, context, received_at, processed_at, frame, epoch, ring, annotated):
        self.metrics["candidates"] += len(candidates)
        png = None
        for candidate in candidates:
            if self.metrics["events_submitted"] >= MAX_EVENTS:
                self.metrics["events_skipped_quota"] += 1
            elif len(self.pending) + len(self.waiting) >= MAX_PENDING:
                self.metrics["events_skipped_backpressure"] += 1
            else:
                payload = reception_payload(candidate, context, received_at, processed_at, frame.pts, epoch.uses_pts)
                if png is None:
                    png = evidence_png(annotated)
                job = PendingEvent(payload, png, list(ring.snapshot()), frame.index + self.post_frames)
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
    pipeline = LabPipeline(config, args)
    if reason := stop_reason():
        return reason
    epoch, ring = Epoch(args.fps), JpegRing(args.fps)
    last_frame = last_preview = -math.inf
    failures_at_frame = 0
    capture = Capture(lambda: Reader(url, args.fps, pipeline.dimensions), fps=args.fps, trace=status.capture_trace)
    status.capture = capture
    status.write("connecting")
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="rtsp-event") as executor:
        publisher = EventPublisher(sink, clips, executor, status.metrics, args.fps)
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
                            status.write("processing" if epoch.number else "connecting")
                        continue
                    received_at = utc_now() - timedelta(seconds=max(0, now - frame.received))
                    epoch_reason, timestamp = epoch.advance(frame)
                    if epoch_reason:
                        publisher.flush()
                        pipeline.reset(epoch.number)
                        ring.clear()
                        status.epoch = epoch.number
                        status.epochs[epoch_reason] += 1
                    annotated, candidates, inference_ms, rules_ms = pipeline.process(frame, timestamp)
                    status.timings["arrival_to_result"].append((monotonic() - frame.received) * 1000)
                    status.timings["inference"].append(inference_ms)
                    status.timings["rules"].append(rules_ms)
                    processed_at = max(received_at, utc_now())
                    status.metrics["frames_processed"] += 1
                    status.last_frame_at = received_at.isoformat()
                    last_frame = now
                    failures_at_frame = failures
                    preview_due = now - last_preview >= PREVIEW_INTERVAL or epoch_reason is not None
                    keep_context = status.metrics["events_submitted"] < MAX_EVENTS
                    if preview_due or keep_context or publisher.waiting:
                        encoded, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
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

    def interrupt(*_):
        nonlocal interrupted
        interrupted = True

    def stop_reason():
        if (args.output / "stop").is_file():
            return "OPERATOR_STOP"
        if interrupted:
            return "SIGNAL"
        if monotonic() - status.started >= args.seconds:
            return "TIME_LIMIT"
        return None

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|probesize;65536|analyzeduration;250000"
    try:
        status.write("starting")
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
    except Exception:
        status.write("error", "WORKER_FAILURE")
        print("El Motor RTSP lab no pudo continuar.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
