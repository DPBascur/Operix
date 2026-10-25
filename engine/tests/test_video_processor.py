# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas reproducibles del procesamiento de video de OP-33."""

from __future__ import annotations

import tempfile
import unittest
from unittest.mock import Mock, patch
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from operix_engine.video_processor import (
    RecordedVideoSource,
    VideoMetadata,
    VideoSourceError,
    process_recorded_video,
    inspect_recorded_video,
    VideoContractError,
)


class VideoProcessorTest(unittest.TestCase):
    width = 64
    height = 48
    fps = 10.0
    frame_count = 12

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.video_path = self.directory / "controlled-synthetic-video.avi"
        self._write_synthetic_video(self.video_path)

    def _write_synthetic_video(self, path: Path) -> None:
        codec = cv2.VideoWriter_fourcc(*"MJPG")
        writer = cv2.VideoWriter(
            str(path),
            codec,
            self.fps,
            (self.width, self.height),
        )
        self.assertTrue(writer.isOpened(), "OpenCV no pudo crear el video sintético MJPEG")

        try:
            for index in range(self.frame_count):
                frame = np.full(
                    (self.height, self.width, 3),
                    fill_value=index * 10,
                    dtype=np.uint8,
                )
                writer.write(frame)
        finally:
            writer.release()

    def test_processes_all_frames_and_reports_metadata(self) -> None:
        result = process_recorded_video(self.video_path)

        self.assertEqual(result.metadata.width, self.width)
        self.assertEqual(result.metadata.height, self.height)
        self.assertAlmostEqual(result.metadata.declared_fps or 0, self.fps, places=2)
        self.assertEqual(result.metadata.declared_frame_count, self.frame_count)
        self.assertAlmostEqual(
            result.metadata.estimated_duration_seconds or 0,
            self.frame_count / self.fps,
            places=2,
        )
        self.assertEqual(result.processed_frames, self.frame_count)
        self.assertGreaterEqual(result.processing_seconds, 0)
        self.assertEqual(result.warnings, ())

    def test_context_manager_releases_capture_after_exception(self) -> None:
        source = RecordedVideoSource(self.video_path)

        with self.assertRaisesRegex(RuntimeError, "fallo controlado"):
            with source:
                self.assertTrue(source.is_open)
                next(source.frames())
                raise RuntimeError("fallo controlado")

        self.assertFalse(source.is_open)

    def test_frame_times_at_30_fps_and_sequential_read(self) -> None:
        video_path = self.directory / "controlled-30fps.avi"
        self.fps = 30.0
        self._write_synthetic_video(video_path)

        with RecordedVideoSource(video_path) as source:
            indexed_frames = list(source.frames())
        with RecordedVideoSource(video_path) as source:
            timed_frames = list(source.frames_with_time())

        self.assertEqual(len(timed_frames), self.frame_count)
        self.assertEqual(
            [index for index, _time, _frame in timed_frames],
            [index for index, _frame in indexed_frames],
        )
        self.assertEqual(timed_frames[0][1], 0.0)
        self.assertAlmostEqual(timed_frames[1][1], 1 / 30)
        self.assertAlmostEqual(timed_frames[9][1], 9 / 30)
        for (_index, original), (_index_timed, _time, timed) in zip(
            indexed_frames, timed_frames
        ):
            self.assertTrue(np.array_equal(original, timed))

    def test_frame_time_unavailable_for_invalid_fps(self) -> None:
        metadata = VideoMetadata(64, 48, 30.0, 12, 0.4)
        for invalid_fps in (None, 0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(fps=invalid_fps):
                invalid_metadata = replace(metadata, declared_fps=invalid_fps)
                self.assertIsNone(invalid_metadata.frame_time_seconds(5))

    def test_frame_time_rejects_negative_index(self) -> None:
        metadata = VideoMetadata(64, 48, 30.0, 12, 0.4)
        with self.assertRaises(ValueError):
            metadata.frame_time_seconds(-1)

    def test_missing_file_produces_controlled_error(self) -> None:
        missing_path = self.directory / "missing.mp4"

        with self.assertRaisesRegex(VideoSourceError, "No existe"):
            process_recorded_video(missing_path)

    def test_invalid_file_produces_controlled_error(self) -> None:
        invalid_path = self.directory / "not-a-video.mp4"
        invalid_path.write_text("contenido no audiovisual", encoding="utf-8")

        with self.assertRaisesRegex(VideoSourceError, "no pudo abrir"):
            process_recorded_video(invalid_path)

    def inspect_fixture(self, *, count=5, declared=5, fps=30.0, positions=None, failure=None, width=64):
        capture = Mock()
        capture.isOpened.return_value = True
        position = -1
        properties = {cv2.CAP_PROP_FRAME_WIDTH: width, cv2.CAP_PROP_FRAME_HEIGHT: 48,
                      cv2.CAP_PROP_FPS: fps, cv2.CAP_PROP_FRAME_COUNT: declared}
        def read():
            nonlocal position
            position += 1
            if failure is not None and position == failure:
                raise cv2.error("controlled decode failure")
            return (True, np.zeros((48, 64, 3), dtype=np.uint8)) if position < count else (False, None)
        def get(key):
            if key == cv2.CAP_PROP_POS_MSEC:
                return positions[position] if positions is not None else position * 1000 / fps
            return properties[key]
        capture.read.side_effect, capture.get.side_effect = read, get
        with patch("operix_engine.video_processor.cv2.VideoCapture", return_value=capture):
            try:
                return inspect_recorded_video(self.video_path)
            finally:
                capture.release.assert_called_once()

    def test_preflight_valid_cfr_uses_relative_decoder_timestamps(self):
        result = self.inspect_fixture(positions=[2000 + i * 1000 / 30 for i in range(5)])
        self.assertEqual(result.frame_count, 5)
        self.assertEqual(result.timestamp_source, "OPENCV_POS_MSEC_RELATIVE")
        self.assertEqual(result.timestamps[0], 0)
        self.assertAlmostEqual(result.timestamps[-1], 4 / 30)

    def test_preflight_premature_eof_is_truncated(self):
        with self.assertRaises(VideoContractError) as error:
            self.inspect_fixture(count=2, declared=100)
        self.assertEqual(error.exception.reason, "TRUNCATED_INPUT")

    def test_preflight_unknown_total_counts_decoded_frames(self):
        result = self.inspect_fixture(declared=0)
        self.assertEqual(result.frame_count, 5)
        self.assertIsNone(result.metadata.declared_frame_count)
        self.assertTrue(result.warnings)

    def test_preflight_all_zero_timestamps_explicit_nominal_fallback(self):
        result = self.inspect_fixture(positions=[0] * 5)
        self.assertEqual(result.timestamp_source, "NOMINAL_FPS_UNVERIFIED_CFR")
        self.assertEqual(result.timestamps, tuple(i / 30 for i in range(5)))
        self.assertTrue(result.warnings)

    def test_preflight_rejects_irregular_nonmonotonic_or_invalid_timestamps(self):
        for positions in ([0, 33, 100, 133, 200], [0, 33, 33, 100, 133],
                          [0, 33, 20, 100, 133], [0, float("nan"), 66, 100, 133]):
            with self.subTest(positions=positions), self.assertRaises(VideoContractError):
                self.inspect_fixture(positions=positions)

    def test_preflight_invalid_fps_or_dimensions(self):
        for fps in (0, -1, float("nan"), float("inf")):
            with self.subTest(fps=fps), self.assertRaises(VideoContractError):
                self.inspect_fixture(fps=fps)
        with self.assertRaises(VideoContractError):
            self.inspect_fixture(width=float("nan"))

    def test_preflight_decode_exception_and_empty_source_are_failures(self):
        for options in ({"failure": 2}, {"count": 0}):
            with self.subTest(options=options), self.assertRaises(VideoContractError) as error:
                self.inspect_fixture(**options)
            self.assertEqual(error.exception.reason, "DECODE_FAILURE")

    def test_preflight_approximate_count_cannot_confirm_completion(self):
        for count, declared in ((5, 6), (1, 2), (2, 3)):
            with self.subTest(count=count, declared=declared), self.assertRaises(VideoContractError) as error:
                self.inspect_fixture(count=count, declared=declared)
            self.assertEqual(error.exception.reason, "TRUNCATED_INPUT")
        with self.assertRaises(VideoContractError) as error:
            self.inspect_fixture(count=10, declared=5)
        self.assertEqual(error.exception.reason, "INVALID_METADATA")

    def test_preflight_one_frame_is_valid(self):
        self.assertEqual(self.inspect_fixture(count=1, declared=1).timestamps, (0,))

    def test_real_synthetic_preflight_and_short_video(self):
        result = inspect_recorded_video(self.video_path)
        self.assertEqual(result.frame_count, self.frame_count)
        self.assertEqual(result.timestamp_source, "OPENCV_POS_MSEC_RELATIVE")

    def test_preflight_rejects_missing_directory_or_disallowed_type(self):
        invalid = self.directory / "not-video.txt"
        invalid.write_text("fixture", encoding="utf-8")
        for path in (self.directory / "missing.mp4", self.directory, invalid):
            with self.subTest(path=path.name), self.assertRaises(VideoContractError) as error:
                inspect_recorded_video(path)
            self.assertEqual(error.exception.reason, "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
