# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audit duplicate candidates, labels and coverage in a prepared detector manifest."""
import argparse
from collections import Counter, defaultdict
import itertools
import json
from pathlib import Path

from PIL import Image

from prepare import CLASSES, digest


def visual_hash(image):
    pixels = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS).get_flattened_data()
    return sum((pixels[i] > pixels[i+1]) << (i-i//9) for i in range(72) if i % 9 != 8)


def audit(dataset):
    manifest = dataset / "manifest.json"
    rows = json.loads(manifest.read_bytes())
    groups = defaultdict(Counter)
    hashes = defaultdict(list)
    signatures = []
    for row in rows:
        key = "/".join((row["split"], row["source"], row["capture_group"]))
        totals = groups[key]
        totals["images"] += 1
        totals["derived_crops"] += bool(row.get("crop_of"))
        positive_only = set(row.get("positive_only", [])) | set(row.get("pseudo_positive_only", []))
        for index, name in enumerate(CLASSES):
            if index in positive_only:
                totals[name + "_positive_only"] += 1
            elif index not in row["supervised"]:
                totals[name + "_not_supervised"] += 1
                continue
            boxes = [box for c, box in row["boxes"] if c == index]
            if index in row["supervised"]:
                totals[name + "_labelled_empty"] += not boxes
            for x1, y1, x2, y2 in boxes:
                size = (x2-x1)*(y2-y1)
                totals[name] += 1
                totals[name + ("_small" if size < .025 else "_large" if size >= .10 else "_medium")] += 1
                totals[name + "_edge"] += x1 <= .01 or y1 <= .01 or x2 >= .99 or y2 >= .99
        if row.get("crop_of"):
            continue
        image = dataset / row["image"]
        hashes[digest(image)].append(row["image"])
        with Image.open(image) as source:
            signatures.append((row["split"], row["image"], visual_hash(source)))
    distant_splits = []
    for (left, first, a), (right, second, b) in itertools.combinations(signatures, 2):
        if (left == "train") == (right == "train"):
            continue
        distance = (a ^ b).bit_count()
        if distance <= 4:
            distant_splits.append({"first": first, "second": second, "hash_distance": distance})
    return {"manifest_sha256": digest(manifest), "groups": dict(groups), "images": len(rows),
            "non_crop_unique_files": len(hashes),
            "exact_duplicates": [members for members in hashes.values() if len(members) > 1],
            "cross_fit_validation_perceptual_candidates": distant_splits}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(audit(args.dataset), indent=2))
