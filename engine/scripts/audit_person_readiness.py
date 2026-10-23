# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audita manifests locales PERSON sin tratar preanotaciones como ground truth."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def audit(final_rows: list[dict[str, str]], pack_rows: list[dict[str, str]]) -> dict:
    """Resume candidatos y bloqueos; no asigna aprobación humana por inferencia."""
    sources = Counter(row["dataset"] for row in final_rows)
    splits = Counter(row["split_candidate"] for row in final_rows)
    resolutions = Counter(f'{row["width"]}x{row["height"]}' for row in final_rows)
    source_groups = {row["source_group"] for row in final_rows}
    group_splits: dict[str, set[str]] = defaultdict(set)
    for row in final_rows:
        group_splits[row["source_group"]].add(row["split_candidate"])
    duplicate_hashes = sum(count - 1 for count in Counter(
        row["sha256"] for row in final_rows).values() if count > 1)
    missing_images = sorted(row["image_id"] for row in final_rows
                            if not Path(row["image_path"]).is_file())
    verified_positives = [row for row in final_rows
                          if row["annotation_status"] == "HUMAN_VERIFIED"
                          and int(row["person_boxes"]) > 0]
    verified_negatives = [row for row in final_rows
                          if row["annotation_status"] == "VALID_FULL_FRAME_NEGATIVE"
                          and int(row["person_boxes"]) == 0]
    # SOURCE synthetic y anotaciones publicadas NO son revisión humana completa Operix.
    source_boxes = {name: sum(int(row["person_boxes"]) for row in final_rows
                               if row["dataset"] == name) for name in sorted(sources)}
    unverified_boxes = sum(int(row["person_boxes"]) for row in final_rows
                           if row["annotation_status"] != "HUMAN_VERIFIED")
    pack_status = Counter(row["annotation_status"] for row in pack_rows)
    pack_split = Counter(row["split_status"] for row in pack_rows)
    return {
        "decision": "PERSON_V2_BLOCKED_BY_ANNOTATION",
        "evaluation_decision": "PERSON_EVALUATION_BLOCKED_BY_GROUND_TRUTH",
        "final_candidate": {
            "total_images": len(final_rows),
            "source_images": dict(sorted(sources.items())),
            "candidate_splits_not_frozen": dict(sorted(splits.items())),
            "source_groups": len(source_groups),
            "strong_run_level_images": sum(row["source_group_quality"] == "run_level"
                                           for row in final_rows),
            "weak_group_images": sum(row["source_group_quality"] != "run_level"
                                     for row in final_rows),
            "group_cross_split_conflicts": sum(len(value) > 1 for value in group_splits.values()),
            "exact_duplicate_sha256_rows": duplicate_hashes,
            "missing_image_count": len(missing_images),
            "missing_image_ids": missing_images,
            "resolution_distribution": dict(sorted(resolutions.items())),
            "person_boxes_from_source_not_human_verified": unverified_boxes,
            "person_boxes_by_source": source_boxes,
            "human_verified_positive_images": len(verified_positives),
            "human_verified_person_boxes": sum(int(row["person_boxes"])
                                               for row in verified_positives),
            "human_verified_full_frame_negatives": len(verified_negatives),
            "published_or_synthetic_boxes_require_full_frame_review": True,
        },
        "existing_human_annotation_pack": {
            "images": len(pack_rows),
            "status_counts": dict(sorted(pack_status.items())),
            "split_status_counts": dict(sorted(pack_split.items())),
            "source_groups": len({row["source_group"] for row in pack_rows}),
            "exact_duplicate_sha256_rows": sum(count - 1 for count in Counter(
                row["sha256"] for row in pack_rows).values() if count > 1),
            "remaining_images_requiring_human_review": sum(
                row["annotation_status"] != "VALID_FULL_FRAME_NEGATIVE" for row in pack_rows),
        },
        "readiness_blockers": [
            "No hay positivos PERSON de contexto industrial real con anotación humana completa y verificable.",
            "El paquete existente tiene imágenes pendientes de anotación/revisión de frame completo.",
            "La validation y el holdout externos no están congelados con grupos independientes y positivos verificados.",
            "CrowdHuman/Keremberke tienen procedencia débil a nivel de escena o secuencia.",
            "Las etiquetas sintéticas NVIDIA y preanotaciones no sustituyen revisión humana de cobertura.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--annotation-pack-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    if args.output.resolve().is_relative_to(repo):
        raise ValueError("el reporte local de readiness debe quedar fuera de Git")
    result = audit(load_rows(args.candidate_manifest), load_rows(args.annotation_pack_manifest))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest().upper()
    print(json.dumps({"decision": result["decision"], "sha256": digest,
                      "images": result["final_candidate"]["total_images"]}, indent=2))


if __name__ == "__main__":
    main()
