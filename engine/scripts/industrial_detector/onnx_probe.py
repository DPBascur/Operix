# SPDX-License-Identifier: AGPL-3.0-or-later
"""Static ONNX FP32 export, CUDA parity and isolated inference comparison."""
import argparse
import ast
import json
import os
import shutil
import statistics
import time
from pathlib import Path

os.environ.update(YOLO_OFFLINE="true", YOLO_AUTOINSTALL="false")

import cv2
import numpy as np
import onnx
import onnxruntime as ort
import torch
from ultralytics import YOLO
from ultralytics.data.augment import LetterBox
from ultralytics.utils.nms import non_max_suppression

from prepare import CLASSES, digest

INPUT = (384, 640)
CUDA = "CUDAExecutionProvider"


def new_session(path, *, profile=False, prefix=None):
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
    if profile:
        options.enable_profiling = True
        options.profile_file_prefix = str(prefix)
    session = ort.InferenceSession(str(path), sess_options=options,
                                   providers=[(CUDA, {"device_id": "0", "use_tf32": "0"})])
    session.disable_fallback()
    if session.get_providers()[0] != CUDA:
        raise RuntimeError("ORT CUDA was not initialized")
    return session


def binding(session, data):
    handle = session.io_binding()
    handle.bind_input(session.get_inputs()[0].name, "cuda", 0, np.float32,
                      tuple(data.shape), data.data_ptr())
    for output in session.get_outputs():
        handle.bind_output(output.name, "cuda", 0)
    return handle


def run(session, bound):
    session.run_with_iobinding(bound)
    return bound.copy_outputs_to_cpu()[0]


def final_boxes(raw, thresholds):
    boxes = non_max_suppression(torch.from_numpy(raw.copy()), conf_thres=float(thresholds.min()),
                                iou_thres=.60, nc=len(CLASSES), max_det=150)[0].numpy()
    return boxes[boxes[:, 4] >= thresholds[0, boxes[:, 5].astype(int), 0]]


def process():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("checkpoint", "samples", "person", "forklift", "preset", "output"):
        p.add_argument(f"--{key}", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if not torch.cuda.is_available() or CUDA not in ort.get_available_providers():
        raise RuntimeError("PyTorch CUDA and ORT CUDA are required")
    torch.set_num_threads(3)
    torch.set_float32_matmul_precision("highest")
    torch.backends.cudnn.allow_tf32 = False
    ort.preload_dlls(directory="")
    args.output.mkdir(parents=True)
    checkpoint = args.output / "industrial-unified.pt"
    shutil.copyfile(args.checkpoint, checkpoint)
    preset = json.loads(args.preset.read_bytes())
    if preset["split"] != "validation" or preset["settings"]["detector_sha256"]["candidate"] != digest(checkpoint):
        raise ValueError("Candidate provenance differs from the validation preset")
    thresholds = np.array([preset["candidate"][k]["threshold"] for k in CLASSES], dtype=np.float32)[None, :, None]
    exported = Path(YOLO(str(checkpoint)).export(format="onnx", imgsz=INPUT, batch=1, device="cpu", opset=17, quantize=32,
                    simplify=False, dynamic=False, nms=False))
    graph = onnx.load(exported, load_external_data=False)
    onnx.checker.check_model(graph)
    if len(graph.graph.input) != 1 or any(node.op_type == "NonMaxSuppression" for node in graph.graph.node):
        raise ValueError("Expected one raw detection output and external NMS")
    candidate = new_session(exported, profile=True, prefix=args.output / "provider")
    pt = YOLO(str(checkpoint)).model.float().eval().fuse().to("cuda")
    names = ast.literal_eval(candidate.get_modelmeta().custom_metadata_map["names"])
    if tuple(names[i] for i in range(len(names))) != CLASSES:
        raise ValueError(f"unexpected export class order: {names}")
    samples, comparisons = [], []
    for path in sorted(args.samples.glob("*.jpg"))[:24]:
        original = cv2.imread(str(path))
        if original is None:
            raise ValueError(f"Unreadable sample: {path}")
        prepared = LetterBox(INPUT, auto=False)(image=original)
        data = np.ascontiguousarray(prepared[:,:,::-1].transpose(2,0,1)[None], dtype=np.float32) / 255.
        x = torch.from_numpy(data).to("cuda")
        torch.cuda.synchronize()
        samples.append(x)
        with torch.inference_mode():
            reference = pt(x)[0].cpu().numpy()
        actual = run(candidate, binding(candidate,x))
        if reference.shape != actual.shape or actual.shape[1] != 4+len(CLASSES):
            raise ValueError("ONNX and PyTorch output shapes differ")
        delta = np.abs(reference-actual)
        pt_boxes, ort_boxes = (final_boxes(raw, thresholds) for raw in (reference, actual))
        nms_passed = (pt_boxes.shape == ort_boxes.shape
                      and np.array_equal(pt_boxes[:, 5], ort_boxes[:, 5])
                      and np.allclose(pt_boxes[:, :4], ort_boxes[:, :4], atol=.05, rtol=0)
                      and np.allclose(pt_boxes[:, 4], ort_boxes[:, 4], atol=.0002, rtol=0))
        comparisons.append({"file": path.name, "sha256": digest(path),
                            "max_box_px": float(delta[:,:4].max()), "max_conf_error": float(delta[:,4:].max()),
                            "nms_detection_count": len(pt_boxes), "nms_passed": bool(nms_passed),
                            "raw_threshold_disagreements": int(np.count_nonzero(
                                (reference[:,4:] >= thresholds) != (actual[:,4:] >= thresholds)))})
    if len(samples) < 12:
        raise ValueError("At least 12 samples are required")
    graph_profile = json.loads(Path(candidate.end_profiling()).read_bytes())
    operators = {}
    for op in graph_profile:
        name = op.get("args",{}).get("provider")
        if name:
            operators[name] = operators.get(name,0)+1
    if not operators.get(CUDA):
        raise RuntimeError("Profiling did not observe CUDA kernels")
    candidate = new_session(exported)
    legacy = [new_session(path) for path in (args.person,args.forklift)]
    routes = {"unified": [candidate], "legacy_dual": legacy}
    handles = {k:[[binding(s,x) for s in sessions] for x in samples] for k,sessions in routes.items()}
    for name, sessions in routes.items():
        for item in handles[name]:
            for session, bound in zip(sessions,item,strict=True):
                run(session,bound)
    times = {key:[] for key in routes}
    for repetition in range(10):
        order = list(routes) if repetition%2 == 0 else tuple(reversed(routes))
        for key in order:
            for group in handles[key]:
                start=time.perf_counter()
                for session, bound in zip(routes[key],group,strict=True):
                    run(session,bound)
                times[key].append((time.perf_counter()-start)*1000)
    summary = {"onnx_sha256": digest(exported), "checkpoint_sha256": digest(checkpoint),
               "legacy_onnx": {"person": digest(args.person), "forklift": digest(args.forklift)},
               "names": names, "input": list(INPUT), "operator_provider_calls": operators,
               "parity": comparisons, "runtime": ort.__version__, "gpu": torch.cuda.get_device_name(0),
               "passed": all(c["max_box_px"] < .05 and c["max_conf_error"] < .0002 and
                             c["nms_passed"] for c in comparisons),
               "inference_plus_copy_ms": {key: {"p50": statistics.median(v), "p95": float(np.percentile(v,95))}
                                           for key,v in times.items()}}
    (args.output / "cuda-probe.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k != "parity"}), flush=True)
    if not summary["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    process()
