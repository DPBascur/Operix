"""Piloto local RTSP. La URL y los permisos de red los administra el operador."""

import argparse
from collections import Counter, deque
from contextlib import nullcontext, redirect_stderr
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter as monotonic
from urllib.parse import urlsplit
from uuid import uuid4

import cv2
import numpy as np
import torch

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.candidate_transport import candidate_payloads
from operix_engine.dual_perception import ClassPerceptionChannel, DualPerception
from operix_engine.operational_config import load_operational_config
from operix_engine.rtsp_pilot import Capture, Epoch
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.video_event_pipeline import _visible_tracks
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig
from run_dual_perception import checked_file

PERSON_SHA = "d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95"
FORKLIFT_SHA = "1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6"


def authorized_url():
    if os.environ.get("OPERIX_RTSP_PILOT") != "1":
        raise ValueError("Piloto deshabilitado")
    url = os.environ.get("OPERIX_RTSP_URL", "")
    parsed = urlsplit(url)
    allowed = ipaddress.ip_address(os.environ.get("OPERIX_RTSP_ALLOWED_IP", "127.0.0.1"))
    if (parsed.scheme != "rtsp" or not parsed.hostname or ipaddress.ip_address(parsed.hostname) != allowed
            or parsed.fragment or (parsed.port is not None and parsed.port == 0)):
        raise ValueError("Fuente fuera de la autorización local")
    return url


class Reader:
    def __init__(self, url, fps, dimensions):
        self.fps, self.dimensions = fps, dimensions
        self.capture = cv2.VideoCapture()
        try:
            opened = self.capture.open(url, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2500, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1500,
                cv2.CAP_PROP_N_THREADS, 1,
            ])
            if not opened or not math.isclose(self.capture.get(cv2.CAP_PROP_FPS), fps, abs_tol=.2):
                raise OSError("Apertura o cadencia RTSP inválida")
        except (cv2.error, OSError):
            self.close()
            raise OSError("Apertura RTSP fallida") from None

    def read(self):
        try:
            ok, image = self.capture.read()
            if not ok or image.shape[:2][::-1] != self.dimensions:
                raise OSError("Lectura o dimensiones inválidas")
            # FFmpeg expone PTS en unidades del FPS. Cero también puede indicar falta de soporte.
            ticks = self.capture.get(cv2.CAP_PROP_PTS)
            pts = ticks / self.fps if math.isfinite(ticks) and ticks > 0 else None
            return image, pts
        except cv2.error:
            raise OSError("Decodificación RTSP fallida") from None

    def close(self):
        self.capture.release()


def detector(path, confidence, iou):
    return YoloDetector(YoloDetectorConfig(path, confidence_threshold=confidence, device="cuda",
                                          image_size=640, iou_threshold=iou))


def percentile(values):
    return sorted(values)[math.ceil(len(values) * .95) - 1] if values else None


def run(args, url):
    if not 0 < args.seconds <= 1800 or not 0 < args.width <= 1920 or not 0 < args.height <= 1080:
        raise ValueError("Límites de sesión inválidos")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA no disponible")
    checked_file(args.person_weights, PERSON_SHA, "PERSON")
    checked_file(args.forklift_weights, FORKLIFT_SHA, "FORKLIFT")
    # checked_file verifica la huella. Los paths de entrada se usan para cargar los pesos.
    models = (detector(args.person_weights, .10, .70), detector(args.forklift_weights, .45, .55))
    perception = DualPerception(person=ClassPerceptionChannel("person", models[0], ByteTracker(ByteTrackConfig())),
                               forklift=ClassPerceptionChannel("forklift", models[1], ByteTracker(ByteTrackConfig())))
    warmed = monotonic()
    perception.process(np.zeros((args.height, args.width, 3), dtype=np.uint8),
                       synchronize=torch.cuda.synchronize)
    warmup_ms = (monotonic() - warmed) * 1000
    snapshot = args.config.read_bytes()
    args.output.mkdir()
    (args.output / "config.json").write_bytes(snapshot)
    config = load_operational_config(args.output / "config.json")
    if config.calibration or (config.motion and config.motion.unit == "m"):
        raise ValueError("El piloto RTSP no admite calibraciones ligadas a archivos; requiere asociación de fuente validada")
    run_id = str(uuid4())
    config_hash = hashlib.sha256(snapshot).hexdigest()
    analyzer = SpatiotemporalAnalyzer(width=args.width, height=args.height, fps=args.fps,
                                      zones=config.zones, proximity_roles=config.proximity_roles, motion=config.motion)
    rules, epoch = RuleEngine(config), Epoch(args.fps)
    epochs = Counter()
    samples, ages, services = (deque(maxlen=8192) for _ in range(3))
    processed = candidates = 0
    started = monotonic()
    termination = "duration"
    diagnostic = ((args.output / "capture.ndjson").open("w", encoding="utf-8")
                  if args.trace_capture else nullcontext())

    def trace(kind, connection, timestamp, **fields):
        capture_log.write(json.dumps({"kind": kind, "connection": connection,
                                      "monotonic_s": timestamp, **fields}) + "\n")

    with (args.output / "frames.ndjson").open("w", encoding="utf-8") as frames, (
            args.output / "candidates.ndjson").open("w", encoding="utf-8") as events, diagnostic as capture_log:
        capture = Capture(lambda: Reader(url, args.fps, (args.width, args.height)),
                          fps=args.fps, trace=trace if capture_log else None)
        try:
            with capture:
                while monotonic() - started < args.seconds:
                    frame = capture.next()
                    if frame is None:
                        continue
                    began = monotonic()
                    reason, timestamp = epoch.advance(frame)
                    if reason:
                        epochs[reason] += 1
                        perception.person.tracker.reset()
                        perception.forklift.tracker.reset()
                        analyzer.reset(epoch=epoch.number)
                        rules.reset()
                    inference_started = monotonic()
                    observed, _ = perception.process(frame.image, synchronize=torch.cuda.synchronize)
                    inference_ended = monotonic()
                    tracks, _, _ = _visible_tracks(observed.person_tracks + observed.forklift_tracks,
                                                   args.width, args.height)
                    result = rules.evaluate(analyzer.update(frame.index, tracks, timestamp_s=timestamp))
                    ended = monotonic()
                    age = (began - frame.received) * 1000
                    latency = (ended - frame.received) * 1000
                    ages.append(age)
                    samples.append(latency)
                    services.append((ended - began) * 1000)
                    processed += 1
                    record = {"run_id": run_id, "epoch": epoch.number, "frame_index": frame.index,
                              "connection": frame.connection, "source_pts_s": frame.pts,
                              "received_monotonic_s": frame.received, "epoch_time_s": timestamp,
                              "time_basis": "source_pts" if epoch.uses_pts else "local_arrival",
                              "epoch_reason": reason, "queue_depth_at_arrival": frame.queue_depth,
                              "queue_age_ms": age, "arrival_to_result_ms": latency}
                    if args.trace_capture:
                        record.update(consume_monotonic_s=began, result_monotonic_s=ended,
                                      perception_ms=(inference_ended - inference_started) * 1000)
                    frames.write(json.dumps(record) + "\n")
                    for candidate in candidate_payloads(result.candidates):
                        candidates += 1
                        events.write(json.dumps({**record, "config_sha256": config_hash,
                                                 "candidate": candidate}) + "\n")
                    if reason or processed % 12 == 0:
                        frames.flush()
                        events.flush()
        except KeyboardInterrupt:
            termination = "operator_stop"
    wall = monotonic() - started
    summary = {"run_id": run_id, "config_sha256": config_hash, "models": [PERSON_SHA, FORKLIFT_SHA],
               "termination": termination, "seconds": wall, "processed": processed, "candidates": candidates,
               "width": args.width, "height": args.height, "source_fps": args.fps,
               "effective_fps": processed / wall, "counters": dict(capture.counts),
               "warmup_ms": warmup_ms,
               "epochs": dict(epochs), "max_queue": capture.depth, "samples": len(samples),
               "p95_queue_age_ms": percentile(ages), "p95_arrival_to_result_ms": percentile(samples),
               "p95_service_ms": percentile(services)}
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return processed > 0 or termination == "operator_stop"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("config", "output", "person-weights", "forklift-weights"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--trace-capture", action="store_true")
    args = parser.parse_args()
    try:
        url = authorized_url()
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|probesize;65536|analyzeduration;250000"
        # FFmpeg puede escribir la URI completa en stderr, incluso por fuera de Python.
        with open(os.devnull, "w") as sink, redirect_stderr(sink):
            previous = os.dup(2)
            try:
                os.dup2(sink.fileno(), 2)
                return 0 if run(args, url) else 1
            finally:
                os.dup2(previous, 2)
                os.close(previous)
    except Exception:
        print("Piloto no iniciado o interrumpido. Revise habilitación, autorización, configuración y CUDA.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
