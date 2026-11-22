from importlib.util import module_from_spec, spec_from_file_location
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock

import benchmark_rtsp_onnx


spec = spec_from_file_location("benchmark_live", Path(__file__).with_name("benchmark-live.py"))
benchmark = module_from_spec(spec)
spec.loader.exec_module(benchmark)


def sample(time, decoded, processed, depth, *, drops=0, evidence_ms=20.0):
    return {"feeds": {"camera": {"healthy_at_poll": True, "metrics": {
        "elapsed_s": time, "frames_processed": processed, "queue_depth": depth,
        "capture": {"decoded": decoded, "queue_drop": drops}, "epochs": {"initial": 1},
        "p95_arrival_to_result_ms": 80.0, "evidence_saved": 3, "evidence_status_ms": evidence_ms,
    }}}}


class CapacityTests(TestCase):
    def test_decreasing_evidence_latency_is_not_a_decreasing_counter(self):
        first = sample(5, 60, 58, 2)
        last = sample(15, 180, 180, 0, evidence_ms=10.0)
        result = benchmark.summarize([first, last], ["camera"], 10, 12)
        self.assertTrue(result["meets_capacity_gate"])
        self.assertEqual(result["feeds"]["camera"]["event_deltas"], {"evidence_saved": 0})
        self.assertEqual(result["feeds"]["camera"]["unaccounted_frames_after_queue"], 0)

    def test_valid_window_can_fail_capacity_for_known_or_unexplained_loss(self):
        first = sample(5, 60, 60, 0)
        for last in (sample(15, 180, 178, 0, drops=2), sample(15, 180, 178, 0)):
            with self.subTest(last=last):
                result = benchmark.summarize([first, last], ["camera"], 10, 12)
                self.assertTrue(result["valid"])
                self.assertFalse(result["meets_capacity_gate"])

    def test_onnx_worker_only_accepts_exports_bound_to_checkpoint_and_artifact_hashes(self):
        with TemporaryDirectory() as directory, mock.patch.object(benchmark_rtsp_onnx, "MODELS", Path(directory)):
            export = Path(directory) / "person.onnx"
            export.write_bytes(b"export")
            checkpoint = "a" * 64
            report = {"models": {"person": {"checkpoint": {"sha256": checkpoint}}},
                      "artifacts": {"person": {"onnx": {"sha256": hashlib.sha256(b"export").hexdigest()}}}}
            self.assertEqual(benchmark_rtsp_onnx.verified_export(report, "person", checkpoint), export)
            with self.assertRaises(ValueError):
                benchmark_rtsp_onnx.verified_export(report, "person", "b" * 64)
            export.write_bytes(b"different")
            with self.assertRaises(ValueError):
                benchmark_rtsp_onnx.verified_export(report, "person", checkpoint)
