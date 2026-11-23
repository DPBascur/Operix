"""Reproduce queue overload with an annotated synthetic video and real ByteTrack.

Detector inputs come from the fixture annotations. Queue arrival times are
simulated. CPU service timing excludes the codec and any detector inference.
"""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np

from operix_engine.detection import BoundingBox, Detection
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.rtsp_pilot import Capture, Epoch, Frame

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine" / "scripts"))
from run_rtsp_lab import LabPipeline


WIDTH, HEIGHT, FPS = 320, 180, 12
BATCHES = (1, 1, 7, 9, *(1 for _ in range(8)))
EXPECTED = {("dwell", 5), ("dwell", 14), ("entry", 20), ("dwell", 22)}


def annotations(index):
    # B enters during the unobserved 9–11 burst and enters again in view at 20.
    center = {8: 206, 17: 206, 18: 204, 19: 206, 20: 210}.get(index, 213)
    moving = {"B": (center - 10, 85, center + 10, 150)}
    return {"A": (60, 85, 82, 150), **moving} if index <= 2 else moving


def make_video(path):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise RuntimeError("No se pudo generar el fixture MJPEG")
    try:
        for index in range(sum(BATCHES)):
            image = np.full((HEIGHT, WIDTH, 3), 38, dtype=np.uint8)
            cv2.line(image, (208, 0), (208, HEIGHT - 1), (160, 160, 160), 1)
            for name, (x1, y1, x2, y2) in annotations(index).items():
                color = (180, 130, 60) if name == "A" else (75, 190, 215)
                cv2.rectangle(image, (x1, y1), (x2, y2), color, -1)
            writer.write(image)
    finally:
        writer.release()


def replay(path, *, candidate):
    zone = Zone("area", "Area", ((.65, 0), (1, 0), (1, 1), (.65, 1)), purpose="restricted")
    rules = tuple(RuleConfig(rule, 1, True, {"kind": f"zone_{rule}", "zone_id": "area",
                                           "class_name": "person", "min_duration_s": seconds})
                  for rule, seconds in (("entry", 0), ("dwell", .15)))
    pipeline = LabPipeline(OperationalConfig(1, "synthetic-rtsp", (zone,), rules),
                           SimpleNamespace(width=WIDTH, height=HEIGHT, fps=FPS), infer_remotely=True)
    epoch = Epoch(FPS)
    reader = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    capture = Capture(lambda: None, fps=FPS)
    index = resets = 0
    logical_clock = 1.
    reasons, events, matches = Counter(), [], {}
    service, arrival = [], []
    observed_tracks = []
    track = pipeline.perception.person.track

    def record_tracks(detections):
        result = track(detections)
        observed_tracks[:] = result
        return result

    try:
        with (patch("operix_engine.rtsp_pilot.monotonic", lambda: logical_clock),
              patch.object(pipeline.perception.person, "track", record_tracks)):
            for batch in BATCHES:
                for _ in range(batch):
                    ok, image = reader.read()
                    if not ok:
                        raise ValueError(f"No se pudo leer el cuadro {index}")
                    logical_clock = 1. + index / FPS
                    if len(capture.queue) == capture.capacity:
                        capture._discard("queue_drop")
                    capture.queue.append(Frame(index, 1, logical_clock, index / FPS, image))
                    index += 1
                while frame := capture.next(timeout=0):
                    began = perf_counter()
                    reason, timestamp = epoch.advance(frame)
                    if reason:
                        preserve = candidate and epoch.preserve_tracking
                        resets += not preserve
                        pipeline.reset(epoch.number, preserve_tracking=preserve)
                        reasons[reason] += 1
                    boxes = annotations(frame.index)
                    detected = SimpleNamespace(person=tuple(Detection(0, "person", .95, BoundingBox(*box))
                                                           for box in boxes.values()), forklift=())
                    _, candidates, _, _ = pipeline.process(frame, timestamp, detected=detected)
                    matches[frame.index] = next((item.track_id for item in observed_tracks
                                                 if item.bounding_box.x_min > WIDTH / 2), None)
                    events.extend((item.rule_id, frame.index) for item in candidates)
                    step = (perf_counter() - began) * 1000
                    service.append(step)
                    arrival.append((logical_clock - frame.received) * 1000 + step)
    finally:
        reader.release()
    observed, expected = Counter(events), Counter(EXPECTED)
    return {"epochs": dict(reasons), "tracking_resets": resets, "observed_events": events,
            "correct_events": sum((observed & expected).values()),
            "missed_observable_events": sorted((expected - observed).elements()),
            "false_events": sorted((observed - expected).elements()), "frames": len(service), "drops": dict(capture.counts),
            "actor_b_track_ids": matches, "processing_fps_cpu_fixture": len(service) * 1000 / sum(service),
            "service_p50_ms": median(service), "service_p95_ms": sorted(service)[math.ceil(.95 * len(service)) - 1],
            "simulated_arrival_p95_ms": sorted(arrival)[math.ceil(.95 * len(arrival)) - 1]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    video = args.output / "annotated-fixture.avi"
    make_video(video)
    reference, candidate = (replay(video, candidate=enabled) for enabled in (False, True))
    report = {"protocol": {"emitter_fps_simulated": FPS, "enqueue_batches": BATCHES,
                           "events_expected_from_observations": sorted(EXPECTED),
                           "unobservable": [["dwell", 2], ["entry", 9]]},
              "reference": reference, "candidate": candidate}
    (args.output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if any(result["false_events"] or result["missed_observable_events"] for result in (reference, candidate)):
        raise SystemExit("Las salidas no coinciden con las anotaciones del escenario")
    if not (candidate["actor_b_track_ids"][1] == candidate["actor_b_track_ids"][3]
            and candidate["tracking_resets"] == reference["tracking_resets"] - 1):
        raise SystemExit("La política no conservó la asociación esperada en el salto aislado")


if __name__ == "__main__":
    main()
