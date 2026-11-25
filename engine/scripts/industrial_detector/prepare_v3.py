# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepare a positive-only PERSON teacher replay and audit the FORKLIFT teacher."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random

import cv2
import torch
from ultralytics import YOLO

from operix_engine.person_metrics import box_iou
from prepare import digest, SEED
from prepare_v2 import verified_negatives

BASE = "528d40257efa22a3411a549e1f293407d07fcbc0fb3e430685e8909636bcd7cc"
TOMIE_AUDIT = "27e0ece00ff1da7e2667389c54b08db5c942cd622d7e576d9c5fab9220a5a294"
CONFIDENCE = .72
MIRROR_IOU = .8


def teacher_boxes(model, images, role, confidence):
    index = next(i for i, name in model.names.items() if name.lower() == role)
    results = model.predict(images, imgsz=(384, 640), rect=False, device="cpu",
                            classes=[index], conf=confidence, iou=.55, verbose=False)
    return [
        [(tuple(map(float, box)), float(score)) for box, score in
         zip(image.boxes.xyxyn.tolist(), image.boxes.conf.tolist(), strict=True)]
        for image in results
    ]


def mirrored_consensus(original, flipped, annotated):
    reflected = [((1-x2, y1, 1-x1, y2), score) for (x1, y1, x2, y2), score in flipped]
    used = set()
    accepted = []
    for box, score in sorted(original, key=lambda pair: -pair[1]):
        if any(box_iou(box, existing) >= .25 for _, existing in annotated):
            continue
        best = max((i for i in range(len(reflected)) if i not in used),
                   key=lambda i: box_iou(box, reflected[i][0]), default=None)
        if best is not None and box_iou(box, reflected[best][0]) >= MIRROR_IOU:
            used.add(best)
            accepted.append((box, min(score, reflected[best][1])))
    return accepted


def label_path(image):
    return Path("labels") / Path(image).relative_to("images").with_suffix(".txt")


def write_labels(path, boxes):
    path.write_text("".join(f"{c} {(x1+x2)/2:.8f} {(y1+y2)/2:.8f} {x2-x1:.8f} {y2-y1:.8f}\n"
                            for c, (x1, y1, x2, y2) in boxes), encoding="utf-8")


def build(args):
    torch.set_num_threads(4)
    base_manifest = args.base / "manifest.json"
    tomie_manifest = args.tomie / "manifest.json"
    if digest(base_manifest) != BASE or digest(tomie_manifest) != TOMIE_AUDIT:
        raise ValueError("Unexpected parent dataset or TOMIE audit")
    rows = json.loads(base_manifest.read_bytes())
    tomie = json.loads(tomie_manifest.read_bytes())
    if any(row["boxes"] or row["split"] != "annotation_audit" for row in tomie):
        raise ValueError("Projected TOMIE boxes must remain outside supervision")
    if any(row["split"] == "holdout" for row in rows):
        raise ValueError("Parent dataset includes a reserved split")
    observed = {row["source_sha256"] for row in rows}
    if any(row["source_sha256"] in observed for row in tomie):
        raise ValueError("External replay duplicates the parent dataset")
    args.output.mkdir(parents=True)
    eligible = [row for row in rows if row["source"] == "loco" and row["split"] == "train"
                and 0 not in row["supervised"] and not row.get("crop_of") and row["boxes"]]
    random.Random(SEED).shuffle(eligible)
    group = [(args.base, row) for row in eligible[:args.loco_count]] + [(args.tomie, row) for row in tomie]
    person = YOLO(str(args.person), task="detect")
    forklift = YOLO(str(args.forklift), task="detect")
    replay, audit = {}, []
    for start in range(0, len(group), 8):
        batch = group[start:start+8]
        frames = []
        for base, row in batch:
            path = base / row["image"]
            if digest(path) != row["sha256"] or (frame := cv2.imread(str(path))) is None:
                raise ValueError(f"Invalid image: {row['image']}")
            frames.append(frame)
        plain = teacher_boxes(person, frames, "person", CONFIDENCE)
        flipped = teacher_boxes(person, [cv2.flip(frame, 1) for frame in frames], "person", CONFIDENCE)
        trucks = teacher_boxes(forklift, frames, "forklift", .65)
        for (base, row), direct, mirror, forks in zip(batch, plain, flipped, trucks, strict=True):
            pseudo = mirrored_consensus(direct, mirror, row["boxes"])
            audit.append({"image_sha256": row["sha256"], "source": row["source"], "capture_group": row["capture_group"],
                          "person_direct": len(direct), "person_retained": len(pseudo),
                          "forklift_teacher": [{"box": box, "score": score,
                                                 "max_verified_iou": max((box_iou(box, other) for cls, other in
                                                                          row["boxes"] if cls == 1), default=None)}
                                                for box, score in forks]})
            if pseudo:
                image = row["image"] if base == args.base else "images/train/tomie-" + Path(row["image"]).name
                replay[image] = (base / row["image"], {**row, "image": image, "split": "train",
                    "boxes": [*row["boxes"], *((0, box) for box, _ in pseudo)],
                    "pseudo_positive_only": [0], "person_teacher_confidence": [score for _, score in pseudo]})
    for row in rows:
        src = Path(row["image"])
        label = label_path(src)
        for relative in (src, label):
            (args.output / relative).parent.mkdir(parents=True, exist_ok=True)
        if row["image"] not in replay:
            os.link(args.base / src, args.output / src)
            os.link(args.base / label, args.output / label)
    rows = [row for row in rows if row["image"] not in replay]
    for image, (src, row) in replay.items():
        os.link(src, args.output / image)
        label = args.output / label_path(image)
        write_labels(label, row["boxes"])
        rows.append({**row, "label_sha256": digest(label)})
    rows.extend(verified_negatives(args.negative_source, args.negative_id, rows, args.output))
    for split in ("train", "val"):
        parent_keys = [row["image"] for row in json.loads(base_manifest.read_bytes()) if row["split"] == split]
        keys = dict.fromkeys([*parent_keys, *(row["image"] for row in rows if row["split"] == split)])
        (args.output / f"{split}.txt").write_text("".join(f"{args.output / key}\n" for key in keys))
    (args.output / "dataset.yaml").write_text(
        (args.base / "dataset.yaml").read_text().replace(args.base.as_posix(), args.output.as_posix()))
    (args.output / "manifest.json").write_text(json.dumps(rows, indent=2))
    stats = Counter(row["source"] for _, row in replay.values())
    report = {"base_sha256": BASE, "tomie_sha256": TOMIE_AUDIT, "seed": SEED,
              "person_sha256": digest(args.person), "forklift_sha256": digest(args.forklift),
              "person_confidence": CONFIDENCE, "mirror_iou": MIRROR_IOU,
              "replay_images": stats, "verified_negative_ids": args.negative_id, "audit": audit}
    (args.output / "teacher-audit.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({**report, "audit": len(audit)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "tomie", "person", "forklift", "output", "negative-source"):
        parser.add_argument(f"--{name}", type=lambda value: Path(value).resolve(), required=name != "negative-source")
    parser.add_argument("--loco-count", type=int, default=72, choices=range(1, 201))
    parser.add_argument("--negative-id", type=int, action="append", default=[])
    args = parser.parse_args()
    if bool(args.negative_source) != bool(args.negative_id):
        parser.error("Provide both the source and reviewed negative IDs.")
    build(args)
