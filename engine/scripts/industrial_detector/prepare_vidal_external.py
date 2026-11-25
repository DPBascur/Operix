# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepare the real RGB partition from Vidal et al. for equipment-only evaluation."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from PIL import Image

from prepare import digest, normalize_box


REVISION = "a53f79e2a4cef3242a4c211298d3ff4857cdf08b"
TREE_SHA = "b63777f956eebbfebf2bd012184ff81a8fbeb011"
SOURCE = "https://github.com/vidaldani/3D_object_detection"
CAMERAS = {
    "sub_14_annotated_dataset": ("Azure Kinect", 14),
    "ZED2_dataset": ("ZED2", 19),
}
# Counts and class semantics come from the paper's real-data partition.
SOURCE_COUNTS = {0: 14, 1: 137, 2: 18, 3: 29, 4: 12}
EQUIPMENT_CLASSES = {0: 1, 2: 2}


def verify_blob(path, expected):
    data = path.read_bytes()
    actual = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
    if actual != expected:
        raise ValueError(f"Archive differs from the pinned repository: {path.name}")
    return data


def annotations(label, image_width, image_height):
    counts = Counter()
    boxes = []
    for line in label.decode("utf-8").splitlines():
        fields = line.split()
        if not fields:
            continue
        kind = int(fields[0])
        if kind not in SOURCE_COUNTS or len(fields) != 5:
            raise ValueError(f"Unknown label: {line}")
        counts[kind] += 1
        if kind in EQUIPMENT_CLASSES:
            x, y, w, h = map(float, fields[1:])
            # Six-decimal YOLO rounding may place an edge slightly outside the image.
            coords = (x-w/2, y-h/2, x+w/2, y+h/2)
            if not all(-1e-5 <= value <= 1+1e-5 for value in coords):
                raise ValueError(f"Out-of-frame annotation: {line}")
            pixels = [min(1, max(0, value))*length for value, length in
                      zip(coords, (image_width, image_height)*2, strict=True)]
            boxes.append(normalize_box(EQUIPMENT_CLASSES[kind], pixels, image_width, image_height))
    return counts, boxes


def prepare(archive, tree):
    if tree["sha"] != TREE_SHA:
        raise ValueError("The file inventory must be from the pinned repository tree")
    blobs = {entry["path"]: entry["sha"] for entry in tree["tree"] if entry["type"] == "blob"}
    rows = []
    totals = Counter()
    for directory, (camera, count) in CAMERAS.items():
        group = archive / "rd_test_dataset" / directory
        images = sorted(file for file in (group / "images").iterdir() if file.suffix in {".jpg", ".png"})
        if len(images) != count:
            raise ValueError(f"{camera}: expected {count} published RGB images")
        for file in images:
            label = group / "bbox_labels" / file.with_suffix(".txt").name
            relative = file.relative_to(archive).as_posix()
            verify_blob(file, blobs[relative])
            label_bytes = verify_blob(label, blobs[label.relative_to(archive).as_posix()])
            with Image.open(file) as image:
                counts, boxes = annotations(label_bytes, *image.size)
            totals.update(counts)
            rows.append({
                "image": relative, "split": "holdout", "source": "vidal-real-rgb",
                "capture_group": directory, "camera": camera,
                "sha256": digest(file), "boxes": boxes, "supervised": [1, 2],
                "label_sha256": digest(label), "label_kind": "publisher_manual",
                "source_url": SOURCE, "revision": REVISION,
            })
    if totals != SOURCE_COUNTS:
        raise ValueError("Class counts differ from the publication")
    if len({row["sha256"] for row in rows}) != len(rows):
        raise ValueError("Exact duplicate images in the published partition")
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("tree", type=Path)
    args = parser.parse_args()
    tree = json.loads(args.tree.read_text(encoding="utf-8-sig"))
    rows = prepare(args.archive, tree)
    with (args.archive / "manifest.json").open("x", encoding="utf-8") as output:
        json.dump(rows, output, indent=2)
