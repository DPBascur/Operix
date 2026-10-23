# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extrae frames uniformes y crea un paquete CVAT PERSON sin preanotaciones."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from pathlib import Path

import cv2

from operix_engine.person_holdout import (
    CANDIDATE, require_outside_repository, sample_indices, sha256_file,
    validate_source_group,
)


def prepare(root: Path, source_group: str, *, sample_count: int | None = None,
            interval_seconds: float | None = None) -> dict:
    validate_source_group(source_group)
    require_outside_repository(root, Path(__file__).resolve().parents[2])
    meta = json.loads((root / "01-ingested" / f"{source_group}.json").read_text(encoding="utf-8"))
    if meta["source_group"] != source_group or meta["evaluation_status"] != CANDIDATE or (
            meta["role"] != "HOLDOUT_ONLY" or meta["model_access_allowed"] is not False):
        raise ValueError("metadata de aislamiento del holdout inválida")
    video = (root / meta["stored_video"]).resolve()
    if not video.is_relative_to(root.resolve()) or sha256_file(video) != meta["sha256"]:
        raise ValueError("SHA o ubicación del video original inválidos")
    indices = sample_indices(meta["frame_count"], meta["fps"],
                             sample_count=sample_count, interval_seconds=interval_seconds)
    package = root / "03-cvat-packages" / source_group
    frames_dir = root / "02-frame-samples" / source_group
    if package.exists() or frames_dir.exists():
        raise FileExistsError("el paquete o sus frames ya existen; no se sobrescriben")
    package.mkdir(parents=True)
    frames_dir.mkdir(parents=True)
    selected = set(indices)
    rows = []
    capture = cv2.VideoCapture(str(video))
    try:
        for frame_index in range(indices[-1] + 1):
            ok, frame = capture.read()
            if not ok or frame is None:
                raise ValueError(f"video truncado antes del frame {frame_index}")
            if frame_index not in selected:
                continue
            if (frame.shape[1], frame.shape[0]) != (meta["width"], meta["height"]):
                raise ValueError("dimensiones inconsistentes al extraer frames")
            ok, encoded = cv2.imencode(".png", frame)
            if not ok:
                raise ValueError(f"no se pudo codificar frame {frame_index}")
            filename = f"{source_group}_frame_{frame_index:06d}.png"
            payload = encoded.tobytes()
            (frames_dir / filename).write_bytes(payload)
            rows.append({"image_id": f"{source_group}:{frame_index:06d}", "filename": filename,
                         "source_group": source_group, "frame_index": frame_index,
                         "timestamp_seconds": f"{frame_index / meta['fps']:.9f}",
                         "width": meta["width"], "height": meta["height"],
                         "image_sha256": hashlib.sha256(payload).hexdigest().upper(),
                         "video_sha256": meta["sha256"], "annotation_status": "UNANNOTATED",
                         "evaluation_status": CANDIDATE})
    finally:
        capture.release()
    if len(rows) != len(indices):
        raise ValueError("extracción incompleta")
    with zipfile.ZipFile(package / "images.zip", "x") as archive:
        for row in rows:
            info = zipfile.ZipInfo(row["filename"], (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, (frames_dir / row["filename"]).read_bytes())
    with (package / "manifest.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (package / "TEMPLATE-review.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("image", "status", "reviewer", "reviewed_at"))
        writer.writeheader()
        writer.writerows({"image": row["filename"], "status": "", "reviewer": "",
                          "reviewed_at": ""} for row in rows)
    (package / "TEMPLATE-completion.json").write_text(json.dumps({
        "task_id": source_group, "reviewer": "", "completed_at": "",
        "image_count": len(rows), "export_sha256": "", "confirmation": "",
    }, indent=2) + "\n", encoding="utf-8")
    (package / "sampling.json").write_text(json.dumps({
        "method": "UNIFORM_FRAME_COUNT" if sample_count is not None else "FIXED_TIME_INTERVAL",
        "sample_count": sample_count, "interval_seconds": interval_seconds,
        "frame_indices": list(indices), "video_sha256": meta["sha256"],
        "exact_duplicate_frames": len(rows) - len({row["image_sha256"] for row in rows}),
        "images_zip_sha256": sha256_file(package / "images.zip"),
        "manifest_sha256": sha256_file(package / "manifest.csv"),
    }, indent=2) + "\n", encoding="utf-8")
    return {"source_group": source_group, "frames": len(rows), "indices": list(indices),
            "images_zip_sha256": sha256_file(package / "images.zip"),
            "package": str(package)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-group", required=True)
    sampling = parser.add_mutually_exclusive_group(required=True)
    sampling.add_argument("--sample-count", type=int)
    sampling.add_argument("--interval-seconds", type=float)
    args = parser.parse_args()
    print(json.dumps(prepare(args.output_root, args.source_group,
        sample_count=args.sample_count, interval_seconds=args.interval_seconds), indent=2))


if __name__ == "__main__":
    main()
