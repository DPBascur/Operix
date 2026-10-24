"""TEST ONLY: worker productivo con detecciones fixture, sin pesos ni evaluación GPU."""

import argparse
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

from operix_engine.detection import BoundingBox, Detection


class FixtureDetector:
    def __init__(self, config):
        self.name = "person" if config.confidence_threshold == .10 else "forklift"
        self.class_names = {0: self.name}
        self.model_device = "cuda:fixture-only"

    def detect(self, frame):
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
    worker["process"].__globals__["YoloDetector"] = FixtureDetector
    with patch("run_dual_perception.checked_file"), patch("torch.cuda.is_available", return_value=True), patch("torch.cuda.synchronize"):
        worker["process"](args)


if __name__ == "__main__":
    main()
