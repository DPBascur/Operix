"""Contexto visual acotado de una época RTSP y entrega al contrato de clips."""

from collections import deque
import hashlib
import json
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import cv2
import numpy as np


class JpegRing:
    def __init__(self, fps, *, seconds=3, max_bytes=4 * 1024 * 1024):
        self.frames = deque()
        self.capacity = math.floor(fps * seconds) + 1
        self.max_bytes = max_bytes
        self.size = 0

    def clear(self):
        self.frames.clear()
        self.size = 0

    def append(self, index, jpeg):
        if self.frames and self.frames[-1][0] + 1 != index:
            self.clear()
        self.frames.append((index, jpeg))
        self.size += len(jpeg)
        while len(self.frames) > self.capacity or self.size > self.max_bytes:
            self.size -= len(self.frames.popleft()[1])

    def snapshot(self):
        return tuple(self.frames)


def _encode_clip(path, frames, fps, limit):
    writer = None
    try:
        for _, jpeg in frames:
            frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                raise ValueError("JPEG de contexto inválido")
            if writer is None:
                height, width = frame.shape[:2]
                scale = min(1.0, 640 / max(height, width))
                dimensions = tuple(max(2, int(value * scale) // 2 * 2) for value in (width, height))
                backend = cv2.CAP_MSMF if os.name == "nt" else cv2.CAP_ANY
                writer = cv2.VideoWriter(str(path), backend, cv2.VideoWriter_fourcc(*"avc1"), fps, dimensions)
                if not writer.isOpened():
                    raise RuntimeError("Codificador H.264 no disponible")
            if frame.shape[:2][::-1] != dimensions:
                frame = cv2.resize(frame, dimensions, interpolation=cv2.INTER_AREA)
            writer.write(frame)
            if path.stat().st_size > limit:
                raise ValueError("Clip fuera del límite de almacenamiento")
    finally:
        if writer is not None:
            writer.release()

    reader = cv2.VideoCapture(str(path))
    try:
        if (not reader.isOpened() or abs(reader.get(cv2.CAP_PROP_FPS) - fps) > .01
                or not all(reader.read()[0] for _ in frames) or reader.read()[0]):
            raise ValueError("Clip H.264 incompleto")
    finally:
        reader.release()


class ClipStore:
    """Publica juntos el MP4 verificado y los metadatos del evento confirmado."""

    def __init__(self, media_root: Path, fps: float):
        self.root = media_root / "evidence-clips"
        self.fps = fps

    def save(self, event_id, payload, frames):
        event_id = str(UUID(event_id))
        run_id = str(UUID(payload["analysis_run_id"]))
        event_frame = payload["frame_index"]
        if (not frames or not frames[0][0] <= event_frame <= frames[-1][0]
                or any(index != frames[0][0] + offset for offset, (index, _) in enumerate(frames))):
            return "unavailable"
        destination = self.root / event_id / run_id
        if destination.exists():
            return "existing"
        remaining = 512 * 1024 * 1024
        for path in self.root.glob("*/*/clip.mp4"):
            try:
                remaining -= path.stat().st_size
            except FileNotFoundError:
                continue  # Un evento pudo borrarse durante el recorrido.
        limit = min(remaining, 12 * 1024 * 1024)
        if limit <= 0:
            return "disk_limit"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".clip-", dir=self.root) as directory:
            scratch = Path(directory)
            output = scratch / "clip.mp4"
            _encode_clip(output, frames, self.fps, limit)
            size = output.stat().st_size
            if not 0 < size <= limit:
                return "disk_limit"
            with output.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            start = frames[0][0]
            source = payload["source"]
            metadata = {
                "kind": "annotated", "event_id": event_id, "analysis_run_id": run_id,
                "source_sha256": source["video_sha256"], "config_sha256": source["config_sha256"],
                "event_frame": event_frame, "event_timestamp_s": payload["video_timestamp_s"],
                "start_frame": start, "end_frame_exclusive": frames[-1][0] + 1, "fps": self.fps,
                "duration_s": len(frames) / self.fps, "event_offset_s": (event_frame - start) / self.fps,
                "bytes": size, "sha256": digest,
            }
            (scratch / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            try:
                scratch.rename(destination)
            except OSError:
                if destination.is_dir():
                    return "existing"
                raise
        return "saved"
