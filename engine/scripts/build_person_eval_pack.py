# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Construye fuera de Git un paquete de imágenes PERSON pendientes de anotación."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import cv2

from operix_engine.person_evaluation import read_person_observations, select_annotation_frames


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_pack(video: Path, current_jsonl: Path, generic_jsonl: Path,
               output: Path, expected_sha256: str) -> dict:
    repo = Path(__file__).resolve().parents[2]
    if output.resolve().is_relative_to(repo):
        raise ValueError("el paquete de imágenes debe permanecer fuera del repositorio")
    if output.exists():
        raise FileExistsError("el directorio de salida ya existe; no se sobrescribe")
    video_hash = sha256(video)
    if video_hash != expected_sha256.upper():
        raise ValueError("SHA-256 del video no coincide")

    current = read_person_observations(current_jsonl)
    generic = read_person_observations(generic_jsonl)
    selected = select_annotation_frames(current, generic)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("no se pudo abrir el video")
    declared = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    if declared != len(current):
        capture.release()
        raise ValueError("video y observaciones no tienen igual cantidad de frames")

    images = output / "images"
    images.mkdir(parents=True)
    rows: list[dict] = []
    hashes: list[str] = []
    try:
        for index in range(declared):
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"video truncado en frame {index}")
            if index not in selected:
                continue
            filename = f"test3_frame_{index:06d}.png"
            image_path = images / filename
            if not cv2.imwrite(str(image_path), frame):
                raise ValueError(f"no se pudo guardar {filename}")
            image_hash = sha256(image_path)
            hashes.append(f"{image_hash}  images/{filename}")
            rows.append({
                "image": filename,
                "frame_index": index,
                "source_video": video.name,
                "source_video_sha256": video_hash,
                "source_group": f"test3:{video_hash}",
                "width": width,
                "height": height,
                "fps": fps,
                "selection_reasons": "|".join(selected[index]),
                "current_model_person_proposals": len(current[index]),
                "generic_model_person_proposals": len(generic[index]),
                "annotation_status": "UNANNOTATED",
                "split_status": "DEVELOPMENT_ONLY_NOT_BLIND_EVALUATION",
                "sha256": image_hash,
            })
    finally:
        capture.release()

    with (output / "manifest.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "source-groups.json").write_text(json.dumps({
        "source_group": f"test3:{video_hash}",
        "source_video": video.name,
        "video_sha256": video_hash,
        "frames": declared,
        "selected_images": len(rows),
        "status": "DEVELOPMENT_DIAGNOSTIC; not independent of prior model inspection",
        "split_rule": "all frames from this video remain in one source group",
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "sha256-manifest.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    (output / "instructions.md").write_text(
        "# Anotación PERSON — paquete de desarrollo\n\n"
        "Las imágenes no tienen etiquetas. Los conteos de propuestas en el manifiesto "
        "son señales de muestreo, no ground truth. Un anotador debe revisar cada frame completo "
        "sin aceptar automáticamente predicciones.\n\n"
        "- Etiquetar cada persona real visible con una caja ajustada a su cuerpo visible; "
        "incluir trabajadores, personas pequeñas y operadores en montacargas si el cuerpo es discernible.\n"
        "- Para oclusión o truncamiento, encuadrar solo la región visible; no extrapolar "
        "partes ocultas. Si no es posible distinguir un cuerpo humano, marcar AMBIGUOUS.\n"
        "- No etiquetar reflejos, posters, maniquíes ni partes del vehículo como personas. "
        "Revisar todo el frame antes de marcar VERIFIED_NEGATIVE.\n"
        "- Cada persona separable lleva su propia caja; no agrupar individuos en una sola caja. "
        "Señalar casos donde la identidad o el límite visible no pueda decidirse.\n"
        "- Registrar por imagen HUMAN_VERIFIED, HUMAN_PARTIAL, VERIFIED_NEGATIVE o "
        "AMBIGUOUS/EXCLUDE; conservar versión y revisor de la anotación.\n"
        "- Exportar COCO 1.0 desde CVAT con categoría person, además de un registro "
        "de revisión por imagen. No usar preanotación como verdad terreno.\n\n"
        "Este video ya fue inspeccionado con ambos modelos: el paquete solo sirve para "
        "desarrollo/análisis de errores. Un resultado final requiere otro grupo independiente "
        "con anotación humana completa y split bloqueado.\n",
        encoding="utf-8",
    )
    return {"images": len(rows), "frames": declared, "video_sha256": video_hash,
            "manifest_sha256": sha256(output / "manifest.csv"), "width": width,
            "height": height, "fps": fps}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--current-jsonl", type=Path, required=True)
    parser.add_argument("--generic-jsonl", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(build_pack(args.video, args.current_jsonl, args.generic_jsonl,
                                args.output, args.expected_sha256), indent=2))


if __name__ == "__main__":
    main()
