# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Auditoría y selección provisional de anotaciones NVIDIA, sin entrenamiento."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

REVISION = "d5b88d3abcf659f304a107f4336b71b4e2159133"
HOLDOUT_RUNS = frozenset({
    "00023b5323028ab83e67_run_6_seed_1486583949",  # A
    "001e53453441935632ae_run_1_seed_1288693302",  # B
    "008caa590c5e5b7b4bca_run_8_seed_4731920",  # C
})
HOLDOUT_SEEDS = frozenset({"1486583949", "1288693302", "4731920"})
CLASS_IDS = {"person": 0, "forklift": 1}
BOX_KEY = "bounding_box_2d_tight_fast"


def read_catalog(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    required = {"run_id", "seed", "scenario", "camera", "annotation_path", "width", "height"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Catálogo vacío o faltan columnas: {sorted(required)}")
    for row in rows:
        if not row["run_id"] or not row["scenario"] or not row["camera"]:
            raise ValueError("run_id, scenario y camera son obligatorios")
        if row["seed"]:
            try:
                seed = Decimal(row["seed"])
            except InvalidOperation as error:
                raise ValueError("Seed inválida") from error
            if not seed.is_finite() or seed != seed.to_integral_value():
                raise ValueError("Seed inválida")
            row["seed"] = str(int(seed))
        row["width"], row["height"] = int(row["width"]), int(row["height"])
        if row["width"] <= 0 or row["height"] <= 0:
            raise ValueError("Resolución inválida")
        row["annotation_path"] = str((path.parent / row["annotation_path"]).resolve())
        if row.get("annotation_sha256"):
            with Path(row["annotation_path"]).open("rb") as annotation:
                actual = hashlib.file_digest(annotation, "sha256").hexdigest()
            if actual.lower() != row["annotation_sha256"].lower():
                raise ValueError(f"SHA-256 de anotación no coincide: {row['run_id']} / {row['camera']}")
        if row.get("video_path"):
            row["video_path"] = str((path.parent / row["video_path"]).resolve())
    if len({(r["run_id"], r["camera"]) for r in rows}) != len(rows):
        raise ValueError("El catálogo repite una combinación run/cámara")
    return rows


def metadata(entity: dict, prim_path: str) -> dict:
    agent = entity.get("metro_agent_data") or {}
    return {
        "label_class": (entity.get("label") or {}).get("class") or "",
        "group": agent.get("agent_group") or "",
        "name": agent.get("agent_name") or "",
        "agent_type": agent.get("agent_type") or "",
        "task_name": agent.get("current_task_name") or "",
        "prim_path": agent.get("prim_path") or prim_path,
        "asset_url": agent.get("asset_url") or (entity.get("annotators") or {}).get("asset_url") or "",
    }


def candidate_class(meta: dict) -> str | None:
    """Mapeo *candidato*: requiere inspección visual antes de uso formativo."""
    if (meta["label_class"] == "character" and meta["group"] == "Worker"
            and meta["agent_type"] == "IRACharacterAPI"
            and meta["name"].startswith("Worker_")):
        return "person"
    if (meta["label_class"] == "robot"
            and meta["group"] in {"forklift", "forklift_group"}
            and "forklift" in meta["name"].lower()
            and meta["asset_url"].lower().endswith("forklift.usd")):
        return "forklift"
    return None


def yolo_box(box: dict, width: int, height: int) -> tuple[float, float, float, float] | None:
    try:
        raw = [float(box[key]) for key in ("x_min", "y_min", "x_max", "y_max")]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in raw):
        return None
    x1, y1, x2, y2 = raw
    if x2 <= x1 or y2 <= y1:
        return None
    x1, x2 = max(0.0, x1), min(float(width), x2)
    y1, y2 = max(0.0, y1), min(float(height), y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return ((x1 + x2) / (2 * width), (y1 + y2) / (2 * height),
            (x2 - x1) / width, (y2 - y1) / height)


def iter_frames(row: dict):
    with Path(row["annotation_path"]).open(encoding="utf-8") as source:
        for index, line in enumerate(source):
            if not line.strip():
                raise ValueError(f"Línea vacía en {row['run_id']}:{row['camera']}:{index}")
            frame = json.loads(line)
            if not isinstance(frame, dict):
                raise ValueError("Cada línea JSONL debe ser un objeto")
            yield index, frame


def observations(row: dict, frame: dict) -> list[dict]:
    result = []
    for source in ("agents", "objects"):
        for prim_path, entity in (frame.get(source) or {}).items():
            meta = metadata(entity, prim_path)
            box = (entity.get("annotators") or {}).get(BOX_KEY) or {}
            normalized = yolo_box(box, row["width"], row["height"])
            result.append({**meta, "source_kind": source, "target_candidate": candidate_class(meta),
                           "bbox": normalized, "raw_bbox": {key: box.get(key) for key in
                           ("x_min", "y_min", "x_max", "y_max")}})
    return result


def audit(rows: list[dict]) -> dict:
    combinations = defaultdict(lambda: {"annotations": 0, "valid_boxes": 0, "frames": set(), "runs": set(),
                                      "cameras": set(), "instances": set()})
    scenarios = defaultdict(lambda: Counter())
    scenario_instances = defaultdict(lambda: {label: set() for label in CLASS_IDS})
    instances = defaultdict(lambda: Counter())
    by_camera = []
    for row in rows:
        stats = Counter()
        unique = {"person": set(), "forklift": set()}
        for frame_index, frame in iter_frames(row):
            stats["frames"] += 1
            present = set()
            for item in observations(row, frame):
                key = (item["source_kind"], item["label_class"], item["group"],
                       item["name"], item["agent_type"], item["task_name"],
                       item["asset_url"].rsplit("/", 1)[-1],
                       item["target_candidate"] or "excluded")
                entry = combinations[key]
                entry["annotations"] += 1
                entry["valid_boxes"] += item["bbox"] is not None
                entry["frames"].add((row["run_id"], row["camera"], frame_index))
                entry["runs"].add(row["run_id"])
                entry["cameras"].add((row["run_id"], row["camera"]))
                entry["instances"].add((row["run_id"], item["prim_path"]))
                instance_key = (row["scenario"], row["run_id"], row["camera"], item["prim_path"],
                                item["label_class"], item["group"], item["name"],
                                item["target_candidate"] or "excluded")
                instances[instance_key]["frames_present"] += 1
                instances[instance_key]["frames_with_valid_box"] += item["bbox"] is not None
                label = item["target_candidate"]
                if label and item["bbox"] is not None:
                    stats[f"{label}_boxes"] += 1
                    unique[label].add(item["prim_path"])
                    scenario_instances[row["scenario"]][label].add((row["run_id"], item["prim_path"]))
                    present.add(label)
                    area = item["bbox"][2] * item["bbox"][3]
                    stats[f"{label}_area_{'small' if area < .01 else 'medium' if area < .10 else 'large'}"] += 1
                elif label:
                    stats[f"{label}_invalid_boxes"] += 1
            for label in present:
                stats[f"frames_with_{label}"] += 1
            if len(present) == 2:
                stats["frames_with_both"] += 1
        for label in CLASS_IDS:
            stats[f"unique_{label}_instances"] = len(unique[label])
        public_row = {key: row[key] for key in ("run_id", "seed", "scenario", "camera")}
        public_row["annotation_sha256"] = row.get("annotation_sha256") or None
        public_row["source_shard"] = row.get("source_shard") or None
        by_camera.append({**public_row, **stats})
        scenarios[row["scenario"]].update(stats)
        scenarios[row["scenario"]]["cameras"] += 1
    combo_rows = []
    for key, entry in sorted(combinations.items()):
        combo_rows.append(dict(zip(("source_kind", "label_class", "group", "name", "agent_type", "task_name",
                                    "asset_name", "target_candidate"), key)) |
                          {"annotations": entry["annotations"], "valid_boxes": entry["valid_boxes"],
                           "frames": len(entry["frames"]),
                           "runs": len(entry["runs"]), "cameras": len(entry["cameras"]),
                           "unique_prim_paths": len(entry["instances"])})
    scenario_rows = []
    for scenario, counts in sorted(scenarios.items()):
        counts = counts.copy()
        for label in CLASS_IDS:
            counts[f"unique_{label}_instances"] = len(scenario_instances[scenario][label])
        scenario_rows.append({"scenario": scenario, "runs": len({r["run_id"] for r in rows if r["scenario"] == scenario}),
                              **counts})
    instance_rows = [dict(zip(("scenario", "run_id", "camera", "prim_path", "label_class", "group",
                               "name", "target_candidate"), key)) |
                     {"frames_present": counts["frames_present"],
                      "frames_with_valid_box": counts["frames_with_valid_box"]}
                     for key, counts in sorted(instances.items())]
    return {"dataset_revision": REVISION, "box_variant": BOX_KEY, "mapping_status": "candidate_unreviewed",
            "catalog_cameras": len(rows), "combinations": combo_rows,
            "scenarios": scenario_rows, "by_camera": by_camera, "instances": instance_rows}


def split_runs(rows: list[dict], salt: str = "operix-nvidia-pilot-v1",
               exploration_runs: frozenset[str] = frozenset()) -> dict[str, str]:
    """Reserva por seed global; un run y sus cámaras nunca cruzan splits."""
    seeds = {}
    exploration_seeds = {row["seed"] for row in rows if row["run_id"] in exploration_runs}
    for row in rows:
        if (row["run_id"] in HOLDOUT_RUNS or row["seed"] in HOLDOUT_SEEDS
                or row["seed"] in exploration_seeds):
            continue
        if not row["seed"]:
            raise ValueError("Sin seed: no asignar a train/val/test automáticamente")
        key = row["seed"]
        digest = hashlib.sha256(f"{salt}:{key}".encode()).digest()
        fraction = int.from_bytes(digest[:8], "big") / 2**64
        seeds[key] = "train" if fraction < .70 else "validation" if fraction < .85 else "test"
    return {row["run_id"]: ("known_regression" if row["run_id"] in HOLDOUT_RUNS
                             or row["seed"] in HOLDOUT_SEEDS else
                             "exploration_seen" if row["seed"] in exploration_seeds else seeds[row["seed"]])
            for row in rows}


def select_frames(frames: list[dict], limit: int) -> list[dict]:
    """Una muestra por tramo temporal, priorizando ambas clases y cambio espacial."""
    if limit < 1:
        raise ValueError("limit debe ser positivo")
    if len(frames) <= limit:
        return frames
    chosen = []
    for bucket in range(limit):
        start = bucket * len(frames) // limit
        end = (bucket + 1) * len(frames) // limit
        options = frames[start:end]
        previous = chosen[-1] if chosen else None

        def score(item):
            labels = {box["target_class"] for box in item["boxes"]}
            novelty = len(labels) * 2 + (4 if len(labels) == 2 else 0)
            if previous and item["boxes"] and previous["boxes"]:
                prior_by_id = {box["prim_path"]: box for box in previous["boxes"]}
                for box in item["boxes"]:
                    prior = prior_by_id.get(box["prim_path"])
                    if prior:
                        novelty += sum(abs(now - old) for now, old in zip(box["bbox"], prior["bbox"]))
                        novelty += 2 if box["task_name"] and box["task_name"] != prior["task_name"] else 0
                    else:
                        novelty += 1
            return novelty, -item["frame"]

        chosen.append(max(options, key=score))
    return chosen


def build_manifest(rows: list[dict], max_frames_per_camera: int = 12,
                   exploration_runs: frozenset[str] = frozenset(),
                   reserved_splits: dict[str, str] | None = None) -> dict:
    splits = reserved_splits if reserved_splits is not None else split_runs(rows, exploration_runs=exploration_runs)
    missing = {row["run_id"] for row in rows} - splits.keys()
    if missing:
        raise ValueError(f"Runs sin split reservado: {sorted(missing)}")
    if reserved_splits is not None and any(splits[row["run_id"]] == "test" for row in rows):
        raise ValueError("No leer anotaciones del test reservado durante la selección del piloto")
    entries = []
    for row in sorted(rows, key=lambda value: (value["scenario"], value["run_id"], value["camera"])):
        frames = []
        for frame_index, frame in iter_frames(row):
            boxes = [{"target_class": item["target_candidate"],
                      "class_id": CLASS_IDS[item["target_candidate"]],
                      "bbox": item["bbox"], "prim_path": item["prim_path"],
                      "task_name": item["task_name"]}
                     for item in observations(row, frame)
                     if item["target_candidate"] and item["bbox"] is not None]
            frames.append({"frame": frame_index, "boxes": boxes})
        for selected in select_frames(frames, max_frames_per_camera):
            entries.append({"run_id": row["run_id"], "seed": row["seed"],
                            "scenario": row["scenario"], "camera": row["camera"],
                            "frame": selected["frame"], "source_annotation": row["annotation_path"],
                            "source_shard": row.get("source_shard") or None,
                            "annotation_sha256": row.get("annotation_sha256") or None,
                            "video_path": row.get("video_path") or None,
                            "width": row["width"], "height": row["height"],
                            "split": splits[row["run_id"]],
                            "selection_reason": "temporal_bin_class_task_and_bbox_change",
                            "boxes": selected["boxes"]})
    return {"dataset_revision": REVISION, "box_variant": BOX_KEY,
            "status": "candidate_not_training_ready_visual_mapping_review_required",
            "entries": entries}
