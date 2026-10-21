# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dos canales de percepción con asociación temporal independiente por clase."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

from operix_engine.detection import Detection, Detector
from operix_engine.tracking import Track, Tracker


@dataclass(frozen=True, slots=True)
class PerceptionFrame:
    person_detections: tuple[Detection, ...]
    forklift_detections: tuple[Detection, ...]
    person_tracks: tuple[Track, ...]
    forklift_tracks: tuple[Track, ...]

    @property
    def track_identities(self) -> tuple[tuple[str, int], ...]:
        """Un ID numérico solo es único dentro de su clase."""
        return tuple((track.class_name, track.track_id) for track in self.person_tracks + self.forklift_tracks)


@dataclass(frozen=True, slots=True)
class PerceptionTiming:
    person_inference_s: float
    forklift_inference_s: float
    person_tracking_s: float
    forklift_tracking_s: float


class ClassPerceptionChannel:
    """Filtra una única clase ANTES de entregarla a su propio tracker."""

    def __init__(self, class_name: str, detector: Detector, tracker: Tracker) -> None:
        if class_name not in ("person", "forklift"):
            raise ValueError("Canal de percepción no soportado")
        if class_name not in detector.class_names.values():
            raise ValueError(f"El modelo no declara la clase {class_name}")
        self.class_name = class_name
        self.detector = detector
        self.tracker = tracker
        # Ultralytics usa un contador global entre instancias BYTETracker.
        # La identidad pública se numera por canal, sin alterar asociaciones.
        self._local_ids: dict[int, int] = {}

    def detect(self, frame: NDArray[np.uint8]) -> tuple[Detection, ...]:
        return tuple(item for item in self.detector.detect(frame) if item.class_name == self.class_name)

    def track(self, detections: tuple[Detection, ...]) -> tuple[Track, ...]:
        if any(item.class_name != self.class_name for item in detections):
            raise ValueError("El tracker recibió una clase ajena a su canal")
        tracks = self.tracker.update(detections)
        if any(item.class_name != self.class_name for item in tracks):
            raise ValueError("El tracker devolvió una clase ajena a su canal")
        normalized = []
        for track in tracks:
            local_id = self._local_ids.setdefault(track.track_id, len(self._local_ids) + 1)
            normalized.append(replace(track, track_id=local_id))
        return tuple(normalized)

    def reset(self) -> None:
        self.tracker.reset()
        self._local_ids.clear()


class DualPerception:
    """Orquesta canales opcionales sin fusionar sus IDs ni sus estados ByteTrack."""

    def __init__(
        self,
        *,
        person: ClassPerceptionChannel | None,
        forklift: ClassPerceptionChannel | None,
    ) -> None:
        if person is None and forklift is None:
            raise ValueError("Se requiere al menos un detector activo")
        if person is not None and person.class_name != "person":
            raise ValueError("El canal person tiene una clase incorrecta")
        if forklift is not None and forklift.class_name != "forklift":
            raise ValueError("El canal forklift tiene una clase incorrecta")
        if person is not None and forklift is not None and person.tracker is forklift.tracker:
            raise ValueError("person y forklift requieren trackers independientes")
        self.person = person
        self.forklift = forklift

    def process(
        self,
        frame: NDArray[np.uint8],
        *,
        synchronize: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> tuple[PerceptionFrame, PerceptionTiming]:
        """Avanza ambos trackers exactamente una vez y mide cada etapa."""
        times = [0.0, 0.0, 0.0, 0.0]
        results: list[tuple[tuple[Detection, ...], tuple[Track, ...]]] = []
        for index, channel in enumerate((self.person, self.forklift)):
            if channel is None:
                results.append(((), ()))
                continue
            if synchronize is not None:
                synchronize()
            start = clock()
            detections = channel.detect(frame)
            if synchronize is not None:
                synchronize()
            times[index] = clock() - start
            start = clock()
            tracks = channel.track(detections)
            times[index + 2] = clock() - start
            results.append((detections, tracks))
        person, forklift = results
        return (
            PerceptionFrame(person[0], forklift[0], person[1], forklift[1]),
            PerceptionTiming(*times),
        )

    def reset(self) -> None:
        for channel in (self.person, self.forklift):
            if channel is not None:
                channel.reset()

    def process_batch(
        self, frames: tuple[NDArray[np.uint8], ...], *,
        synchronize: Callable[[], None] | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> tuple[tuple[PerceptionFrame, PerceptionTiming], ...]:
        """Agrupa solo detección; ambos trackers avanzan una vez por frame y en orden.

        El tiempo de detección del lote se reparte por frame para telemetría;
        no representa la latencia individual de un frame esperando su lote.
        """
        if not frames:
            return ()
        detections, inference_times = [], []
        for channel in (self.person, self.forklift):
            if channel is None:
                detections.append(tuple(() for _ in frames))
                inference_times.append(0.0)
                continue
            if synchronize is not None:
                synchronize()
            start = clock()
            batch_detector = getattr(channel.detector, "detect_batch", None)
            if batch_detector is None:
                observed = tuple(channel.detect(frame) for frame in frames)
            else:
                batch = batch_detector(frames)
                if len(batch) != len(frames):
                    raise RuntimeError("El detector no conservó el tamaño del lote")
                observed = tuple(tuple(d for d in items if d.class_name == channel.class_name)
                                 for items in batch)
            if synchronize is not None:
                synchronize()
            inference_times.append((clock() - start) / len(frames))
            detections.append(observed)
        results = []
        for index in range(len(frames)):
            tracks, tracking_times = [], []
            for role, channel in enumerate((self.person, self.forklift)):
                start = clock()
                tracks.append(channel.track(detections[role][index]) if channel else ())
                tracking_times.append(clock() - start if channel else 0.0)
            results.append((
                PerceptionFrame(detections[0][index], detections[1][index], tracks[0], tracks[1]),
                PerceptionTiming(*inference_times, *tracking_times),
            ))
        return tuple(results)
