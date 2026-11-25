# SPDX-License-Identifier: AGPL-3.0-or-later
"""Use a verified single detector in the isolated RTSP capacity probe only."""
from collections import defaultdict
from pathlib import Path
import json
import os
import sys
import time

import numpy as np
import torch

from operix_engine.dual_perception import DualPerception, PerceptionFrame, PerceptionTiming
from prepare import CLASSES, digest


class SinglePerception(DualPerception):
    """Keep independent legacy tracking channels after one shared detector call."""

    def __init__(self, channels, detector, thresholds):
        super().__init__(person=channels.person, forklift=channels.forklift)
        self.detector = detector
        self.thresholds = thresholds

    def process(self, frame, *, synchronize=None, clock=time.perf_counter):
        if synchronize is not None:
            synchronize()
        before = clock()
        observations = self.detector.detect(frame)
        if synchronize is not None:
            synchronize()
        elapsed = clock() - before
        groups = defaultdict(list)
        for entry in observations:
            if entry.class_name in ("person", "forklift") and entry.confidence >= self.thresholds[entry.class_name]:
                groups[entry.class_name].append(entry)
        people, forklifts = (tuple(groups[role]) for role in ("person", "forklift"))
        before = clock()
        people_tracks = self.person.track(people)
        middle = clock()
        forklift_tracks = self.forklift.track(forklifts)
        return (PerceptionFrame(people, forklifts, people_tracks, forklift_tracks),
                PerceptionTiming(elapsed, 0., middle - before, clock() - middle))


def run():
    if (os.environ.get("OPERIX_RTSP_LAB_EVENT_POLICY") != "benchmark"
            or os.environ.get("OPERIX_EVENT_API_BASE_URL") != "http://127.0.0.1:18081/api/v1"
            or os.environ.get("OPERIX_RTSP_INFERENCE_SOCKET")):
        raise RuntimeError("The unified probe runs only with the local test sink")
    root = Path("/research-input")
    artifact = root / "industrial-unified.onnx"
    receipt = json.loads((root / "cuda-probe.json").read_bytes())
    validation = json.loads((root / "validation.json").read_bytes())
    if (not receipt["passed"] or digest(artifact) != receipt["onnx_sha256"]
            or receipt["checkpoint_sha256"] != validation["settings"]["detector_sha256"]["candidate"]):
        raise ValueError("The probe artifact or validation preset changed")
    thresholds = {key: validation["candidate"][key]["threshold"] for key in CLASSES}

    import run_rtsp_lab as lab

    sys.path.insert(0, "/app/deployment/rtsp-lab")
    try:
        from benchmark_backends import make_detectors, strict_ort_sessions
    finally:
        sys.path.pop(0)
    legacy_pipeline = lab.LabPipeline

    class ResearchPipeline(legacy_pipeline):
        def __init__(self, config, args, *, onnx_directory):
            super().__init__(config, args, infer_remotely=True)
            spec = {"unified": {"confidence": min(thresholds.values()), "nms_iou": .60, "class_filter": None}}
            with strict_ort_sessions():
                detector = make_detectors(spec, {"unified": artifact}, (384, 640), False)["unified"][0]
                unified = SinglePerception(self.perception, detector, thresholds)
                unified.process(np.zeros((args.height,args.width,3), dtype=np.uint8),
                                synchronize=torch.cuda.synchronize)
                if detector.class_names != dict(enumerate(CLASSES)):
                    raise ValueError("Unexpected ONNX class mapping")
                unified.reset()
                self.perception = unified
    lab.LabPipeline = ResearchPipeline
    raise SystemExit(lab.main())


if __name__ == "__main__":
    run()
