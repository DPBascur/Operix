# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compare exploratory PERSON proposals on approved lab frames, without ground truth."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

from operix_engine.person_metrics import box_iou


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def approved_child(root, name, digest):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,130}", name):
        raise ValueError("Expected a basename in the prepared media directory")
    path = root / name
    if path.is_symlink() or sha256(path) != digest:
        raise ValueError(f"Prepared media integrity mismatch: {name}")
    return path


def pair_boxes(left, right, cutoff=0.5):
    candidates = sorted(
        (-box_iou(a["bbox_xyxy"], b["bbox_xyxy"]), i, j)
        for i, a in enumerate(left)
        for j, b in enumerate(right)
    )
    used_left, used_right, matches = set(), set(), []
    for negative_iou, i, j in candidates:
        if -negative_iou < cutoff:
            break
        if i not in used_left and j not in used_right:
            used_left.add(i)
            used_right.add(j)
            matches.append({"first_index": i, "second_index": j, "iou": -negative_iou})
    return matches


def compare_sample(frame, sample, model, options):
    result, = model.predict(frame, **options)
    second = [
        {"bbox_xyxy": values[:4], "confidence": values[4]}
        for values in result.boxes.data.cpu().tolist()
        if values[5] == 0 and values[0] < values[2] and values[1] < values[3]
    ]
    first = sample["person_boxes"]
    return {**sample, "second_person_boxes": second, "matches": pair_boxes(first, second)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--proposals", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--checkpoint-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.checkpoint.suffix != ".pt" or sha256(args.checkpoint) != args.checkpoint_sha256:
        raise ValueError("Local checkpoint does not match its expected SHA-256")
    proposals = json.loads(args.proposals.read_text(encoding="utf-8"))
    if proposals["status"] != "exploratory_unreviewed":
        raise ValueError("Expected an unreviewed lab proposal bundle")
    pin = proposals["prepared_manifest"]
    approved_child(args.prepared, pin["filename"], pin["sha256"])
    os.environ.update(CUDA_VISIBLE_DEVICES="-1", YOLO_OFFLINE="true", YOLO_AUTOINSTALL="false")
    import cv2
    import torch
    import ultralytics

    torch.set_num_threads(2)
    cv2.setNumThreads(2)
    model = ultralytics.YOLO(str(args.checkpoint.resolve()), task="detect")
    if model.names.get(0) != "person":
        raise ValueError("Checkpoint must map class zero to PERSON")
    options = dict(device="cpu", classes=[0], conf=0.25, iou=0.7, imgsz=640,
                   rect=True, half=False, max_det=100, verbose=False, save=False)
    clips = []
    for clip in proposals["clips"]:
        path = approved_child(args.prepared, clip["filename"], clip["prepared_sha256"])
        capture = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
        samples = []
        frame_index = -1
        try:
            for sample in clip["samples"]:
                required_index = sample["frame_index"]
                if type(required_index) is not int or required_index <= frame_index:
                    raise ValueError("Expected strictly increasing frame indices")
                while frame_index < required_index:
                    ok, frame = capture.read()
                    if not ok:
                        raise ValueError(f"Cannot read frame {required_index}")
                    frame_index += 1
                samples.append(compare_sample(frame, sample, model, options))
        finally:
            capture.release()
        matched = sum(len(sample["matches"]) for sample in samples)
        clips.append({"filename": path.name, "sha256": clip["prepared_sha256"], "matched": matched,
                      "first_only": sum(len(sample["person_boxes"]) for sample in samples) - matched,
                      "second_only": sum(len(sample["second_person_boxes"]) for sample in samples) - matched,
                      "samples": samples})
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump({"status": "exploratory_no_ground_truth", "match_iou": 0.5,
                   "first_model": proposals["model"], "proposal_bundle_sha256": sha256(args.proposals),
                   "second_model": {"checkpoint": args.checkpoint.name, "sha256": args.checkpoint_sha256,
                                    "ultralytics": ultralytics.__version__, "inference": options},
                   "clips": clips}, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
