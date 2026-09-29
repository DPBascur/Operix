"""Genera tablas OP-37 desde un JSONL de tracks ya producido por Operix."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import load_operational_config
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track


def sha256_file(path: Path) -> str:
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
    parser.add_argument("--start-frame", type=int, required=True)
    parser.add_argument("--end-frame", type=int, required=True)
    parser.add_argument("--output-objects", type=Path, required=True)
    parser.add_argument("--output-pairs", type=Path, required=True)
    args = parser.parse_args()

    if args.start_frame < 0 or args.end_frame < args.start_frame:
        parser.error("El intervalo de frames debe ser no negativo y ordenado")
    if args.output_objects.resolve() == args.output_pairs.resolve():
        parser.error("Las dos salidas deben ser archivos distintos")
    if sha256_file(args.input_jsonl).lower() != args.expected_jsonl_sha256.lower():
        parser.error("SHA-256 del JSONL no coincide")

    config = load_operational_config(args.config)
    if config.view_id != args.view_id:
        parser.error("La vista de la configuración no coincide con --view-id")
    analyzer = SpatiotemporalAnalyzer(
        width=args.width, height=args.height, fps=args.fps,
        zones=config.zones,
    )
    object_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, object]] = []
    expected_frame = args.start_frame

    with args.input_jsonl.open(encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            frame_index = record["frame_index"]
            if frame_index < args.start_frame or frame_index > args.end_frame:
                continue
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
            state = analyzer.update(frame_index, tracks)
            for obj in state.objects:
                for zone in obj.zones:
                    object_rows.append({
                        "frame_index": frame_index,
                        "timestamp_s": state.timestamp_s,
                        "track_id": obj.track_id,
                        "class_name": obj.class_name,
                        "x_norm": obj.position.x,
                        "y_norm": obj.position.y,
                        "zone_id": zone.zone_id,
                        "inside_zone": zone.inside,
                        "dwell_time_s": zone.dwell_time_s,
                        "trajectory_frames": ";".join(
                            str(sample.frame_index) for sample in obj.trajectory
                        ),
                    })
            for pair in state.proximities:
                pair_rows.append({
                    "frame_index": frame_index,
                    "timestamp_s": state.timestamp_s,
                    "track_id_a": pair.track_id_a,
                    "track_id_b": pair.track_id_b,
                    "normalized_distance": pair.normalized_distance,
                })
            expected_frame += 1
    if expected_frame != args.end_frame + 1:
        raise ValueError(f"Faltan frames desde {expected_frame} hasta {args.end_frame}")

    object_columns = (
        "frame_index", "timestamp_s", "track_id", "class_name", "x_norm", "y_norm",
        "zone_id", "inside_zone", "dwell_time_s", "trajectory_frames",
    )
    pair_columns = (
        "frame_index", "timestamp_s", "track_id_a", "track_id_b", "normalized_distance",
    )
    for path, columns, rows in (
        (args.output_objects, object_columns, object_rows),
        (args.output_pairs, pair_columns, pair_rows),
    ):
        with path.open("x", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
    print(f"Frames: {args.end_frame - args.start_frame + 1}; "
          f"filas objeto/zona: {len(object_rows)}; pares: {len(pair_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
