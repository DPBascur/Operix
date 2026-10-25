"""TEST ONLY: worker productivo con detecciones fixture, sin pesos ni evaluación GPU."""

import argparse
from pathlib import Path
import runpy
import sys
import hashlib
import json
import os
from unittest.mock import patch

from operix_engine.detection import BoundingBox, Detection
from operix_engine.visualization import OpenCvRenderer
from operix_engine.rules import PairRuleEvaluation


class FixtureDetector:
    def __init__(self, config):
        self.name = "person" if config.confidence_threshold == .10 else "forklift"
        self.class_names = {0: self.name}
        self.model_device = "cuda:fixture-only"

    def detect(self, frame):
        if os.environ.get("OPERIX_TEST_OCCUPANCY_SCENARIO") == "contained":
            boxes = ((50,35,60,70),) if self.name == "person" else ((40,20,80,80),(65,20,95,80))
        else:
            boxes = ((40,30,60,70),) if self.name == "person" else ((55,30,75,70),(80,30,100,70))
        return tuple(Detection(0, self.name, .9, BoundingBox(*box)) for box in boxes)

    def detect_batch(self, frames):
        return tuple(self.detect(frame) for frame in frames)


def main():
    script = Path(sys.argv[1])
    sys.path.insert(0, str(script.parent))
    worker = runpy.run_path(str(script), run_name="fixture_worker")
    parser = argparse.ArgumentParser()
    for flag in ("session-dir", "video", "config", "polygon", "person-weights", "forklift-weights", "event-context"):
        parser.add_argument("--" + flag, type=Path)
    parser.add_argument("--person-sha256")
    parser.add_argument("--forklift-sha256")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--preview-width", type=int, default=1280)
    parser.add_argument("--preview-fps", type=float, default=10)
    args = parser.parse_args(sys.argv[2:])
    receipts = []

    class RecordingRenderer(OpenCvRenderer):
        def render_proximity(self, frame, spatial, result, **kwargs):
            annotated = super().render_proximity(frame, spatial, result, **kwargs)
            receipts.append({"frame": spatial.frame_index,
                "image_sha256": hashlib.sha256(annotated.tobytes()).hexdigest(),
                "relations": [{"person": item.interaction.person.track_id,
                    "forklift": item.interaction.forklift.track_id,
                    "distance": item.observed_normalized_distance,
                    "duration": item.observed_duration_s, "state": item.rule_state,
                    "geometry_version": item.proximity_geometry_version,
                    "person_anchor": [item.person_anchor.x, item.person_anchor.y],
                    "equipment_target": [item.equipment_target.x, item.equipment_target.y],
                    "started_frame": item.started_frame_index}
                    for item in result.evaluations if isinstance(item, PairRuleEvaluation)]})
            (args.session_dir / "TEST_ONLY_overlay_receipts.json").write_text(json.dumps(receipts), encoding="utf-8")
            return annotated

    worker["process"].__globals__["OpenCvRenderer"] = RecordingRenderer
    worker["process"].__globals__["YoloDetector"] = FixtureDetector
    with patch("run_dual_perception.checked_file"), patch("torch.cuda.is_available", return_value=True), patch("torch.cuda.synchronize"):
        worker["process"](args)


if __name__ == "__main__":
    main()
