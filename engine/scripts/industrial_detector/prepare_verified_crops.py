# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append reviewed FORKLIFT-only negative regions without modifying the parent dataset."""
import argparse
import json
import os
from pathlib import Path

from PIL import Image

from prepare import digest


def prepare(base, reviews, output):
    manifest = base / "manifest.json"
    review = json.loads(reviews.read_bytes())
    if digest(manifest) != review["parent_manifest_sha256"]:
        raise ValueError("Parent manifest differs from the reviewed experiment")
    rows = json.loads(manifest.read_bytes())
    if any(row["split"] == "holdout" for row in rows):
        raise ValueError("Training build cannot include an external reserve")
    output.mkdir(parents=True)
    for row in rows:
        image = Path(row["image"])
        label = Path("labels") / image.relative_to("images").with_suffix(".txt")
        for entry in (image, label):
            (output / entry).parent.mkdir(parents=True, exist_ok=True)
            os.link(base / entry, output / entry)
    used = {(row["source_sha256"], tuple(row.get("crop_window", ()))) for row in rows}
    for i, item in enumerate(review["crops"]):
        original = reviews.parent / item["file"]
        x1, y1, x2, y2 = window = tuple(item["window"])
        original_hash = digest(original)
        if (original_hash != item["sha256"] or (original_hash, window) in used
                or not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1)
                or not item["review"] or item["split"] != "development"):
            raise ValueError(f"Invalid or duplicate reviewed crop: {item['file']}")
        used.add((original_hash, window))
        image = Path("images/train") / f"reviewed-industrial-crop-{i:03d}.jpg"
        with Image.open(original) as im:
            pixels = tuple(round(value * im.size[j % 2]) for j, value in enumerate(window))
            im.crop(pixels).convert("RGB").save(output / image, quality=94)
        label = output / "labels/train" / image.with_suffix(".txt").name
        label.touch(exist_ok=False)
        rows.append({"source": item["source"], "source_sha256": original_hash, "split": "train",
                     "member": item["member"], "capture_group": item["capture_group"],
                     "image": image.as_posix(), "sha256": digest(output / image),
                     "label_sha256": digest(label), "supervised": [1], "boxes": [],
                     "crop_window": window, "review": item["review"]})
    for split in ("train", "val"):
        (output / f"{split}.txt").write_text("".join(
            f"{output / row['image']}\n" for row in rows if row["split"] == split))
    (output / "dataset.yaml").write_text(
        (base / "dataset.yaml").read_text().replace(base.as_posix(), output.as_posix()))
    (output / "manifest.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "reviews", "output"):
        parser.add_argument(f"--{name}", required=True, type=lambda value: Path(value).resolve())
    args = parser.parse_args()
    prepare(args.base, args.reviews, args.output)
