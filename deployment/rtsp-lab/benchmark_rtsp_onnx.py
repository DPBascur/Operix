"""Adapt the dedicated worker to verified ONNX exports in the benchmark image."""

import hashlib
import json
from pathlib import Path
import sys


MODELS = Path("/experimental-models")
SHAPE = (384, 640)


def verified_export(report, role, expected_checkpoint):
    artifact = MODELS / f"{role}.onnx"
    checkpoint = report["models"][role]["checkpoint"]["sha256"]
    with artifact.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if checkpoint != expected_checkpoint or report["artifacts"][role]["onnx"]["sha256"] != actual:
        raise ValueError(f"The {role} export does not match the frozen checkpoint and proof report")
    return artifact


def main():
    import _rtsp_pytorch_worker as worker

    sys.path.insert(0, "/app/rtsp-proof")
    from benchmark_backends import make_detectors, strict_ort_sessions

    feeds = json.loads(Path("/run-data/feeds.json").read_bytes())
    if feeds["mode"] != "optimized" or feeds["width"] * 9 != feeds["height"] * 16:
        raise ValueError("ONNX proof requires dedicated workers and 16:9 replay")
    report = json.loads((MODELS / "report.json").read_bytes())
    if (report["status"] != "complete" or report["protocol"]["backend"] != "ort-cuda"
            or report["protocol"]["nchw"] != [1, 3, *SHAPE]):
        raise ValueError("Expected a completed FP32 ONNX CUDA report for 384x640 input")
    checkpoints = {"person": worker.PERSON_SHA, "forklift": worker.FORKLIFT_SHA}
    artifacts = {role: verified_export(report, role, checksum) for role, checksum in checkpoints.items()}

    def detector(checkpoint, confidence, iou):
        role = checkpoint.stem
        spec = report["models"][role]
        if (confidence, iou) != (spec["confidence"], spec["nms_iou"]):
            raise ValueError(f"The {role} proof used different confidence or NMS settings")
        return make_detectors({role: spec}, artifacts, SHAPE, rect=False)[role][0]

    worker.detector = detector
    with strict_ort_sessions():
        return worker.main()


if __name__ == "__main__":
    sys.exit(main())
