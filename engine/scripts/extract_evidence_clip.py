"""Extrae un intervalo de un MP4 anotado CFR sin cargar modelos."""

import argparse
import os
from pathlib import Path

import cv2


def extract(source: Path, output: Path, start: int, stop: int, fps: float, limit: int) -> None:
    capture = cv2.VideoCapture(str(source))
    writer = None
    try:
        if not capture.isOpened() or abs(capture.get(cv2.CAP_PROP_FPS) - fps) > 0.01:
            raise ValueError("Cadencia inesperada del MP4 anotado")
        if start and not capture.set(cv2.CAP_PROP_POS_FRAMES, start):
            raise ValueError("No se pudo localizar el primer fotograma del clip")
        for index in range(start, stop):
            ok, frame = capture.read()
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if (not ok or round(capture.get(cv2.CAP_PROP_POS_FRAMES)) != index + 1
                    or abs(timestamp - index / fps) > 0.25 / fps):
                raise ValueError("El MP4 no entregó el fotograma temporal esperado")
            if writer is None:
                height, width = frame.shape[:2]
                scale = min(1.0, 640 / max(height, width))
                dimensions = (max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2))
                backend = cv2.CAP_MSMF if os.name == "nt" else cv2.CAP_ANY
                writer = cv2.VideoWriter(str(output), backend, cv2.VideoWriter_fourcc(*"avc1"), fps, dimensions)
                if not writer.isOpened():
                    raise RuntimeError("No se pudo iniciar el codificador H.264")
            if frame.shape[:2][::-1] != dimensions:
                frame = cv2.resize(frame, dimensions, interpolation=cv2.INTER_AREA)
            writer.write(frame)
            if output.stat().st_size > limit:
                raise ValueError("El clip supera el límite de almacenamiento")
    finally:
        capture.release()
        if writer is not None:
            writer.release()

    verified = cv2.VideoCapture(str(output))
    try:
        decoded = 0
        while verified.read()[0]:
            decoded += 1
        if decoded != stop - start or abs(verified.get(cv2.CAP_PROP_FPS) - fps) > 0.01:
            raise ValueError("El clip no conservó fotogramas o FPS")
    finally:
        verified.release()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("start", type=int)
    parser.add_argument("stop", type=int)
    parser.add_argument("fps", type=float)
    parser.add_argument("limit", type=int)
    args = parser.parse_args()
    extract(args.source, args.output, args.start, args.stop, args.fps, args.limit)
