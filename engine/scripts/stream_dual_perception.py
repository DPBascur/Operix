# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Procesa libremente y publica muestras JPEG indexadas por tiempo de fuente."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import cv2
import torch

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.candidate_transport import candidate_payloads
from operix_engine.event_outbox import EventOutbox
from operix_engine.event_publishing import EventContext, HttpEventSink
from operix_engine.dual_perception import ClassPerceptionChannel, DualPerception
from operix_engine.operational_config import load_operational_config
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.video_event_pipeline import _visible_tracks
from operix_engine.video_processor import RecordedVideoSource, VideoContractError, VideoSourceError, inspect_recorded_video
from operix_engine.visualization import OpenCvRenderer, TrajectoryAccumulator, VisualizationConfig
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


def _write_atomic(path: Path, data: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.01)  # Lectura concurrente breve del Backend en Windows.


def _status(directory: Path, **fields: object) -> None:
    _write_atomic(
        directory / "status.json",
        json.dumps(fields, ensure_ascii=False).encode("utf-8"),
    )


def _preview_due(frame_index, total, source_fps, previous, fps):
    """Muestrea la fuente, no el throughput; la API reproduce estas muestras a 1×."""
    if any(not math.isfinite(rate) or rate <= 0 for rate in (fps, source_fps)):
        raise ValueError("Los FPS de fuente y preview deben ser positivos y finitos")
    return (
        previous is None or frame_index == 0 or frame_index + 1 == total
        or math.floor(frame_index * fps / source_fps + 1e-9)
        > math.floor(previous * fps / source_fps + 1e-9)
    )


def _validated_zone(config, polygon_path: Path | None):
    if polygon_path is None:
        return config
    points = json.loads(polygon_path.read_text(encoding="utf-8"))
    if len(config.zones) != 1:
        raise ValueError("El editor requiere exactamente una zona en el perfil")
    zone = replace(config.zones[0], polygon=tuple(tuple(point) for point in points))
    # La pertenencia valida lados, área y autointersecciones con el mismo Motor.
    from operix_engine.zone_geometry import NormalizedPoint, point_in_zone

    point_in_zone(NormalizedPoint(0, 0), zone)
    return replace(config, zones=(zone,))


def _publish_preview(frame, directory: Path, frame_index: int, width: int) -> None:
    preview = frame
    if width and frame.shape[1] > width:
        height = round(frame.shape[0] * width / frame.shape[1])
        preview = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    success, encoded = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not success:
        raise RuntimeError("No se pudo codificar el frame de preview")
    # JPEG comprimidos en disco temporal; no se acumulan frames raw en RAM.
    _write_atomic(directory / f"{frame_index:09d}.jpg", encoded.tobytes())


def _analyzed_batches(frames, perception, batch_size, synchronize):
    """Lectura acotada; nunca omite frames ni reordena tracking/análisis."""
    if type(batch_size) is not int or batch_size <= 0:
        raise ValueError("batch_size debe ser entero positivo")
    iterator = iter(frames)
    while True:
        batch = []
        for _ in range(batch_size):
            tick = time.perf_counter_ns()
            try:
                index, frame = next(iterator)
            except StopIteration:
                break
            batch.append((index, frame, (time.perf_counter_ns() - tick) / 1e6))
        if not batch:
            return
        if batch_size == 1:
            results = (perception.process(batch[0][1], synchronize=synchronize),)
        else:
            results = perception.process_batch(
                tuple(item[1] for item in batch), synchronize=synchronize,
            )
        yield tuple((index, frame, observed, timing, decode_ms)
                    for (index, frame, decode_ms), (observed, timing)
                    in zip(batch, results, strict=True))


def _analyzed_frames(frames, perception, batch_size, synchronize):
    """Solapa un lote siguiente con render/IPC del actual; memoria acotada a dos."""
    batches = iter(_analyzed_batches(frames, perception, batch_size, synchronize))
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="operix-perception") as pool:
        future = pool.submit(next, batches, None)
        try:
            while True:
                batch = future.result()
                if batch is None:
                    return
                future = pool.submit(next, batches, None)
                yield from batch
        finally:
            future.cancel()


def _release_analysis_resources(frames, writer) -> None:
    """Intenta ambos cierres y conserva todos los errores, incluido el de análisis."""
    original = sys.exception()
    failures = []
    for close in (frames.close, writer.release):
        try:
            close()
        except BaseException as error:
            failures.append(error)
    if failures:
        if original is not None:
            raise BaseExceptionGroup("Falló el análisis y su cleanup", [original, *failures]) from None
        if len(failures) == 1:
            raise failures[0]
        raise BaseExceptionGroup("Fallaron ambos cierres del análisis", failures)


def process(args: argparse.Namespace) -> None:
    from run_dual_perception import checked_file, model_identity

    checked_file(args.person_weights, args.person_sha256, "person_weights")
    checked_file(args.forklift_weights, args.forklift_sha256, "forklift_weights")
    _status(args.session_dir, state="preparing", frame=0, total=None, percent=None,
            detail="Verificando integridad y cadencia del video")
    inspection = inspect_recorded_video(args.video)
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA no está disponible para ambos detectores")
    config = _validated_zone(load_operational_config(args.config), args.polygon)
    outbox = None
    context = None
    persistence = {"state": "disabled", "candidates": 0, "saved": 0, "failed": 0}
    if getattr(args, "event_context", None):
        document = json.loads(args.event_context.read_text(encoding="utf-8"))
        context = EventContext(UUID(document["analysis_run_id"]), config.view_id,
                               datetime.fromisoformat(document["analysis_started_at"]), document["source"])
        outbox = EventOutbox(args.event_context.parent, HttpEventSink(document["api_url"], local_only=True))
        persistence = {"state": "pending", "candidates": 0, "saved": 0, "failed": 0}
    visual = VisualizationConfig(max_trajectory_points=60, inactive_retention_frames=30)
    renderer = OpenCvRenderer(visual)
    histories = {name: TrajectoryAccumulator(visual) for name in ("person", "forklift")}

    def channel(name: str, weights: Path, confidence: float, iou: float):
        detector = YoloDetector(YoloDetectorConfig(
            weights, confidence_threshold=confidence, device="cuda",
            image_size=640, iou_threshold=iou,
        ))
        return ClassPerceptionChannel(name, detector, ByteTracker(ByteTrackConfig()))

    perception = DualPerception(
        person=channel("person", args.person_weights, 0.10, 0.70),
        forklift=channel("forklift", args.forklift_weights, 0.45, 0.55),
    )
    with RecordedVideoSource(args.video) as source:
        metadata = source.metadata()
        if metadata != inspection.metadata:
            raise VideoContractError("INVALID_METADATA", "La fuente cambió después de la verificación")
        partial_result = args.session_dir / "annotated.partial.mp4"
        final_result = args.session_dir / "annotated.mp4"
        writer = cv2.VideoWriter(
            str(partial_result), cv2.VideoWriter_fourcc(*"avc1"),
            metadata.declared_fps, (metadata.width, metadata.height),
        )
        if not writer.isOpened():
            writer.release()
            raise RuntimeError("Este equipo no dispone de un codificador H.264 para el resultado")
        output_backend = writer.getBackendName()
        analyzer = SpatiotemporalAnalyzer(
            width=metadata.width, height=metadata.height,
            fps=metadata.declared_fps, zones=config.zones,
            proximity_roles=config.proximity_roles,
        )
        rules = RuleEngine(config)
        started = time.perf_counter()
        total = inspection.frame_count
        processed = 0
        observed = None
        totals_ms = {name: 0.0 for name in (
            "decode", "person_detector", "forklift_detector", "tracking",
            "rules", "renderer", "jpeg", "video_write", "status_ipc",
        )}
        measured = 0
        batch_size = getattr(args, "batch_size", 4)
        frames = iter(_analyzed_frames(source.frames(), perception, batch_size, torch.cuda.synchronize))
        last_preview = None
        preview_fps = getattr(args, "preview_fps", 10.0)
        preview_dir = args.session_dir / "preview"
        preview_dir.mkdir(exist_ok=True)
        try:
            while True:
                try:
                    entry = next(frames)
                except StopIteration:
                    break
                frame_index, frame, observed, timing, decode_ms = entry
                if frame_index != processed or frame_index >= total:
                    raise VideoContractError("INVALID_METADATA", "La segunda lectura no coincide con la verificación")
                if frame_index == 0:
                    devices = (
                        perception.person.detector.model_device,
                        perception.forklift.detector.model_device,
                    )
                    if any(not device.startswith("cuda") for device in devices):
                        raise RuntimeError("Un detector no quedó en CUDA")
                tick = time.perf_counter_ns()
                visible_tracks, _, _ = _visible_tracks(
                    observed.person_tracks + observed.forklift_tracks,
                    metadata.width, metadata.height,
                )
                spatial = analyzer.update(
                    frame_index, visible_tracks, timestamp_s=inspection.timestamps[frame_index],
                )
                result = rules.evaluate(spatial)
                frame_candidates = candidate_payloads(result.candidates)
                rules_ms = (time.perf_counter_ns() - tick) / 1e6
                tick = time.perf_counter_ns()
                annotated = frame
                for zone in config.zones:
                    event = any(item.zone_id == zone.zone_id for item in result.candidates)
                    annotated = renderer.render_zone(annotated, zone, event=event)
                for name in ("person", "forklift"):
                    tracks = getattr(observed, f"{name}_tracks")
                    annotated = renderer.render_tracks(
                        annotated, tracks, histories[name].update(frame_index, tracks),
                    )
                annotated = renderer.render_proximity(annotated, spatial, result)
                renderer_ms = (time.perf_counter_ns() - tick) / 1e6
                if outbox is not None and result.candidates:
                    image = annotated
                    height, width = image.shape[:2]
                    if max(width, height) > 960:
                        scale = 960 / max(width, height)
                        image = cv2.resize(image, (round(width * scale), round(height * scale)))
                    try:
                        encoded, png = cv2.imencode(".png", image)
                    except cv2.error:
                        encoded, png = False, None
                    evidence = png.tobytes() if encoded and png is not None else None
                    if evidence is not None and len(evidence) > 2 * 1024 * 1024:
                        evidence = None
                    outbox.enqueue(result.candidates, context, evidence, fallback_frame=image)
                    persistence = outbox.summary()
                tick = time.perf_counter_ns()
                writer.write(annotated)
                video_write_ms = (time.perf_counter_ns() - tick) / 1e6
                tick = time.perf_counter_ns()
                if _preview_due(frame_index, total, metadata.declared_fps, last_preview, preview_fps):
                    _publish_preview(annotated, preview_dir, frame_index, args.preview_width)
                    last_preview = frame_index
                jpeg_ms = (time.perf_counter_ns() - tick) / 1e6
                processed = frame_index + 1
                if frame_index >= 20:
                    measured += 1
                    stage = {
                        "decode": decode_ms,
                        "person_detector": timing.person_inference_s * 1000,
                        "forklift_detector": timing.forklift_inference_s * 1000,
                        "tracking": (timing.person_tracking_s + timing.forklift_tracking_s) * 1000,
                        "rules": rules_ms, "renderer": renderer_ms,
                        "jpeg": jpeg_ms, "video_write": video_write_ms,
                    }
                    for name, milliseconds in stage.items():
                        totals_ms[name] += milliseconds
                elapsed = max(time.perf_counter() - started, 1e-9)
                tick = time.perf_counter_ns()
                _status(
                    args.session_dir, state="processing", frame=processed, total=total,
                    percent=min(99.9, round(100 * processed / total, 1)),
                    fps=round(processed / elapsed, 2), width=metadata.width,
                    height=metadata.height, source_fps=metadata.declared_fps,
                    preview_sample_fps=preview_fps, preview_latest_frame=last_preview,
                    person_detections=len(observed.person_detections),
                    forklift_detections=len(observed.forklift_detections),
                    person_tracks=len(observed.person_tracks),
                    forklift_tracks=len(observed.forklift_tracks),
                    candidates=frame_candidates, persistence=persistence,
                    declared_frame_count=metadata.declared_frame_count,
                    timestamp_source=inspection.timestamp_source, warnings=inspection.warnings,
                )
                if frame_index >= 20:
                    totals_ms["status_ipc"] += (time.perf_counter_ns() - tick) / 1e6
            if processed != total:
                raise VideoContractError("TRUNCATED_INPUT", "La lectura terminó antes del total previamente verificado")
            if last_preview != processed - 1:
                # También termina correctamente cuando la fuente no declaró su cantidad de frames.
                _publish_preview(annotated, preview_dir, processed - 1, args.preview_width)
                last_preview = processed - 1
        finally:
            _release_analysis_resources(frames, writer)
        capture = cv2.VideoCapture(str(partial_result))
        try:
            encoded_frames = int(round(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
            encoded_fps = float(capture.get(cv2.CAP_PROP_FPS))
            encoded_width = int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
            encoded_height = int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            decoded_frames = 0
            while True:
                decoded, _ = capture.read()
                if not decoded:
                    break
                decoded_frames += 1
        finally:
            capture.release()
        if (decoded_frames != processed or encoded_frames != processed or
                abs(encoded_fps - metadata.declared_fps) > 0.1 or
                (encoded_width, encoded_height) != (metadata.width, metadata.height)):
            raise RuntimeError("El MP4 H.264 final no conservó frames, FPS o resolución")
        os.replace(partial_result, final_result)
        if outbox is not None:
            outbox.enqueue((), context, None)
            persistence = outbox.summary()
        _status(
            args.session_dir, state="completed", frame=processed,
            total=processed, percent=100, fps=round(processed / max(time.perf_counter() - started, 1e-9), 2),
            termination_reason="NORMAL_EOF", declared_frame_count=metadata.declared_frame_count,
            timestamp_source=inspection.timestamp_source, warnings=inspection.warnings,
            width=metadata.width, height=metadata.height,
            source_fps=metadata.declared_fps,
            preview_sample_fps=preview_fps, preview_latest_frame=last_preview,
            person_detections=len(observed.person_detections),
            forklift_detections=len(observed.forklift_detections),
            person_tracks=len(observed.person_tracks),
            forklift_tracks=len(observed.forklift_tracks),
            candidates=frame_candidates, persistence=persistence,
            result_video={"codec": "H.264/avc1", "encoder_backend": output_backend,
                          "fps": encoded_fps, "frames": encoded_frames,
                          "width": encoded_width, "height": encoded_height},
            timing_ms={name: round(value / measured, 3) for name, value in totals_ms.items()}
            if measured else None,
            model_identities={"person": model_identity(args.person_sha256),
                              "forklift": model_identity(args.forklift_sha256)},
            profiling_frames=measured,
            performance={"detection_batch_size": batch_size, "preview_target_fps": preview_fps,
                         "detector_timing": "amortized batch milliseconds per frame"},
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--polygon", type=Path)
    parser.add_argument("--person-weights", required=True, type=Path)
    parser.add_argument("--person-sha256", required=True)
    parser.add_argument("--forklift-weights", required=True, type=Path)
    parser.add_argument("--forklift-sha256", required=True)
    parser.add_argument("--preview-width", type=int, default=1280)
    parser.add_argument("--preview-fps", type=float, default=10.0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--event-context", type=Path)
    args = parser.parse_args()
    try:
        process(args)
    except Exception as error:
        _write_atomic(args.session_dir / "error.log", traceback.format_exc().encode("utf-8"))
        try:
            previous = json.loads((args.session_dir / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            previous = {}
        previous.pop("result_video", None)
        previous.update(state="error", detail="El Motor no pudo procesar el video o la zona.",
                        termination_reason=error.reason if isinstance(error, VideoContractError) else
                        "DECODE_FAILURE" if isinstance(error, VideoSourceError) else "PROCESSING_FAILURE")
        if previous.get("percent") is not None:
            previous["percent"] = min(99.9, previous["percent"])
        _status(args.session_dir, **previous)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
