# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prueba integración del orquestador sin GPU ni pesos descargados."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import cv2
import numpy as np

from operix_engine.detection import BoundingBox, Detection
from operix_engine.event_publishing import EventContext, PublishResult
from operix_engine.operational_config import OperationalConfig, RuleConfig, Zone
from operix_engine.tracking import Track
from operix_engine.video_event_pipeline import _visible_tracks, run_video_event_pipeline
from operix_engine.video_processor import VideoMetadata


BOX = BoundingBox(40, 30, 60, 70)


class _Source:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def metadata(self):
        return VideoMetadata(200, 100, 2.0, 4, 2.0)

    def frames(self):
        for index in range(4):
            yield index, np.full((100, 200, 3), (17, 97, 100 + index), dtype=np.uint8)


class _Detector:
    def detect(self, _frame):
        return (Detection(0, "person", 0.9, BOX),)


class _Tracker:
    def update(self, _detections):
        return (Track(7, 0, "person", 0.9, BOX),)


class _Sink:
    def __init__(self):
        self.calls = []

    def publish(self, candidate, context, evidence_png):
        self.calls.append((candidate, context, evidence_png))
        return PublishResult("published", 201, "95111111-1111-4111-8111-111111111111")


class VideoEventPipelineTest(unittest.TestCase):
    def test_transient_failure_retries_the_same_candidate_and_real_frame(self):
        from operix_engine.event_publishing import publish_with_retries
        from unittest.mock import Mock
        candidate = object()
        context = object()
        evidence = b"same-frame"
        sink = Mock()
        sink.publish.side_effect = [PublishResult("failed", reason="timeout"),
                                   PublishResult("duplicate", 200, "existing-id")]
        with patch("operix_engine.event_publishing.time.sleep"):
            result, attempts = publish_with_retries(sink, candidate, context, evidence)
        self.assertEqual((result.status, attempts), ("duplicate", 2))
        self.assertEqual(sink.publish.call_count, 2)
        self.assertEqual(sink.publish.call_args_list[0], sink.publish.call_args_list[1])

    def test_retry_is_bounded_and_does_not_retry_permanent_errors(self):
        from operix_engine.event_publishing import publish_with_retries
        from unittest.mock import Mock
        for failure, expected in ((PublishResult("failed", 503, reason="http_error"), 3),
                                  (PublishResult("failed", 400, reason="http_error"), 1),
                                  (PublishResult("failed", reason="invalid_payload"), 1)):
            with self.subTest(failure=failure):
                sink = Mock()
                sink.publish.return_value = failure
                with patch("operix_engine.event_publishing.time.sleep"):
                    result, attempts = publish_with_retries(sink, object(), object())
                self.assertEqual((result.status, attempts), ("failed", expected))
                self.assertEqual(sink.publish.call_count, expected)

    def test_failed_image_retry_keeps_existing_event_identifier(self):
        from operix_engine.event_publishing import publish_with_retries
        from unittest.mock import Mock
        sink = Mock()
        sink.publish.side_effect = [
            PublishResult("failed", event_id="created-id", reason="evidence_network_error"),
            PublishResult("failed", reason="network_error"),
            PublishResult("failed", reason="timeout"),
        ]
        with patch("operix_engine.event_publishing.time.sleep"):
            result, attempts = publish_with_retries(sink, object(), object(), b"same-frame")
        self.assertEqual((result.event_id, attempts), ("created-id", 3))

    def test_tracker_predictions_outside_frame_are_clipped_or_dropped(self):
        partial = Track(1, 0, "person", 0.9, BoundingBox(180, 30, 210, 70))
        outside = Track(2, 0, "person", 0.9, BoundingBox(205, 30, 220, 70))
        visible, clipped, discarded = _visible_tracks((partial, outside), 200, 100)
        self.assertEqual((clipped, discarded), (1, 1))
        self.assertEqual(tuple(track.track_id for track in visible), (1,))
        self.assertEqual(visible[0].bounding_box.x_max, 200)

    def test_candidate_and_png_come_from_same_real_frame(self):
        zone = Zone("demo", "Zona de prueba", ((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)))
        rule = RuleConfig("dwell", 1, True, {
            "kind": "zone_dwell", "class_name": "person", "zone_id": "demo", "min_duration_s": 1.0,
        })
        config = OperationalConfig(1, "ceiling_04", (zone,), (rule,))
        sink = _Sink()
        context = EventContext(
            UUID("12222222-2222-4222-8222-222222222222"),
            "ceiling_04", datetime(2026, 10, 14, tzinfo=timezone.utc),
        )
        with patch("operix_engine.video_event_pipeline.RecordedVideoSource", _Source):
            result = run_video_event_pipeline(
                Path("test.mp4"), detector=_Detector(), tracker=_Tracker(),
                config=config, sink=sink, context=context,
            )
        self.assertEqual((result["processed_frames"], result["person_detections"]), (4, 4))
        self.assertEqual((result["track_observations"], result["unique_track_ids"]), (4, 1))
        self.assertEqual((result["candidate_count"], result["published_count"]), (1, 1))
        candidate, sent_context, evidence = sink.calls[0]
        self.assertIs(sent_context, context)
        self.assertEqual((candidate.frame_index, candidate.timestamp_s, candidate.track_id), (2, 1.0, 7))
        decoded = cv2.imdecode(np.frombuffer(evidence, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(decoded.shape, (100, 200, 3))
        self.assertEqual(tuple(decoded[90, 190]), (17, 97, 102))
        self.assertEqual(result["publications"][0]["candidate"]["normalized_position"], {"x": 0.25, "y": 0.7})

    def test_pipeline_recovers_after_transient_backend_failure(self):
        zone = Zone("demo", "Zona sintética", ((.1,.1),(.9,.1),(.9,.9),(.1,.9)))
        rule = RuleConfig("dwell", 1, True, {
            "kind": "zone_dwell", "class_name": "person", "zone_id": "demo", "min_duration_s": 1,
        })
        from unittest.mock import Mock
        sink = Mock()
        sink.publish.side_effect = [PublishResult("failed", reason="timeout"),
                                   PublishResult("published", 201, "recovered")]
        context = EventContext(UUID("12222222-2222-4222-8222-222222222222"),
                               "synthetic", datetime(2026, 10, 23, tzinfo=timezone.utc))
        with patch("operix_engine.video_event_pipeline.RecordedVideoSource", _Source), \
                patch("operix_engine.event_publishing.time.sleep"):
            result = run_video_event_pipeline(Path("controlled.avi"), detector=_Detector(),
                tracker=_Tracker(), config=OperationalConfig(1, "synthetic", (zone,), (rule,)),
                sink=sink, context=context)
        self.assertEqual((result["candidate_count"], result["published_count"]), (1, 1))
        self.assertEqual(result["publications"][0]["publish_attempts"], 2)
        self.assertEqual(sink.publish.call_args_list[0], sink.publish.call_args_list[1])


if __name__ == "__main__":
    unittest.main()
