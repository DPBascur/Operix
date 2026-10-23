# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Métricas puras para futura evaluación PERSON con anotación humana completa."""

from __future__ import annotations

from dataclasses import dataclass

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Prediction:
    box: Box
    confidence: float


@dataclass(frozen=True)
class Counts:
    tp: int
    fp: int
    fn: int


def box_iou(left: Box, right: Box) -> float:
    for box in (left, right):
        if box[0] >= box[2] or box[1] >= box[3]:
            raise ValueError("bounding box vacía o invertida")
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    overlap = width * height
    area_l = (left[2] - left[0]) * (left[3] - left[1])
    area_r = (right[2] - right[0]) * (right[3] - right[1])
    return overlap / (area_l + area_r - overlap)


def match_frame(ground_truth: tuple[Box, ...], predictions: tuple[Prediction, ...],
                *, confidence: float, match_iou: float = 0.5) -> Counts:
    """Matching uno-a-uno por confidence; extras sobre el mismo GT cuentan FP."""
    if not 0 <= confidence <= 1 or not 0 < match_iou <= 1:
        raise ValueError("umbral fuera de rango")
    unmatched = set(range(len(ground_truth)))
    tp = fp = 0
    ranked = sorted(enumerate(predictions), key=lambda item: (-item[1].confidence, item[0]))
    for _, prediction in ranked:
        if prediction.confidence < confidence:
            continue
        best = max(unmatched, key=lambda i: (box_iou(prediction.box, ground_truth[i]), -i),
                   default=None)
        if best is not None and box_iou(prediction.box, ground_truth[best]) >= match_iou:
            unmatched.remove(best)
            tp += 1
        else:
            fp += 1
    return Counts(tp=tp, fp=fp, fn=len(unmatched))


def summarize(counts: tuple[Counts, ...]) -> dict[str, float | int | None]:
    tp = sum(item.tp for item in counts)
    fp = sum(item.fp for item in counts)
    fn = sum(item.fn for item in counts)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = None
    if precision is not None and recall is not None:
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision,
            "recall": recall, "f1": f1}


def threshold_grid(ground_truth: dict[str, tuple[Box, ...]],
                   predictions: dict[str, tuple[Prediction, ...]],
                   thresholds: tuple[float, ...], *, match_iou: float = 0.5
                   ) -> dict[float, dict[str, float | int | None]]:
    if ground_truth.keys() != predictions.keys():
        raise ValueError("anotaciones y predicciones deben cubrir las mismas imágenes")
    return {threshold: summarize(tuple(match_frame(ground_truth[key], predictions[key],
                        confidence=threshold, match_iou=match_iou)
                        for key in sorted(ground_truth))) for threshold in thresholds}
