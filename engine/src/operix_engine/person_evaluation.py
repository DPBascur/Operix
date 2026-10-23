# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Selección reproducible de imágenes para anotación PERSON, sin generar etiquetas."""

from __future__ import annotations

import json
from pathlib import Path


def read_person_observations(path: Path) -> dict[int, tuple[dict, ...]]:
    """Lee únicamente las detecciones PERSON de un JSONL diagnóstico existente."""
    observations: dict[int, tuple[dict, ...]] = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            index = int(row["frame_index"])
            if index in observations:
                raise ValueError(f"frame duplicado: {index}")
            observations[index] = tuple(row["detections"]["person"])
    if list(observations) != list(range(len(observations))):
        raise ValueError("los índices de frame deben ser consecutivos desde cero")
    return observations


def select_annotation_frames(
    current: dict[int, tuple[dict, ...]],
    generic: dict[int, tuple[dict, ...]],
    *,
    total: int = 48,
    occlusion_review: tuple[int, ...] = (0, 100, 400, 800, 1000, 1050, 1400),
) -> dict[int, tuple[str, ...]]:
    """Combina muestreo uniforme con señales de modelos, sin usarlas como etiquetas."""
    if current.keys() != generic.keys() or not current:
        raise ValueError("ambos JSONL deben cubrir los mismos frames")
    count = len(current)
    if total < 2 or total > count:
        raise ValueError("total fuera de rango")
    chosen: dict[int, set[str]] = {}

    def add(index: int, reason: str) -> None:
        chosen.setdefault(index, set()).add(reason)

    uniform_count = min(32, total)
    for step in range(uniform_count):
        add(round(step * (count - 1) / (uniform_count - 1)), "TEMPORAL_UNIFORM")

    for index in occlusion_review:
        if 0 <= index < count and (index in chosen or len(chosen) < total):
            add(index, "VISUAL_OCCLUSION_REVIEW")

    categories = (
        ("GENERIC_ONLY", lambda i: not current[i] and bool(generic[i])),
        ("BOX_DIVERGENCE", lambda i: abs(len(current[i]) - len(generic[i])) >= 2),
        ("CURRENT_POSITIVE", lambda i: bool(current[i])),
        ("BOTH_EMPTY_AMBIGUOUS", lambda i: not current[i] and not generic[i]),
    )
    while len(chosen) < total:
        before = len(chosen)
        for reason, predicate in categories:
            candidates = (i for i in current if i not in chosen and predicate(i))
            index = max(
                candidates,
                key=lambda i: (min(abs(i - j) for j in chosen), -i),
                default=None,
            )
            if index is not None:
                add(index, reason)
            if len(chosen) == total:
                break
        if len(chosen) == before:
            raise ValueError("no se pudo completar la muestra")

    return {index: tuple(sorted(chosen[index])) for index in sorted(chosen)}
