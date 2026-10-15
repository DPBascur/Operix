# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audita anotaciones NVIDIA y prepara un manifest candidato local, sin entrenar."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

from operix_engine.nvidia_dataset import REVISION, audit, build_manifest, read_catalog, split_runs

BASE_URL = ("https://huggingface.co/datasets/nvidia/"
            "PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes/resolve/")
REPO_ROOT = Path(__file__).resolve().parents[2]


def local_output(path: Path) -> Path:
    result = path.resolve()
    if result == REPO_ROOT or REPO_ROOT in result.parents:
        raise ValueError("Salidas de auditoría, manifest e imágenes deben quedar fuera del repositorio")
    return result


def read_range(url: str, offset: int, size: int) -> bytes:
    request = Request(url, headers={"Range": f"bytes={offset}-{offset + size - 1}"})
    with urlopen(request, timeout=60) as response:
        content_range = response.headers.get("Content-Range", "")
        if response.status != 206 or not content_range.startswith(f"bytes {offset}-"):
            raise RuntimeError("Servidor sin soporte HTTP Range: se cancela antes de bajar un shard")
        data = response.read(size)
    if len(data) != size:
        raise RuntimeError("Respuesta parcial incompleta")
    return data


def fetch_member(shard: str, run_id: str, camera: str, output: Path, suffix: str) -> str:
    if not shard.startswith("artifacts/") or not shard.endswith(".tar") or ".." in Path(shard).parts:
        raise ValueError("Se requiere una ruta artifacts/*.tar del repositorio NVIDIA")
    if not run_id or not camera or any(c in run_id + camera for c in "/\\"):
        raise ValueError("run_id/camera inválidos")
    url = BASE_URL + REVISION + "/" + shard
    offset = 0
    for _ in range(30000):
        header = read_range(url, offset, 512)
        if not header.strip(b"\0"):
            break
        name = header[:100].split(b"\0", 1)[0].decode("utf-8")
        size = int(header[124:136].strip(b"\0 "), 8)
        if run_id in name and f".{camera}.{suffix}" in name:
            if size > 64 * 1024 * 1024:
                raise ValueError("Miembro supera el límite de descarga selectiva de 64 MiB")
            output = local_output(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("wb") as target:
                cursor = offset + 512
                end = cursor + size
                while cursor < end:
                    step = min(1024 * 1024, end - cursor)
                    target.write(read_range(url, cursor, step))
                    cursor += step
            return name
        offset += 512 + ((size + 511) // 512) * 512
    raise FileNotFoundError(f"No se halló {run_id} / {camera} en {shard}")


def load_registry(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("dataset_revision") != REVISION:
        raise ValueError("Registro de splits de otra revisión")
    return data["splits"]


def check_blind_test(rows: list[dict], registry: dict[str, str] | None) -> None:
    if registry is not None:
        if any(row["run_id"] not in registry for row in rows):
            raise ValueError("Run ausente del registro de splits")
        if any(registry[row["run_id"]] == "test" for row in rows):
            raise ValueError("El test reservado debe permanecer sin inspección durante el piloto")


def reserve_splits(index: Path, output: Path, seen_runs: frozenset[str]) -> None:
    output = local_output(output)
    with index.open(newline="", encoding="utf-8-sig") as source:
        rows = [row for row in csv.DictReader(source) if row.get("source_kind") == "multi_camera_run"]
    if not rows or not {"run_id", "scenario", "seed"}.issubset(rows[0]):
        raise ValueError("Índice de runs vacío o sin run_id/scenario/seed/source_kind")
    if len({row["run_id"] for row in rows}) != len(rows):
        raise ValueError("Run duplicado en índice")
    unknown_seen = seen_runs - {row["run_id"] for row in rows}
    if unknown_seen:
        raise ValueError(f"Runs inspeccionados ausentes del índice: {sorted(unknown_seen)}")
    splits = split_runs(rows, exploration_runs=seen_runs)
    with index.open("rb") as source:
        index_hash = hashlib.file_digest(source, "sha256").hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"dataset_revision": REVISION, "algorithm": "sha256_seed_70_15_15",
                                  "runs_index_sha256": index_hash,
                                  "status": "reservation_before_label_review_for_unseen_runs",
                                  "splits": dict(sorted(splits.items()))},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_audit(catalog: Path, output_dir: Path, registry: Path | None = None) -> None:
    output_dir = local_output(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_catalog(catalog)
    check_blind_test(rows, load_registry(registry))
    result = audit(rows)
    (output_dir / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    combinations = result["combinations"]
    with (output_dir / "combinations.csv").open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=list(combinations[0]) if combinations else
                                ["source_kind", "label_class", "group", "name", "agent_type", "task_name", "asset_name",
                                 "target_candidate", "annotations", "valid_boxes", "frames", "runs", "cameras",
                                 "unique_prim_paths"])
        writer.writeheader()
        writer.writerows(combinations)
    instances = result["instances"]
    with (output_dir / "instances.csv").open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=list(instances[0]) if instances else
                                ["scenario", "run_id", "camera", "prim_path", "label_class", "group", "name",
                                 "target_candidate", "frames_present", "frames_with_valid_box"])
        writer.writeheader()
        writer.writerows(instances)


def write_manifest(catalog: Path, output: Path, frames: int, seen_runs: frozenset[str],
                   registry: Path | None = None) -> None:
    output = local_output(output)
    rows = read_catalog(catalog)
    reserved = load_registry(registry)
    check_blind_test(rows, reserved)
    result = build_manifest(rows, frames, seen_runs, reserved)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def contact_sheet(manifest: Path, output: Path, indices: list[int]) -> None:
    import cv2  # import diferido: audit/manifest no necesitan OpenCV
    import numpy as np

    output = local_output(output)
    entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
    panels = []
    for number in indices:
        entry = entries[number]
        if not entry.get("video_path"):
            raise ValueError(f"Entrada {number} sin video_path")
        capture = cv2.VideoCapture(entry["video_path"])
        try:
            if not capture.isOpened():
                raise ValueError(f"Video no disponible para entrada {number}")
            width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if (width, height) != (entry["width"], entry["height"]):
                raise ValueError(f"Resolución no coincide en entrada {number}")
            capture.set(cv2.CAP_PROP_POS_FRAMES, entry["frame"])
            ok, image = capture.read()
            if not ok:
                raise ValueError(f"Frame no decodificable en entrada {number}")
            decoded_position = int(round(capture.get(cv2.CAP_PROP_POS_FRAMES)))
            if decoded_position != entry["frame"] + 1:
                raise ValueError(f"Frame desalineado en entrada {number}: {decoded_position}")
        finally:
            capture.release()
        for box in entry["boxes"]:
            cx, cy, bw, bh = box["bbox"]
            x1, y1 = int((cx - bw / 2) * width), int((cy - bh / 2) * height)
            x2, y2 = int((cx + bw / 2) * width), int((cy + bh / 2) * height)
            color = (0, 230, 0) if box["class_id"] == 0 else (0, 160, 255)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
            cv2.putText(image, box["target_class"], (x1, max(20, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, .7, color, 2)
        image = cv2.resize(image, (480, 270))
        cv2.putText(image, f"{entry['scenario']} {entry['camera']} f{entry['frame']}",
                    (8, 255), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2)
        panels.append(image)
    if not panels:
        raise ValueError("Sin paneles")
    while len(panels) % 3:
        panels.append(np.zeros_like(panels[0]))
    sheet = np.vstack([np.hstack(panels[i:i + 3]) for i in range(0, len(panels), 3)])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), sheet):
        raise OSError("No se pudo guardar contact sheet")


def verify_yolo(manifest: Path, output: Path, index: int) -> None:
    """Escribe solamente una muestra de etiquetas; no exporta dataset."""
    output = local_output(output)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("dataset_revision") != REVISION:
        raise ValueError("Revisión del dataset distinta de la fijada")
    entry = data["entries"][index]
    lines = [f"{box['class_id']} " + " ".join(f"{value:.6f}" for value in box["bbox"])
             for box in entry["boxes"]]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch-annotation", help="Extrae un JSONL por HTTP Range de la revisión fijada")
    fetch.add_argument("--shard", required=True)
    fetch.add_argument("--run-id", required=True)
    fetch.add_argument("--camera", required=True)
    fetch.add_argument("--output", type=Path, required=True)
    rgb = sub.add_parser("fetch-rgb", help="Extrae un solo MP4 para revisión visual, nunca el shard completo")
    rgb.add_argument("--shard", required=True)
    rgb.add_argument("--run-id", required=True)
    rgb.add_argument("--camera", required=True)
    rgb.add_argument("--output", type=Path, required=True)
    audit_cmd = sub.add_parser("audit", help="Conteos reales en un catálogo local de JSONL")
    audit_cmd.add_argument("--catalog", type=Path, required=True)
    audit_cmd.add_argument("--output-dir", type=Path, required=True)
    audit_cmd.add_argument("--registry", type=Path, help="Impide abrir runs reservados para test")
    reserve = sub.add_parser("reserve-splits", help="Reserva test por seed antes de inspeccionar etiquetas")
    reserve.add_argument("--runs-index", type=Path, required=True, help="CSV local exportado de runs.parquet")
    reserve.add_argument("--output", type=Path, required=True)
    reserve.add_argument("--seen-run", action="append", default=[])
    manifest = sub.add_parser("build-manifest", help="Manifest candidato; no exporta YOLO")
    manifest.add_argument("--catalog", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--max-frames-per-camera", type=int, default=12)
    manifest.add_argument("--seen-run", action="append", default=[], help="Run ya inspeccionado: nunca test ciego")
    manifest.add_argument("--registry", type=Path)
    preview = sub.add_parser("contact-sheet", help="Dibuja cajas candidatas en videos locales alineados")
    preview.add_argument("--manifest", type=Path, required=True)
    preview.add_argument("--output", type=Path, required=True)
    preview.add_argument("--indices", type=int, nargs="+", required=True)
    labels = sub.add_parser("verify-yolo", help="Convierte una sola entrada a etiqueta YOLO de verificación")
    labels.add_argument("--manifest", type=Path, required=True)
    labels.add_argument("--output", type=Path, required=True)
    labels.add_argument("--index", type=int, required=True)
    args = parser.parse_args()
    if args.command == "fetch-annotation":
        print(fetch_member(args.shard, args.run_id, args.camera, args.output, "object_detection.jsonl"))
    elif args.command == "fetch-rgb":
        print(fetch_member(args.shard, args.run_id, args.camera, args.output, "rgb.mp4"))
    elif args.command == "audit":
        write_audit(args.catalog, args.output_dir, args.registry)
    elif args.command == "reserve-splits":
        reserve_splits(args.runs_index, args.output, frozenset(args.seen_run))
    elif args.command == "build-manifest":
        write_manifest(args.catalog, args.output, args.max_frames_per_camera,
                       frozenset(args.seen_run), args.registry)
    elif args.command == "contact-sheet":
        contact_sheet(args.manifest, args.output, args.indices)
    else:
        verify_yolo(args.manifest, args.output, args.index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
