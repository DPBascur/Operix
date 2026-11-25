"""Pinned FP32 ONNX CUDA detectors for the dedicated RTSP lab worker."""

from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys

from run_rtsp_pilot import checked_file


INPUT_SHAPE = (384, 640)
ORT_VERSION = "1.27.0"
EXPORT_HASHES = {
    "person": "fd09d875322bc9b152671ed4729dd2bf579b568b293e141973bacaabbc090b9c",
    "forklift": "d73cdedf9d938651e161c7cbaa1d0a50975f9ca8fa77894dd821b0375d1359ed",
}


def verified_exports(directory):
    paths = {role: directory / f"{role}.onnx" for role in EXPORT_HASHES}
    for role, path in paths.items():
        checked_file(path, EXPORT_HASHES[role], f"{role} ONNX")
    return paths


@contextmanager
def verified_cuda_runtime():
    if version("onnxruntime-gpu") != ORT_VERSION:
        raise RuntimeError(f"RTSP lab requiere onnxruntime-gpu=={ORT_VERSION}")
    try:
        version("onnxruntime")
    except PackageNotFoundError:
        pass
    else:
        raise RuntimeError("RTSP lab requiere un entorno sin la distribución onnxruntime CPU")

    # Reuse the same letterbox, postprocessing and strict session setup as the
    # evaluated deployment. The scope covers predictor creation and warmup.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deployment" / "rtsp-lab"))
    try:
        from benchmark_backends import make_detectors, strict_ort_sessions
    finally:
        sys.path.pop(0)
    with strict_ort_sessions():
        yield make_detectors


@contextmanager
def cuda_detectors(directory, specs):
    paths = verified_exports(directory)
    with verified_cuda_runtime() as make_detectors:
        models = make_detectors(specs, paths, INPUT_SHAPE, rect=False)
        yield models["person"][0], models["forklift"][0]


def unified_selected(env):
    profile = env.get("OPERIX_DETECTOR_PROFILE", "legacy-dual")
    if profile not in ("legacy-dual", "unified-v7"):
        raise ValueError("Perfil de detector desconocido")
    if profile == "unified-v7" and not env.get("OPERIX_UNIFIED_V7_DIR"):
        raise ValueError("Falta el directorio aprobado para UNIFIED V7")
    return profile == "unified-v7"


def load_unified_perception(directory, channels, frame, synchronize):
    import json

    from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
    from operix_engine.dual_perception import SinglePerception

    config = json.loads((Path(__file__).resolve().parents[1] / "config/unified-v7.json").read_bytes())
    model = directory / "industrial-unified.onnx"
    checked_file(model, config["sha256"], "UNIFIED V7 ONNX")
    thresholds = config["confidence"]
    spec = {"confidence": min(thresholds.values()), "nms_iou": config["nms_iou"], "class_filter": None}
    with verified_cuda_runtime() as make_detectors:
        detector = make_detectors({"unified": spec}, {"unified": model}, tuple(config["input"]), False)["unified"][0]
        display_tracker = ByteTracker(ByteTrackConfig(
            track_high_thresh=thresholds["pallet_jack"], track_low_thresh=0,
            new_track_thresh=thresholds["pallet_jack"], fuse_score=False,
        ))
        perception = SinglePerception(channels, detector, thresholds, display_tracker=display_tracker)
        perception.process(frame, synchronize=synchronize)
    if detector.class_names != {0: "person", 1: "forklift", 2: "pallet_jack"}:
        raise ValueError("Índices de clase incompatibles con UNIFIED V7")
    if not detector.model_device.startswith("cuda"):
        raise RuntimeError("UNIFIED V7 no quedó en CUDA")
    perception.reset()
    return perception, config["model_id"]
