# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Orquestación mínima de video a candidatos y evidencia visual real."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
from numpy.typing import NDArray

from operix_engine.detection import BoundingBox
from operix_engine.event_publishing import EventContext, EventSink, publish_with_retries
from operix_engine.operational_config import OperationalConfig, Zone
from operix_engine.rules import EventCandidate, RuleEngine
from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
from operix_engine.tracking import Track
from operix_engine.video_processor import RecordedVideoSource, VideoSourceError
from operix_engine.visualization import OpenCvRenderer, TrajectoryAccumulator, VisualizationConfig


class Detector(Protocol):
    def detect(self, frame: NDArray[np.uint8]) -> tuple: ...


class Tracker(Protocol):
    def update(self, detections: tuple) -> tuple[Track, ...]: ...


def _real_frame_png(
    frame: NDArray[np.uint8],
    frame_index: int,
    candidate: EventCandidate,
    tracks: tuple[Track, ...],
    zone: Zone,
    renderer: OpenCvRenderer,
    trajectories: dict,
) -> bytes:
    """Anota una copia del frame leído, nunca una escena reconstruida."""
    if candidate.frame_index != frame_index or not any(
        track.track_id == candidate.track_id for track in tracks
    ):
        raise ValueError("El candidato no corresponde a un track del frame actual")
    annotated = renderer.render_zone(
        frame, zone, event=True,
        rule_kind=str(candidate.parameters.get("kind", candidate.rule_id)),
        frame_index=frame_index,
    )
    annotated = renderer.render_tracks(annotated, tracks, trajectories)
    height, width = frame.shape[:2]
    # El endpoint acepta PNG hasta 2 MiB; una copia reducida conserva el frame real.
    if width > 960:
        annotated = cv2.resize(
            annotated, (960, round(height * 960 / width)), interpolation=cv2.INTER_AREA
        )
    encoded, png = cv2.imencode(".png", annotated)
    if not encoded or png is None:
        raise OSError("No se pudo codificar la evidencia PNG del frame")
    evidence = png.tobytes()
    if len(evidence) > 2 * 1024 * 1024:
        raise OSError("La evidencia PNG supera el límite de 2 MiB del Backend")
    return evidence


def _visible_tracks(
    tracks: tuple[Track, ...], width: int, height: int
) -> tuple[tuple[Track, ...], int, int]:
    """Adapta predicciones de ByteTrack a la región observable del frame."""
    visible = []
    clipped = outside = 0
    for track in tracks:
        box = track.bounding_box
        left, right = min(box.x_min, width), min(box.x_max, width)
        top, bottom = min(box.y_min, height), min(box.y_max, height)
        if left >= right or top >= bottom:
            outside += 1
            continue
        if (left, top, right, bottom) != (box.x_min, box.y_min, box.x_max, box.y_max):
            track = replace(track, bounding_box=BoundingBox(left, top, right, bottom))
            clipped += 1
        visible.append(track)
    return tuple(visible), clipped, outside


def run_video_event_pipeline(
    video_path: Path,
    *,
    detector: Detector,
    tracker: Tracker,
    config: OperationalConfig,
    sink: EventSink,
    context: EventContext,
) -> dict[str, object]:
    """Procesa el video desde cero y publica solo candidatos reales del RuleEngine."""
    if config.view_id != context.view_id:
        raise ValueError("La vista configurada y el contexto de publicación no coinciden")
    visual_config = VisualizationConfig(max_trajectory_points=60, inactive_retention_frames=30)
    renderer = OpenCvRenderer(visual_config)
    trajectories = TrajectoryAccumulator(visual_config)
    engine = RuleEngine(config)
    zones = {zone.zone_id: zone for zone in config.zones}
    frames = detections_count = track_observations = clipped_tracks = outside_tracks = 0
    track_ids: set[int] = set()
    publications: list[dict[str, object]] = []
    started = time.perf_counter()

    with RecordedVideoSource(video_path) as source:
        metadata = source.metadata()
        if metadata.declared_fps is None:
            raise VideoSourceError("El video debe declarar FPS para calcular permanencia")
        analyzer = SpatiotemporalAnalyzer(
            width=metadata.width,
            height=metadata.height,
            fps=metadata.declared_fps,
            zones=config.zones,
        )
        for frame_index, frame in source.frames():
            if frame_index != frames:
                raise VideoSourceError("La lectura de frames no es consecutiva")
            person_detections = tuple(
                detection for detection in detector.detect(frame)
                if detection.class_name == "person"
            )
            detections_count += len(person_detections)
            tracks, clipped, outside = _visible_tracks(
                tracker.update(person_detections), metadata.width, metadata.height
            )
            clipped_tracks += clipped
            outside_tracks += outside
            track_observations += len(tracks)
            track_ids.update(track.track_id for track in tracks)
            spatial = analyzer.update(frame_index, tracks)
            result = engine.evaluate(spatial)
            if result.candidates:
                frame_trajectories = trajectories.update(frame_index, tracks)
                for candidate in result.candidates:
                    evidence = _real_frame_png(
                        frame, frame_index, candidate, tracks, zones[candidate.zone_id],
                        renderer, frame_trajectories,
                    )
                    publication, attempts = publish_with_retries(sink, candidate, context, evidence)
                    obj = next(obj for obj in spatial.objects if obj.track_id == candidate.track_id)
                    publications.append({
                        "candidate": {
                            "frame_index": candidate.frame_index,
                            "video_timestamp_s": candidate.timestamp_s,
                            "track_id": candidate.track_id,
                            "class_name": candidate.class_name,
                            "zone_id": candidate.zone_id,
                            "rule_id": candidate.rule_id,
                            "rule_version": candidate.rule_version,
                            "parameters": dict(candidate.parameters),
                            "observed_dwell_time_s": candidate.observed_dwell_time_s,
                            "normalized_position": asdict(obj.position),
                        },
                        "result": asdict(publication),
                        "publish_attempts": attempts,
                        "source_frame_sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
                        "evidence_png_sha256": hashlib.sha256(evidence).hexdigest(),
                        "evidence_bytes": len(evidence),
                    })
            else:
                trajectories.update(frame_index, tracks)
            frames += 1

    elapsed = time.perf_counter() - started
    return {
        "analysis_run_id": str(context.analysis_run_id),
        "view_id": context.view_id,
        "video_name": video_path.name,
        "width": metadata.width,
        "height": metadata.height,
        "fps_source": metadata.declared_fps,
        "declared_frames": metadata.declared_frame_count,
        "processed_frames": frames,
        "video_duration_s": frames / metadata.declared_fps,
        "processing_seconds": elapsed,
        "effective_fps": frames / elapsed,
        "person_detections": detections_count,
        "track_observations": track_observations,
        "clipped_track_observations": clipped_tracks,
        "offscreen_track_observations": outside_tracks,
        "unique_track_ids": len(track_ids),
        "candidate_count": len(publications),
        "created_event_count": sum(item["result"]["status"] == "published" for item in publications),
        "duplicate_event_count": sum(item["result"]["status"] == "duplicate" for item in publications),
        "published_count": sum(
            item["result"]["status"] in ("published", "duplicate") for item in publications
        ),
        "publications": publications,
    }
