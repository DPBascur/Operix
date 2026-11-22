# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Measure the two frozen RTSP detectors on a shared, predecoded local clip."""

from __future__ import annotations

import argparse
from collections import defaultdict
import gc
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
from statistics import mean, median
import sys
from tempfile import TemporaryDirectory
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
FROZEN_SETTINGS = ROOT / "assets/demo/v0.2.0/metadata.json"
BATCH_SIZES = (1, 2, 4)
STAGES = ("preprocess", "inference", "postprocess")
MATCH_IOU = 0.50


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True, help="Local video file")
    parser.add_argument("--person-weights", type=Path, required=True, help="Frozen YOLO11m checkpoint")
    parser.add_argument("--forklift-weights", type=Path, required=True, help="Frozen specialist v2 checkpoint")
    parser.add_argument("--output", type=Path, required=True, help="New JSON file in an existing directory")
    parser.add_argument("--start-frame", type=int, default=0, help="Zero-based decoded frame index (default 0)")
    parser.add_argument("--frames", type=positive_int, default=120, help="Frames per trial, multiple of 4 (default 120)")
    parser.add_argument("--warmup-batches", type=positive_int, default=5, help="Warmup calls per model and case (default 5)")
    parser.add_argument("--repeats", type=positive_int, default=3, help="Timed trials per case (default 3)")
    parser.add_argument("--fp16", action="store_true", help="Also measure FP16 and compare to FP32 at the same batch size")
    parser.add_argument("--batch-eight", action="store_true", help="Also try batch 8 on a GPU with sufficient free memory")
    args = parser.parse_args()
    if args.start_frame < 0:
        parser.error("--start-frame must be nonnegative")
    largest_batch = 8 if args.batch_eight else max(BATCH_SIZES)
    if args.frames % largest_batch:
        parser.error(f"--frames must be divisible by {largest_batch} so every trial uses only full batches")
    return args


def file_receipt(path: Path, expected_sha256: str | None = None) -> dict:
    path = path.expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError(f"Expected a local file: {path}")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if expected_sha256 is not None and digest != expected_sha256.lower():
        raise ValueError(f"Wrong frozen checkpoint for {path}: expected {expected_sha256}, got {digest}")
    return {"path": str(path), "sha256": digest, "bytes": path.stat().st_size}


def decode_frames(path: str, start: int, count: int) -> tuple[tuple, dict]:
    import cv2
    import numpy as np

    started = perf_counter()
    capture = cv2.VideoCapture(path, cv2.CAP_FFMPEG, [cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE])
    frames = []
    try:
        if not capture.isOpened():
            raise ValueError(f"FFmpeg could not open the local video: {path}")
        backend = capture.getBackendName()
        # Decode sequentially so an approximate seek cannot change frame identity.
        for index in range(start + count):
            ok, image = capture.read()
            if not ok or image is None:
                raise ValueError(f"Video ended or failed to decode at frame {index}; need {start + count} frames")
            if index < start:
                continue
            if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
                raise ValueError(f"Expected a BGR uint8 image at frame {index}")
            if frames and image.shape != frames[0].shape:
                raise ValueError(f"Frame {index} has a different shape from frame {start}")
            image = np.ascontiguousarray(image)
            image.setflags(write=False)
            frames.append(image)
    finally:
        capture.release()
    decode_seconds = perf_counter() - started
    return tuple(frames), {
        "backend": backend,
        "decode_seconds_including_skipped_frames": decode_seconds,
        "shape_hwc": frames[0].shape,
        "decoded_bytes": sum(image.nbytes for image in frames),
        "frames": [
            {"index": index, "bgr_sha256": hashlib.sha256(image).hexdigest()}
            for index, image in enumerate(frames, start)
        ],
    }


def make_detectors(models: dict, fp16: bool) -> dict:
    from ultralytics import YOLO

    from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig

    class ProfiledYOLO(YOLO):
        def predict(self, source, **kwargs):
            kwargs.update(
                device="cuda:0",
                quantize=16 if fp16 else None, rect=True, augment=False,
                agnostic_nms=False, max_det=300, classes=None, compile=False,
            )
            started = perf_counter()
            results = super().predict(source=source, **kwargs)
            if not results:
                raise RuntimeError("Ultralytics returned no results for a nonempty batch")
            self.predict_ms = (perf_counter() - started) * 1000
            # Ultralytics divides each synchronized stage by the number of results.
            self.stage_ms = {key: results[0].speed[key] * len(results) for key in STAGES}
            return results

    detectors = {}
    for role, spec in models.items():
        path = Path(spec["checkpoint"]["path"])
        config = YoloDetectorConfig(
            path, confidence_threshold=spec["confidence"], image_size=spec["imgsz"],
            iou_threshold=spec["nms_iou"], device="cuda",
        )
        model = ProfiledYOLO(str(path), task="detect")
        detector = YoloDetector(config, model_factory=lambda _path, task: model)
        if spec["class_filter"] not in detector.class_names.values():
            raise ValueError(f"{path} does not declare {spec['class_filter']}")
        detectors[role] = detector, model, spec["class_filter"]
    return detectors


def run_batch(frames: tuple, detectors: dict, synchronize) -> tuple[dict, dict]:
    outputs, samples = {}, {}
    for role, (detector, model, class_name) in detectors.items():
        started = perf_counter()
        rows = (detector.detect(frames[0]),) if len(frames) == 1 else detector.detect_batch(frames)
        outputs[role] = tuple(tuple(item for item in row if item.class_name == class_name) for row in rows)
        synchronize()
        samples[role] = {
            **model.stage_ms,
            "predict_wall": model.predict_ms,
            "detector_wall_including_conversion_and_filter": (perf_counter() - started) * 1000,
        }
    return outputs, samples


def summarize(values: list[float], batch_size: int | None = None) -> dict:
    ordered = sorted(values)
    average = mean(values) if values else None
    result = {
        "samples": len(values),
        "mean": average,
        "p50": ordered[math.ceil(len(values) * .50) - 1] if values else None,
        "p95": ordered[math.ceil(len(values) * .95) - 1] if values else None,
        "max": ordered[-1] if values else None,
    }
    if batch_size is not None and average is not None:
        result["amortized_mean_per_frame"] = average / batch_size
    return result


def compare_outputs(reference: tuple, candidate: tuple, start_frame: int) -> dict:
    """Match the most detections above the IoU cutoff, then maximize total IoU."""
    import lap
    import numpy as np

    from operix_engine.person_metrics import box_iou

    def coordinates(detection):
        box = detection.bounding_box
        return box.x_min, box.y_min, box.x_max, box.y_max

    ious, confidence_deltas, coordinate_deltas, unmatched = [], [], [], []
    exact_in_order = reference_count = candidate_count = 0
    for offset, (before, after) in enumerate(zip(reference, candidate, strict=True)):
        exact_in_order += before == after
        reference_count += len(before)
        candidate_count += len(after)
        matched = 0
        if before and after:
            left = [coordinates(item) for item in before]
            right = [coordinates(item) for item in after]
            overlaps = np.array([
                [box_iou(a, b) if before[i].class_id == after[j].class_id else 0.0
                 for j, b in enumerate(right)]
                for i, a in enumerate(left)
            ])
            eligible = overlaps >= MATCH_IOU
            scores = np.where(eligible, min(len(left), len(right)) + 1 + overlaps, 0)
            _, assignment, _ = lap.lapjv(-scores, extend_cost=True)
            for i, j in enumerate(assignment):
                if j >= 0 and eligible[i, j]:
                    matched += 1
                    ious.append(float(overlaps[i, j]))
                    confidence_deltas.append(abs(before[i].confidence - after[j].confidence))
                    coordinate_deltas.append(max(abs(a - b) for a, b in zip(left[i], right[j], strict=True)))
        if matched != len(before) or matched != len(after):
            unmatched.append({
                "frame_index": start_frame + offset,
                "reference_only": len(before) - matched,
                "candidate_only": len(after) - matched,
            })
    return {
        "exact_in_order_frames": exact_in_order,
        "reference_detections": reference_count,
        "candidate_detections": candidate_count,
        "matched_detections": len(ious),
        "unmatched_frames": unmatched,
        "iou": {**summarize(ious), "min": min(ious, default=None)},
        "absolute_confidence_delta": summarize(confidence_deltas),
        "max_absolute_xyxy_delta_px": summarize(coordinate_deltas),
    }


def measure_trial(batches: tuple, detectors: dict, device) -> tuple[dict, dict]:
    import psutil
    import torch

    batch_size = len(batches[0])
    frame_count = batch_size * len(batches)
    process = psutil.Process()
    cuda = torch.cuda
    synchronize = lambda: cuda.synchronize(device)
    synchronize()
    memory = {
        "rss_before_bytes": process.memory_info().rss,
        "cuda_allocated_before_bytes": cuda.memory_allocated(device),
        "cuda_reserved_before_bytes": cuda.memory_reserved(device),
    }
    cuda.reset_peak_memory_stats(device)
    outputs = {role: [] for role in detectors}
    timings = {role: defaultdict(list) for role in detectors}
    batch_wall_ms = []
    started = perf_counter()
    for batch in batches:
        batch_started = perf_counter()
        result, samples = run_batch(batch, detectors, synchronize)
        batch_wall_ms.append((perf_counter() - batch_started) * 1000)
        for role, rows in result.items():
            outputs[role].extend(rows)
            for stage, elapsed in samples[role].items():
                timings[role][stage].append(elapsed)
    wall_seconds = perf_counter() - started
    memory.update(
        cuda_peak_allocated_bytes=cuda.max_memory_allocated(device),
        cuda_peak_reserved_bytes=cuda.max_memory_reserved(device),
        rss_after_bytes=process.memory_info().rss,
    )
    return {
        "wall_seconds": wall_seconds,
        "frames_per_second": frame_count / wall_seconds,
        "dual_batch_wall_ms": summarize(batch_wall_ms, batch_size),
        "per_model_batch_ms": {
            role: {stage: summarize(samples, batch_size) for stage, samples in stages.items()}
            for role, stages in timings.items()
        },
        "memory": memory,
    }, {role: tuple(rows) for role, rows in outputs.items()}


def measure_case(args, frames: tuple, models: dict, batch_size: int, fp16: bool, device, references: dict):
    import torch

    gc.collect()
    torch.cuda.empty_cache()
    batches = tuple(frames[i:i + batch_size] for i in range(0, len(frames), batch_size))
    detectors = make_detectors(models, fp16)
    synchronize = lambda: torch.cuda.synchronize(device)
    for i in range(args.warmup_batches):
        run_batch(batches[i % len(batches)], detectors, synchronize)
    for role, (_, model, _) in detectors.items():
        backend = model.predictor.model
        if backend.device != device or backend.format != "pt" or bool(backend.fp16) != fp16:
            raise RuntimeError(f"{role} did not use the requested device, PyTorch backend and precision")

    trials = []
    for _ in range(args.repeats):
        trial, outputs = measure_trial(batches, detectors, device)
        if not fp16:
            references.setdefault(batch_size, outputs)
        trial["parity_vs_first_fp32_batch_1"] = {
            role: compare_outputs(references[1][role], outputs[role], args.start_frame) for role in models
        }
        if fp16 and batch_size != 1:
            trial["parity_vs_first_fp32_same_batch"] = {
                role: compare_outputs(references[batch_size][role], outputs[role], args.start_frame)
                for role in models
            }
        trials.append(trial)
    return trials


def benchmark(args, models: dict, frames: tuple) -> dict:
    import cv2
    import numpy as np
    import torch
    import ultralytics

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable in this environment")
    device = torch.device("cuda:0")
    torch.cuda.set_device(device)
    random.seed(0)
    np.random.seed(0)
    torch.manual_seed(0)
    torch.backends.cudnn.benchmark = False
    torch.set_float32_matmul_precision("highest")
    torch.backends.cudnn.allow_tf32 = False

    batch_sizes = BATCH_SIZES + (8,) if args.batch_eight else BATCH_SIZES
    if args.batch_eight and torch.cuda.mem_get_info(device)[0] < 4 * 1024**3:
        raise RuntimeError("Batch 8 requires at least 4 GiB of free CUDA memory")
    cases, references = [], {}
    for fp16 in ((False, True) if args.fp16 else (False,)):
        for batch_size in batch_sizes:
            precision = "fp16" if fp16 else "fp32"
            print(f"Measuring {precision}, batch {batch_size}", file=sys.stderr, flush=True)
            trials = measure_case(args, frames, models, batch_size, fp16, device, references)
            cases.append({
                "precision": precision,
                "batch_size": batch_size,
                "median_wall_seconds": median(trial["wall_seconds"] for trial in trials),
                "median_frames_per_second": median(trial["frames_per_second"] for trial in trials),
                "trials": trials,
            })
    baseline_wall = cases[0]["median_wall_seconds"]
    for case in cases:
        case["speedup_vs_fp32_batch_1"] = baseline_wall / case["median_wall_seconds"]
    gpu = torch.cuda.get_device_properties(device)
    return {
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pytorch": torch.__version__,
            "ultralytics": ultralytics.__version__,
            "cuda": torch.version.cuda,
            "cudnn": torch.backends.cudnn.version(),
            "device": str(device),
            "gpu": gpu.name,
            "gpu_memory_bytes": gpu.total_memory,
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        },
        "protocol": {
            "seed": 0,
            "fp32_tf32": False,
            "cudnn_benchmark": False,
            "rect": True,
            "augment": False,
            "agnostic_nms": False,
            "max_det": 300,
            "warmup_batches_per_case": args.warmup_batches,
            "repeats_per_case": args.repeats,
            "match_iou": MATCH_IOU,
            "parity_scope": "Same frame and class ID, after NMS and the production role filter.",
            "timing_scope": "Warm dual-detector wall with both models resident. Decode, model setup, warmup and parity are outside trial wall.",
            "stage_scope": "Ultralytics synchronized stage timings scaled to whole batches. Postprocess includes NMS and box scaling.",
            "memory_scope": "PyTorch CUDA allocator peaks with both detectors resident, plus process RSS snapshots.",
        },
        "cases": cases,
    }


def main() -> None:
    args = parse_args()
    output = args.output.expanduser().resolve()
    try:
        if output.exists() or not output.parent.is_dir():
            raise ValueError("--output must name a new file in an existing directory")
        settings = json.loads(FROZEN_SETTINGS.read_text(encoding="utf-8"))["configuration"]["perception"]
        models = {
            role: {**spec, "checkpoint": file_receipt(getattr(args, f"{role}_weights"), spec["weights_sha256"])}
            for role, spec in settings.items()
        }
        media = file_receipt(args.video)
        frames, decode = decode_frames(media["path"], args.start_frame, args.frames)
        with TemporaryDirectory(prefix="operix-benchmark-yolo-") as config_dir:
            os.environ.update(YOLO_CONFIG_DIR=config_dir, YOLO_OFFLINE="true", YOLO_AUTOINSTALL="false")
            report = benchmark(args, models, frames)
        report.update(schema_version=1, video={**media, **decode}, models=models,
                      benchmark_sha256=file_receipt(Path(__file__))["sha256"])
        payload = json.dumps(report, indent=2, allow_nan=False)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(payload + "\n")
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Benchmark failed: {error}") from error
    print(output)


if __name__ == "__main__":
    main()
