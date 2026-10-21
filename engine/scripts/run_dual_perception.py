# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Diagnóstico local de person + forklift, sin publicar eventos ni abrir TEST2."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import cv2
import torch

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.candidate_transport import candidate_payloads
from operix_engine.dual_perception import ClassPerceptionChannel, DualPerception
from operix_engine.operational_config import load_operational_config
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.video_event_pipeline import _visible_tracks
from operix_engine.video_processor import RecordedVideoSource
from operix_engine.visualization import OpenCvRenderer, TrajectoryAccumulator, VisualizationConfig
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_file(path: Path | None, expected: str | None, label: str) -> str:
    if path is None or not path.is_file():
        raise ValueError(f"{label}: archivo local ausente")
    if expected is None or len(expected) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected):
        raise ValueError(f"{label}: SHA-256 esperado inválido")
    actual = sha256_file(path)
    if actual.lower() != expected.lower():
        raise ValueError(f"{label}: SHA-256 distinto al esperado")
    return actual


def run(args: argparse.Namespace) -> dict[str, object]:
    repository = Path(__file__).resolve().parents[2]
    output = args.output_dir.resolve()
    if output == repository or repository in output.parents:
        raise ValueError("Las salidas diagnósticas deben permanecer fuera del repositorio")
    if output.exists():
        raise ValueError("El directorio de salida ya existe; no se sobrescriben artefactos")
    if args.disable_person and args.disable_forklift:
        raise ValueError("Debe permanecer activo al menos un detector")
    video_hash = checked_file(args.video, args.expected_video_sha256, "video")
    weight_hashes = {}
    if not args.disable_person:
        weight_hashes["person"] = checked_file(
            args.person_weights, args.expected_person_sha256, "person_weights"
        )
    if not args.disable_forklift:
        weight_hashes["forklift"] = checked_file(
            args.forklift_weights, args.expected_forklift_sha256, "forklift_weights"
        )
    config = load_operational_config(args.config)
    tracker_config = ByteTrackConfig()

    def channel(name: str, weights: Path, confidence: float, iou: float) -> ClassPerceptionChannel:
        detector = YoloDetector(YoloDetectorConfig(
            weights, confidence_threshold=confidence, device=args.device,
            image_size=640, iou_threshold=iou,
        ))
        return ClassPerceptionChannel(name, detector, ByteTracker(tracker_config))

    person = None if args.disable_person else channel("person", args.person_weights, args.person_conf, args.person_iou)
    forklift = None if args.disable_forklift else channel("forklift", args.forklift_weights, args.forklift_conf, args.forklift_iou)
    perception = DualPerception(person=person, forklift=forklift)
    visual_config = VisualizationConfig(max_trajectory_points=60, inactive_retention_frames=30)
    renderer = OpenCvRenderer(visual_config)
    histories = {"person": TrajectoryAccumulator(visual_config), "forklift": TrajectoryAccumulator(visual_config)}
    detections = {"person": 0, "forklift": 0}
    seen_frames = {"person": 0, "forklift": 0}
    track_observations: dict[str, dict[int, list[int]]] = {
        "person": defaultdict(list), "forklift": defaultdict(list),
    }
    times = defaultdict(float)
    candidates = []
    capture_names = []
    missing_frames = {"person": [], "forklift": []}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    started = time.perf_counter()
    if args.device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA no está disponible")
        torch.cuda.reset_peak_memory_stats()
    with RecordedVideoSource(args.video) as source:
        metadata = source.metadata()
        if metadata.declared_fps is None:
            raise ValueError("El video debe declarar FPS")
        analyzer = SpatiotemporalAnalyzer(
            width=metadata.width, height=metadata.height,
            fps=metadata.declared_fps, zones=config.zones,
        )
        rules = RuleEngine(config)
        writer = cv2.VideoWriter(
            str(output / "annotated.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
            metadata.declared_fps, (metadata.width, metadata.height),
        )
        if not writer.isOpened():
            raise OSError("No se pudo abrir VideoWriter")
        processed = 0
        try:
            with (output / "observations.jsonl").open("w", encoding="utf-8") as jsonl:
                for frame_index, frame in source.frames():
                    if frame_index != processed:
                        raise ValueError("Índices de frame no consecutivos")
                    observed, timing = perception.process(
                        frame, synchronize=torch.cuda.synchronize if args.device == "cuda" else None,
                    )
                    for name in ("person", "forklift"):
                        times[f"{name}_inference_s"] += getattr(timing, f"{name}_inference_s")
                        times[f"{name}_tracking_s"] += getattr(timing, f"{name}_tracking_s")
                        current_detections = getattr(observed, f"{name}_detections")
                        current_tracks = getattr(observed, f"{name}_tracks")
                        detections[name] += len(current_detections)
                        seen_frames[name] += bool(current_detections)
                        if not current_detections:
                            missing_frames[name].append(frame_index)
                        for track in current_tracks:
                            track_observations[name][track.track_id].append(frame_index)
                    # Conservar IDs locales: el analizador distingue (clase, track_id).
                    visible_tracks, _, _ = _visible_tracks(
                        observed.person_tracks + observed.forklift_tracks,
                        metadata.width, metadata.height,
                    )
                    spatial = analyzer.update(frame_index, visible_tracks)
                    rule_result = rules.evaluate(spatial)
                    frame_candidates = candidate_payloads(rule_result.candidates)
                    candidates.extend(frame_candidates)
                    jsonl.write(json.dumps({
                        "frame_index": frame_index,
                        "candidates": frame_candidates,
                        "detections": {
                            name: [asdict(item) for item in getattr(observed, f"{name}_detections")]
                            for name in ("person", "forklift")
                        },
                        "tracks": {
                            name: [asdict(item) | {"identity": f"{name}:{item.track_id}"}
                                   for item in getattr(observed, f"{name}_tracks")]
                            for name in ("person", "forklift")
                        },
                    }, ensure_ascii=False) + "\n")
                    render_start = time.perf_counter()
                    annotated = frame
                    for zone in config.zones:
                        zone_candidate = next(
                            (item for item in frame_candidates if item["zone_id"] == zone.zone_id), None,
                        )
                        event = zone_candidate is not None
                        annotated = renderer.render_zone(
                            annotated, zone, event=event,
                            rule_kind=zone_candidate["candidate_kind"] if event else None,
                            frame_index=frame_index if event else None,
                        )
                    for name in ("person", "forklift"):
                        tracks = getattr(observed, f"{name}_tracks")
                        history = histories[name].update(frame_index, tracks)
                        annotated = renderer.render_tracks(annotated, tracks, history)
                    times["rendering_s"] += time.perf_counter() - render_start
                    if frame_index in args.capture_frames and observed.person_tracks and observed.forklift_tracks:
                        name = f"frame-{frame_index:04d}.png"
                        if not cv2.imwrite(str(output / name), annotated):
                            raise OSError("No se pudo guardar la captura diagnóstica")
                        capture_names.append(name)
                    write_start = time.perf_counter()
                    writer.write(annotated)
                    times["writing_s"] += time.perf_counter() - write_start
                    processed += 1
        finally:
            writer.release()
    elapsed = time.perf_counter() - started
    devices = {
        name: channel.detector.model_device
        for name, channel in (("person", person), ("forklift", forklift)) if channel is not None
    }
    if args.device == "cuda" and any(not device.startswith("cuda") for device in devices.values()):
        raise RuntimeError(f"Un modelo no quedó en GPU: {devices}")
    track_stats = {}
    for name in ("person", "forklift"):
        observations = track_observations[name]
        track_stats[name] = {
            "detections": detections[name], "frames_with_detection": seen_frames[name],
            "frames_without_detection": missing_frames[name],
            "track_observations": sum(map(len, observations.values())),
            "unique_track_ids": len(observations),
            "track_gaps": sum(
                current - previous - 1
                for frames in observations.values()
                for previous, current in zip(frames, frames[1:]) if current > previous + 1
            ),
            "track_gap_episodes": sum(
                current > previous + 1
                for frames in observations.values()
                for previous, current in zip(frames, frames[1:])
            ),
        }
    summary = {
        "video_name": args.video.name, "video_sha256": video_hash,
        "processed_frames": processed, "declared_frames": metadata.declared_frame_count,
        "width": metadata.width, "height": metadata.height, "source_fps": metadata.declared_fps,
        "elapsed_s": elapsed, "effective_fps": processed / elapsed,
        "model_devices": devices, "weight_sha256": weight_hashes,
        "config_name": args.config.name,
        "detector_config": {
            "person": {"imgsz": 640, "confidence": args.person_conf, "nms_iou": args.person_iou},
            "forklift": {"imgsz": 640, "confidence": args.forklift_conf, "nms_iou": args.forklift_iou},
        },
        "tracker_config": asdict(tracker_config), "by_class": track_stats,
        "candidate_count": len(candidates), "candidates": candidates,
        "stage_seconds": dict(times), "captures": capture_names,
        "gpu_memory_bytes": {
            "allocated": torch.cuda.memory_allocated(),
            "reserved": torch.cuda.memory_reserved(),
            "peak_allocated": torch.cuda.max_memory_allocated(),
            "peak_reserved": torch.cuda.max_memory_reserved(),
        } if args.device == "cuda" else None,
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-video-sha256", required=True)
    parser.add_argument("--person-weights", type=Path)
    parser.add_argument("--expected-person-sha256")
    parser.add_argument("--forklift-weights", type=Path)
    parser.add_argument("--expected-forklift-sha256")
    parser.add_argument("--disable-person", action="store_true")
    parser.add_argument("--disable-forklift", action="store_true")
    parser.add_argument("--person-conf", type=float, default=0.10)
    parser.add_argument("--person-iou", type=float, default=0.70)
    parser.add_argument("--forklift-conf", type=float, default=0.45)
    parser.add_argument("--forklift-iou", type=float, default=0.55)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--capture-frames", type=int, nargs="*", default=())
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
