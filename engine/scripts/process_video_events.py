# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ejecuta video, detección, tracking, regla y publicación local con frame real."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.event_publishing import EventContext, HttpEventSink
from operix_engine.operational_config import load_operational_config
from operix_engine.video_event_pipeline import run_video_event_pipeline
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Fecha ISO 8601 inválida") from error
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("La fecha requiere zona horaria explícita")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--expected-video-sha256", required=True)
    parser.add_argument("--expected-weights-sha256", required=True)
    parser.add_argument("--analysis-run-id", type=UUID, required=True)
    parser.add_argument("--recording-start-at", type=_datetime, required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--iou", type=float, default=0.70)
    args = parser.parse_args()

    parsed_url = urlparse(args.api_base_url)
    if parsed_url.scheme != "http" or parsed_url.hostname not in ("localhost", "127.0.0.1"):
        parser.error("La demostración solo permite API HTTP en localhost")
    for name, path, expected in (
        ("video", args.video, args.expected_video_sha256),
        ("pesos", args.weights, args.expected_weights_sha256),
    ):
        if not path.is_file() or _sha256(path).lower() != expected.lower():
            parser.error(f"{name}: archivo ausente o SHA-256 distinto")

    config = load_operational_config(args.config)
    context = EventContext(args.analysis_run_id, config.view_id, args.recording_start_at)
    detector = YoloDetector(YoloDetectorConfig(
        args.weights, confidence_threshold=args.conf, device="cuda",
        image_size=args.imgsz, iou_threshold=args.iou,
    ))
    tracker = ByteTracker(ByteTrackConfig())
    sink = HttpEventSink(args.api_base_url)
    summary = run_video_event_pipeline(
        args.video, detector=detector, tracker=tracker, config=config, sink=sink, context=context
    )
    summary["video_sha256"] = _sha256(args.video)
    summary["weights_name"] = args.weights.name
    summary["weights_sha256"] = _sha256(args.weights)
    summary["detector_configuration"] = {
        "model": args.weights.name,
        "device": "cuda", "confidence_threshold": args.conf,
        "image_size": args.imgsz, "iou_threshold": args.iou,
        "class_filter": "person",
    }
    summary["tracker_configuration"] = {
        "track_high_thresh": tracker.config.track_high_thresh,
        "track_low_thresh": tracker.config.track_low_thresh,
        "new_track_thresh": tracker.config.new_track_thresh,
        "track_buffer": tracker.config.track_buffer,
        "match_thresh": tracker.config.match_thresh,
        "fuse_score": tracker.config.fuse_score,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["candidate_count"] and summary["published_count"] == summary["candidate_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
