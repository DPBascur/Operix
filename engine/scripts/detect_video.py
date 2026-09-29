# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Valida detección YOLO11 sobre un video y genera evidencia diagnóstica."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import cv2

from operix_engine.video_processor import RecordedVideoSource, VideoSourceError
from operix_engine.visualization import OpenCvRenderer
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--output-video", type=Path, required=True)
    parser.add_argument("--expected-video-sha256", required=True)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--iou", type=float, default=0.70)
    args = parser.parse_args()

    video_hash = sha256_file(args.video)
    if video_hash.lower() != args.expected_video_sha256.lower():
        print("Error: SHA-256 del video no coincide con el esperado", file=sys.stderr)
        return 2

    config = YoloDetectorConfig(
        weights_path=args.weights,
        confidence_threshold=args.conf,
        device=args.device,
        image_size=args.imgsz,
        iou_threshold=args.iou,
    )
    detector = YoloDetector(config)
    renderer = OpenCvRenderer()

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    args.output_video.parent.mkdir(parents=True, exist_ok=True)
    class_counts: Counter[str] = Counter()
    frames_with_detections = 0
    processed_frames = 0

    try:
        with RecordedVideoSource(args.video) as source:
            metadata = source.metadata()
            if metadata.declared_fps is None:
                raise VideoSourceError("El video no declara FPS para generar la evidencia")
            writer = cv2.VideoWriter(
                str(args.output_video),
                cv2.VideoWriter_fourcc(*"mp4v"),
                metadata.declared_fps,
                (metadata.width, metadata.height),
            )
            if not writer.isOpened():
                raise VideoSourceError("OpenCV no pudo crear el video anotado")

            try:
                with args.output_jsonl.open("w", encoding="utf-8") as output:
                    for frame_index, frame in source.frames():
                        detections = detector.detect(frame)
                        if detections:
                            frames_with_detections += 1
                        class_counts.update(detection.class_name for detection in detections)
                        output.write(
                            json.dumps(
                                {
                                    "frame_index": frame_index,
                                    "detections": [asdict(item) for item in detections],
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        writer.write(renderer.render_detections(frame, detections))
                        processed_frames += 1
            finally:
                writer.release()
    except (VideoSourceError, ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    summary = {
        "video_sha256": video_hash,
        "weights_name": args.weights.name,
        "weights_sha256": sha256_file(args.weights),
        "configuration": {
            "confidence_threshold": config.confidence_threshold,
            "device": config.device,
            "image_size": config.image_size,
            "iou_threshold": config.iou_threshold,
        },
        "processed_frames": processed_frames,
        "frames_with_detections": frames_with_detections,
        "total_detections": sum(class_counts.values()),
        "class_counts": dict(sorted(class_counts.items())),
        "model_class_names": detector.class_names,
        "output_jsonl_name": args.output_jsonl.name,
        "output_jsonl_sha256": sha256_file(args.output_jsonl),
        "output_video_name": args.output_video.name,
        "output_video_sha256": sha256_file(args.output_video),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
