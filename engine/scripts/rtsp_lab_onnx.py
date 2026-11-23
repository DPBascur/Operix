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
def cuda_detectors(directory, specs):
    paths = verified_exports(directory)
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
        models = make_detectors(specs, paths, INPUT_SHAPE, rect=False)
        yield models["person"][0], models["forklift"][0]
