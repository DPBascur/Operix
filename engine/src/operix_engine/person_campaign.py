# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contratos puros de campaña PERSON; las propuestas nunca son ground truth."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class CampaignImage:
    image_id: str
    filename: str
    source: str
    source_group: str
    width: int
    height: int
    sha256: str
    annotation_status: str
    preannotation_source: str
    person_box_count: int
    provenance: str
    negative_verified: bool = False
    frame_index: int | None = None


def plan_tasks(images: list[CampaignImage], *, max_size: int = 60) -> dict[str, list[CampaignImage]]:
    if max_size < 1:
        raise ValueError("tamaño de tarea inválido")
    categories = {
        "PERSON-REVIEW": sorted((r for r in images if r.source == "KEREMBERKE"
                                 and r.annotation_status == "PENDING_HUMAN_REANNOTATION"),
                                key=lambda r: (r.source_group, r.image_id)),
        "PERSON-NEGATIVE-REVIEW": sorted((r for r in images if r.source == "KEREMBERKE"
                                          and r.annotation_status == "PENDING_FULL_FRAME_NEGATIVE_REVIEW"),
                                         key=lambda r: (r.source_group, r.image_id)),
        "TEST3-PERSON-REVIEW": sorted((r for r in images if r.source == "TEST3"),
                                     key=lambda r: r.frame_index if r.frame_index is not None else -1),
    }
    tasks: dict[str, list[CampaignImage]] = {}
    for prefix, rows in categories.items():
        if not rows:
            continue
        if prefix == "TEST3-PERSON-REVIEW":
            tasks[prefix] = rows
            continue
        # Distribución equilibrada; no se parten grupos conocidos de más de una imagen.
        group_rows: dict[str, list[CampaignImage]] = defaultdict(list)
        for row in rows:
            group_rows[row.source_group].append(row)
        buckets: list[list[CampaignImage]] = [[] for _ in range(math.ceil(len(rows) / max_size))]
        for group in sorted(group_rows):
            members = group_rows[group]
            if len(members) > max_size:
                raise ValueError(f"source_group mayor que tarea: {group}")
            possible = [bucket for bucket in buckets if len(bucket) + len(members) <= max_size]
            if not possible:
                raise ValueError("no se pueden balancear grupos en tareas manejables")
            min(possible, key=len).extend(members)
        if any(len(bucket) > max_size for bucket in buckets):
            raise ValueError("tarea demasiado grande")
        for number, bucket in enumerate(buckets, 1):
            tasks[f"{prefix}-{number:02d}"] = bucket
    if len({row.sha256 for row in images}) != len(images):
        raise ValueError("imagen duplicada por SHA-256 en la campaña")
    return tasks


def plan_split(rows: list[dict], *, seed: int, minimum_positive_groups: int = 3,
               minimum_negative_groups: int = 3,
               required_tags: tuple[str, ...] = ()) -> dict[str, str]:
    """Plan por grupo, nunca por frame; solo material humano completo y elegible."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["annotation_status"] not in {"HUMAN_VERIFIED", "VERIFIED_NEGATIVE"}:
            continue
        if row.get("source") == "TEST3" or row.get("split_eligibility") != "ELIGIBLE":
            continue
        groups[row["source_group"]].append(row)
    strong_groups = {g for g, members in groups.items() if all(
        m.get("provenance") == "STRONG" and m.get("source_group_confidence") == "STRONG"
        for m in members)}
    positive = [g for g in strong_groups if any(int(m["person_box_count"]) > 0 for m in groups[g])]
    negative = [g for g in strong_groups if any(m["annotation_status"] == "VERIFIED_NEGATIVE"
                                                for m in groups[g])]
    if len(positive) < minimum_positive_groups or len(negative) < minimum_negative_groups:
        raise ValueError("grupos positivos/negativos elegibles con procedencia fuerte insuficientes para tres splits")
    def order(group: str) -> str:
        return hashlib.sha256(f"{seed}:{group}".encode()).hexdigest()
    positive.sort(key=order)
    negative.sort(key=order)
    split: dict[str, str] = {}
    for kind in (positive, negative):
        for group, value in zip(kind, ("LOCKED_EVALUATION", "CALIBRATION", "TRAIN")):
            if group not in split:
                split[group] = value
    for group in sorted(groups, key=order):
        split.setdefault(group, "TRAIN")
    for value in ("TRAIN", "CALIBRATION", "LOCKED_EVALUATION"):
        members = [m for g, records in groups.items() if split[g] == value for m in records]
        if not any(int(m["person_box_count"]) > 0 for m in members) or not any(
                m["annotation_status"] == "VERIFIED_NEGATIVE" for m in members):
            raise ValueError("no es posible cubrir positivos y negativos en los tres splits")
        for tag in required_tags:
            if not any(tag in m.get("difficulty_tags", "").split("|") for m in members):
                raise ValueError(f"diversidad insuficiente para {tag} en {value}")
    return split


def readiness(rows: list[dict], tasks: dict[str, dict], issues: list[dict],
              evaluation_frozen: bool, *, minimum_negative_images: int = 30,
              minimum_independent_groups: int = 3,
              split: dict[str, str] | None = None) -> dict:
    """Gate conservador; los mínimos son parámetros, no garantía de representatividad."""
    if minimum_negative_images < 1 or minimum_independent_groups < 3:
        raise ValueError("readiness exige al menos un negativo y tres grupos independientes")
    counts = Counter(row["annotation_status"] for row in rows)
    positives = [r for r in rows if r["annotation_status"] == "HUMAN_VERIFIED"
                 and int(r["person_box_count"]) > 0]
    negatives = [r for r in rows if r["annotation_status"] in {
        "VERIFIED_NEGATIVE", "VALID_FULL_FRAME_NEGATIVE"}]
    def strong_eligible(row: dict) -> bool:
        return (row.get("provenance") == "STRONG"
                and row.get("source_group_confidence") == "STRONG"
                and row.get("split_eligibility") == "ELIGIBLE"
                and row.get("source") != "TEST3")
    groups = {r["source_group"] for r in positives if strong_eligible(r)}
    negative_groups = {r["source_group"] for r in negatives if strong_eligible(r)}
    blockers = []
    if not positives:
        blockers.append("NO_HUMAN_VERIFIED_POSITIVES")
    if len(negatives) < minimum_negative_images:
        blockers.append("INSUFFICIENT_VERIFIED_NEGATIVES")
    if len(groups) < minimum_independent_groups:
        blockers.append("INSUFFICIENT_STRONG_POSITIVE_SOURCE_GROUPS")
    if len(negative_groups) < minimum_independent_groups:
        blockers.append("INSUFFICIENT_STRONG_NEGATIVE_SOURCE_GROUPS")
    if any(row["annotation_status"] in {"UNANNOTATED", "PENDING_HUMAN_REANNOTATION",
                                         "PENDING_FULL_FRAME_NEGATIVE_REVIEW", "REVIEW_AMBIGUOUS"}
           for row in rows):
        blockers.append("ANNOTATION_REVIEW_PENDING")
    if any(issue.get("severity") == "BLOCKER" for issue in issues):
        blockers.append("QA_BLOCKERS")
    if not tasks or not all(task.get("completed", False) for task in tasks.values()):
        blockers.append("TASKS_INCOMPLETE")
    if not evaluation_frozen:
        blockers.append("EVALUATION_NOT_FROZEN")
    if not split or set(split.values()) != {"TRAIN", "CALIBRATION", "LOCKED_EVALUATION"}:
        blockers.append("SPLIT_NOT_READY")
    warnings = []
    if any(r.get("provenance") != "STRONG" for r in positives):
        warnings.append("WEAK_OR_PARTIAL_PROVENANCE_PRESENT")
    if any(r.get("source") == "TEST3" for r in positives):
        warnings.append("TEST3_IS_DEVELOPMENT_ONLY")
    if not any("HEAVY_OCCLUSION" in r.get("difficulty_tags", "").split("|") for r in positives):
        warnings.append("HEAVY_OCCLUSION_COVERAGE_NOT_DOCUMENTED")
    if not any("FORKLIFT_OPERATOR" in r.get("difficulty_tags", "").split("|") for r in positives):
        warnings.append("FORKLIFT_OPERATOR_COVERAGE_NOT_DOCUMENTED")
    if not blockers:
        decision = "PERSON_V2_READY_TO_TRAIN"
    elif any(code in blockers for code in ("ANNOTATION_REVIEW_PENDING", "TASKS_INCOMPLETE",
                                          "NO_HUMAN_VERIFIED_POSITIVES")):
        decision = "PERSON_V2_BLOCKED_BY_ANNOTATION"
    elif "QA_BLOCKERS" in blockers:
        decision = "PERSON_V2_BLOCKED_BY_DATA_QUALITY"
    elif any(code in blockers for code in ("INSUFFICIENT_STRONG_POSITIVE_SOURCE_GROUPS",
                                          "INSUFFICIENT_STRONG_NEGATIVE_SOURCE_GROUPS")):
        decision = "PERSON_V2_BLOCKED_BY_PROVENANCE"
    elif "INSUFFICIENT_VERIFIED_NEGATIVES" in blockers:
        decision = "PERSON_V2_BLOCKED_BY_DATA_DIVERSITY"
    else:
        decision = "PERSON_V2_BLOCKED_BY_SPLIT"
    return {
        "decision": decision,
        "criteria": {"minimum_negative_images": minimum_negative_images,
                     "minimum_independent_strong_positive_groups": minimum_independent_groups,
                     "requires_all_tasks_complete": True, "requires_frozen_evaluation": True},
        "counts": dict(sorted(counts.items())), "verified_positive_images": len(positives),
        "verified_negative_images": len(negatives), "strong_positive_groups": len(groups),
        "strong_negative_groups": len(negative_groups),
        "blockers": blockers, "warnings": warnings,
    }


def freeze_payload(rows: list[dict], split: dict[str, str]) -> dict:
    selected = [r for r in rows if split.get(r["source_group"]) == "LOCKED_EVALUATION"]
    if not selected or any(r["annotation_status"] not in {"HUMAN_VERIFIED", "VERIFIED_NEGATIVE"}
                           or r.get("provenance") != "STRONG"
                           or r.get("source_group_confidence") != "STRONG"
                           or r.get("split_eligibility") != "ELIGIBLE"
                           or r.get("source") == "TEST3" or not r.get("label_sha256")
                           for r in selected):
        raise ValueError("evaluation requiere imágenes humanas elegibles, independientes y hashes de labels")
    if not any(int(r["person_box_count"]) > 0 for r in selected) or not any(
            r["annotation_status"] == "VERIFIED_NEGATIVE" for r in selected):
        raise ValueError("evaluation requiere positivos y negativos")
    payload = {"split": "LOCKED_EVALUATION", "source_groups": sorted({r["source_group"] for r in selected}),
               "images": [{k: str(r[k]) for k in ("image_id", "source_group", "image_sha256",
                                                   "label_sha256", "annotation_status", "person_box_count")}
                          for r in sorted(selected, key=lambda x: x["image_id"])]}
    payload["manifest_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest().upper()
    return payload
