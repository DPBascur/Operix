# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run a verified unified detector in the isolated, managed three-camera QA stack."""

from dataclasses import replace
import json
import os
from pathlib import Path
import sys

if __name__ == "__main__":
    sys.path.insert(0, "/qualification/research")

from prepare import CLASSES, digest


def qualified_artifact(root):
    model = root / "industrial-unified.onnx"
    receipt = json.loads((root / "cuda-probe.json").read_bytes())
    preset = json.loads((root / "validation.json").read_bytes())
    settings = preset["settings"]
    shape = tuple(receipt["input"])
    nms = receipt["candidate_nms"]
    thresholds = {name: preset["candidate"][name]["threshold"] for name in CLASSES}
    if (receipt["passed"] is not True or receipt["precision"] != "fp32"
            or shape != (384, 640) or shape != tuple(settings["candidate_input"])
            or receipt["onnx_sha256"] != digest(model) or nms != settings["candidate_nms"]
            or not 0 < nms <= 1 or not all(0 < v <= 1 for v in thresholds.values())
            or receipt["checkpoint_sha256"] != settings["detector_sha256"]["candidate"]
            or receipt["names"] != {str(i): name for i, name in enumerate(CLASSES)}):
        raise ValueError("The QA artifact or its receipt does not match")
    return model, receipt["onnx_sha256"], shape, nms, thresholds


def qualified_source(source, variant, weight_hash, width, nms, thresholds):
    perception = {}
    result = {**source, "perception": perception}
    for role in ("person", "forklift"):
        result[f"{role}_weights_sha256"] = weight_hash
        perception[role] = {
            "model_id": f"UNIFIED_{variant.upper()}_ONNX_CUDA",
            "weights_sha256": weight_hash,
            "class_filter": role,
            "imgsz": width,
            "confidence": thresholds[role],
            "nms_iou": nms,
        }
    return result


def run():
    variant = os.environ.get("OPERIX_QUALIFICATION_VARIANT")
    if (variant not in {"v3", "v7"}
            or os.environ.get("OPERIX_EVENT_API_BASE_URL") != "http://127.0.0.1:8000/api/v1"
            or os.environ.get("OPERIX_RTSP_INFERENCE_SOCKET")):
        raise RuntimeError("Dedicated QA worker and the local event API are required")
    model, weight_hash, shape, nms, thresholds = qualified_artifact(Path("/qualification/artifact"))

    import numpy as np
    import torch
    import qualification_lab_original as lab
    from rtsp_probe_worker import SinglePerception

    sys.path.insert(0, "/app/deployment/rtsp-lab")
    try:
        from benchmark_backends import make_detectors, strict_ort_sessions
    finally:
        sys.path.pop(0)
    original_context = lab.load_context

    def linked_context(output, config_path):
        event, config = original_context(output, config_path)
        source = qualified_source(event.source, variant, weight_hash, shape[1], nms, thresholds)
        return replace(event, source=source), config

    class QualificationPipeline(lab.LabPipeline):
        def __init__(self, config, args, *, infer_remotely=False, onnx_directory=None):
            if infer_remotely or onnx_directory is None:
                raise RuntimeError("Dedicated ONNX test route required")
            super().__init__(config, args, infer_remotely=True)
            spec = {"unified": {"confidence": min(thresholds.values()), "nms_iou": nms, "class_filter": None}}
            with strict_ort_sessions():
                detector = make_detectors(spec, {"unified": model}, shape, False)["unified"][0]
                probe = SinglePerception(self.perception, detector, thresholds)
                probe.process(np.zeros((args.height, args.width, 3), dtype=np.uint8),
                              synchronize=torch.cuda.synchronize)
            if detector.class_names != dict(enumerate(CLASSES)):
                raise ValueError("Unexpected runtime class order")
            probe.reset()
            self.perception = probe

    lab.load_context = linked_context
    lab.LabPipeline = QualificationPipeline
    return lab.main()


if __name__ == "__main__":
    raise SystemExit(run())
