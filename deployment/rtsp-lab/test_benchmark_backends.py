# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock

import benchmark_backends as benchmark


class TensorRTArtifactTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        packages = dict.fromkeys((*benchmark.TRT_PACKAGES, "onnx"), "test-version")
        self.manifest = {
            "protocol": {
                "backend": "trt-fp16", "nchw": [1, 3, 384, 640], "opset": 17,
                "embedded_nms": False, "tf32": False, "trt_workspace_bytes": benchmark.WORKSPACE_BYTES,
                "trt_builder_optimization_level": benchmark.BUILD_OPTIMIZATION_LEVEL,
            },
            "models": {role: {"checkpoint": {"sha256": role * 8, "path": f"{role}.pt"}}
                       for role in ("person", "forklift")},
            "runtime": {"packages": packages},
            "clips": [{"path": "clip.mp4"}],
        }
        self.report = deepcopy(self.manifest)
        self.report.update(schema_version=1, status="compiled",
                           cuda={"gpu": "Test GPU", "compute_capability": [8, 6]}, artifacts={})
        for role in self.manifest["models"]:
            self.report["artifacts"][role] = {}
            for kind in ("onnx", "engine"):
                path = self.root / f"{role}.{kind}"
                path.write_bytes(path.name.encode())
                receipt = benchmark.lab.file_receipt(path)
                self.report["artifacts"][role][kind] = {**receipt, "path": f"/old/mount/{path.name}"}
        self.args = SimpleNamespace(backend="trt-fp16", engine_report=self.root / "report.json",
                                    compile_only=False, frames=32, start_frame=80)
        self.write_report()

    def write_report(self):
        payload = json.dumps(self.report).encode()
        self.args.engine_report.write_bytes(payload)
        self.args.engine_report_sha256 = sha256(payload).hexdigest()

    def test_verifies_relocated_artifacts_and_rejects_changed_bytes(self):
        benchmark.verify_engine_report(self.args, self.manifest)
        self.assertEqual(self.manifest["artifacts"]["person"]["engine"]["path"], str(self.root / "person.engine"))
        for name in ("person.engine", "forklift.onnx"):
            with self.subTest(artifact=name):
                path = self.root / name
                original = path.read_bytes()
                path.write_bytes(b"x" * len(original))
                with self.assertRaisesRegex(ValueError, "artifact mismatch"):
                    benchmark.verify_engine_report(self.args, self.manifest)
                path.write_bytes(original)

    def test_rejects_unpinned_or_incompatible_reports(self):
        self.args.engine_report_sha256 = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            benchmark.verify_engine_report(self.args, self.manifest)
        for target, key, value, error in (
            (self.report, "status", "planned", "completed"),
            (self.report["protocol"], "backend", "trt-fp32", "backend"),
            (self.report["protocol"], "nchw", [1, 3, 640, 640], "nchw"),
            (self.report["models"]["person"]["checkpoint"], "sha256", "changed", "checkpoint mismatch"),
        ):
            with self.subTest(key=key):
                original = target[key]
                target[key] = value
                self.write_report()
                with self.assertRaisesRegex(ValueError, error):
                    benchmark.verify_engine_report(self.args, self.manifest)
                target[key] = original

    def fake_torch(self):
        torch = mock.Mock()
        torch.cuda.get_device_properties.return_value = SimpleNamespace(name="Test GPU", major=8, minor=6,
                                                                       total_memory=8 * 1024**3)
        return mock.patch.dict("sys.modules", torch=torch)

    def test_reuse_measures_verified_engines_without_export_or_compile(self):
        benchmark.verify_engine_report(self.args, self.manifest)
        with (self.fake_torch(),
              mock.patch.object(benchmark.lab, "decode_frames", return_value=((), {})),
              mock.patch.object(benchmark, "export_onnx") as export,
              mock.patch.object(benchmark, "build_engine") as compile_engine,
              mock.patch.object(benchmark, "measure_case", return_value=[[(None, {})]]) as measure):
            benchmark.run(self.args, self.manifest, self.root)
        export.assert_not_called()
        compile_engine.assert_not_called()
        self.assertEqual([call.args[5] for call in measure.call_args_list], ["pt", "pt", "engine"])
        self.assertEqual(measure.call_args.args[2], {role: self.root / f"{role}.engine"
                                                    for role in self.manifest["models"]})
        self.assertEqual(self.manifest["status"], "complete")

    def test_reuse_rejects_different_runtime_before_measurement(self):
        benchmark.verify_engine_report(self.args, self.manifest)
        with (self.fake_torch(),
              mock.patch.object(benchmark.lab, "decode_frames", return_value=((), {})),
              mock.patch.object(benchmark, "measure_case") as measure):
            self.manifest["engine_build"]["cuda"]["compute_capability"] = [8, 9]
            with self.assertRaisesRegex(RuntimeError, "CUDA device differs"):
                benchmark.run(self.args, self.manifest, self.root)
            self.manifest["engine_build"]["packages"][benchmark.TRT_PACKAGES[0]] = "different-version"
            with self.assertRaisesRegex(RuntimeError, "TensorRT packages differ"):
                benchmark.run(self.args, self.manifest, self.root)
        measure.assert_not_called()

    def test_compile_only_records_both_engines_without_decode_or_measurement(self):
        self.args.engine_report = None
        self.args.compile_only = True
        self.manifest["protocol"]["trt_builder_optimization_level"] = 0
        with (self.fake_torch(),
              mock.patch.object(benchmark.lab, "decode_frames") as decode,
              mock.patch.object(benchmark, "measure_case") as measure,
              mock.patch.object(benchmark, "export_onnx",
                                side_effect=lambda args, role, model, output: (output / f"{role}.onnx", {})),
              mock.patch.object(benchmark, "build_engine",
                                side_effect=lambda path, metadata, fp16, level: path.with_suffix(".engine")) as build):
            benchmark.run(self.args, self.manifest, self.root)
        decode.assert_not_called()
        measure.assert_not_called()
        self.assertEqual(build.call_args_list, [mock.call(self.root / f"{role}.onnx", {}, True, 0)
                                               for role in self.manifest["models"]])
        self.assertEqual(self.manifest["status"], "compiled")
        self.assertEqual(set(self.manifest["artifacts"]), {"person", "forklift"})
