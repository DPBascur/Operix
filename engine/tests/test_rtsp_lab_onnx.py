import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rtsp_lab_onnx as onnx
import run_rtsp_lab as lab


class OnnxLabTests(TestCase):
    def setUp(self):
        self.args = SimpleNamespace(width=960, height=540, fps=12, seconds=30, config=None)
        self.env = {
            "OPERIX_RTSP_LAB_INFERENCE_PROFILE": "onnx-cuda",
            "OPERIX_RTSP_LAB_ONNX_DIR": "/verified/models",
            "OPERIX_RTSP_LAB_CAMERA_ID": "lab-cam-01",
            "OPERIX_RTSP_URL": "rtsp://127.0.0.1/lab",
            "OPERIX_RTSP_ALLOWED_IP": "127.0.0.1",
            "OPERIX_EVENT_PUBLISH_TOKEN": "test",
            "OPERIX_EVENT_API_BASE_URL": "http://127.0.0.1:8000/api/v1",
        }

    def test_default_and_explicit_profiles_and_invalid_combinations(self):
        self.assertEqual(lab.inference_profile({}, self.args), "pytorch-fp32")
        self.assertEqual(lab.inference_profile(
            {**self.env, "OPERIX_RTSP_LAB_INFERENCE_PROFILE": "pytorch-fp32"}, self.args), "pytorch-fp32")
        self.assertEqual(lab.inference_profile(self.env, self.args), "onnx-cuda")
        for overrides in (
            {"OPERIX_RTSP_LAB_INFERENCE_PROFILE": "cpu"},
            {"OPERIX_RTSP_LAB_ONNX_DIR": ""},
            {"OPERIX_RTSP_INFERENCE_SOCKET": "/tmp/broker.sock"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(lab.InvalidInferenceProfile):
                lab.inference_profile({**self.env, **overrides}, self.args)
        self.args.width = 800
        with self.assertRaises(lab.InvalidInferenceProfile):
            lab.inference_profile(self.env, self.args)

    def test_each_graph_must_match_its_pinned_hash(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            paths = {role: directory / f"{role}.onnx" for role in onnx.EXPORT_HASHES}
            hashes = {}
            for role, path in paths.items():
                payload = role.encode()
                path.write_bytes(payload)
                hashes[role] = hashlib.sha256(payload).hexdigest()
            with mock.patch.object(onnx, "EXPORT_HASHES", hashes):
                self.assertEqual(onnx.verified_exports(directory), paths)
                for role, path in paths.items():
                    with self.subTest(role=role):
                        path.write_bytes(b"changed")
                        with self.assertRaisesRegex(ValueError, role):
                            onnx.verified_exports(directory)
                        path.write_bytes(role.encode())

    def test_v7_requires_dedicated_worker_and_pinned_artifact(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            env = {"OPERIX_DETECTOR_PROFILE": "unified-v7", "OPERIX_UNIFIED_V7_DIR": temp}
            self.assertEqual(lab.inference_profile(env, self.args), "unified-v7")
            for overrides in ({"OPERIX_UNIFIED_V7_DIR": ""},
                              {"OPERIX_RTSP_INFERENCE_SOCKET": "/tmp/shared.sock"}):
                with self.assertRaises(lab.InvalidInferenceProfile):
                    lab.inference_profile({**env, **overrides}, self.args)
            (directory / "industrial-unified.onnx").write_bytes(b"changed")
            with (mock.patch.object(onnx, "verified_cuda_runtime") as runtime,
                  self.assertRaises(ValueError)):
                onnx.load_unified_perception(directory, None, None, None)
            runtime.assert_not_called()

    def test_worker_checks_both_original_checkpoints_before_loading_onnx(self):
        self.args.person_weights = Path("original-person.pt")
        self.args.forklift_weights = Path("original-forklift.pt")
        config = SimpleNamespace(calibration=None)
        with (mock.patch.object(lab, "checked_file", side_effect=(None, ValueError("wrong hash"))) as check,
              mock.patch.object(lab, "cuda_detectors") as load):
            with self.assertRaisesRegex(ValueError, "wrong hash"):
                lab.LabPipeline(config, self.args, onnx_directory=Path("/verified/models"))
            self.assertEqual(check.call_args_list, [
                mock.call(self.args.person_weights, lab.PERSON_SHA, "PERSON"),
                mock.call(self.args.forklift_weights, lab.FORKLIFT_SHA, "FORKLIFT"),
            ])
            load.assert_not_called()

    def test_adapters_use_strict_session_options_and_reject_cpu(self):
        ort = mock.Mock()
        ort.get_available_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        create_session = ort.InferenceSession
        session = create_session.return_value
        person, forklift = mock.Mock(), mock.Mock()
        specs = {role: {"confidence": conf, "nms_iou": iou, "class_filter": role}
                 for role, (conf, iou) in lab.DETECTOR_THRESHOLDS.items()}
        paths = {role: Path(f"{role}.onnx") for role in onnx.EXPORT_HASHES}

        def make_detectors(*args, **kwargs):
            for path in paths.values():
                ort.InferenceSession(path, None, providers=["CPUExecutionProvider"])
            return {"person": (person,), "forklift": (forklift,)}

        def package_version(name):
            if name == "onnxruntime-gpu":
                return onnx.ORT_VERSION
            raise onnx.PackageNotFoundError(name)

        with (mock.patch.dict(sys.modules, {"onnxruntime": ort}),
              mock.patch.object(onnx, "verified_exports", return_value=paths),
              mock.patch.object(onnx, "version", side_effect=package_version)):
            # Import once via the same directory as the worker, then replace only model construction.
            sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "deployment" / "rtsp-lab"))
            try:
                import benchmark_backends
            finally:
                sys.path.pop(0)
            with mock.patch.object(benchmark_backends, "make_detectors", side_effect=make_detectors) as make:
                session.get_providers.return_value = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                with onnx.cuda_detectors(Path("unused"), specs) as models:
                    self.assertEqual(models, (person, forklift))
                make.assert_called_once_with(specs, paths, (384, 640), rect=False)
                self.assertEqual(create_session.call_args_list, [
                    mock.call(path, ort.SessionOptions.return_value, providers=[
                        ("CUDAExecutionProvider", {"device_id": "0", "use_tf32": "0"}),
                    ]) for path in paths.values()
                ])
                ort.SessionOptions.return_value.add_session_config_entry.assert_called_with(
                    "session.disable_cpu_ep_fallback", "1")
                self.assertEqual(session.disable_fallback.call_count, 2)
                session.get_providers.return_value = ["CPUExecutionProvider"]
                with self.assertRaisesRegex(RuntimeError, "failed to initialize CUDA"):
                    with onnx.cuda_detectors(Path("unused"), specs):
                        self.fail("ONNX CPU session escaped startup")

    def test_real_worker_reports_effective_profile_and_never_retries_with_pytorch(self):
        with TemporaryDirectory() as temp:
            self.args.output = Path(temp)
            context = SimpleNamespace(analysis_run_id=uuid4(), source={"camera_id": "lab-cam-01"})
            status = lab.WorkerStatus(self.args)
            with (mock.patch.dict(lab.os.environ, self.env, clear=True),
                  mock.patch.object(lab, "load_context", return_value=(context, None)),
                  mock.patch.object(lab, "LabPipeline") as pipeline):
                pipeline.side_effect = RuntimeError("CUDA failed")
                with self.assertRaises(lab.OnnxStartupError):
                    lab.run(self.args, status, lambda: None)
                pipeline.assert_called_once_with(None, self.args, onnx_directory=Path("/verified/models"))
                self.assertIsNone(status.inference_profile)

                pipeline.side_effect = None
                stop = mock.Mock(side_effect=(None, None, "OPERATOR_STOP"))
                self.assertEqual(lab.run(self.args, status, stop), "OPERATOR_STOP")
                status.write("stopped", "OPERATOR_STOP")
                data = json.loads((self.args.output / "status.json").read_bytes())
                self.assertEqual(data["metrics"]["inference_profile"], "onnx-cuda")
