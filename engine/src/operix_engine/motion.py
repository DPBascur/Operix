"""Movimiento observable del contacto estimado; no determina riesgo físico."""
from collections import deque
from dataclasses import asdict, dataclass
import math

import numpy as np

from .calibration import contacts_in_calibrated_area, project

VERSION = "bottom_center_window_motion_v1"
CONFIRMED_VERSION = "bottom_center_window_motion_v2"


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
    confirmation_seconds: float | None = None

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
        delay = self.confirmation_seconds
        if delay is not None and (type(delay) not in (int, float) or not 0 < delay <= self.window_seconds):
            raise ValueError("Confirmación debe ser positiva y no superar la ventana")
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
    confirmation_started_at: float | None = None

    def to_dict(self):
        snapshot = asdict(self)
        if self.version == VERSION:
            snapshot.pop("confirmation_started_at")
        return snapshot


class MotionEstimator:
    def __init__(self, config: MotionConfig):
        self.config = config
        self.reset()

    def reset(self):
        self._history = {}
        self._proposals = {}
        self._calibration_key = None

    def retain(self, identities):
        for identity in tuple(self._history):
            if identity not in identities:
                del self._history[identity]
                self._proposals.pop(identity, None)

    def update(self, identity, frame_index, timestamp_s, point, *, epoch=0, calibration=None):
        cfg = self.config
        unit = "m_per_s" if cfg.unit == "m" else "normalized_image_per_s"
        digest = calibration.get("sha256") if calibration else None
        key = (epoch, digest)
        if key != self._calibration_key:
            self._history.clear()
            self._proposals.clear()
            self._calibration_key = key

        def observation(state="UNKNOWN", speed=None, reason=None, history=(), residual=None, confirmed_at=None):
            if state == "UNKNOWN" and reason != "awaiting_motion_confirmation":
                self._proposals.pop(identity, None)
            configuration = asdict(cfg)
            if cfg.confirmation_seconds is None:
                configuration.pop("confirmation_seconds")
            return MotionObservation(state, speed, unit, frame_index, timestamp_s, epoch,
                history[0][0] if history else None,
                timestamp_s-history[0][0] if history else 0., len(history), residual,
                reason, configuration, digest,
                VERSION if cfg.confirmation_seconds is None else CONFIRMED_VERSION, confirmed_at)

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
            self._proposals.pop(identity, None)
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
            state = "MOVING"
        elif speed <= cfg.stationary_speed or math.isclose(speed,cfg.stationary_speed,rel_tol=1e-12,abs_tol=0):
            state = "STATIONARY"
        else:
            return observation(speed=speed, reason="between_speed_thresholds", history=history, residual=residual)

        if cfg.confirmation_seconds is None:
            return observation(state, speed, history=history, residual=residual)
        previous_state, started = self._proposals.get(identity, (state, timestamp_s))
        if state != previous_state:
            started = timestamp_s
        self._proposals[identity] = (state, started)
        # La banda intermedia o una observación dudosa cortan la confirmación.
        if timestamp_s - started < cfg.confirmation_seconds - 1e-9:
            return observation(speed=speed, reason="awaiting_motion_confirmation",
                               history=history, residual=residual, confirmed_at=started)
        return observation(state, speed, history=history, residual=residual, confirmed_at=started)
