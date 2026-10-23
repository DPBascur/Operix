# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Valida COCO humano de un grupo reservado; no ejecuta modelos."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from process_person_cvat_export import inspect_task
from operix_engine.person_holdout import (
    CANDIDATE, acquisition_readiness, require_outside_repository, sha256_file,
    validate_source_group,
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_rows(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def process(root: Path, source_group: str, *, reviewer: str | None = None,
            human_review_confirmed: bool = False,
            ambiguous_images: set[str] | None = None) -> dict:
    validate_source_group(source_group)
    require_outside_repository(root, Path(__file__).resolve().parents[2])
    meta = json.loads((root / "01-ingested" / f"{source_group}.json").read_text(encoding="utf-8"))
    if meta["source_group"] != source_group or meta["evaluation_status"] != CANDIDATE or (
            meta["role"] != "HOLDOUT_ONLY" or meta["model_access_allowed"] is not False):
        raise ValueError("metadata de aislamiento inválida")
    video = (root / meta["stored_video"]).resolve()
    if not video.is_relative_to(root.resolve()) or sha256_file(video) != meta["sha256"]:
        raise ValueError("video original ausente o SHA distinto")
    package = root / "03-cvat-packages" / source_group
    manifest = package / "manifest.csv"
    rows = read_rows(manifest)
    sampling = json.loads((package / "sampling.json").read_text(encoding="utf-8"))
    if not rows or sha256_file(manifest) != sampling["manifest_sha256"] or (
            sha256_file(package / "images.zip") != sampling["images_zip_sha256"] or
            sampling["video_sha256"] != meta["sha256"]):
        raise ValueError("sampling/paquete alterado")
    if len({r["filename"] for r in rows}) != len(rows):
        raise ValueError("nombres de imagen duplicados dentro del grupo")
    with zipfile.ZipFile(package / "images.zip") as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        if len(names) != len(rows) or set(names) != {r["filename"] for r in rows} or archive.testzip():
            raise ValueError("contenido del ZIP de imágenes inválido")
        for row in rows:
            if row["source_group"] != source_group or row["video_sha256"] != meta["sha256"]:
                raise ValueError("source_group o video SHA de frame inválido")
            payload = archive.read(row["filename"])
            image = root / "02-frame-samples" / source_group / row["filename"]
            if hashlib.sha256(payload).hexdigest().upper() != row["image_sha256"] or (
                    sha256_file(image) != row["image_sha256"]):
                raise ValueError(f"frame SHA inválido: {row['filename']}")
    export_dir = root / "04-exports" / source_group
    archive = export_dir / "annotations.zip"
    if not archive.is_file():
        raise FileNotFoundError(f"TASK_EXPORT_MISSING: {archive}")
    receipt = export_dir / "completion.json"
    review = export_dir / "review.csv"
    if not receipt.exists() and not review.exists():
        if not human_review_confirmed or not reviewer or not reviewer.strip():
            raise ValueError("se requiere confirmación humana completa y revisor")
        with zipfile.ZipFile(archive) as zf:
            paths = [name for name in zf.namelist() if name.endswith(".json")]
            if len(paths) != 1:
                raise ValueError("COCO debe contener exactamente un JSON")
            coco = json.loads(zf.read(paths[0]))
        images = coco.get("images", [])
        names = [image["file_name"] for image in images]
        expected = {row["filename"] for row in rows}
        if len(names) != len(rows) or len(set(names)) != len(names) or set(names) != expected:
            raise ValueError("COCO no contiene exactamente los frames del source_group")
        image_ids = [image["id"] for image in images]
        annotation_ids = [annotation["id"] for annotation in coco.get("annotations", [])]
        if len(set(image_ids)) != len(image_ids) or len(set(annotation_ids)) != len(annotation_ids):
            raise ValueError("COCO contiene IDs de imagen o anotación duplicados")
        ambiguous = ambiguous_images or set()
        if not ambiguous <= expected:
            raise ValueError("imagen ambigua ajena al paquete")
        ids = {image["id"]: image["file_name"] for image in images}
        counts = Counter(ids.get(annotation.get("image_id"))
                         for annotation in coco.get("annotations", []))
        if None in counts:
            raise ValueError("COCO contiene caja sin imagen válida")
        now = datetime.now().astimezone().isoformat()
        write_rows(review, [{"image": name,
            "status": "REVIEW_AMBIGUOUS" if name in ambiguous else
                      "HUMAN_VERIFIED" if counts[name] else "VERIFIED_NEGATIVE",
            "reviewer": reviewer.strip(), "reviewed_at": now} for name in names],
            ["image", "status", "reviewer", "reviewed_at"])
        with receipt.open("x", encoding="utf-8") as stream:
            json.dump({"task_id": source_group, "reviewer": reviewer.strip(),
                       "completed_at": now, "image_count": len(rows),
                       "export_sha256": sha256_file(archive),
                       "confirmation": "FULL_FRAME_HUMAN_REVIEW_COMPLETED"}, stream, indent=2)
            stream.write("\n")
    elif not receipt.is_file() or not review.is_file():
        raise ValueError("recibo/review parcial; no se sobrescribe")
    expected_rows = [{"filename": row["filename"], "width": row["width"],
                      "height": row["height"]} for row in rows]
    state, issues, labels, statuses = inspect_task(source_group, expected_rows, export_dir)
    output = root / "final" / source_group
    if output.exists():
        raise FileExistsError("manifest verificado ya existe; no se sobrescribe")
    qa_path = root / "05-qa" / f"{source_group}.json"
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa = {"source_group": source_group, "completed": state["completed"],
          "blocking_issues": len(issues), "issues": issues,
          "export_sha256": sha256_file(archive), "review_sha256": sha256_file(review),
          "completion_sha256": sha256_file(receipt),
          "warnings": (["EXACT_DUPLICATE_FRAMES_WITHIN_SOURCE_GROUP"]
                       if len({r["image_sha256"] for r in rows}) != len(rows) else [])}
    qa_path.write_text(json.dumps(qa, indent=2) + "\n", encoding="utf-8")
    if issues:
        return {"qa": qa, "readiness": acquisition_readiness(root)}
    labels_dir = output / "labels"
    labels_dir.mkdir(parents=True)
    verified = []
    for row in rows:
        name = row["filename"]
        lines = [f"{cls} {x:.8f} {y:.8f} {w:.8f} {h:.8f}"
                 for cls, x, y, w, h in labels[name]]
        label_path = labels_dir / (Path(name).stem + ".txt")
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        verified.append({**row, "annotation_status": statuses[name],
                         "person_box_count": len(lines), "label_sha256": sha256_file(label_path)})
    write_rows(output / "verified-manifest.csv", verified, list(verified[0]))
    qa["verified_manifest_sha256"] = sha256_file(output / "verified-manifest.csv")
    qa_path.write_text(json.dumps(qa, indent=2) + "\n", encoding="utf-8")
    return {"qa": qa, "positive_images": sum(r["annotation_status"] == "HUMAN_VERIFIED"
                                                 for r in verified),
            "negative_images": sum(r["annotation_status"] == "VERIFIED_NEGATIVE"
                                                 for r in verified),
            "ambiguous_images": sum(r["annotation_status"] == "REVIEW_AMBIGUOUS"
                                                 for r in verified),
            "person_boxes": sum(int(r["person_box_count"]) for r in verified),
            "readiness": acquisition_readiness(root)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--source-group", required=True)
    parser.add_argument("--reviewer")
    parser.add_argument("--confirm-full-frame-human-review", action="store_true")
    parser.add_argument("--ambiguous-image", action="append", default=[])
    args = parser.parse_args()
    print(json.dumps(process(args.output_root, args.source_group, reviewer=args.reviewer,
        human_review_confirmed=args.confirm_full_frame_human_review,
        ambiguous_images=set(args.ambiguous_image)), indent=2))


if __name__ == "__main__":
    main()
