# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Valida exports humanos CVAT y actualiza QA/progreso local sin tocar producción."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path

from operix_engine.person_campaign import freeze_payload, plan_split, readiness


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def inspect_task(task_id: str, expected: list[dict[str, str]], export_dir: Path
                 ) -> tuple[dict, list[dict], dict[str, list[tuple[int, float, float, float, float]]],
                            dict[str, str]]:
    """Sin recibo humano explícito no se promueve ninguna imagen a verificada."""
    state = {"completed": False, "images": len(expected)}
    issues: list[dict] = []
    labels: dict[str, list[tuple[int, float, float, float, float]]] = {}
    statuses: dict[str, str] = {}

    def issue(code: str, image: str = "", detail: str = "") -> None:
        issues.append({"severity": "BLOCKER", "task_id": task_id, "image": image,
                       "code": code, "detail": detail})

    archive = export_dir / "annotations.zip"
    receipt = export_dir / "completion.json"
    review_file = export_dir / "review.csv"
    if not archive.is_file() or not receipt.is_file() or not review_file.is_file():
        issue("TASK_EXPORT_INCOMPLETE", detail="requiere annotations.zip, completion.json y review.csv")
        return state, issues, labels, statuses
    try:
        completion = json.loads(receipt.read_text(encoding="utf-8-sig"))
        if (completion.get("task_id") != task_id or completion.get("image_count") != len(expected)
            or completion.get("export_sha256", "").upper() != digest(archive)
            or completion.get("confirmation") != "FULL_FRAME_HUMAN_REVIEW_COMPLETED"
            or not completion.get("reviewer") or not completion.get("completed_at")):
            issue("INVALID_HUMAN_COMPLETION_RECEIPT")
        reviews = csv_rows(review_file)
        review_by_name = {r["image"]: r for r in reviews}
        expected_names = {r["filename"] for r in expected}
        if len(review_by_name) != len(reviews) or set(review_by_name) != expected_names:
            issue("REVIEW_MANIFEST_MISMATCH")
        with zipfile.ZipFile(archive) as zf:
            paths = [n for n in zf.namelist() if n.endswith(".json")]
            if len(paths) != 1:
                raise ValueError("el export COCO debe contener exactamente un JSON")
            coco = json.loads(zf.read(paths[0]))
        categories = coco.get("categories", [])
        if len(categories) != 1 or categories[0].get("name") != "person":
            issue("UNKNOWN_CLASS", detail="se requiere una única categoría person")
        category_ids = {r.get("id") for r in categories}
        export_images = coco.get("images", [])
        image_by_name = {r["file_name"]: r for r in export_images}
        if len(image_by_name) != len(export_images) or set(image_by_name) != expected_names:
            issue("IMAGE_MANIFEST_MISMATCH")
        by_export_id = {r["id"]: r["file_name"] for r in export_images}
        boxes: dict[str, list[tuple[int, float, float, float, float]]] = {
            name: [] for name in expected_names}
        for ann in coco.get("annotations", []):
            name = by_export_id.get(ann.get("image_id"))
            if name not in boxes:
                issue("LABEL_WITHOUT_IMAGE", detail=str(ann.get("image_id")))
                continue
            if ann.get("category_id") not in category_ids:
                issue("UNKNOWN_CLASS", name)
                continue
            bbox = ann.get("bbox")
            if not isinstance(bbox, list) or len(bbox) != 4:
                issue("MALFORMED_BOX", name)
                continue
            try:
                x, y, w, h = (float(v) for v in bbox)
            except (TypeError, ValueError):
                issue("MALFORMED_BOX", name)
                continue
            dimensions = image_by_name.get(name, {})
            width, height = dimensions.get("width", 0), dimensions.get("height", 0)
            if not (w > 0 and h > 0 and x >= 0 and y >= 0 and x + w <= width + 1e-6
                    and y + h <= height + 1e-6):
                issue("BOX_OUT_OF_RANGE_OR_ZERO_AREA", name)
                continue
            box = (0, (x + w / 2) / width, (y + h / 2) / height, w / width, h / height)
            if box in boxes[name]:
                issue("DUPLICATE_BOX", name)
            boxes[name].append(box)
        for row in expected:
            name = row["filename"]
            image = image_by_name.get(name)
            if image and (int(image.get("width", -1)) != int(row["width"])
                          or int(image.get("height", -1)) != int(row["height"])):
                issue("IMAGE_DIMENSION_MISMATCH", name)
            review = review_by_name.get(name)
            if not review or not review.get("reviewer") or not review.get("reviewed_at"):
                issue("IMAGE_NOT_HUMAN_REVIEWED", name)
                continue
            count = len(boxes[name])
            status = review.get("status")
            if status == "HUMAN_VERIFIED" and count > 0:
                statuses[name] = status
            elif status == "VERIFIED_NEGATIVE" and count == 0:
                statuses[name] = status
            elif status == "REVIEW_AMBIGUOUS":
                statuses[name] = status
            else:
                issue("STATUS_LABEL_MISMATCH", name, f"{status}; boxes={count}")
            labels[name] = boxes[name]
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        issue("INVALID_CVAT_EXPORT", detail=str(exc))
    state["completed"] = not issues
    if issues:
        return state, issues, {}, {}
    return state, issues, labels, statuses


def process(campaign: Path, *, seed: int = 42, minimum_negative_images: int = 30,
            minimum_independent_groups: int = 3) -> dict:
    inventory_path = campaign / "00-inventory" / "consolidated-images.csv"
    rows = csv_rows(inventory_path)
    tasks = json.loads((campaign / "03-manifests" / "tasks.json").read_text(encoding="utf-8"))
    states: dict[str, dict] = {}
    issues: list[dict] = []
    for row in rows:
        if (not row["source_group"] or (row["source"] == "TEST3" and
                                      row["source_group"] != "TEST3_VIDEO")):
            issues.append({"severity": "BLOCKER", "task_id": row["recommended_task"],
                           "image": row["filename"], "code": "INVALID_SOURCE_GROUP", "detail": ""})
    labels_dir = campaign / "final" / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        task_id = task["task_id"]
        expected = [r for r in rows if r["recommended_task"] == task_id]
        package_dir = campaign / "01-cvat-packages" / task_id
        review_template = package_dir / "TEMPLATE-review.csv"
        if not review_template.exists():
            write_csv(review_template, [{"image": r["filename"], "status": "",
                                        "reviewer": "", "reviewed_at": ""} for r in expected],
                      ["image", "status", "reviewer", "reviewed_at"])
        completion_template = package_dir / "TEMPLATE-completion.json"
        if not completion_template.exists():
            completion_template.write_text(json.dumps({
                "task_id": task_id, "reviewer": "", "completed_at": "",
                "image_count": len(expected), "export_sha256": "", "confirmation": "",
            }, indent=2) + "\n", encoding="utf-8")
        state, task_issues, labels, statuses = inspect_task(
            task_id, expected, campaign / "exports" / task_id)
        states[task_id] = state
        issues.extend(task_issues)
        if not state["completed"]:
            continue
        for row in expected:
            name = row["filename"]
            label_path = labels_dir / (row["image_id"].replace(":", "_") + ".txt")
            lines = [f"{cls} {x:.8f} {y:.8f} {w:.8f} {h:.8f}" for cls, x, y, w, h in labels[name]]
            label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            row["annotation_status"] = statuses[name]
            row["person_box_count"] = len(lines)
            row["label_sha256"] = digest(label_path)
    for row in rows:
        if row["annotation_status"] == "VALID_FULL_FRAME_NEGATIVE":
            row["annotation_status"] = "VERIFIED_NEGATIVE"
            empty_hash = hashlib.sha256(b"").hexdigest().upper()
            row["label_sha256"] = empty_hash
    duplicate_shas = [value for value, count in Counter(r["image_sha256"] for r in rows).items()
                      if count > 1]
    if duplicate_shas:
        issues.append({"severity": "BLOCKER", "task_id": "", "image": "",
                       "code": "DUPLICATE_IMAGE_SHA", "detail": str(len(duplicate_shas))})
    groups = {}
    try:
        groups = plan_split(rows, seed=seed,
            minimum_positive_groups=minimum_independent_groups,
            minimum_negative_groups=minimum_independent_groups)
        split_result = {"status": "CANDIDATE_NOT_FROZEN", "seed": seed, "groups": groups}
    except ValueError as exc:
        split_result = {"status": "BLOCKED", "seed": seed, "reason": str(exc), "groups": {}}
    (campaign / "06-split-planning" / "split-plan.json").write_text(
        json.dumps(split_result, indent=2) + "\n", encoding="utf-8")
    frozen_path = campaign / "final" / "frozen-evaluation.json"
    frozen = False
    if frozen_path.is_file():
        try:
            frozen = (json.loads(frozen_path.read_text(encoding="utf-8")) ==
                      freeze_payload(rows, groups))
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
        if not frozen:
            issues.append({"severity": "BLOCKER", "task_id": "", "image": "",
                           "code": "FROZEN_EVALUATION_MISMATCH", "detail": "freeze no coincide con el manifest actual"})
    gate = readiness(rows, states, issues, frozen,
                     minimum_negative_images=minimum_negative_images,
                     minimum_independent_groups=minimum_independent_groups, split=groups)
    (campaign / "07-readiness" / "readiness.json").write_text(
        json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    write_csv(campaign / "04-qa" / "qa-issues.csv", issues,
              ["severity", "task_id", "image", "code", "detail"])
    qa = {"issue_counts": dict(sorted(Counter(r["code"] for r in issues).items())),
          "blocking_issues": sum(r["severity"] == "BLOCKER" for r in issues),
          "completed_tasks": sum(s["completed"] for s in states.values()),
          "total_tasks": len(states), "exact_duplicate_images": len(duplicate_shas)}
    (campaign / "04-qa" / "qa-summary.json").write_text(
        json.dumps(qa, indent=2) + "\n", encoding="utf-8")
    write_csv(campaign / "final" / "verified-manifest.csv", rows,
              list(dict.fromkeys([*rows[0], "label_sha256"])))
    counts = Counter(r["annotation_status"] for r in rows)
    (campaign / "annotation-progress.md").write_text(
        f"# Progreso PERSON\n\nTotal: {len(rows)}; positivas verificadas: "
        f"{sum(r['annotation_status'] == 'HUMAN_VERIFIED' for r in rows)}; "
        f"negativas verificadas: {counts['VERIFIED_NEGATIVE']}; "
        f"pendientes: {len(rows) - counts['HUMAN_VERIFIED'] - counts['VERIFIED_NEGATIVE']}; "
        f"ambiguas: {counts['REVIEW_AMBIGUOUS']}; "
        f"tareas completas: {qa['completed_tasks']}/{qa['total_tasks']}.\n",
        encoding="utf-8")
    return {"qa": qa, "readiness": gate["decision"], "split": split_result["status"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--minimum-negative-images", type=int, default=30)
    parser.add_argument("--minimum-independent-groups", type=int, default=3)
    args = parser.parse_args()
    print(json.dumps(process(args.campaign, seed=args.seed,
        minimum_negative_images=args.minimum_negative_images,
        minimum_independent_groups=args.minimum_independent_groups), indent=2))


if __name__ == "__main__":
    main()
