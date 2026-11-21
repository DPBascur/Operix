"""Run the opt-in shared detector service for the RTSP lab."""

import argparse
import os
from pathlib import Path
import signal
import sys

import numpy as np

from operix_engine.rtsp_inference import InferenceBroker, check_ready


def load_detectors(args):
    import torch

    from run_rtsp_pilot import FORKLIFT_SHA, PERSON_SHA, checked_file, detector

    checked_file(args.person_weights, PERSON_SHA, "PERSON")
    checked_file(args.forklift_weights, FORKLIFT_SHA, "FORKLIFT")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable")

    person = detector(args.person_weights, .10, .70)
    forklift = detector(args.forklift_weights, .45, .55)
    frame = np.zeros((args.height, args.width, 3), dtype=np.uint8)
    for role, model in (("person", person), ("forklift", forklift)):
        if role not in model.class_names.values():
            raise ValueError(f"checkpoint does not declare {role}")
        model.detect(frame)
        for size in range(2, args.batch_cap + 1):
            model.detect_batch((frame,) * size)
        torch.cuda.synchronize()
        if torch.device(model.model_device).type != "cuda":
            raise RuntimeError(f"{role} detector did not warm up on CUDA")
    return person, forklift, torch.cuda.synchronize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--check-ready", action="store_true", help="probe the warmed broker and exit")
    parser.add_argument("--person-weights", type=Path)
    parser.add_argument("--forklift-weights", type=Path)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--height", type=int, default=540)
    parser.add_argument("--batch-cap", type=int, choices=(1, 2, 4), default=1)
    parser.add_argument("--batch-wait-ms", type=float, default=3)
    parser.add_argument("--max-clients", type=int, default=8)
    args = parser.parse_args()
    if args.check_ready:
        return 0 if check_ready(args.socket) else 1
    if os.environ.get("OPERIX_RTSP_INFERENCE") != "1":
        parser.error("set OPERIX_RTSP_INFERENCE=1 to enable the broker")
    if args.person_weights is None or args.forklift_weights is None:
        parser.error("--person-weights and --forklift-weights are required to serve")
    if os.name != "posix":
        parser.error("the broker requires POSIX Unix sockets")
    if not 1 <= args.width <= 1920 or not 1 <= args.height <= 1080:
        parser.error("frame dimensions exceed the RTSP limits")
    if not 0 <= args.batch_wait_ms <= 20 or not args.batch_cap <= args.max_clients <= 32:
        parser.error("batch wait must be 0–20 ms and max clients must be between batch cap and 32")
    try:
        person, forklift, synchronize = load_detectors(args)
        broker = InferenceBroker(args.socket, person=person, forklift=forklift, batch_cap=args.batch_cap,
                                 batch_wait_s=args.batch_wait_ms / 1000, max_clients=args.max_clients,
                                 synchronize=synchronize, fatal_detector_errors=True)
        previous = signal.signal(signal.SIGTERM, lambda *_: broker.stop())
        try:
            broker.serve_forever()
        finally:
            signal.signal(signal.SIGTERM, previous)
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"RTSP inference broker failed: {exc}", file=sys.stderr)
        if exc.__cause__ is not None:
            print(f"Cause: {exc.__cause__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
