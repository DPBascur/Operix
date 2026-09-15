"""Medición reproducible de latencia y FPS para el pipeline de Operix."""

from __future__ import annotations

import csv
import json
import math
import re
import statistics
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class BenchmarkScenario(str, Enum):
    """Escenarios aprobados para OP-43."""

    BASE = "A"
    VISUALIZATION = "B"
    END_TO_END = "C"

    @property
    def uses_visualization(self) -> bool:
        return self in (self.VISUALIZATION, self.END_TO_END)

    @property
    def uses_writer(self) -> bool:
        return self is self.END_TO_END


@dataclass(frozen=True, slots=True)
class FrameMeasurement:
    """Tiempos de un frame medido, expresados internamente en nanosegundos."""

    scenario: BenchmarkScenario
    repetition: int
    execution_order: int
    frame_index: int
    read_ns: int
    inference_ns: int
    tracking_ns: int
    visualization_ns: int | None
    write_ns: int | None
    total_ns: int

    def __post_init__(self) -> None:
        required = (
            self.repetition,
            self.execution_order,
            self.frame_index,
            self.read_ns,
            self.inference_ns,
            self.tracking_ns,
            self.total_ns,
        )
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in required):
            raise TypeError("Los índices y tiempos requeridos deben ser enteros")
        if self.repetition <= 0 or self.execution_order <= 0 or self.frame_index < 0:
            raise ValueError("Los índices de medición no son válidos")
        if min(self.read_ns, self.inference_ns, self.tracking_ns, self.total_ns) < 0:
            raise ValueError("Los tiempos no pueden ser negativos")
        for optional in (self.visualization_ns, self.write_ns):
            if optional is not None and (not isinstance(optional, int) or optional < 0):
                raise ValueError("Los tiempos opcionales deben ser enteros no negativos")


@dataclass(frozen=True, slots=True)
class RunMeasurement:
    """Mediciones de una repetición completa de un escenario."""

    scenario: BenchmarkScenario
    repetition: int
    execution_order: int
    warmup_frames: int
    frames: tuple[FrameMeasurement, ...]
    writer_finalize_ns: int = 0

    @property
    def measured_frames(self) -> int:
        return len(self.frames)

    @property
    def elapsed_ns(self) -> int:
        return sum(frame.total_ns for frame in self.frames) + self.writer_finalize_ns

    @property
    def fps(self) -> float:
        return frames_per_second(self.measured_frames, self.elapsed_ns)


@dataclass(frozen=True, slots=True)
class LatencyStatistics:
    """Estadísticos descriptivos de una serie de latencias."""

    count: int
    mean_ms: float
    median_ms: float
    min_ms: float
    max_ms: float
    sample_stdev_ms: float
    p95_ms: float


class VideoSourceLike(Protocol):
    def __enter__(self) -> VideoSourceLike: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def frames(self) -> Any: ...


class DetectorLike(Protocol):
    def detect(self, frame: Any) -> tuple[Any, ...]: ...


class TrackerLike(Protocol):
    def update(self, detections: tuple[Any, ...]) -> tuple[Any, ...]: ...

    def reset(self) -> None: ...


class RendererLike(Protocol):
    def render_tracks(
        self,
        frame: Any,
        tracks: tuple[Any, ...],
        trajectories: Mapping[int, Sequence[Any]],
    ) -> Any: ...


class TrajectoryAccumulatorLike(Protocol):
    def update(self, frame_index: int, tracks: tuple[Any, ...]) -> Mapping[int, Sequence[Any]]: ...

    def reset(self) -> None: ...


class WriterLike(Protocol):
    def write(self, frame: Any) -> None: ...

    def release(self) -> None: ...


WriterFactory = Callable[[bool, int], WriterLike]


class PipelineBenchmark:
    """Orquesta mediciones sin acoplar la estadística a OpenCV, CUDA o Ultralytics."""

    def __init__(
        self,
        *,
        source_factory: Callable[[], VideoSourceLike],
        detector: DetectorLike,
        tracker: TrackerLike,
        renderer: RendererLike,
        trajectory_accumulator: TrajectoryAccumulatorLike,
        writer_factory: WriterFactory | None = None,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        cuda_synchronize: Callable[[], None] = lambda: None,
    ) -> None:
        self._source_factory = source_factory
        self._detector = detector
        self._tracker = tracker
        self._renderer = renderer
        self._trajectory_accumulator = trajectory_accumulator
        self._writer_factory = writer_factory
        self._clock_ns = clock_ns
        self._cuda_synchronize = cuda_synchronize

    def run_scenario(
        self,
        scenario: BenchmarkScenario,
        *,
        repetition: int,
        execution_order: int,
        warmup_frames: int,
    ) -> RunMeasurement:
        """Ejecuta una repetición y excluye del resultado los frames de warm-up."""
        if repetition <= 0 or execution_order <= 0 or warmup_frames < 0:
            raise ValueError("La repetición, orden o warm-up no son válidos")
        if scenario.uses_writer and self._writer_factory is None:
            raise ValueError("El escenario C requiere writer_factory")

        self._tracker.reset()
        self._trajectory_accumulator.reset()
        warmup_writer: WriterLike | None = None
        measured_writer: WriterLike | None = None
        measurements: list[FrameMeasurement] = []
        writer_finalize_ns = 0

        with self._source_factory() as source:
            frames = iter(source.frames())
            if scenario.uses_writer:
                warmup_writer = self._writer_factory(True, repetition)  # type: ignore[misc]
            try:
                for _ in range(warmup_frames):
                    try:
                        frame_index, frame = next(frames)
                    except StopIteration as error:
                        raise ValueError("La fuente no contiene suficientes frames de warm-up") from error
                    self._process_warmup_frame(
                        scenario,
                        frame_index,
                        frame,
                        warmup_writer,
                    )
            finally:
                if warmup_writer is not None:
                    warmup_writer.release()

            if scenario.uses_writer:
                measured_writer = self._writer_factory(False, repetition)  # type: ignore[misc]
            try:
                while True:
                    frame_started = self._clock_ns()
                    try:
                        frame_index, frame = next(frames)
                    except StopIteration:
                        break
                    read_ns = self._clock_ns() - frame_started

                    self._cuda_synchronize()
                    inference_started = self._clock_ns()
                    detections = self._detector.detect(frame)
                    self._cuda_synchronize()
                    inference_ns = self._clock_ns() - inference_started

                    tracking_started = self._clock_ns()
                    person_detections = tuple(
                        item for item in detections if item.class_name == "person"
                    )
                    tracks = self._tracker.update(person_detections)
                    tracking_ns = self._clock_ns() - tracking_started

                    visualization_ns: int | None = None
                    annotated = frame
                    if scenario.uses_visualization:
                        visualization_started = self._clock_ns()
                        trajectories = self._trajectory_accumulator.update(frame_index, tracks)
                        annotated = self._renderer.render_tracks(frame, tracks, trajectories)
                        visualization_ns = self._clock_ns() - visualization_started

                    write_ns: int | None = None
                    if measured_writer is not None:
                        write_started = self._clock_ns()
                        measured_writer.write(annotated)
                        write_ns = self._clock_ns() - write_started

                    total_ns = self._clock_ns() - frame_started
                    measurements.append(
                        FrameMeasurement(
                            scenario=scenario,
                            repetition=repetition,
                            execution_order=execution_order,
                            frame_index=frame_index,
                            read_ns=read_ns,
                            inference_ns=inference_ns,
                            tracking_ns=tracking_ns,
                            visualization_ns=visualization_ns,
                            write_ns=write_ns,
                            total_ns=total_ns,
                        )
                    )
            finally:
                if measured_writer is not None:
                    finalize_started = self._clock_ns()
                    measured_writer.release()
                    writer_finalize_ns = self._clock_ns() - finalize_started

        if not measurements:
            raise ValueError("La fuente no contiene frames medibles después del warm-up")
        return RunMeasurement(
            scenario=scenario,
            repetition=repetition,
            execution_order=execution_order,
            warmup_frames=warmup_frames,
            frames=tuple(measurements),
            writer_finalize_ns=writer_finalize_ns,
        )

    def _process_warmup_frame(
        self,
        scenario: BenchmarkScenario,
        frame_index: int,
        frame: Any,
        writer: WriterLike | None,
    ) -> None:
        self._cuda_synchronize()
        detections = self._detector.detect(frame)
        self._cuda_synchronize()
        person_detections = tuple(item for item in detections if item.class_name == "person")
        tracks = self._tracker.update(person_detections)
        annotated = frame
        if scenario.uses_visualization:
            trajectories = self._trajectory_accumulator.update(frame_index, tracks)
            annotated = self._renderer.render_tracks(frame, tracks, trajectories)
        if writer is not None:
            writer.write(annotated)


def frames_per_second(frame_count: int, elapsed_ns: int) -> float:
    """Calcula throughput como razón entre frames y tiempo acumulado."""
    if frame_count <= 0 or elapsed_ns <= 0:
        raise ValueError("frame_count y elapsed_ns deben ser positivos")
    return frame_count / (elapsed_ns / 1_000_000_000)


def nearest_rank_percentile(values: Sequence[int], percentile: float) -> int:
    """Percentil nearest-rank: valor ordenado en ceil(p * n)."""
    if not values:
        raise ValueError("Se requiere al menos un valor")
    if not 0 < percentile <= 1:
        raise ValueError("percentile debe pertenecer a (0, 1]")
    ordered = sorted(values)
    rank = math.ceil(percentile * len(ordered))
    return ordered[rank - 1]


def latency_statistics(values_ns: Sequence[int]) -> LatencyStatistics:
    """Resume nanosegundos como milisegundos con p95 nearest-rank."""
    if not values_ns:
        raise ValueError("Se requiere al menos una latencia")
    if any(value < 0 for value in values_ns):
        raise ValueError("Las latencias no pueden ser negativas")
    values_ms = [value / 1_000_000 for value in values_ns]
    return LatencyStatistics(
        count=len(values_ms),
        mean_ms=statistics.fmean(values_ms),
        median_ms=statistics.median(values_ms),
        min_ms=min(values_ms),
        max_ms=max(values_ms),
        sample_stdev_ms=statistics.stdev(values_ms) if len(values_ms) > 1 else 0.0,
        p95_ms=nearest_rank_percentile(values_ns, 0.95) / 1_000_000,
    )


def summarize_runs(runs: Sequence[RunMeasurement]) -> dict[str, Any]:
    """Agrupa resultados por escenario usando FPS global ponderado por tiempo."""
    if not runs:
        raise ValueError("Se requiere al menos una ejecución")
    result: dict[str, Any] = {}
    for scenario in BenchmarkScenario:
        scenario_runs = [run for run in runs if run.scenario is scenario]
        if not scenario_runs:
            continue
        all_frames = [frame for run in scenario_runs for frame in run.frames]
        total_frames = len(all_frames)
        total_elapsed_ns = sum(run.elapsed_ns for run in scenario_runs)
        core_ns = sum(frame.inference_ns + frame.tracking_ns for frame in all_frames)
        stage_values: dict[str, list[int]] = {
            "read": [frame.read_ns for frame in all_frames],
            "inference": [frame.inference_ns for frame in all_frames],
            "tracking": [frame.tracking_ns for frame in all_frames],
            "total": [frame.total_ns for frame in all_frames],
        }
        visualization = [
            frame.visualization_ns
            for frame in all_frames
            if frame.visualization_ns is not None
        ]
        writing = [frame.write_ns for frame in all_frames if frame.write_ns is not None]
        if visualization:
            stage_values["visualization"] = visualization
        if writing:
            stage_values["write"] = writing
        result[scenario.value] = {
            "scenario_name": {
                "A": "pipeline base de procesamiento",
                "B": "pipeline con visualización",
                "C": "end-to-end con salida",
            }[scenario.value],
            "repetitions": len(scenario_runs),
            "warmup_frames_per_repetition": scenario_runs[0].warmup_frames,
            "measured_frames": total_frames,
            "elapsed_ms": total_elapsed_ns / 1_000_000,
            "global_fps": frames_per_second(total_frames, total_elapsed_ns),
            "core_processing_fps": frames_per_second(total_frames, core_ns),
            "run_fps": [run.fps for run in scenario_runs],
            "writer_finalize_ms": [run.writer_finalize_ns / 1_000_000 for run in scenario_runs],
            "latency_ms": {
                stage: asdict(latency_statistics(values))
                for stage, values in stage_values.items()
            },
        }
    return result


def write_measurements_csv(path: Path, runs: Sequence[RunMeasurement]) -> None:
    """Escribe mediciones sin rutas locales ni artefactos multimedia."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "scenario",
        "repetition",
        "execution_order",
        "frame_index",
        "read_ms",
        "inference_ms",
        "tracking_ms",
        "visualization_ms",
        "write_ms",
        "total_ms",
    ]
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for run in runs:
            for frame in run.frames:
                writer.writerow(
                    {
                        "scenario": frame.scenario.value,
                        "repetition": frame.repetition,
                        "execution_order": frame.execution_order,
                        "frame_index": frame.frame_index,
                        "read_ms": frame.read_ns / 1_000_000,
                        "inference_ms": frame.inference_ns / 1_000_000,
                        "tracking_ms": frame.tracking_ns / 1_000_000,
                        "visualization_ms": ""
                        if frame.visualization_ns is None
                        else frame.visualization_ns / 1_000_000,
                        "write_ms": ""
                        if frame.write_ns is None
                        else frame.write_ns / 1_000_000,
                        "total_ms": frame.total_ns / 1_000_000,
                    }
                )


_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def assert_no_local_paths(value: Any) -> None:
    """Rechaza rutas de perfiles locales antes de versionar un resumen."""
    if isinstance(value, str):
        if _WINDOWS_PATH.match(value) or value.startswith(("/Users/", "/home/")):
            raise ValueError("El resumen no puede contener rutas locales")
    elif isinstance(value, Mapping):
        for key, item in value.items():
            assert_no_local_paths(key)
            assert_no_local_paths(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            assert_no_local_paths(item)


def write_summary_json(path: Path, summary: Mapping[str, Any]) -> None:
    """Valida y serializa el resumen reproducible de OP-43."""
    assert_no_local_paths(summary)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        json.dump(summary, output, ensure_ascii=False, indent=2)
        output.write("\n")
