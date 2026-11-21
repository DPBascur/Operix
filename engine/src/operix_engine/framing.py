"""Compare a recorded view with its operator-confirmed first frame."""

import math

import cv2
import numpy as np

from .pattern_framing import PatternFramingGuard


REFERENCE = "first_frame_orb_affine_v1"
SAMPLE_SECONDS = .25
STABLE_DISPLACEMENT = .008
SHIFT_DISPLACEMENT = .015
SHIFT_SAMPLES = 3
MIN_INLIERS = 24


class RecordedFraming:
    """Aplica la política de encuadre de la calibración ligada al video."""

    def __init__(self, calibration):
        self.calibration = calibration
        self.manually_invalid = bool(calibration and calibration["status"] == "invalid")
        evidence = calibration.get("pattern_evidence") if calibration and not self.manually_invalid else None
        self.pattern = PatternFramingGuard(evidence) if evidence else None
        self.guard = FramingGuard() if (
            calibration and not self.manually_invalid and self.pattern is None
            and calibration.get("framing_reference") == REFERENCE
        ) else None

    def update(self, frame, frame_index, timestamp_s, boxes):
        if self.pattern is not None:
            return self.pattern.update(frame, frame_index, timestamp_s) == "VALID"
        if self.guard is not None:
            return self.guard.update(frame, frame_index, timestamp_s, boxes) == "VALID"
        return not self.manually_invalid

    def status(self):
        if self.pattern is not None:
            return self.pattern.status()
        if self.guard is not None:
            return self.guard.status()
        if self.manually_invalid:
            return {"state": "INVALID", "reason": "operator_invalidated"}
        if self.calibration is not None:
            # Los snapshots anteriores conservan la confirmación manual de vista fija.
            return {"state": "UNAVAILABLE", "reason": "legacy_manual_only"}
        return None


class FramingGuard:
    def __init__(self):
        self.state = "UNAVAILABLE"
        self.reason = "awaiting_reference"
        self._orb = cv2.ORB_create(nfeatures=1600, fastThreshold=12, edgeThreshold=19)
        self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self._reference = None
        self._next_sample = 0.
        self._shift_samples = 0
        self._stable_samples = 0
        self._sample_frame = None
        self._displacement = None
        self._inliers = 0
        self.first_suspended_frame = None
        self.invalidated_frame = None

    def _features(self, frame, boxes):
        height, width = frame.shape[:2]
        scale = min(1., 640 / max(width, height))
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        gray = cv2.cvtColor(cv2.resize(frame, size, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        mask = np.full(gray.shape, 255, dtype=np.uint8)
        for box in boxes:
            # Exclude detected foreground and a margin around its contours.
            left = max(0, math.floor(box.x_min * scale) - 12)
            right = min(size[0], math.ceil(box.x_max * scale) + 12)
            top = max(0, math.floor(box.y_min * scale) - 12)
            bottom = min(size[1], math.ceil(box.y_max * scale) + 12)
            if left < right and top < bottom:
                mask[top:bottom, left:right] = 0
        keys, descriptors = self._orb.detectAndCompute(gray, mask)
        return np.asarray([key.pt for key in keys], dtype=np.float32), descriptors, size

    @staticmethod
    def _distributed(points, size):
        if len(points) < MIN_INLIERS:
            return False
        normalized = points / size
        cells = np.minimum((normalized * 3).astype(int), 2)
        return len(set(map(tuple, cells))) >= 5 and cv2.contourArea(
            cv2.convexHull(normalized.astype(np.float32))
        ) >= .16

    def _compare(self, current):
        original, reference_descriptors, size = self._reference
        points, descriptors, _ = current
        if reference_descriptors is None or descriptors is None:
            return None, 0
        matches = {}
        for pair in self._matcher.knnMatch(reference_descriptors, descriptors, k=2):
            if len(pair) != 2:
                continue
            best, second = pair
            if best.distance < .75 * second.distance:
                old = matches.get(best.trainIdx)
                if old is None or best.distance < old.distance:
                    matches[best.trainIdx] = best
        if len(matches) < MIN_INLIERS:
            return None, 0
        start = original[[match.queryIdx for match in matches.values()]]
        end = points[list(matches)]
        transform, mask = cv2.estimateAffinePartial2D(start, end, ransacReprojThreshold=2.5)
        if transform is None or mask is None or not np.isfinite(transform).all():
            return None, 0
        inliers = mask.ravel().astype(bool)
        count = int(inliers.sum())
        if (count < .6 * len(matches) or not self._distributed(start[inliers], size)
                or not self._distributed(end[inliers], size)):
            return None, count
        width, height = size
        anchors = np.array([[0, 0], [width, 0], [0, height], [width, height]])
        displacement = anchors @ transform[:, :2].T + transform[:, 2] - anchors
        return float(np.linalg.norm(displacement, axis=1).max() / math.hypot(*size)), count

    def update(self, frame, frame_index, timestamp_s, boxes=()):
        if self.state == "INVALID" or timestamp_s + 1e-9 < self._next_sample:
            return self.state
        self._next_sample = timestamp_s + SAMPLE_SECONDS
        self._sample_frame = frame_index
        current = self._features(frame, boxes)
        if frame_index == 0:
            self._reference = current
            if self._distributed(current[0], current[2]):
                self.state, self.reason = "VALID", "reference_ready"
                return self.state
        displacement, self._inliers = self._compare(current)
        self._displacement = displacement
        if displacement is None:
            self._shift_samples = self._stable_samples = 0
            self.state, self.reason = "UNAVAILABLE", "insufficient_static_matches"
        elif displacement <= STABLE_DISPLACEMENT:
            self._shift_samples = 0
            self._stable_samples += 1
            if self.state == "VALID" or self._stable_samples >= 2:
                self.state, self.reason = "VALID", "reference_match"
        else:
            self._stable_samples = 0
            self._shift_samples = self._shift_samples + 1 if displacement >= SHIFT_DISPLACEMENT else 0
            self.state, self.reason = "SUSPECT", "reference_displacement"
            if self._shift_samples >= SHIFT_SAMPLES:
                self.state, self.reason = "INVALID", "sustained_reference_displacement"
                self.invalidated_frame = frame_index
        if self.state != "VALID" and self.first_suspended_frame is None:
            self.first_suspended_frame = frame_index
        return self.state

    def status(self):
        return {
            "method": REFERENCE, "state": self.state, "reason": self.reason,
            "sample_frame": self._sample_frame, "displacement": self._displacement,
            "inliers": self._inliers, "first_suspended_frame": self.first_suspended_frame,
            "invalidated_frame": self.invalidated_frame,
        }
