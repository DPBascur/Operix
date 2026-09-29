# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pruebas reproducibles del procesamiento de video de OP-33."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np

from operix_engine.video_processor import (
    RecordedVideoSource,
    VideoMetadata,
    VideoSourceError,
    process_recorded_video,
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


if __name__ == "__main__":
    unittest.main()
