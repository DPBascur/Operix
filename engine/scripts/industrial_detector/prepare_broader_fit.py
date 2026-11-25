# SPDX-License-Identifier: AGPL-3.0-or-later
"""Add vetted development images without reopening an evaluation partition."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path

from PIL import Image

from dataset_audit import visual_hash
from prepare import digest
from prepare_v2 import PARENT, verified_negatives


def label_path(image):
    return Path("labels") / Path(image).relative_to("images").with_suffix(".txt")


def build(base, consumed, output, excluded, negative_source, negative_ids):
    base_manifest, consumed_manifest = base / "manifest.json", consumed / "manifest.json"
    if digest(consumed_manifest) != PARENT:
        raise ValueError("Unexpected licensed source revision")
    rows = json.loads(base_manifest.read_bytes())
    if any(row["split"] == "holdout" for row in rows):
        raise ValueError("Evaluation material cannot be included in this training build")
    output.mkdir(parents=True)
    content = {row["source_sha256"] for row in rows}
    visual = defaultdict(list)
    for row in rows:
        image, label = Path(row["image"]), label_path(row["image"])
        for entry in (image, label):
            (output / entry).parent.mkdir(parents=True, exist_ok=True)
            os.link(base / entry, output / entry)
        if not row.get("crop_of"):
            with Image.open(base / image) as frame:
                visual[visual_hash(frame)].append(row["image"])

    rejected, imported = {}, []
    for row in json.loads(consumed_manifest.read_bytes()):
        if (row["source"] != "roboflow" or row["capture_group"] != "roboflow-train.zip"
                or not any(cls == 1 for cls, _ in row["boxes"])):
            continue
        image = Path(row["image"])
        label = label_path(image)
        if digest(consumed / image) != row["sha256"] or digest(consumed / label) != row["label_sha256"]:
            raise ValueError(f"Modified source image or annotation: {image.name}")
        with Image.open(consumed / image) as frame:
            fingerprint = visual_hash(frame)
        similar = next((matches[0] for signature, matches in visual.items()
                        if (signature ^ fingerprint).bit_count() <= 4), None)
        if image.name in excluded or row["source_sha256"] in content or similar:
            rejected[image.name] = "reviewed" if image.name in excluded else similar or "exact"
            continue
        destination = Path("images/train") / image.name
        # Exhaustive coverage was not verified across this mixed collection.
        # Keep both human-annotated roles positive-only.
        person = any(cls == 0 for cls, _ in row["boxes"])
        os.link(consumed / image, output / destination)
        os.link(consumed / label, output / label_path(destination))
        imported.append({**row, "split": "train", "image": destination.as_posix(),
                         "supervised": [], "positive_only": [0, 1] if person else [1],
                         "label_use": "consumed_development_only"})
        visual[fingerprint].append(destination.as_posix())
        content.add(row["source_sha256"])

    rows.extend(imported)
    rows.extend(verified_negatives(negative_source, negative_ids, rows, output))
    for split in ("train", "val"):
        (output / f"{split}.txt").write_text("".join(
            f"{output / row['image']}\n" for row in rows if row["split"] == split))
    (output / "dataset.yaml").write_text(
        (base / "dataset.yaml").read_text().replace(base.as_posix(), output.as_posix()))
    (output / "manifest.json").write_text(json.dumps(rows, indent=2))
    report = {"retired_source": "roboflow-train.zip development only",
              "base_manifest_sha256": digest(base_manifest), "consumed_manifest_sha256": digest(consumed_manifest),
              "imported_positive_images": len(imported), "excluded": rejected, "negative_ids": negative_ids}
    (output / "source-audit.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("base", "consumed", "output", "negative-source"):
        parser.add_argument(f"--{key}", required=key != "negative-source", type=lambda value: Path(value).resolve())
    parser.add_argument("--negative-id", type=int, action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    args = parser.parse_args()
    if bool(args.negative_id) != bool(args.negative_source):
        parser.error("Supply both the catalog and the reviewed negative IDs")
    build(args.base, args.consumed, args.output, args.exclude, args.negative_source, args.negative_id)
