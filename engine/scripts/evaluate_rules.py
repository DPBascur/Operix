# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reproduce OP-38 sobre un JSONL de tracks existente, sin inferencia ni video."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import load_operational_config
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_jsonl", type=Path)
    parser.add_argument("--expected-jsonl-sha256", required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--view-id", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--fps", type=float, required=True)
    parser.add_argument("--end-frame", type=int, required=True)
    args = parser.parse_args()

    if args.end_frame < 0:
        parser.error("--end-frame debe ser no negativo")

    if _sha256(args.input_jsonl).lower() != args.expected_jsonl_sha256.lower():
        parser.error("SHA-256 del JSONL no coincide")
    config = load_operational_config(args.config)
    if config.view_id != args.view_id:
        parser.error("La vista de la configuración no coincide con --view-id")
    analyzer = SpatiotemporalAnalyzer(
        width=args.width, height=args.height, fps=args.fps, zones=config.zones
    )
    engine = RuleEngine(config)
    expected_frame = 0
    candidates = []
    with args.input_jsonl.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            frame_index = record["frame_index"]
            if frame_index > args.end_frame:
                break
            if frame_index != expected_frame:
                raise ValueError(f"Frame esperado {expected_frame}; recibido {frame_index}")
            tracks = tuple(
                Track(
                    track_id=item["track_id"],
                    class_id=item["class_id"],
                    class_name=item["class_name"],
                    confidence=item["confidence"],
                    bounding_box=BoundingBox(**item["bounding_box"]),
                )
                for item in record["tracks"]
            )
            result = engine.evaluate(analyzer.update(frame_index, tracks))
            candidates.extend(
                {
                    "rule_id": candidate.rule_id,
                    "rule_version": candidate.rule_version,
                    "frame_index": candidate.frame_index,
                    "timestamp_s": candidate.timestamp_s,
                    "track_id": candidate.track_id,
                    "class_name": candidate.class_name,
                    "zone_id": candidate.zone_id,
                    "parameters": dict(candidate.parameters),
                    "observed_inside": candidate.observed_inside,
                    "observed_dwell_time_s": candidate.observed_dwell_time_s,
                }
                for candidate in result.candidates
            )
            expected_frame += 1
    if expected_frame != args.end_frame + 1:
        raise ValueError(f"Faltan frames desde {expected_frame} hasta {args.end_frame}")
    print(json.dumps({"frames": expected_frame, "candidates": candidates}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
