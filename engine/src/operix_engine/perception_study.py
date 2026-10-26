# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Validaciones y agregación de selección de desarrollo; no configura producción."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import statistics

from operix_engine.person_metrics import Prediction, match_frame, summarize

PROTECTED = ("person_final_holdout", "person-independent-holdout", "test2", "real_holdout")


def validate_manifest(manifest: dict) -> dict:
    if manifest.get("study_id") != "PERSON_MODEL_SELECTION_DEVELOPMENT" or manifest.get("label") != "DEVELOPMENT_SELECTION_METRICS":
        raise ValueError("Identidad de campaña de desarrollo requerida")
    config = manifest["configuration"]
    if tuple(config.get(key) for key in ("imgsz","confidence","nms_iou","batch","device","match_iou")) != (640,.1,.7,1,"cuda:0",.5):
        raise ValueError("No se permite tuning en esta comparación")
    for key in ("warmup","repetitions","pipeline_warmup_frames","pipeline_repetitions"):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise ValueError("Warm-up y repeticiones deben ser enteros positivos")
    for key in ("samples","models"):
        ids = [row["id"] for row in manifest[key]]
        if not ids or len(ids)!=len(set(ids)):
            raise ValueError("Identidades vacías o duplicadas en el manifiesto")
    return config


def development_path(path: str | Path) -> Path:
    """Frontera previa a lectura o creación, incluso para manifiesto y salida."""
    source = Path(path).expanduser()
    for candidate in (str(source), str(source.resolve())):
        if any(token in candidate.lower() for token in PROTECTED):
            raise ValueError("El estudio no admite material de evaluación reservado")
    return source


def checked_input(path: str, expected_sha256: str) -> Path:
    """Rechaza rutas protegidas antes de abrirlas; verifica identidad local."""
    source = development_path(path)
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256.lower()):
        raise ValueError("SHA-256 inválido")
    if hashlib.sha256(source.read_bytes()).hexdigest() != expected_sha256.lower():
        raise ValueError("El archivo no coincide con el manifiesto fijado")
    return source


def class_id(names: dict[int, str], name: str) -> int:
    matches = [key for key, value in names.items() if value == name]
    if len(matches) != 1:
        raise ValueError(f"Clase ausente o ambigua: {name}")
    return matches[0]


def metrics(samples: list[dict], predictions: dict[str, tuple[Prediction, ...]]) -> dict:
    ids = [row["id"] for row in samples]
    if len(ids) != len(set(ids)) or set(ids) != set(predictions):
        raise ValueError("GT y predicciones deben cubrir exactamente las mismas imágenes")
    return summarize(tuple(match_frame(tuple(tuple(box) for box in row["ground_truth"]),
                                      predictions[row["id"]], confidence=.10, match_iou=.50)
                           for row in samples))


def timing_summary(seconds: list[float]) -> dict:
    if not seconds or any(not math.isfinite(t) or t <= 0 for t in seconds):
        raise ValueError("Tiempos positivos y finitos requeridos")
    ordered = sorted(seconds)
    position = .95 * (len(ordered) - 1)
    lower = int(position)
    p95 = ordered[lower] + (position-lower) * (ordered[min(lower+1,len(ordered)-1)]-ordered[lower])
    return {"samples": len(seconds), "total_s": sum(seconds), "fps": len(seconds)/sum(seconds),
            "mean_ms": statistics.mean(seconds)*1000, "median_ms": statistics.median(seconds)*1000,
            "p95_ms": p95*1000, "min_ms": ordered[0]*1000, "max_ms": ordered[-1]*1000,
            "stdev_ms": statistics.stdev(seconds)*1000 if len(seconds)>1 else 0.}


def track_summary(observations: dict[int, list[int]]) -> dict:
    gaps = [right-left-1 for frames in observations.values() for left,right in zip(frames,frames[1:]) if right>left+1]
    return {"ids": len(observations), "observations": sum(map(len,observations.values())),
            "internal_gap_episodes": len(gaps), "missing_track_frames": sum(gaps),
            "short_tracks_le_3_observations": sum(len(frames)<=3 for frames in observations.values())}
