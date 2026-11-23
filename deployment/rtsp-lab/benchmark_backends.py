# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compare one exported backend with frozen PyTorch detectors on local clips.

Default mode hashes inputs and reports installed package metadata. --execute
exports ONNX on CPU, optionally builds TensorRT 10 engines, then measures CUDA.
For TensorRT, --execute --compile-only produces a reusable report and engines.
Use --engine-report and --engine-report-sha256 to verify those files for inference.
Run in an isolated container with a new output directory and read-only inputs.
"""

from __future__ import annotations

import argparse
from contextlib import nullcontext
from dataclasses import asdict
import gc
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import re
import shutil
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

import benchmark_gpu as lab


PACKAGES = (
    "operix-engine", "ultralytics", "torch", "torchvision", "opencv-python",
    "numpy", "lap", "psutil", "onnx", "onnxruntime", "onnxruntime-gpu",
    "tensorrt-cu13-bindings", "tensorrt-cu13-libs", "nvidia-cuda-runtime",
    "nvidia-cudnn-cu13", "ml-dtypes", "flatbuffers", "protobuf",
)
OPSET = 17
WORKSPACE_BYTES = 512 * 1024**2
BUILD_OPTIMIZATION_LEVEL = 1
WARMUP_BATCHES = 3
REPEATS = 2
TRT_PACKAGES = ("tensorrt-cu13-bindings", "tensorrt-cu13-libs")
ENGINE_PROTOCOL_KEYS = (
    "backend", "nchw", "opset", "embedded_nms", "tf32",
    "trt_workspace_bytes", "trt_builder_optimization_level",
)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, action="append", default=[],
                        help="Local video file, supply once or twice")
    parser.add_argument("--media-manifest", type=Path, help="Verify clip hashes and retain source attribution")
    for role in ("person", "forklift"):
        parser.add_argument(f"--{role}-weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="New directory for manifest, report and exports")
    parser.add_argument("--backend", choices=("ort-cuda", "trt-fp32", "trt-fp16"), default="ort-cuda")
    parser.add_argument("--batch", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--imgsz", type=int, default=640, help="Input width, multiple of 32 from 320 to 960")
    parser.add_argument("--input-height", type=int, help="Static input height, defaults to --imgsz")
    parser.add_argument("--frames", type=int, default=32, help="Consecutive frames per clip, at most 64")
    parser.add_argument("--start-frame", type=int, default=0, help="First decoded ordinal, at most 3600")
    parser.add_argument("--trt-build-level", type=int, choices=(0, 1), default=BUILD_OPTIMIZATION_LEVEL,
                        help="TensorRT builder optimization level, logged in the engine report")
    parser.add_argument("--execute", action="store_true", help="Authorize CUDA work in this process")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--compile-only", action="store_true", help="Export ONNX and build TensorRT engines without video")
    mode.add_argument("--engine-report", type=Path, help="Completed compile-only report.json alongside its artifacts")
    parser.add_argument("--engine-report-sha256", help="Trusted SHA-256 of --engine-report")
    args = parser.parse_args()
    if (args.compile_only or args.engine_report) and args.backend == "ort-cuda":
        parser.error("engine compilation and reuse require a TensorRT backend")
    if args.compile_only and (not args.execute or args.video or args.media_manifest):
        parser.error("--compile-only requires --execute and takes no video or media manifest")
    if not args.compile_only and not 1 <= len(args.video) <= 2:
        parser.error("supply one or two local clips")
    if args.engine_report is None and args.engine_report_sha256 is not None:
        parser.error("--engine-report-sha256 requires --engine-report")
    if args.engine_report and not re.fullmatch(r"[0-9a-fA-F]{64}", args.engine_report_sha256 or ""):
        parser.error("--engine-report requires a 64-digit --engine-report-sha256")
    if not 1 <= args.frames <= 64 or args.frames % args.batch or not 0 <= args.start_frame <= 3600:
        parser.error("require 1–64 frames divisible by batch and start frame in 0–3600")
    if args.input_height is None:
        args.input_height = args.imgsz
    if any(not 320 <= size <= 960 or size % 32 for size in (args.input_height, args.imgsz)):
        parser.error("image dimensions must be multiples of 32 from 320 to 960")
    if args.execute and not args.output:
        parser.error("--execute requires --output")
    return args


def package_versions():
    packages = {}
    for name in PACKAGES:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return packages


def make_manifest(args):
    specs = json.loads(lab.FROZEN_SETTINGS.read_text(encoding="utf-8"))["configuration"]["perception"]
    clips = [lab.file_receipt(path) for path in args.video]
    provenance = None
    if args.media_manifest:
        receipt = lab.file_receipt(args.media_manifest)
        media = json.loads(Path(receipt["path"]).read_text(encoding="utf-8"))
        by_name = {entry["filename"]: entry for entry in media["clips"]}
        for clip in clips:
            approved = by_name.get(Path(clip["path"]).name)
            if approved is None or approved["sha256"].lower() != clip["sha256"]:
                raise ValueError(f"Clip is missing from the media manifest or has a different hash: {clip['path']}")
            clip["provenance"] = approved
        provenance = {"manifest": receipt, "source": media["source"]}
    return {
        "schema_version": 1,
        "status": "planned",
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "packages": package_versions(),
            "trtexec": shutil.which("trtexec"),
        },
        "source": [lab.file_receipt(path) for path in (Path(__file__), Path(lab.__file__), lab.FROZEN_SETTINGS)],
        "models": {
            role: {**spec, "checkpoint": lab.file_receipt(getattr(args, f"{role}_weights"), spec["weights_sha256"])}
            for role, spec in specs.items()
        },
        "clips": clips,
        "media_provenance": provenance,
        "protocol": {
            "backend": args.backend,
            "frames_per_clip": args.frames,
            "start_frame": args.start_frame,
            "nchw": [args.batch, 3, args.input_height, args.imgsz],
            "opset": OPSET,
            "embedded_nms": False,
            "tf32": False,
            "match_iou": lab.MATCH_IOU,
            "warmup_batches": WARMUP_BATCHES,
            "repeats": REPEATS,
            "trt_workspace_bytes": WORKSPACE_BYTES,
            "trt_builder_optimization_level": args.trt_build_level,
            "scope": "Predecoded detector timing and post-NMS role-filtered detection parity. "
                     "Unmatched detections are relative to PyTorch. Tracking, rules and events are untested.",
            "memory_scope": "PyTorch allocator and process RSS. External backend VRAM is outside allocator stats.",
        },
    }


def verify_engine_report(args, manifest):
    report_path = args.engine_report.expanduser().resolve(strict=True)
    payload = report_path.read_bytes()
    digest = sha256(payload).hexdigest()
    if digest != args.engine_report_sha256.lower():
        raise ValueError(f"Engine report SHA-256 mismatch: {report_path}")
    report_receipt = {"path": str(report_path), "sha256": digest, "bytes": len(payload)}
    report = json.loads(payload)
    try:
        if report["schema_version"] != 1 or report["status"] != "compiled":
            raise ValueError("Expected a completed TensorRT compile-only report")
        for key in ENGINE_PROTOCOL_KEYS:
            if report["protocol"][key] != manifest["protocol"][key]:
                raise ValueError(f"Engine report protocol mismatch: {key}")
        build_cuda = {key: report["cuda"][key] for key in ("gpu", "compute_capability")}
        packages = {name: report["runtime"]["packages"][name] for name in TRT_PACKAGES}
        if not all(packages.values()):
            raise ValueError("Engine report is missing TensorRT package versions")
        artifacts = {}
        for role, spec in manifest["models"].items():
            if report["models"][role]["checkpoint"]["sha256"] != spec["checkpoint"]["sha256"]:
                raise ValueError(f"Engine report checkpoint mismatch: {role}")
            artifacts[role] = {}
            for kind in ("onnx", "engine"):
                expected = report["artifacts"][role][kind]
                path = report_path.with_name(f"{role}.{kind}")
                receipt = lab.file_receipt(path)
                if receipt["sha256"] != expected["sha256"] or receipt["bytes"] != expected["bytes"]:
                    raise ValueError(f"Engine report artifact mismatch: {path}")
                artifacts[role][kind] = receipt
    except (KeyError, TypeError) as error:
        raise ValueError("Malformed TensorRT compile report") from error
    manifest.update(artifacts=artifacts, engine_build={
        "report": report_receipt, "cuda": build_cuda, "packages": packages,
    })


def export_onnx(args, role, spec, output):
    import onnx
    from ultralytics import YOLO

    # Exporters write beside their input. Stage a hash-verified private copy.
    with TemporaryDirectory(prefix="operix-export-") as staging:
        checkpoint = Path(staging) / f"{role}.pt"
        shutil.copyfile(spec["checkpoint"]["path"], checkpoint)
        lab.file_receipt(checkpoint, spec["weights_sha256"])
        artifact = Path(YOLO(str(checkpoint), task="detect").export(
            format="onnx", device="cpu", quantize=32, nms=False, simplify=False,
            opset=OPSET, dynamic=False, batch=args.batch, imgsz=(args.input_height, args.imgsz),
        ))
        graph = onnx.load(artifact, load_external_data=False)
        onnx.checker.check_model(graph)
        inputs = graph.graph.input
        if len(inputs) != 1:
            raise RuntimeError(f"Expected one ONNX input for {role}")
        shape = [dim.dim_value for dim in inputs[0].type.tensor_type.shape.dim]
        if (inputs[0].name != "images"
                or shape != [args.batch, 3, args.input_height, args.imgsz]
                or inputs[0].type.tensor_type.elem_type != onnx.TensorProto.FLOAT):
            raise RuntimeError(f"Unexpected ONNX input for {role}: {shape}")
        if any(node.op_type == "NonMaxSuppression" for node in graph.graph.node):
            raise RuntimeError(f"Unexpected embedded NMS for {role}")
        path = output / f"{role}.onnx"
        shutil.copyfile(artifact, path)
    return path, {item.key: item.value for item in graph.metadata_props}


def build_engine(onnx_path, metadata, fp16, optimization_level):
    import tensorrt as trt

    if trt.__version__.partition(".")[0] != "10":
        raise RuntimeError("This builder requires TensorRT 10.x")
    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(0)
    parser = trt.OnnxParser(network, logger)
    if not parser.parse_from_file(str(onnx_path)):
        raise RuntimeError("\n".join(str(parser.get_error(i)) for i in range(parser.num_errors)))
    settings = builder.create_builder_config()
    settings.clear_flag(trt.BuilderFlag.TF32)
    if fp16:
        if not builder.platform_has_fast_fp16:
            raise RuntimeError("TensorRT does not report fast FP16 on this device")
        settings.set_flag(trt.BuilderFlag.FP16)
    settings.builder_optimization_level = optimization_level
    settings.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, WORKSPACE_BYTES)
    engine = builder.build_serialized_network(network, settings)
    if engine is None:
        raise RuntimeError(f"TensorRT build failed for {onnx_path.name}")
    # Ultralytics' length-prefixed header preserves class labels and input metadata.
    header = json.dumps(metadata).encode("utf-8")
    path = onnx_path.with_suffix(".engine")
    with path.open("xb") as stream:
        stream.write(len(header).to_bytes(4, "little"))
        stream.write(header)
        stream.write(engine)
    return path


def strict_ort_sessions():
    import onnxruntime as ort

    if "CUDAExecutionProvider" not in ort.get_available_providers():
        raise RuntimeError("ONNX Runtime CUDAExecutionProvider is unavailable")
    ort.preload_dlls(directory="")
    create_session = ort.InferenceSession

    def cuda_session(path, session_options, *, providers):
        # Ultralytics normally allows CPU node placement. A CUDA result here must
        # have a CUDA-only graph, and the Runtime retry fallback stays disabled.
        options = session_options or ort.SessionOptions()
        options.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        session = create_session(path, options, providers=[
            ("CUDAExecutionProvider", {"device_id": "0", "use_tf32": "0"}),
        ])
        session.disable_fallback()
        if session.get_providers()[0] != "CUDAExecutionProvider":
            raise RuntimeError(f"ONNX Runtime failed to initialize CUDA: {session.get_providers()}")
        return session

    return patch.object(ort, "InferenceSession", cuda_session)


def make_detectors(models, paths, shape, rect):
    from ultralytics import YOLO
    from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig

    class ProfiledYOLO(YOLO):
        def predict(self, source, **kwargs):
            started = perf_counter()
            if not rect:
                kwargs["imgsz"] = shape
            results = super().predict(
                source, **kwargs, rect=rect, quantize=32, augment=False,
                agnostic_nms=False, max_det=300, compile=False,
            )
            self.predict_ms = (perf_counter() - started) * 1000
            self.stage_ms = {stage: results[0].speed[stage] * len(results) for stage in lab.STAGES}
            return results

    detectors = {}
    for role, spec in models.items():
        path = paths[role]
        model = ProfiledYOLO(str(path), task="detect")
        config = YoloDetectorConfig(
            path, confidence_threshold=spec["confidence"], iou_threshold=spec["nms_iou"],
            image_size=spec["imgsz"] if rect else shape[1], device="cuda",
        )
        detectors[role] = YoloDetector(config, model_factory=lambda *_args, **_kwargs: model), model, spec["class_filter"]
    return detectors


def measure_case(args, models, paths, clips, device, backend, rect=False):
    import torch

    batch_size = 1 if rect else args.batch
    with strict_ort_sessions() if backend == "onnx" else nullcontext():
        detectors = make_detectors(models, paths, (args.input_height, args.imgsz), rect)
        observations = []
        for frames in clips:
            batches = tuple(frames[i:i + batch_size] for i in range(0, len(frames), batch_size))
            for i in range(WARMUP_BATCHES):
                lab.run_batch(batches[i % len(batches)], detectors, lambda: torch.cuda.synchronize(device))
            for role, (detector, model, target) in detectors.items():
                loaded = model.predictor.model
                if loaded.format != backend or loaded.device != device or loaded.fp16:
                    raise RuntimeError(f"{role} did not load the requested {backend} CUDA backend with FP32 input")
                if target not in detector.class_names.values():
                    raise RuntimeError(f"{role} is missing class {target}")
            observations.append([lab.measure_trial(batches, detectors, device) for _ in range(REPEATS)])
    return observations


def compare_trials(candidate, reference, matched_shape, start):
    comparisons = {}
    for role, rows in candidate.items():
        comparisons[role] = {
            "vs_operational_rect_batch_1": lab.compare_outputs(reference[role], rows, start),
            "vs_same_shape_and_batch": lab.compare_outputs(matched_shape[role], rows, start),
        }
    return comparisons


def serialize_detections(outputs, start):
    return {
        role: [{"frame_index": start + i, "detections": [asdict(item) for item in row]}
               for i, row in enumerate(rows)]
        for role, rows in outputs.items()
    }


def run(args, manifest, output):
    packages = manifest["runtime"]["packages"]
    is_ort = args.backend == "ort-cuda"
    if is_ort:
        required = ("onnx", "onnxruntime-gpu")
    elif args.engine_report:
        required = TRT_PACKAGES
    else:
        required = ("onnx", *TRT_PACKAGES)
    missing = [name for name in required if not packages[name]]
    if missing:
        raise RuntimeError(f"Missing packages: {', '.join(missing)}")
    if is_ort and packages["onnxruntime"]:
        raise RuntimeError("ORT CUDA requires onnxruntime-gpu without the CPU onnxruntime distribution")
    if args.engine_report and any(packages[name] != manifest["engine_build"]["packages"][name]
                                  for name in TRT_PACKAGES):
        raise RuntimeError("TensorRT packages differ from the engine build")

    import torch

    clips, decoded = [], []
    if not args.compile_only:
        for clip in manifest["clips"]:
            frames, receipt = lab.decode_frames(clip["path"], args.start_frame, args.frames)
            clips.append(frames)
            decoded.append(receipt)
    models = manifest["models"]
    paths = {role: Path(spec["checkpoint"]["path"]) for role, spec in models.items()}
    artifacts, onnx_models = {}, {}
    if not args.engine_report:
        for role, spec in models.items():
            started = perf_counter()
            onnx_path, metadata = export_onnx(args, role, spec, output)
            onnx_models[role] = (onnx_path, metadata)
            artifacts[role] = {"onnx": lab.file_receipt(onnx_path), "export_seconds": perf_counter() - started}

    device = torch.device("cuda:0")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA device 0 is unavailable")
    torch.cuda.set_device(device)
    torch.set_float32_matmul_precision("highest")
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    gpu = torch.cuda.get_device_properties(device)
    cuda = {"gpu": gpu.name, "compute_capability": [gpu.major, gpu.minor],
            "vram_bytes": gpu.total_memory, "torch_cuda": torch.version.cuda}

    if args.engine_report:
        if any(cuda[key] != value for key, value in manifest["engine_build"]["cuda"].items()):
            raise RuntimeError("CUDA device differs from the engine build")
        artifacts = manifest["artifacts"]
        candidate_paths = {role: Path(files["engine"]["path"]) for role, files in artifacts.items()}
    else:
        candidate_paths = {}
        for role, (onnx_path, metadata) in onnx_models.items():
            if is_ort:
                candidate_paths[role] = onnx_path
                continue
            if args.compile_only:
                print(f"Building {role} ({args.backend})", flush=True)
            started = perf_counter()
            engine = build_engine(onnx_path, metadata, args.backend == "trt-fp16",
                                  manifest["protocol"]["trt_builder_optimization_level"])
            artifacts[role].update(engine=lab.file_receipt(engine), build_seconds=perf_counter() - started)
            candidate_paths[role] = engine
            if args.compile_only:
                print(f"Built {role} in {artifacts[role]['build_seconds']:.1f}s", flush=True)
    if args.compile_only:
        manifest.update(status="compiled", artifacts=artifacts, cuda=cuda)
        return
    refs = measure_case(args, models, paths, clips, device, "pt", rect=True)
    gc.collect()
    torch.cuda.empty_cache()
    matched_shapes = measure_case(args, models, paths, clips, device, "pt")
    gc.collect()
    torch.cuda.empty_cache()
    candidates = measure_case(args, models, candidate_paths, clips, device, "onnx" if is_ort else "engine")

    comparisons = []
    for decode, reference, matched, candidate in zip(decoded, refs, matched_shapes, candidates, strict=True):
        comparisons.append({
            "decode": decode,
            "operational_pt_fp32": [timing for timing, _ in reference],
            "matched_shape_pt_fp32": [timing for timing, _ in matched],
            "candidate": [
                {
                    "timing": timing,
                    "parity": compare_trials(rows, reference[0][1], matched[0][1], args.start_frame),
                    "detections": serialize_detections(rows, args.start_frame),
                }
                for timing, rows in candidate
            ],
            "operational_detections": serialize_detections(reference[0][1], args.start_frame),
            "matched_shape_detections": serialize_detections(matched[0][1], args.start_frame),
        })
    manifest.update(
        status="complete", artifacts=artifacts, comparisons=comparisons,
        cuda={**cuda, "cudnn": torch.backends.cudnn.version()},
    )


def write_json(path, data):
    payload = json.dumps(data, indent=2, allow_nan=False)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload + "\n")


def main():
    args = parse_args()
    try:
        manifest = make_manifest(args)
        if args.compile_only:
            manifest["compile_only"] = True
        if args.engine_report:
            verify_engine_report(args, manifest)
        if not args.output:
            print(json.dumps(manifest, indent=2))
            return
        output = args.output.expanduser().resolve()
        output.mkdir()
        write_json(output / "manifest.json", manifest)
        if args.execute:
            with TemporaryDirectory(prefix="operix-backend-config-") as config_dir:
                os.environ.update(YOLO_CONFIG_DIR=config_dir, YOLO_OFFLINE="true", YOLO_AUTOINSTALL="false")
                try:
                    run(args, manifest, output)
                except Exception as error:
                    write_json(output / "failure.json", {"status": "failed", "error": str(error)})
                    raise
                write_json(output / "report.json", manifest)
    except (ImportError, OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Backend proof failed: {error}") from error
    print(output)


if __name__ == "__main__":
    main()
