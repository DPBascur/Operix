# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas sintéticas de la instrumentación de OP-43."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from operix_engine.performance import (
    BenchmarkScenario,
    FrameMeasurement,
    PipelineBenchmark,
    RunMeasurement,
    assert_no_local_paths,
    frames_per_second,
    latency_statistics,
    nearest_rank_percentile,
    summarize_runs,
    write_measurements_csv,
    write_summary_json,
)


class StepClock:
    def __init__(self, step_ns: int = 1_000_000) -> None:
        self.value = 0
        self.step_ns = step_ns

    def __call__(self) -> int:
        current = self.value
        self.value += self.step_ns
        return current


class FakeSource:
    def __init__(self, frame_count: int) -> None:
        self.frame_count = frame_count

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def frames(self):
        for index in range(self.frame_count):
            yield index, f"frame-{index}"


class FakeDetector:
    def __init__(self) -> None:
        self.calls = 0

    def detect(self, _frame):
        self.calls += 1
        return (
            SimpleNamespace(class_name="person"),
            SimpleNamespace(class_name="truck"),
        )


class FakeTracker:
    def __init__(self) -> None:
        self.reset_calls = 0
        self.inputs = []

    def reset(self) -> None:
        self.reset_calls += 1

    def update(self, detections):
        self.inputs.append(detections)
        return ()


class FakeRenderer:
    def __init__(self) -> None:
        self.calls = 0

    def render_tracks(self, frame, _tracks, _trajectories):
        self.calls += 1
        return f"annotated-{frame}"


class FakeAccumulator:
    def __init__(self) -> None:
        self.reset_calls = 0
        self.calls = 0

    def reset(self) -> None:
        self.reset_calls += 1

    def update(self, _frame_index, _tracks):
        self.calls += 1
        return {}


class FakeWriter:
    def __init__(self) -> None:
        self.frames = []
        self.release_calls = 0

    def write(self, frame) -> None:
        self.frames.append(frame)

    def release(self) -> None:
        self.release_calls += 1


def frame_measurement(
    scenario: BenchmarkScenario,
    total_ns: int,
    *,
    repetition: int = 1,
) -> FrameMeasurement:
    return FrameMeasurement(
        scenario=scenario,
        repetition=repetition,
        execution_order=repetition,
        frame_index=20,
        read_ns=1_000_000,
        inference_ns=6_000_000,
        tracking_ns=1_000_000,
        visualization_ns=None,
        write_ns=None,
        total_ns=total_ns,
    )


class StatisticsTest(unittest.TestCase):
    def test_fps_uses_frames_divided_by_accumulated_time(self) -> None:
        self.assertEqual(frames_per_second(30, 1_000_000_000), 30.0)

    def test_nearest_rank_p95_is_explicit(self) -> None:
        values = list(range(1, 101))
        self.assertEqual(nearest_rank_percentile(values, 0.95), 95)

    def test_latency_statistics_include_required_metrics(self) -> None:
        result = latency_statistics([1_000_000, 2_000_000, 3_000_000, 4_000_000])
        self.assertEqual(result.count, 4)
        self.assertEqual(result.mean_ms, 2.5)
        self.assertEqual(result.median_ms, 2.5)
        self.assertEqual((result.min_ms, result.max_ms, result.p95_ms), (1.0, 4.0, 4.0))
        self.assertGreater(result.sample_stdev_ms, 0)

    def test_summary_calculates_global_fps_from_all_runs(self) -> None:
        runs = (
            RunMeasurement(BenchmarkScenario.BASE, 1, 1, 20, (frame_measurement(BenchmarkScenario.BASE, 100_000_000),)),
            RunMeasurement(BenchmarkScenario.BASE, 2, 2, 20, (frame_measurement(BenchmarkScenario.BASE, 300_000_000, repetition=2),)),
        )
        summary = summarize_runs(runs)["A"]
        self.assertEqual(summary["measured_frames"], 2)
        self.assertEqual(summary["global_fps"], 5.0)
        self.assertEqual(summary["scenario_name"], "pipeline base de procesamiento")


class PipelineBenchmarkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.detector = FakeDetector()
        self.tracker = FakeTracker()
        self.renderer = FakeRenderer()
        self.accumulator = FakeAccumulator()
        self.writers = []
        self.sync_calls = 0

        def synchronize() -> None:
            self.sync_calls += 1

        def writer_factory(_warmup: bool, _repetition: int):
            writer = FakeWriter()
            self.writers.append(writer)
            return writer

        self.benchmark = PipelineBenchmark(
            source_factory=lambda: FakeSource(4),
            detector=self.detector,
            tracker=self.tracker,
            renderer=self.renderer,
            trajectory_accumulator=self.accumulator,
            writer_factory=writer_factory,
            clock_ns=StepClock(),
            cuda_synchronize=synchronize,
        )

    def _run_scenario(self, scenario: BenchmarkScenario) -> RunMeasurement:
        return self.benchmark.run_scenario(
            scenario,
            repetition=1,
            execution_order=1,
            warmup_frames=1,
        )

    def test_warmup_is_processed_but_excluded(self) -> None:
        result = self._run_scenario(BenchmarkScenario.BASE)
        self.assertEqual(result.measured_frames, 3)
        self.assertEqual([frame.frame_index for frame in result.frames], [1, 2, 3])
        self.assertEqual(self.detector.calls, 4)
        self.assertEqual(self.sync_calls, 8)
        self.assertTrue(all(len(items) == 1 for items in self.tracker.inputs))

    def test_scenario_a_disables_render_and_writer(self) -> None:
        result = self._run_scenario(BenchmarkScenario.BASE)
        self.assertEqual(self.renderer.calls, 0)
        self.assertEqual(self.accumulator.calls, 0)
        self.assertEqual(self.writers, [])
        self.assertTrue(all(frame.visualization_ns is None for frame in result.frames))
        self.assertTrue(all(frame.write_ns is None for frame in result.frames))

    def test_scenario_b_enables_render_without_writer(self) -> None:
        result = self._run_scenario(BenchmarkScenario.VISUALIZATION)
        self.assertEqual(self.renderer.calls, 4)
        self.assertEqual(self.accumulator.calls, 4)
        self.assertEqual(self.writers, [])
        self.assertTrue(all(frame.visualization_ns is not None for frame in result.frames))

    def test_scenario_c_separates_writer_finalization(self) -> None:
        result = self._run_scenario(BenchmarkScenario.END_TO_END)
        self.assertEqual(len(self.writers), 2)
        self.assertEqual(len(self.writers[0].frames), 1)
        self.assertEqual(len(self.writers[1].frames), 3)
        self.assertEqual([writer.release_calls for writer in self.writers], [1, 1])
        self.assertGreater(result.writer_finalize_ns, 0)
        self.assertTrue(all(frame.write_ns is not None for frame in result.frames))
        self.assertEqual(result.elapsed_ns, sum(frame.total_ns for frame in result.frames) + result.writer_finalize_ns)

    def test_tracker_and_accumulator_reset_for_every_run(self) -> None:
        self._run_scenario(BenchmarkScenario.BASE)
        self._run_scenario(BenchmarkScenario.VISUALIZATION)
        self.assertEqual(self.tracker.reset_calls, 2)
        self.assertEqual(self.accumulator.reset_calls, 2)


class SerializationTest(unittest.TestCase):
    def test_summary_rejects_local_paths(self) -> None:
        with self.assertRaisesRegex(ValueError, "rutas locales"):
            assert_no_local_paths({"video": r"X:\local\clip.mp4"})

    def test_csv_and_json_contain_no_local_paths(self) -> None:
        run = RunMeasurement(
            BenchmarkScenario.BASE,
            1,
            1,
            20,
            (frame_measurement(BenchmarkScenario.BASE, 10_000_000),),
        )
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "measurements.csv"
            json_path = Path(directory) / "summary.json"
            write_measurements_csv(csv_path, (run,))
            write_summary_json(json_path, {"video_name": "sample.mp4", "results": {}})

            with csv_path.open(encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            with json_path.open(encoding="utf-8") as file:
                summary = json.load(file)
            self.assertEqual(len(rows), 1)
            self.assertEqual(summary["video_name"], "sample.mp4")
            self.assertNotIn("Users", csv_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
