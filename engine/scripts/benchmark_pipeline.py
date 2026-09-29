# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mide FPS y latencia del pipeline base, visual y end-to-end de Operix."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from importlib import metadata as package_metadata
from pathlib import Path

import cv2
import psutil
import torch

from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
from operix_engine.performance import (
    BenchmarkScenario,
    PipelineBenchmark,
    summarize_runs,
    write_measurements_csv,
    write_summary_json,
)
from operix_engine.video_processor import RecordedVideoSource, VideoSourceError
from operix_engine.visualization import (
    OpenCvRenderer,
    TrajectoryAccumulator,
    VisualizationConfig,
)
from operix_engine.yolo_detector import YoloDetector, YoloDetectorConfig


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> str:
    try:
        return package_metadata.version(name)
    except package_metadata.PackageNotFoundError:
        return "no instalado"


def cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    return platform.processor() or "no disponible"


def nvidia_driver_version() -> str:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=driver_version",
                "--format=csv,noheader",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip().splitlines()[0]
    except (OSError, subprocess.SubprocessError, IndexError):
        return "no disponible"


def environment_snapshot() -> dict[str, object]:
    properties = torch.cuda.get_device_properties(0)
    return {
        "operating_system": f"{platform.system()} {platform.release()}",
        "architecture": platform.machine(),
        "cpu": cpu_name(),
        "ram_bytes": psutil.virtual_memory().total,
        "gpu": torch.cuda.get_device_name(0),
        "vram_bytes": properties.total_memory,
        "nvidia_driver": nvidia_driver_version(),
        "python": platform.python_version(),
        "pytorch": torch.__version__,
        "torchvision": package_version("torchvision"),
        "cuda_compiled": torch.version.cuda,
        "opencv": cv2.__version__,
        "ultralytics": package_version("ultralytics"),
        "lap": package_version("lap"),
        "operix_engine": package_version("operix-engine"),
    }


def validate_metadata(args: argparse.Namespace) -> None:
    with RecordedVideoSource(args.video) as source:
        video = source.metadata()
    if (video.width, video.height) != (args.expected_width, args.expected_height):
        raise VideoSourceError("La resolución no coincide con la muestra esperada")
    if video.declared_frame_count != args.expected_frames:
        raise VideoSourceError("La cantidad de frames no coincide con la muestra esperada")
    if video.declared_fps is None or abs(video.declared_fps - args.expected_fps) > 0.01:
        raise VideoSourceError("Los FPS no coinciden con la muestra esperada")


def execution_plan(repetitions: int) -> list[tuple[int, BenchmarkScenario]]:
    rotations = (
        (BenchmarkScenario.BASE, BenchmarkScenario.VISUALIZATION, BenchmarkScenario.END_TO_END),
        (BenchmarkScenario.VISUALIZATION, BenchmarkScenario.END_TO_END, BenchmarkScenario.BASE),
        (BenchmarkScenario.END_TO_END, BenchmarkScenario.BASE, BenchmarkScenario.VISUALIZATION),
    )
    return [
        (repetition, scenario)
        for repetition in range(1, repetitions + 1)
        for scenario in rotations[(repetition - 1) % len(rotations)]
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--video-sha256", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-video", type=Path, required=True)
    parser.add_argument("--expected-frames", type=int, default=277)
    parser.add_argument("--expected-fps", type=float, default=30.0)
    parser.add_argument("--expected-width", type=int, default=1920)
    parser.add_argument("--expected-height", type=int, default=1080)
    parser.add_argument("--warmup-frames", type=int, default=20)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()

    if args.warmup_frames != 20 or args.repetitions != 5:
        parser.error("La validación aprobada exige 20 frames de warm-up y 5 repeticiones")
    if not torch.cuda.is_available():
        print("Error: CUDA no está disponible", file=sys.stderr)
        return 2
    try:
        video_hash = sha256_file(args.video)
        if video_hash.lower() != args.video_sha256.lower():
            raise VideoSourceError("El SHA-256 del video no coincide")
        validate_metadata(args)
    except (OSError, VideoSourceError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    detector_config = YoloDetectorConfig(
        weights_path=args.weights,
        confidence_threshold=0.10,
        device="cuda",
        image_size=640,
        iou_threshold=0.70,
    )
    tracker_config = ByteTrackConfig(
        track_high_thresh=0.25,
        track_low_thresh=0.10,
        new_track_thresh=0.25,
        track_buffer=30,
        match_thresh=0.80,
        fuse_score=True,
    )
    visualization_config = VisualizationConfig(
        max_trajectory_points=60,
        inactive_retention_frames=30,
    )
    detector = YoloDetector(detector_config)
    tracker = ByteTracker(tracker_config)
    renderer = OpenCvRenderer(visualization_config)
    accumulator = TrajectoryAccumulator(visualization_config)

    warmup_video = args.output_video.with_name(
        f"{args.output_video.stem}.warmup{args.output_video.suffix}"
    )

    def writer_factory(warmup: bool, _repetition: int):
        output = warmup_video if warmup else args.output_video
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.exists():
            output.unlink()
        writer = cv2.VideoWriter(
            str(output),
            cv2.VideoWriter_fourcc(*"mp4v"),
            args.expected_fps,
            (args.expected_width, args.expected_height),
        )
        if not writer.isOpened():
            writer.release()
            raise VideoSourceError("OpenCV no pudo crear la salida temporal del benchmark")
        return writer

    benchmark = PipelineBenchmark(
        source_factory=lambda: RecordedVideoSource(args.video),
        detector=detector,
        tracker=tracker,
        renderer=renderer,
        trajectory_accumulator=accumulator,
        writer_factory=writer_factory,
        cuda_synchronize=torch.cuda.synchronize,
    )

    runs = []
    plan = execution_plan(args.repetitions)
    try:
        for order, (repetition, scenario) in enumerate(plan, start=1):
            print(
                f"Ejecutando escenario {scenario.value}, repetición {repetition}/"
                f"{args.repetitions}, orden {order}/{len(plan)}...",
                flush=True,
            )
            run = benchmark.run_scenario(
                scenario,
                repetition=repetition,
                execution_order=order,
                warmup_frames=args.warmup_frames,
            )
            if run.measured_frames != args.expected_frames - args.warmup_frames:
                raise VideoSourceError(
                    f"Se midieron {run.measured_frames} frames; se esperaban "
                    f"{args.expected_frames - args.warmup_frames}"
                )
            runs.append(run)
    except (OSError, ValueError, VideoSourceError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2
    finally:
        if warmup_video.exists():
            warmup_video.unlink()

    write_measurements_csv(args.output_csv, runs)
    output_capture = cv2.VideoCapture(str(args.output_video))
    output_frames = int(round(output_capture.get(cv2.CAP_PROP_FRAME_COUNT)))
    output_capture.release()
    summary = {
        "schema_version": 1,
        "task": "OP-43",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "methodology": {
            "clock": "time.perf_counter_ns",
            "cuda_synchronization": "before and after each measured inference",
            "fps_formula": "measured_frames / accumulated_elapsed_seconds",
            "p95_method": "nearest-rank (ceil(0.95 * n))",
            "warmup_frames_per_repetition": args.warmup_frames,
            "measured_frames_per_repetition": args.expected_frames - args.warmup_frames,
            "repetitions_per_scenario": args.repetitions,
            "execution_order": [
                {
                    "order": order,
                    "repetition": repetition,
                    "scenario": scenario.value,
                }
                for order, (repetition, scenario) in enumerate(plan, start=1)
            ],
        },
        "environment": environment_snapshot(),
        "input": {
            "video_name": args.video.name,
            "video_sha256": video_hash.upper(),
            "frames": args.expected_frames,
            "fps": args.expected_fps,
            "width": args.expected_width,
            "height": args.expected_height,
        },
        "model": {
            "name": "YOLO11n-COCO",
            "weights_name": args.weights.name,
            "weights_sha256": sha256_file(args.weights).upper(),
            **(asdict(detector_config) | {"weights_path": args.weights.name}),
            "class_filter": "person",
        },
        "tracker": asdict(tracker_config),
        "visualization": asdict(visualization_config),
        "results": summarize_runs(runs),
        "scenario_c_output": {
            "video_name": args.output_video.name,
            "frames": output_frames,
            "sha256": sha256_file(args.output_video).upper(),
            "bytes": args.output_video.stat().st_size,
            "repository_policy": "outside repository",
        },
    }
    write_summary_json(args.output_summary, summary)
    print(json.dumps(summary["results"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
