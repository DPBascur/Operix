# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mapeo y transporte opcional de candidatos, sin red externa."""

from __future__ import annotations

import io
import json
import os
import runpy
import sys
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from uuid import UUID

from operix_engine.detection import BoundingBox
from operix_engine.event_evidence import render_track_frame
from operix_engine.event_publishing import (
    EventContext,
    HttpEventSink,
    NoopEventSink,
    event_candidate_payload,
)
from operix_engine.operational_config import load_operational_config
from operix_engine.rules import RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track


EXAMPLE = Path(__file__).resolve().parents[1] / "config" / "examples" / "op30-zone-rule.json"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "op39-zone-dwell-tracks.ndjson"
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_rules.py"
FIXTURE_SHA256 = "10e0bbead4df4297db5847567a0d5288750167cd2fa279e816b5c26d8102688d"
EVENT_ID = "95111111-1111-4111-8111-111111111111"


class EventPublishingTest(unittest.TestCase):
    def setUp(self) -> None:
        config = load_operational_config(EXAMPLE)
        analyzer = SpatiotemporalAnalyzer(width=100, height=100, fps=2, zones=config.zones)
        engine = RuleEngine(config)
        track = Track(731, 0, "person", 0.9, BoundingBox(35, 40, 45, 50))
        for frame in range(5):
            result = engine.evaluate(analyzer.update(frame, (track,)))
        self.candidate = result.candidates[0]
        self.context = EventContext(
            UUID("12222222-2222-4222-8222-222222222222"),
            config.view_id,
            datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc),
        )

    def _response(self, status: int, body: bytes) -> MagicMock:
        response = MagicMock()
        response.__enter__.return_value.status = status
        response.__enter__.return_value.read.return_value = body
        return response

    def test_mapping_preserves_trace_and_uses_explicit_context(self) -> None:
        payload = event_candidate_payload(self.candidate, self.context)
        self.assertEqual(payload["analysis_run_id"], str(self.context.analysis_run_id))
        self.assertEqual(payload["view_id"], "ceiling_04")
        self.assertEqual(payload["occurred_at"], "2026-10-13T12:00:02+00:00")
        self.assertEqual((payload["video_timestamp_s"], payload["frame_index"]), ("2.000", 4))
        self.assertEqual((payload["rule_id"], payload["rule_version"]), ("restricted_zone_presence", 1))
        self.assertEqual(payload["rule_parameters"], dict(self.candidate.parameters))
        self.assertEqual((payload["zone_id"], payload["track_id"]), ("zona_critica_01", 731))
        self.assertEqual(payload["observed_dwell_time_s"], "2.000")

    def test_context_requires_real_timezone(self) -> None:
        with self.assertRaises(ValueError):
            EventContext(self.context.analysis_run_id, "ceiling_04", datetime(2026, 10, 13))

    def test_noop_does_not_send(self) -> None:
        with patch("operix_engine.event_publishing.urlopen") as send:
            result = NoopEventSink().publish(self.candidate, self.context)
        self.assertEqual(result.status, "skipped")
        send.assert_not_called()

    def test_success_sends_once_and_returns_persisted_id(self) -> None:
        sink = HttpEventSink("http://127.0.0.1:8000/api/v1", timeout_s=2)
        with patch("operix_engine.event_publishing.urlopen") as send:
            send.return_value = self._response(201, json.dumps({"id": EVENT_ID}).encode())
            first = sink.publish(self.candidate, self.context)
            second = sink.publish(self.candidate, self.context)
        self.assertEqual((first.status, first.http_status, first.event_id), ("published", 201, EVENT_ID))
        self.assertEqual(second.status, "duplicate")
        send.assert_called_once()
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/api/v1/events/")
        self.assertEqual(send.call_args.kwargs["timeout"], 2)
        self.assertEqual(json.loads(request.data), event_candidate_payload(self.candidate, self.context))

    def test_backend_unavailable_is_reported_without_exception(self) -> None:
        with patch("operix_engine.event_publishing.urlopen", side_effect=URLError("refused")):
            result = HttpEventSink("http://127.0.0.1:8000/api/v1").publish(self.candidate, self.context)
        self.assertEqual((result.status, result.reason), ("failed", "network_error"))

    def test_timeout_is_reported_without_exception(self) -> None:
        with patch("operix_engine.event_publishing.urlopen", side_effect=TimeoutError):
            result = HttpEventSink("http://127.0.0.1:8000/api/v1").publish(self.candidate, self.context)
        self.assertEqual((result.status, result.reason), ("failed", "timeout"))

    def test_non_success_status_is_reported(self) -> None:
        error = HTTPError("http://localhost/events/", 503, "unavailable", {}, None)
        with patch("operix_engine.event_publishing.urlopen", side_effect=error):
            result = HttpEventSink("http://127.0.0.1:8000/api/v1").publish(self.candidate, self.context)
        self.assertEqual((result.status, result.http_status, result.reason), ("failed", 503, "http_error"))

    def test_unexpected_2xx_and_invalid_response_are_rejected(self) -> None:
        for status, body, reason in ((200, b"{}", "unexpected_status"), (201, b"{}", "invalid_response")):
            with self.subTest(status=status, reason=reason):
                with patch(
                    "operix_engine.event_publishing.urlopen",
                    return_value=self._response(status, body),
                ):
                    result = HttpEventSink("http://127.0.0.1:8000/api/v1").publish(
                        self.candidate, self.context
                    )
                self.assertEqual((result.status, result.reason), ("failed", reason))

    def test_invalid_candidate_does_not_send(self) -> None:
        invalid = replace(self.candidate, timestamp_s=float("nan"))
        with patch("operix_engine.event_publishing.urlopen") as send:
            result = HttpEventSink("http://127.0.0.1:8000/api/v1").publish(invalid, self.context)
        self.assertEqual((result.status, result.reason), ("failed", "invalid_payload"))
        send.assert_not_called()

    def test_evidence_is_generated_from_matching_frame(self) -> None:
        track = Track(731, 0, "person", 0.9, BoundingBox(35, 40, 45, 50))
        config = load_operational_config(EXAMPLE)
        evidence = render_track_frame(self.candidate, (track,), config.zones, width=100, height=100)
        self.assertTrue(evidence.startswith(b"\x89PNG\r\n\x1a\n"))
        import cv2
        import numpy as np
        decoded = cv2.imdecode(np.frombuffer(evidence, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(decoded.shape[:2], (600, 600))
        self.assertNotEqual(tuple(decoded[240, 210]), (245, 245, 245))
        with self.assertRaises(ValueError):
            render_track_frame(self.candidate, (), config.zones, width=100, height=100)

    def test_evidence_encoding_failure_is_reported(self) -> None:
        track = Track(731, 0, "person", 0.9, BoundingBox(35, 40, 45, 50))
        config = load_operational_config(EXAMPLE)
        with patch("operix_engine.event_evidence.cv2.imencode", return_value=(False, None)):
            with self.assertRaises(OSError):
                render_track_frame(self.candidate, (track,), config.zones, width=100, height=100)

    def test_replay_capture_failure_does_not_send(self) -> None:
        with patch("operix_engine.event_evidence.cv2.imencode", return_value=(False, None)):
            with patch("operix_engine.event_publishing.urlopen") as send:
                status, output = self._run_replay(publish=True, capture=True)
        self.assertEqual(status, 1)
        self.assertEqual(output["publications"][0]["reason"], "evidence_render_error")
        send.assert_not_called()

    def test_publish_uploads_matching_png_after_event(self) -> None:
        sink = HttpEventSink("http://127.0.0.1:8000/api/v1")
        with patch("operix_engine.event_publishing.urlopen") as send:
            send.side_effect = [self._response(201, json.dumps({"id": EVENT_ID}).encode()),
                                self._response(201, b"{}")]
            result = sink.publish(self.candidate, self.context, b"\x89PNG\r\n\x1a\ncontent")
        self.assertEqual((result.status, result.event_id), ("published", EVENT_ID))
        upload = send.call_args_list[1].args[0]
        self.assertTrue(upload.full_url.endswith(f"/events/{EVENT_ID}/evidence/"))
        self.assertIn(b'name="frame_index"\r\n\r\n4', upload.data)
        self.assertIn(b'name="video_timestamp_s"\r\n\r\n2.000', upload.data)

    def test_upload_failure_keeps_persisted_event_id(self) -> None:
        with patch("operix_engine.event_publishing.urlopen") as send:
            send.side_effect = [self._response(201, json.dumps({"id": EVENT_ID}).encode()),
                                URLError("refused")]
            result = HttpEventSink("http://127.0.0.1:8000/api/v1").publish(
                self.candidate, self.context, b"\x89PNG\r\n\x1a\ncontent"
            )
        self.assertEqual((result.status, result.event_id, result.reason),
                         ("failed", EVENT_ID, "evidence_network_error"))

    def _run_replay(self, *, publish: bool, capture: bool = False) -> tuple[int, dict[str, object]]:
        main = runpy.run_path(str(SCRIPT), run_name="operix_replay_test")["main"]
        args = [
            str(SCRIPT), str(FIXTURE),
            "--expected-jsonl-sha256", FIXTURE_SHA256,
            "--config", str(EXAMPLE), "--view-id", "ceiling_04",
            "--width", "100", "--height", "100", "--fps", "2", "--end-frame", "5",
        ]
        if publish:
            args.extend([
                "--publish-api", "--analysis-run-id", str(self.context.analysis_run_id),
                "--recording-start-at", "2026-10-13T12:00:00Z",
            ])
        if capture:
            args.append("--capture-evidence")
        output = io.StringIO()
        with patch.object(sys, "argv", args), patch.dict(os.environ, {
            "OPERIX_API_BASE_URL": "http://127.0.0.1:8000/api/v1",
            "OPERIX_API_TIMEOUT_S": "5",
        }), redirect_stdout(output):
            result = main()
        return result, json.loads(output.getvalue())

    def test_replay_without_publication_keeps_motor_isolated(self) -> None:
        with patch("operix_engine.event_publishing.urlopen") as send:
            status, output = self._run_replay(publish=False)
        self.assertEqual(status, 0)
        self.assertEqual((output["frames"], len(output["candidates"])), (6, 1))
        self.assertNotIn("publications", output)
        send.assert_not_called()

    def test_replay_continues_after_backend_failure(self) -> None:
        with patch("operix_engine.event_publishing.urlopen", side_effect=URLError("refused")):
            status, output = self._run_replay(publish=True)
        self.assertEqual(status, 1)
        self.assertEqual((output["frames"], len(output["candidates"])), (6, 1))
        self.assertEqual(output["publications"][0]["reason"], "network_error")

    def test_replay_capture_uses_candidate_frame(self) -> None:
        with patch("operix_engine.event_publishing.urlopen") as send:
            send.side_effect = [self._response(201, json.dumps({"id": EVENT_ID}).encode()),
                                self._response(201, b"{}")]
            status, output = self._run_replay(publish=True, capture=True)
        self.assertEqual(status, 0)
        self.assertEqual(output["publications"][0]["frame_index"], 4)
        self.assertEqual(output["publications"][0]["event_id"], EVENT_ID)
        self.assertEqual(send.call_count, 2)


if __name__ == "__main__":
    unittest.main()
