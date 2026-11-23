"""Bounded display observations for the RTSP lab run directory."""

from collections import deque
from datetime import datetime, timezone
from itertools import islice
import json
import logging
import math

import numpy as np

from operix_engine.zone_geometry import NormalizedPoint, point_in_zone


WINDOW_S = 4.0
WRITE_INTERVAL_S = .20
IDLE_S = 1.0
MAX_ITEMS = 64
MAX_BYTES = 512 * 1024
MAX_OBJECTS = 128
MAX_ZONES = 32
MAX_ZONE_VERTICES = 128
logger = logging.getLogger(__name__)


def _json(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")


def frame_fingerprint(image):
    """Sample 16 columns by 12 rows, in row-major order, from the OpenCV BGR frame."""
    height, width = image.shape[:2]
    xs = (2 * np.arange(16) + 1) * width // 32
    ys = (2 * np.arange(12) + 1) * height // 24
    bgr = image[ys[:, None], xs].astype(np.int32)
    luma = (77 * bgr[..., 2] + 150 * bgr[..., 1] + 29 * bgr[..., 0] + 128) // 256
    return luma.ravel().tolist()


def _zone_overlays(zones):
    result = []
    for zone in zones:
        if not zone.enabled or len(zone.polygon) > MAX_ZONE_VERTICES or len(zone.zone_id) > 128:
            continue
        try:
            point_in_zone(NormalizedPoint(0, 0), zone)  # Validates the polygon even with no tracks.
        except ValueError:
            continue
        result.append({"zone_id": zone.zone_id, "polygon": zone.polygon})
        if len(result) == MAX_ZONES:
            break
    return result


class OverlayMetadata:
    """Publish a bounded display window independently of evidence."""

    def __init__(self, directory, run_id, zones, *, write_atomic, stream_id=None):
        self.path = directory / "overlay.json"
        self.write_atomic = write_atomic
        self.items = deque(maxlen=MAX_ITEMS)
        self.clocked = stream_id is not None
        header = {"run_id": str(run_id)}
        if stream_id is not None:
            header["stream_id"] = stream_id
        self.prefix = _json(header)[:-1] + b',"items":['
        self.zones = _zone_overlays(zones)
        self.epoch = None
        self.zones_usable = False
        self.last_publish = -math.inf
        self.published_empty = False  # Clear any previous file at startup.

    def observe(self, frame, tracks, *, epoch, received_utc, spatial_allowed):
        zones_usable = bool(self.zones) and spatial_allowed
        if zones_usable != self.zones_usable or (epoch != self.epoch and not self.clocked):
            self.clear()
        self.epoch = epoch
        self.zones_usable = zones_usable

        height, width = frame.image.shape[:2]
        objects = []
        for track in islice(tracks, MAX_OBJECTS):
            box = track.bounding_box  # Already clipped by the lab pipeline.
            objects.append({
                "role": track.class_name, "track_id": track.track_id,
                "box": [box.x_min / width, box.y_min / height, box.x_max / width, box.y_max / height],
            })
        item = {
            "index": frame.index, "epoch": epoch,
            "pts_s": frame.pts if frame.pts is not None and math.isfinite(frame.pts) else None,
            "received_utc": received_utc.isoformat(),
            "processed_utc": max(received_utc, datetime.now(timezone.utc)).isoformat(),
            "fingerprint": frame_fingerprint(frame.image),
            "objects": objects,
        }
        if zones_usable:
            item["zones"] = self.zones
        if frame.source_ordinal is not None:
            item["source_ordinal"] = frame.source_ordinal
        self.items.append((frame.received, _json(item)))

    def expire(self, now):
        if self.items and now - self.items[-1][0] >= IDLE_S:
            self.clear()

    def publish(self, now):
        self.expire(now)
        if not self.items or now - self.last_publish < WRITE_INTERVAL_S:
            return
        self.last_publish = now
        while self.items and now - self.items[0][0] > WINDOW_S:
            self.items.popleft()

        # Include one byte per item for delimiters, plus the envelope.
        size = len(self.prefix) + 2 + sum(len(item) + 1 for _, item in self.items)
        while size > MAX_BYTES and self.items:
            _, item = self.items.popleft()
            size -= len(item) + 1
        if not self.items:
            self.clear()
            return
        if self._write(b",".join(item for _, item in self.items)):
            self.published_empty = False

    def clear(self):
        self.items.clear()
        if not self.published_empty and self._write(b""):
            self.published_empty = True

    def _write(self, items):
        try:
            self.write_atomic(self.path, self.prefix + items + b"]}")
        except OSError as error:
            logger.warning("Could not publish RTSP overlay metadata: %s", error)
            return False
        return True
