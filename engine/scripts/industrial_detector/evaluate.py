# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evaluate at IoU 0.50–0.95, with validation-only operating point selection."""
import argparse
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

from prepare import CLASSES, digest
from operix_engine.person_metrics import Prediction, box_iou, match_frame, summarize

LEGACY = {"person": (.10, .70), "forklift": (.45, .55)}
IOU = tuple(round(.50 + i*.05, 2) for i in range(10))

# Predeclared before inference on independent Roboflow. These are promotion gates.
LIMITS = {
    "person_recall_max_loss": .03, "person_precision_max_loss": .03, "person_ap50_max_loss": .03,
    "forklift_recall_max_loss": .03, "forklift_min_f1_gain": .08, "forklift_max_fp_per_image_gain": .02,
    "forklift_min_precision": .60, "forklift_min_recall": .55,
}


def ranked_matches(truth, detections, iou):
    edges = {key: set(range(len(boxes))) for key, boxes in truth.items()}
    ranks = sorted(((pred.confidence, key, index, pred.box)
                    for key, boxes in detections.items() for index, pred in enumerate(boxes)),
                   key=lambda row: (-row[0], row[1], row[2]))
    for score, key, _, bbox in ranks:
        eligible = edges[key]
        best = max(eligible, key=lambda i: (box_iou(bbox, truth[key][i]), -i), default=None)
        matched = best is not None and box_iou(bbox, truth[key][best]) >= iou
        if matched:
            eligible.remove(best)
        yield score, matched


def calculate_ap(truth, detections, iou):
    n = sum(map(len, truth.values()))
    if not n:
        return None
    seen, tps, precision, recall = 0, 0, [], []
    for _, hit in ranked_matches(truth, detections, iou):
        seen += 1
        tps += hit
        precision.append(tps / seen)
        recall.append(tps / n)
    for i in range(len(precision)-2, -1, -1):
        precision[i] = max(precision[i], precision[i+1])
    j, total = 0, 0.
    for step in range(101):
        while j < len(recall) and recall[j] < step / 100:
            j += 1
        if j < len(precision):
            total += precision[j]
    return total / 101


def operating_point(truth, detections, threshold):
    stats = summarize(tuple(match_frame(boxes, detections[key], confidence=threshold)
                            for key, boxes in truth.items()))
    return {**stats, "fp_per_image": stats["fp"] / len(truth)}


def predict(weights, rows, dataset, *, device, classes, nms, input_size):
    import torch
    from ultralytics import YOLO

    model = YOLO(str(weights), task="detect")
    class_index = {name.lower(): int(idx) for idx, name in model.names.items()}
    if not set(classes) <= class_index.keys():
        raise ValueError(f"Unexpected class names for {weights.name}: {model.names}")
    observations = {name: defaultdict(tuple) for name in classes}
    duration = []
    for start in range(0, len(rows), 8):
        batch = rows[start:start+8]
        predictions = model.predict([str(dataset/r["image"]) for r in batch],
                          imgsz=input_size, rect=False, conf=.001, iou=nms, max_det=150,
                          device=device, classes=[class_index[c] for c in classes], verbose=False)
        for row, pred in zip(batch, predictions, strict=True):
            duration.append(pred.speed["inference"])
            scores = defaultdict(list)
            width, height = pred.orig_shape[1], pred.orig_shape[0]
            for a,b,c,d,confidence,idx in pred.boxes.data.cpu().tolist():
                name = pred.names[int(idx)].lower()
                if a < c and b < d:
                    scores[name].append(Prediction((a/width,b/height,c/width,d/height), confidence))
            for name in classes:
                observations[name][row["image"]] = tuple(scores[name])
    peak = torch.cuda.max_memory_allocated() // 2**20 if device == "0" else None
    return observations, {"inference_median_ms_per_image_batch_8": statistics.median(duration),
                          "peak_torch_mib_process": peak}


def score(rows, detections, thresholds, validation, reference=None):
    report = {}
    for name, predicted in detections.items():
        index = CLASSES.index(name)
        supervised = [row for row in rows if index in row["supervised"]]
        truth = {row["image"]: tuple(box for cls, box in row["boxes"] if cls == index) for row in supervised}
        if not truth:
            continue
        decisions = thresholds[name]
        observed = {key: predicted[key] for key in truth}
        ap = [calculate_ap(truth, observed, iou) for iou in IOU]
        metrics = {"images": len(truth), "instances": sum(map(len, truth.values())),
                   "ap50": ap[0], "ap50_95": statistics.mean(ap) if ap[0] is not None else None}
        if validation:
            grid = tuple(round(i*.025, 3) for i in range(2, 37))
            curve = {t: operating_point(truth, observed, t) for t in grid}
            if decisions is None:
                eligible = list(curve)
                if name == "person" and reference:
                    required = reference[name]["operating_point"]["recall"] - LIMITS["person_recall_max_loss"]
                    eligible = [t for t in eligible if (curve[t]["recall"] or 0) >= required] or [grid[0]]
                if name == "forklift":
                    eligible = [t for t in eligible if (curve[t]["precision"] or 0) >= LIMITS["forklift_min_precision"]] or eligible
                decisions = max(eligible, key=lambda t: (curve[t]["f1"] or 0, curve[t]["precision"] or 0, t))
            metrics["validation_curve"] = curve
        metrics["threshold"] = decisions
        metrics["operating_point"] = operating_point(truth, observed, decisions)
        negatives = {key: boxes for key, boxes in truth.items() if not boxes}
        metrics["negative_images"] = len(negatives)
        metrics["fp_on_negative_images"] = sum(
            pred.confidence >= decisions for key in negatives for pred in observed[key]
        )
        # Recall by normalized box area avoids silently comparing different source dimensions.
        for tag, interval in (("small", (0, .025)), ("medium", (.025, .10)), ("large", (.10, 1.01))):
            sub = {key: tuple(box for box in boxes if interval[0] <= (box[2]-box[0])*(box[3]-box[1]) < interval[1])
                   for key, boxes in truth.items()}
            counts = operating_point(sub, observed, decisions)
            metrics[f"{tag}_recall"] = {"recall": counts["recall"], "instances": sum(map(len, sub.values()))}
        report[name] = metrics
    return report


def error_counts(rows, detections, report):
    errors = defaultdict(Counter)
    for row in rows:
        key = row["image"]
        for name, observations in detections.items():
            index = CLASSES.index(name)
            if index not in row["supervised"]:
                continue
            threshold = report[name]["threshold"]
            truth = [box for c, box in row["boxes"] if c == index]
            available = set(range(len(truth)))
            for pred in sorted(observations[key], key=lambda detection: -detection.confidence):
                if pred.confidence < threshold:
                    break
                best = max(available, key=lambda i: box_iou(pred.box, truth[i]), default=None)
                if best is not None and box_iou(pred.box, truth[best]) >= .5:
                    available.remove(best)
                    continue
                same_overlap = max((box_iou(pred.box, box) for box in truth), default=0.)
                other = max(((box_iou(pred.box, box), c) for c, box in row["boxes"] if c != index), default=(0., -1))
                if same_overlap >= .5:
                    category = "duplicate"
                elif other[0] >= .5:
                    category = "overlaps_" + CLASSES[other[1]]
                elif same_overlap >= .1:
                    category = "localization"
                else:
                    category = "unmatched"
                errors[name][category] += 1
    return errors


def error_sheet(rows, detections, report, dataset, output):
    from PIL import Image, ImageDraw

    tiles = []
    for name, predicted in detections.items():
        if name not in report:
            continue
        threshold = report[name]["threshold"]
        for row in rows:
            index = CLASSES.index(name)
            if index not in row["supervised"]:
                continue
            expected = tuple(box for cls, box in row["boxes"] if cls == index)
            detected = tuple(p for p in predicted[row["image"]] if p.confidence >= threshold)
            counts = match_frame(expected, detected, confidence=threshold)
            if counts.fp or counts.fn:
                tiles.append((counts.fp + counts.fn, name, row, counts, expected, detected))
    if not tiles:
        return
    tiles.sort(key=lambda tile: (-tile[0], tile[1], tile[2]["image"]))
    selection = []
    for name in detections:
        selection.extend([t for t in tiles if t[1] == name][:6])
    sheet = Image.new("RGB", (900, ((len(selection)+2)//3)*210), (23, 29, 43))
    font = ImageDraw.Draw(sheet)
    for i, (_, name, row, counts, expected, detected) in enumerate(selection):
        with Image.open(dataset / row["image"]) as original:
            frame = original.copy()
        frame.thumbnail((290, 175))
        draw = ImageDraw.Draw(frame)
        for boxes, color in ((expected, "cyan"), ([p.box for p in detected], "orange")):
            for a,b,c,d in boxes:
                draw.rectangle((a*frame.width,b*frame.height,c*frame.width,d*frame.height), outline=color, width=2)
        x, y = (i%3)*300, (i//3)*210
        font.text((x+4,y+2), f"{name} | {row['source']} | FP {counts.fp} FN {counts.fn}", fill="white")
        font.text((x+4,y+16), "cyan: annotation  orange: prediction", fill="white")
        sheet.paste(frame,(x+4,y+29))
    sheet.save(output, quality=92)


def eligibility(baseline, candidate):
    b, c = baseline, candidate
    bp, cp = (d["person"]["operating_point"] for d in (b,c))
    bf, cf = (d["forklift"]["operating_point"] for d in (b,c))
    num = lambda n: n if n is not None else 0.
    gates = {
        "person_recall": num(cp["recall"]) >= num(bp["recall"]) - LIMITS["person_recall_max_loss"],
        "person_precision": num(cp["precision"]) >= num(bp["precision"]) - LIMITS["person_precision_max_loss"],
        "person_ap50": num(c["person"]["ap50"]) >= num(b["person"]["ap50"]) - LIMITS["person_ap50_max_loss"],
        "forklift_precision": num(cf["precision"]) >= LIMITS["forklift_min_precision"],
        "forklift_recall": num(cf["recall"]) >= max(LIMITS["forklift_min_recall"], num(bf["recall"]) - LIMITS["forklift_recall_max_loss"]),
        "forklift_f1": num(cf["f1"]) >= num(bf["f1"]) + LIMITS["forklift_min_f1_gain"],
        "forklift_false_positives": cf["fp_per_image"] <= bf["fp_per_image"] + LIMITS["forklift_max_fp_per_image_gain"],
    }
    return {"passed": all(gates.values()), "checks": gates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("split", choices=("validation", "holdout"))
    for name in ("dataset", "candidate", "person", "forklift", "output", "preset"):
        parser.add_argument(f"--{name}", type=lambda p: Path(p).resolve(), required=name != "preset")
    parser.add_argument("--device", choices=("0", "cpu"), default="0")
    parser.add_argument("--candidate-size", nargs=2, type=int, default=(384, 640))
    args = parser.parse_args()
    if (args.split == "holdout") != bool(args.preset):
        parser.error("holdout requires one frozen validation preset")
    if args.output.exists():
        raise FileExistsError(args.output)
    validation = args.split == "validation"
    manifests = args.dataset / "manifest.json"
    rows = [r for r in json.loads(manifests.read_bytes()) if
            r["split"] in (("val", "loco_val") if validation else ("holdout",))]
    if not rows:
        raise ValueError("split is empty")
    if any(digest(args.dataset / r["image"]) != r["sha256"] for r in rows):
        raise ValueError("image provenance changed")
    params = {"dataset_sha256": digest(manifests), "detector_sha256": {key: digest(getattr(args,key))
               for key in ("person","forklift","candidate")}, "candidate_input": list(args.candidate_size),
              "baseline_input": [384,640], "candidate_nms": .60, "limits": LIMITS}
    preset = json.loads(args.preset.read_bytes()) if args.preset else None
    if preset and (preset["settings"] != params or preset["split"] != "validation"):
        raise ValueError("validation preset does not match exactly")
    start = time.perf_counter()
    baseline_detections, timing = {}, {}
    for key, (conf, nms) in LEGACY.items():
        subset = [r for r in rows if CLASSES.index(key) in r["supervised"]]
        part, timing[key] = predict(getattr(args,key), subset, args.dataset,
                                    device=args.device, classes=(key,), nms=nms, input_size=(384,640))
        baseline_detections.update(part)
    categories = tuple(c for i,c in enumerate(CLASSES) if any(i in r["supervised"] for r in rows))
    predicted, timing["candidate"] = predict(args.candidate, rows, args.dataset,
                        device=args.device, classes=categories, nms=.60, input_size=args.candidate_size)
    baseline = score(rows, baseline_detections, {k: v[0] for k,v in LEGACY.items()}, validation)
    candidate = score(rows, predicted, {k: preset["candidate"][k]["threshold"] if preset else None
                                       for k in categories}, validation, reference=baseline)
    output = {"split": args.split, "settings": params, "images": len(rows), "device": args.device,
              "baseline": baseline, "candidate": candidate, "timing": timing, "wall_s": time.perf_counter()-start}
    output["false_positive_breakdown"] = {
        "baseline": error_counts(rows, baseline_detections, baseline),
        "candidate": error_counts(rows, predicted, candidate),
    }
    if not validation:
        output["promotion_quality_gate"] = eligibility(baseline, candidate)
        output["validation_preset_sha256"] = digest(args.preset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False), encoding="utf-8")
    error_sheet(rows, predicted, candidate, args.dataset, args.output.with_suffix(".jpg"))
    for model in ("baseline","candidate"):
        print(model, {key:(r["threshold"],r["operating_point"],r["ap50"],r["ap50_95"])
                     for key,r in output[model].items()}, flush=True)
    print(output.get("promotion_quality_gate"), flush=True)


if __name__ == "__main__":
    main()
