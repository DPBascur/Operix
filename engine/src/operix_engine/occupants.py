"""Asociación experimental entre tracks; sin reclasificar detecciones."""
from collections import Counter, deque
from dataclasses import dataclass
from math import dist


@dataclass(frozen=True, slots=True)
class OccupantObservation:
    state: str
    reason: str
    samples: int
    duration_s: float
    version: str = "co_motion_cabin_proxy_v1"


class OccupantEstimator:
    """Solo confirma identidad única y co-movimiento continuo en una cámara fija."""

    def __init__(self):
        self._history = {}

    def reset(self):
        self._history.clear()

    def update(self, objects, frame_index, timestamp_s):
        people = [obj for obj in objects if obj.class_name == "person"]
        vehicles = [obj for obj in objects if obj.class_name == "forklift"]
        compatible = {}
        for person in people:
            for vehicle in vehicles:
                geometry = self._cabin_proxy(person.bounding_box, vehicle.bounding_box)
                if geometry is not None:
                    compatible[(person.identity, vehicle.identity)] = (geometry, vehicle.motion)

        person_options = Counter(person for person, _ in compatible)
        vehicle_options = Counter(vehicle for _, vehicle in compatible)
        observations = {}
        for pair, (geometry, motion) in compatible.items():
            if person_options[pair[0]] > 1 or vehicle_options[pair[1]] > 1:
                observations[pair] = OccupantObservation("UNCERTAIN", "ambiguous_cabin_overlap", 0, 0.)
                self._history.pop(pair, None)
                continue
            history = self._history.setdefault(pair, deque(maxlen=120))
            if history and (
                frame_index != history[-1][0] + 1 or timestamp_s - history[-1][1] > .25
            ):
                history.clear()
            history.append((frame_index, timestamp_s, *geometry))
            while len(history) > 1 and timestamp_s - history[0][1] > 1.25:
                history.popleft()
            state, reason = self._classify(history, motion)
            observations[pair] = OccupantObservation(state, reason, len(history), timestamp_s - history[0][1])
        for pair in self._history.keys() - compatible.keys():
            self._history.pop(pair)
        return observations

    @staticmethod
    def _cabin_proxy(person, vehicle):
        width, height = vehicle.x_max - vehicle.x_min, vehicle.y_max - vehicle.y_min
        if width <= 0 or height <= 0:
            return None
        pw, ph = person.x_max - person.x_min, person.y_max - person.y_min
        if pw <= 0 or ph <= 0 or not .22 <= ph / height <= .65 or pw / width > .55:
            return None
        pc = ((person.x_min + person.x_max) / 2, (person.y_min + person.y_max) / 2)
        vc = (vehicle.x_min + width / 2, vehicle.y_min + height / 2)
        x, y = (pc[0] - vehicle.x_min) / width, (pc[1] - vehicle.y_min) / height
        if not (.28 <= x <= .72 and .22 <= y <= .57 and person.y_max <= vehicle.y_min + .78 * height):
            return None
        if (person.x_min < vehicle.x_min or person.x_max > vehicle.x_max
                or person.y_min < vehicle.y_min):
            return None
        return pc, vc, (x, y), (width, height)

    @staticmethod
    def _classify(history, motion):
        duration = history[-1][1] - history[0][1]
        if len(history) < 6 or duration < .75 - 1e-9:
            return "UNCERTAIN", "insufficient_cabin_observations"
        if motion is None or motion.state != "MOVING":
            return "UNCERTAIN", "co_motion_unconfirmed"
        _, _, pc, vc, relative, size = history[0]
        last_pc, last_vc = history[-1][2:4]
        if dist(vc, last_vc) < .22 * min(size):
            return "UNCERTAIN", "insufficient_vehicle_translation"
        for _, _, point, vehicle_point, local, other_size in history:
            if (dist(relative, local) > .055
                    or any(abs(a / b - 1) > .20 for a, b in zip(other_size, size))
                    or dist((point[0] - pc[0], point[1] - pc[1]),
                            (vehicle_point[0] - vc[0], vehicle_point[1] - vc[1])) > .07 * min(size)):
                return "UNCERTAIN", "relative_motion_or_scale_changed"
        # A positive net translation alone could be a one-frame ID switch.
        ix = len(history) // 2
        mid = history[ix][3]
        if min(dist(vc, mid), dist(mid, last_vc)) < .07 * min(size):
            return "UNCERTAIN", "vehicle_translation_not_sustained"
        if dist(pc, last_pc) < .15 * min(size):
            return "UNCERTAIN", "person_translation_unconfirmed"
        return "POSSIBLE_OCCUPANT", "persistent_cabin_overlap_and_co_motion"
