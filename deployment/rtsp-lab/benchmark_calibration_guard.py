"""CPU-only comparison of the RTSP lab's guard gate with identical replay inputs.

Uses the production PatternFramingGuard with real ArUco detection, synthetic BGR
frames, and a deterministic arrival clock. Decode, sleeping, inference, tracking
and rule evaluation are outside the timed section. Each camera has its own guard.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter_ns, process_time_ns

import cv2
import numpy as np

from benchmark_decode_local import p95

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine" / "src"))
from operix_engine.calibration_patterns import detect_marker_corners
from operix_engine.pattern_framing import PatternFramingGuard, SAMPLE_SECONDS, SHIFT_SAMPLES


DICTIONARY = "DICT_4X4_50"
MARKERS = ((0, .17, .24), (1, .52, .34), (2, .72, .68))


def fixture(width, height):
    frame = np.full((height, width, 3), 220, dtype=np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    size = min(width, height) // 9
    for marker, x, y in MARKERS:
        tag = cv2.aruco.generateImageMarker(dictionary, marker, size)
        left, top = int(x * width), int(y * height)
        frame[top:top + size, left:left + size] = tag[:, :, None]
    reference = detect_marker_corners(frame, DICTIONARY)
    if set(reference) != {marker for marker, _, _ in MARKERS}:
        raise RuntimeError(f"Fixture markers failed detection: {list(reference)}")
    moved = np.roll(frame, round(width * .05), axis=1)
    return frame, moved, {"width": width, "height": height, "dictionary": DICTIONARY,
                          "marker_corners": reference}


def distribution(samples):
    return {"calls": len(samples), "p50_ms": median(samples) / 1e6,
            "p95_ms": p95(samples) / 1e6}


def replay(stable, moved, evidence, *, fps, seconds, cameras, scenario, mode):
    guards = [PatternFramingGuard(evidence) if camera < mode else None for camera in range(cameras)]
    timings, sampled, other = [], [], []
    states, transitions = [Counter() for _ in guards], [[] for _ in guards]
    previous = [None] * cameras
    shift_at = fps * 3
    cpu_start = process_time_ns()
    for index in range(seconds * fps):
        received = index / fps
        frame = moved if scenario == "shift" and index >= shift_at else stable
        for camera, guard in enumerate(guards):
            due = guard is not None and guard.state != "INVALID" and (
                received >= guard._next_sample
            )
            started = perf_counter_ns()
            metric_valid = guard is None or guard.update(frame, index, received) == "VALID"
            elapsed = perf_counter_ns() - started
            timings.append(elapsed)
            (sampled if due else other).append(elapsed)
            status = guard.state if guard is not None else "UNCALIBRATED"
            states[camera][status] += 1
            if previous[camera] != status:
                transitions[camera].append([index, status, metric_valid])
                previous[camera] = status
    replay_cpu_ms = (process_time_ns() - cpu_start) / 1e6
    invalidations = [guard.invalidated_frame if guard is not None else None for guard in guards]
    for camera, counts in enumerate(states):
        if camera >= mode:
            expected = [[0, "UNCALIBRATED", True]]
        elif scenario == "stable":
            expected = [[0, "VALID", True]]
        else:
            invalidated = shift_at + round((SHIFT_SAMPLES - 1) * SAMPLE_SECONDS * fps)
            expected = [[0, "VALID", True], [shift_at, "SUSPECT", False],
                        [invalidated, "INVALID", False]]
            if invalidations[camera] != invalidated:
                raise RuntimeError(f"Unexpected invalidation frame: {invalidations[camera]}")
        if transitions[camera] != expected or sum(counts.values()) != seconds * fps:
            raise RuntimeError(f"Unexpected guard state progression: {transitions[camera]}")
    return {"all_calls": distribution(timings), "sample_calls": distribution(sampled) if sampled else None,
            "other_calls": distribution(other), "timed_calls_total_ms": sum(timings) / 1e6,
            "replay_process_cpu_ms": replay_cpu_ms, "states_by_camera": states,
            "transitions_by_camera": transitions, "invalidated_frame_by_camera": invalidations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--fps", type=int, default=12)
    parser.add_argument("--seconds", type=int, default=8)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    if not (240 <= args.width <= 3840 and 240 <= args.height <= 2160
            and 2 <= args.fps <= 60 and 7 <= args.seconds <= 120 and 1 <= args.repeats <= 30):
        parser.error("Use 240–3840 width, 240–2160 height, 2–60 FPS, 7–120 seconds and 1–30 repeats")
    cv2.ocl.setUseOpenCL(False)
    cv2.setNumThreads(1)
    stable, moved, evidence = fixture(args.width, args.height)
    report = {"platform": platform.platform(), "opencv": cv2.__version__, "numpy": np.__version__,
              "opencv_threads": cv2.getNumThreads(), "replay": vars(args),
              "input": {"stable_sha256": hashlib.sha256(stable).hexdigest(),
                        "shifted_sha256": hashlib.sha256(moved).hexdigest(), "shift_at_seconds": 3},
              "guard_sample_seconds": SAMPLE_SECONDS, "comparisons": []}
    for cameras in (1, 2):
        for scenario in ("stable", "shift"):
            results = {mode: [] for mode in range(cameras + 1)}
            for repeat in range(-1, args.repeats):
                order = list(results) if repeat % 2 == 0 else list(reversed(results))
                for mode in order:
                    sample = replay(stable, moved, evidence, fps=args.fps, seconds=args.seconds,
                                    cameras=cameras, scenario=scenario, mode=mode)
                    if repeat >= 0:
                        results[mode].append(sample)
            for mode, runs in results.items():
                report["comparisons"].append({"cameras": cameras, "calibrated": mode,
                                              "scenario": scenario, "runs": runs})
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
