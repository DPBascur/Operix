# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reproduce OP-38 sobre tracks; captura técnica opcional del frame sintético."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from uuid import UUID

from operix_engine.detection import BoundingBox
from operix_engine.event_evidence import render_track_frame
from operix_engine.event_publishing import EventContext, HttpEventSink
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


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError("Fecha/hora ISO 8601 inválida") from error
    if parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("La fecha/hora requiere zona horaria explícita")
    return parsed


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
    parser.add_argument("--publish-api", action="store_true", help="Publicar candidatos por HTTP")
    parser.add_argument("--capture-evidence", action="store_true", help="Adjuntar captura técnica del frame de tracks")
    parser.add_argument("--analysis-run-id", type=UUID)
    parser.add_argument("--recording-start-at", type=_aware_datetime)
    args = parser.parse_args()

    if args.capture_evidence and not args.publish_api:
        parser.error("--capture-evidence requiere --publish-api")

    if args.end_frame < 0:
        parser.error("--end-frame debe ser no negativo")

    if _sha256(args.input_jsonl).lower() != args.expected_jsonl_sha256.lower():
        parser.error("SHA-256 del JSONL no coincide")
    config = load_operational_config(args.config)
    if config.view_id != args.view_id:
        parser.error("La vista de la configuración no coincide con --view-id")
    sink = None
    context = None
    if args.publish_api:
        if args.analysis_run_id is None or args.recording_start_at is None:
            parser.error("--publish-api requiere --analysis-run-id y --recording-start-at")
        api_base_url = os.environ.get("OPERIX_API_BASE_URL", "")
        try:
            timeout_s = float(os.environ.get("OPERIX_API_TIMEOUT_S", "5"))
            sink = HttpEventSink(api_base_url, timeout_s=timeout_s)
            context = EventContext(args.analysis_run_id, config.view_id, args.recording_start_at)
        except ValueError as error:
            parser.error(str(error))
    elif args.analysis_run_id is not None or args.recording_start_at is not None:
        parser.error("El contexto de publicación requiere --publish-api")
    analyzer = SpatiotemporalAnalyzer(
        width=args.width, height=args.height, fps=args.fps, zones=config.zones
    )
    engine = RuleEngine(config)
    expected_frame = 0
    candidates = []
    publications = []
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
            if sink is not None and context is not None:
                for candidate in result.candidates:
                    try:
                        evidence = (
                            render_track_frame(
                                candidate, tracks, config.zones, width=args.width, height=args.height
                            )
                            if args.capture_evidence else None
                        )
                    except (OSError, ValueError):
                        publications.append({
                            "frame_index": candidate.frame_index,
                            "track_id": candidate.track_id,
                            "status": "failed",
                            "reason": "evidence_render_error",
                        })
                        continue
                    publications.append({
                        "frame_index": candidate.frame_index,
                        "track_id": candidate.track_id,
                        **asdict(sink.publish(candidate, context, evidence)),
                    })
            expected_frame += 1
    if expected_frame != args.end_frame + 1:
        raise ValueError(f"Faltan frames desde {expected_frame} hasta {args.end_frame}")
    output = {"frames": expected_frame, "candidates": candidates}
    if context is not None:
        output["analysis_run_id"] = str(context.analysis_run_id)
        output["publications"] = publications
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if any(item["status"] == "failed" for item in publications) else 0


if __name__ == "__main__":
    raise SystemExit(main())
