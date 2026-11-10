"""Movimiento observable del contacto estimado; no determina riesgo físico."""
from collections import deque
from dataclasses import asdict, dataclass
import math

import numpy as np

from .calibration import contacts_in_calibrated_area, project

VERSION = "bottom_center_window_motion_v1"


@dataclass(frozen=True, slots=True)
class MotionConfig:
    unit: str
    window_seconds: float
    min_observations: int
    max_gap_seconds: float
    stationary_speed: float
    moving_speed: float
    max_position_residual: float
    camera_fixed_confirmed: bool

    def __post_init__(self):
        if self.unit not in {"normalized", "m"} or type(self.camera_fixed_confirmed) is not bool:
            raise ValueError("Indique unidad y confirmación de cámara fija")
        for name in ("window_seconds", "max_gap_seconds", "stationary_speed", "moving_speed", "max_position_residual"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Movimiento: {name} debe ser finito y no negativo")
        if not 0 < self.max_gap_seconds <= self.window_seconds <= 30:
            raise ValueError("Movimiento: 0 < hueco máximo <= ventana <= 30 s")
        if type(self.min_observations) is not int or not 3 <= self.min_observations <= 4096:
            raise ValueError("Movimiento: se requieren entre 3 y 4096 observaciones")
        if self.stationary_speed >= self.moving_speed:
            raise ValueError("La velocidad de movimiento debe superar el máximo estacionario")


@dataclass(frozen=True, slots=True)
class MotionObservation:
    state: str
    speed: float | None
    unit: str
    frame_index: int
    timestamp_s: float
    epoch: int
    start_timestamp_s: float | None
    duration_s: float
    sample_count: int
    position_residual: float | None
    reason: str | None
    configuration: dict
    calibration_sha256: str | None
    version: str = VERSION

    def to_dict(self):
        return asdict(self)


class MotionEstimator:
    def __init__(self, config: MotionConfig):
        self.config = config
        self.reset()

    def reset(self):
        self._history = {}
        self._calibration_key = None

    def retain(self, identities):
        for identity in tuple(self._history):
            if identity not in identities:
                del self._history[identity]

    def update(self, identity, frame_index, timestamp_s, point, *, epoch=0, calibration=None):
        cfg = self.config
        unit = "m_per_s" if cfg.unit == "m" else "normalized_image_per_s"
        digest = calibration.get("sha256") if calibration else None
        key = (epoch, digest)
        if key != self._calibration_key:
            self._history.clear()
            self._calibration_key = key

        def observation(state="UNKNOWN", speed=None, reason=None, history=(), residual=None):
            return MotionObservation(state, speed, unit, frame_index, timestamp_s, epoch,
                history[0][0] if history else None,
                timestamp_s-history[0][0] if history else 0., len(history), residual,
                reason, asdict(cfg), digest)

        if not cfg.camera_fixed_confirmed or (calibration and calibration["status"] != "valid"):
            self._history.pop(identity, None)
            return observation(reason="camera_unconfirmed_or_invalid")
        if cfg.unit == "m":
            if not calibration or calibration["status"] != "valid":
                self._history.pop(identity, None)
                return observation(reason="calibration_unavailable")
            if not contacts_in_calibrated_area(calibration, (point,)):
                self._history.pop(identity, None)
                return observation(reason="outside_calibrated_area")
            try:
                point = project(calibration, point)
            except ValueError:
                self._history.pop(identity, None)
                return observation(reason="calibration_unavailable")
        history = self._history.setdefault(identity, deque(maxlen=4096))
        if history and (frame_index != history[-1][3]+1 or timestamp_s <= history[-1][0]
                        or timestamp_s-history[-1][0] > cfg.max_gap_seconds+1e-9):
            history.clear()
        history.append((timestamp_s, float(point[0]), float(point[1]), frame_index))
        while len(history) > 2 and history[1][0] <= timestamp_s-cfg.window_seconds:
            history.popleft()
        if len(history) < cfg.min_observations or timestamp_s-history[0][0] < cfg.window_seconds-1e-9:
            return observation(reason="insufficient_observations", history=history)
        data = np.asarray(history, dtype=float)
        times = data[:,0]-data[:,0].mean()
        positions = data[:,1:3]-data[:,1:3].mean(axis=0)
        velocity = (times[:,None]*positions).sum(axis=0)/np.dot(times,times)
        residual = float(np.sqrt(np.mean(np.sum((positions-times[:,None]*velocity)**2,axis=1))))
        speed = float(np.linalg.norm(velocity))
        if not math.isfinite(speed) or residual > cfg.max_position_residual+1e-12:
            return observation(reason="noisy_observation", history=history, residual=residual)
        if speed >= cfg.moving_speed or math.isclose(speed,cfg.moving_speed,rel_tol=1e-12,abs_tol=0):
            return observation("MOVING", speed, history=history, residual=residual)
        if speed <= cfg.stationary_speed or math.isclose(speed,cfg.stationary_speed,rel_tol=1e-12,abs_tol=0):
            return observation("STATIONARY", speed, history=history, residual=residual)
        return observation(speed=speed,reason="between_speed_thresholds",history=history,residual=residual)
