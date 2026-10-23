# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ingiere videos PERSON independientes sin ejecutar ningún detector."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

import cv2

from operix_engine.person_holdout import (
    CANDIDATE, acquisition_readiness, group_manifests, require_outside_repository,
    sha256_file, validate_source_group,
)


def ingest(video: Path, root: Path, *, source_group: str, origin: str,
           camera_or_source: str, scenario: str, rights_or_license: str,
           lighting: str = "UNKNOWN", environment: str = "UNKNOWN",
           contains_person_expected: str = "UNKNOWN",
           contains_forklift_expected: str = "UNKNOWN", notes: str = "",
           acquisition_date: str | None = None) -> dict:
    source_group = validate_source_group(source_group)
    repository = Path(__file__).resolve().parents[2]
    require_outside_repository(root, repository)
    if not video.is_file() or video.resolve().is_relative_to(repository):
        raise ValueError("se requiere un video nuevo fuera del repositorio")
    if video.resolve().is_relative_to(root.resolve()):
        raise ValueError("el video ya está dentro de la carpeta de adquisición")
    if any(not value.strip() for value in (origin, camera_or_source, scenario, rights_or_license)):
        raise ValueError("origin, camera_or_source, scenario y rights_or_license son obligatorios")
    if contains_person_expected not in {"YES", "NO", "UNKNOWN"} or (
            contains_forklift_expected not in {"YES", "NO", "UNKNOWN"}):
        raise ValueError("presencia esperada debe ser YES, NO o UNKNOWN")
    acquired = acquisition_date or date.today().isoformat()
    date.fromisoformat(acquired)
    digest = sha256_file(video)
    existing = group_manifests(root)
    if any(item["source_group"] == source_group for item in existing):
        raise FileExistsError("source_group ya registrado")
    if any(item["sha256"] == digest for item in existing):
        raise ValueError("video SHA-256 ya registrado en otro source_group")
    output_video = root / "00-source-videos" / f"{source_group}{video.suffix.lower()}"
    output_manifest = root / "01-ingested" / f"{source_group}.json"
    if output_video.exists() or output_manifest.exists():
        raise FileExistsError("video o manifest destino ya existe")
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            raise ValueError("OpenCV no pudo abrir el video")
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        declared_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fourcc = int(capture.get(cv2.CAP_PROP_FOURCC))
        decoded, first = capture.read()
        if not decoded or first is None or width < 1 or height < 1 or fps <= 0:
            raise ValueError("video no decodificable o metadata incompleta")
        if (first.shape[1], first.shape[0]) != (width, height):
            raise ValueError("resolución declarada no coincide con el frame decodificado")
        frames = 1
        while True:
            decoded, frame = capture.read()
            if not decoded or frame is None:
                break
            if (frame.shape[1], frame.shape[0]) != (width, height):
                raise ValueError("resolución variable durante el video")
            frames += 1
        codec = "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4)).strip("\x00")
    finally:
        capture.release()
    output_video.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(video, output_video)
    if sha256_file(output_video) != digest:
        raise ValueError("el video copiado no coincide con el SHA original")
    manifest = {
        "source_group": source_group, "source_file": video.name,
        "stored_video": str(output_video.relative_to(root)).replace("\\", "/"),
        "sha256": digest, "acquisition_date": acquired, "origin": origin,
        "camera_or_source": camera_or_source, "width": width, "height": height,
        "resolution": f"{width}x{height}", "fps": fps, "frame_count": frames,
        "declared_frame_count": declared_frames,
        "duration_seconds": frames / fps,
        "orientation": "PORTRAIT" if height > width else "LANDSCAPE" if width > height else "SQUARE",
        "codec": codec, "scenario": scenario, "lighting": lighting,
        "environment": environment, "contains_person_expected": contains_person_expected,
        "contains_forklift_expected": contains_forklift_expected, "notes": notes,
        "rights_or_license": rights_or_license, "role": "HOLDOUT_ONLY",
        "evaluation_status": CANDIDATE, "independence_status": "PENDING_ATTESTATION",
        "model_access_allowed": False,
    }
    with output_manifest.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"manifest": manifest, "readiness": acquisition_readiness(root)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-group", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--camera-or-source", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--rights-or-license", required=True)
    parser.add_argument("--lighting", default="UNKNOWN")
    parser.add_argument("--environment", default="UNKNOWN")
    parser.add_argument("--contains-person-expected", choices=("YES", "NO", "UNKNOWN"),
                        default="UNKNOWN")
    parser.add_argument("--contains-forklift-expected", choices=("YES", "NO", "UNKNOWN"),
                        default="UNKNOWN")
    parser.add_argument("--acquisition-date")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    print(json.dumps(ingest(args.video, args.output_root, source_group=args.source_group,
        origin=args.origin, camera_or_source=args.camera_or_source, scenario=args.scenario,
        rights_or_license=args.rights_or_license, lighting=args.lighting,
        environment=args.environment, contains_person_expected=args.contains_person_expected,
        contains_forklift_expected=args.contains_forklift_expected,
        acquisition_date=args.acquisition_date, notes=args.notes), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
