"""Verify framing against the marker corners saved at calibration confirmation."""

import math

import cv2
import numpy as np


SAMPLE_SECONDS = 1.
STABLE_DISPLACEMENT = .008
SHIFT_DISPLACEMENT = .015
SHIFT_SAMPLES = 3


def _detect(frame, dictionary):
    from .calibration_patterns import detect_marker_corners

    return detect_marker_corners(frame, dictionary)


class PatternFramingGuard:
    def __init__(self, evidence, *, dimensions=None, operator_invalidated=False):
        self._dimensions = (evidence["width"], evidence["height"])
        self._profile_matches = dimensions is None or dimensions == self._dimensions
        self._dictionary = evidence["dictionary"]
        self._marker_ids = tuple(int(marker_id) for marker_id in evidence["marker_corners"])
        self._reference = np.asarray(list(evidence["marker_corners"].values()), dtype=float)
        self._pixel_scale = np.asarray(self._dimensions) / math.hypot(*self._dimensions)
        self._next_sample = -math.inf
        self._large_shifts = 0
        self._sample_frame = None
        self._displacement = None
        self.first_suspended_frame = None
        self.invalidated_frame = None
        self.state, self.reason = "UNAVAILABLE", "awaiting_pattern_match"
        if operator_invalidated:
            self.state, self.reason = "INVALID", "operator_invalidated"

    def suspend(self, reason):
        # Preserve the confirmed reference, sticky invalidation and sampling budget.
        if self.state != "INVALID":
            self.state, self.reason = "UNAVAILABLE", reason
            self._displacement = None

    def update(self, frame, frame_index, timestamp_s):
        if self.state == "INVALID":
            return self.state
        if not self._profile_matches or frame.shape[:2][::-1] != self._dimensions:
            self._large_shifts = 0
            self.suspend("capture_dimensions_mismatch")
        elif timestamp_s >= self._next_sample:
            self._next_sample = timestamp_s + SAMPLE_SECONDS
            self._sample_frame = frame_index
            self._sample(frame, frame_index)
        if self.state != "VALID" and self.first_suspended_frame is None:
            self.first_suspended_frame = frame_index
        return self.state

    def _sample(self, frame, frame_index):
        try:
            markers = _detect(frame, self._dictionary)
            current = np.asarray([markers[marker_id] for marker_id in self._marker_ids], dtype=float)
        except (ImportError, KeyError, ValueError, TypeError, RuntimeError, cv2.error):
            self._large_shifts = 0
            self.suspend("pattern_unverified")
            return
        if (current.size == 0 or current.shape != self._reference.shape
                or not np.isfinite(current).all() or (current < 0).any() or (current > 1).any()):
            self._large_shifts = 0
            self.suspend("pattern_unverified")
            return
        displacement = float(np.linalg.norm((current - self._reference) * self._pixel_scale, axis=-1).max())
        self._displacement = displacement
        if displacement <= STABLE_DISPLACEMENT:
            self._large_shifts = 0
            self.state, self.reason = "VALID", "pattern_matches"
        else:
            self._large_shifts = self._large_shifts + 1 if displacement >= SHIFT_DISPLACEMENT else 0
            self.state, self.reason = "SUSPECT", "pattern_displacement"
            if self._large_shifts >= SHIFT_SAMPLES:
                self.state, self.reason = "INVALID", "sustained_pattern_displacement"
                self.invalidated_frame = frame_index

    def status(self):
        return {
            "method": "confirmed_marker_corners", "state": self.state, "reason": self.reason,
            "sample_frame": self._sample_frame, "displacement": self._displacement,
            "first_suspended_frame": self.first_suspended_frame, "invalidated_frame": self.invalidated_frame,
        }
