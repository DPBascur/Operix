# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Congela un holdout humano independiente sin ejecutar ni comparar detectores."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

from operix_engine.person_holdout import (
    CANDIDATE, FROZEN, acquisition_readiness, group_manifests,
    guard_holdout_assignment, require_outside_repository, sha256_file,
    validate_source_group,
)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def freeze(root: Path, *, attestor: str, independent_groups_attested: bool,
           minimum_groups: int = 3) -> dict:
    require_outside_repository(root, Path(__file__).resolve().parents[2])
    if not independent_groups_attested or not attestor.strip():
        raise ValueError("requiere atestación humana explícita de independencia")
    if minimum_groups < 3:
        raise ValueError("se requieren al menos tres grupos independientes")
    groups = group_manifests(root)
    if len(groups) < minimum_groups:
        raise ValueError("grupos independientes insuficientes")
    ids = [validate_source_group(meta["source_group"]) for meta in groups]
    if len(ids) != len(set(ids)) or len({meta["sha256"] for meta in groups}) != len(groups):
        raise ValueError("source_group o video SHA duplicado")
    guard_holdout_assignment(set(ids), {group: "LOCKED_EVALUATION" for group in ids})
    csv_target = root / "final" / "locked-evaluation-manifest.csv"
    json_target = root / "final" / "locked-evaluation-manifest.json"
    freeze_target = root / "06-freeze" / "freeze.json"
    if any(path.exists() for path in (csv_target, json_target, freeze_target)):
        raise FileExistsError("freeze existente; requiere nuevo versionado, no sobrescritura")
    combined: list[dict[str, str]] = []
    sources = []
    image_hashes: dict[str, str] = {}
    for meta in groups:
        group = meta["source_group"]
        required = ("origin", "camera_or_source", "scenario", "rights_or_license")
        if (meta["evaluation_status"] != CANDIDATE or meta["role"] != "HOLDOUT_ONLY"
                or meta["model_access_allowed"] is not False
                or any(str(meta.get(k, "")).strip().upper() in
                       {"", "UNKNOWN", "UNVERIFIED", "TBD"} for k in required)):
            raise ValueError(f"metadata/procedencia incompleta: {group}")
        video = (root / meta["stored_video"]).resolve()
        if not video.is_relative_to(root.resolve()) or sha256_file(video) != meta["sha256"]:
            raise ValueError(f"video original alterado: {group}")
        qa_path = root / "05-qa" / f"{group}.json"
        qa = json.loads(qa_path.read_text(encoding="utf-8"))
        if not qa.get("completed") or qa.get("blocking_issues") != 0:
            raise ValueError(f"QA humano incompleto: {group}")
        export = root / "04-exports" / group / "annotations.zip"
        if sha256_file(export) != qa["export_sha256"]:
            raise ValueError(f"export humano alterado: {group}")
        if (sha256_file(root / "04-exports" / group / "review.csv") != qa["review_sha256"]
                or sha256_file(root / "04-exports" / group / "completion.json") !=
                qa["completion_sha256"]):
            raise ValueError(f"revisión o recibo alterado: {group}")
        receipt = json.loads((root / "04-exports" / group / "completion.json").read_text(
            encoding="utf-8"))
        if (receipt.get("confirmation") != "FULL_FRAME_HUMAN_REVIEW_COMPLETED"
                or receipt.get("export_sha256") != qa["export_sha256"]
                or receipt.get("task_id") != group or not receipt.get("reviewer")):
            raise ValueError(f"recibo humano inválido: {group}")
        package_rows = read_rows(root / "03-cvat-packages" / group / "manifest.csv")
        verified_path = root / "final" / group / "verified-manifest.csv"
        if sha256_file(verified_path) != qa["verified_manifest_sha256"]:
            raise ValueError(f"manifest verificado alterado: {group}")
        rows = read_rows(verified_path)
        if len(rows) != len(package_rows) or len(rows) != receipt.get("image_count") or (
                {r["image_id"] for r in rows} != {r["image_id"] for r in package_rows}):
            raise ValueError(f"manifest incompleto: {group}")
        for row in rows:
            name = row["filename"]
            if Path(name).name != name or row["source_group"] != group or (
                    row["video_sha256"] != meta["sha256"] or
                    row["annotation_status"] not in {"HUMAN_VERIFIED", "VERIFIED_NEGATIVE"}):
                raise ValueError(f"frame no elegible o ambiguo: {group}/{name}")
            if (row["annotation_status"] == "HUMAN_VERIFIED") != (int(row["person_box_count"]) > 0):
                raise ValueError(f"estado/cajas inconsistente: {group}/{name}")
            image = root / "02-frame-samples" / group / name
            label = root / "final" / group / "labels" / (Path(name).stem + ".txt")
            if sha256_file(image) != row["image_sha256"] or sha256_file(label) != row["label_sha256"]:
                raise ValueError(f"SHA frame/label inválido: {group}/{name}")
            previous_group = image_hashes.get(row["image_sha256"])
            if previous_group and previous_group != group:
                raise ValueError("frame duplicado exacto entre grupos")
            image_hashes[row["image_sha256"]] = group
            combined.append({**row, "evaluation_status": FROZEN})
        sources.append({"source_group": group, "source_video_sha256": meta["sha256"],
                        "source_manifest_sha256": sha256_file(root / "01-ingested" / f"{group}.json"),
                        "export_sha256": qa["export_sha256"],
                        "review_sha256": qa["review_sha256"],
                        "completion_sha256": qa["completion_sha256"],
                        "verified_manifest_sha256": qa["verified_manifest_sha256"],
                        "qa_sha256": sha256_file(qa_path), "images": len(rows)})
    if not any(r["annotation_status"] == "HUMAN_VERIFIED" for r in combined) or not any(
            r["annotation_status"] == "VERIFIED_NEGATIVE" for r in combined):
        raise ValueError("holdout requiere positivos y negativos humanos")
    combined.sort(key=lambda row: (row["source_group"], int(row["frame_index"])))
    csv_target.parent.mkdir(parents=True, exist_ok=True)
    freeze_target.parent.mkdir(parents=True, exist_ok=True)
    with csv_target.open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(combined[0]))
        writer.writeheader()
        writer.writerows(combined)
    frozen_at = datetime.now().astimezone().isoformat()
    summary = {"status": FROZEN, "frozen_at": frozen_at, "attestor": attestor.strip(),
               "independence_attested": True, "minimum_groups": minimum_groups,
               "source_groups": sorted(ids), "sources": sources, "images": len(combined),
               "positive_images": sum(r["annotation_status"] == "HUMAN_VERIFIED" for r in combined),
               "negative_images": sum(r["annotation_status"] == "VERIFIED_NEGATIVE" for r in combined),
               "matching_protocol": "person, one-to-one IoU >= 0.5; threshold fixed on separate calibration",
               "manifest_csv_sha256": sha256_file(csv_target)}
    with json_target.open("x", encoding="utf-8") as stream:
        json.dump({**summary, "records": combined}, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    with freeze_target.open("x", encoding="utf-8") as stream:
        json.dump({**summary, "manifest_json_sha256": sha256_file(json_target)},
                  stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return {"freeze": summary, "readiness": acquisition_readiness(root)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--attestor", required=True)
    parser.add_argument("--attest-independent-groups", action="store_true")
    parser.add_argument("--minimum-groups", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output_root, attestor=args.attestor,
        independent_groups_attested=args.attest_independent_groups,
        minimum_groups=args.minimum_groups), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
