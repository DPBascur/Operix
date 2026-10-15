# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Audita anotaciones NVIDIA y prepara un manifest candidato local, sin entrenar."""

from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from operix_engine.nvidia_dataset import (
    CLASS_IDS, HOLDOUT_RUNS, REVISION, audit, build_manifest, iter_frames, observations,
    read_catalog, select_frames, split_runs,
)

BASE_URL = ("https://huggingface.co/datasets/nvidia/"
            "PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes/resolve/")
REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_SHARDS = {
    "nearmiss": ("forklift_human_nearmiss", "nearmiss"),
    "forklift_collision": ("forklift_shelf_collision", "forklift_collision"),
    "box_pickup": ("warehouse_box_pickup", "box_pickup"),
    "fire": ("warehouse_fire", "fire"),
}
RUN_PATTERN = re.compile(r"[0-9a-f]{20}_run_\d+_seed_\d+")
_RATE_LOCK = threading.Lock()
_NEXT_REQUEST_AT = 0.0
PILOT_QUOTAS = {
    "train": {"nearmiss": 21, "forklift_collision": 14, "box_pickup": 14, "fire": 7},
    "validation": {"nearmiss": 5, "forklift_collision": 3, "box_pickup": 3, "fire": 1},
    "test": {"nearmiss": 4, "forklift_collision": 3, "box_pickup": 3, "fire": 2},
}
PILOT_CAMERAS = {
    "nearmiss": ("ceiling_00", "eye_00"),
    "forklift_collision": ("cam_00", "cam_03"),
    "box_pickup": ("cam_00", "cam_05"),
    "fire": ("ceiling_00", "ceiling_04"),
}


def local_output(path: Path) -> Path:
    result = path.resolve()
    if result == REPO_ROOT or REPO_ROOT in result.parents:
        raise ValueError("Salidas de auditoría, manifest e imágenes deben quedar fuera del repositorio")
    return result


def read_range(url: str, offset: int, size: int) -> bytes:
    global _NEXT_REQUEST_AT
    for attempt in range(8):
        try:
            with _RATE_LOCK:
                now = time.monotonic()
                delay = max(0.0, _NEXT_REQUEST_AT - now)
                _NEXT_REQUEST_AT = max(now, _NEXT_REQUEST_AT) + .8
            if delay:
                time.sleep(delay)
            request = Request(url, headers={"Range": f"bytes={offset}-{offset + size - 1}"})
            with urlopen(request, timeout=60) as response:
                content_range = response.headers.get("Content-Range", "")
                if response.status != 206 or not content_range.startswith(f"bytes {offset}-"):
                    raise RuntimeError("Servidor sin soporte HTTP Range: se cancela antes de bajar un shard")
                data = response.read(size)
            if len(data) != size:
                raise URLError("Respuesta parcial incompleta")
            return data
        except (HTTPError, URLError, TimeoutError) as error:
            if isinstance(error, HTTPError) and error.code == 429:
                try:
                    retry_after = max(30, min(120, int(error.headers.get("Retry-After", "30"))))
                except ValueError:
                    retry_after = 30
                with _RATE_LOCK:
                    _NEXT_REQUEST_AT = max(_NEXT_REQUEST_AT, time.monotonic() + retry_after)
            if attempt == 7:
                raise
            time.sleep(min(30, 2 ** attempt))
    raise AssertionError("Reintento HTTP inalcanzable")


def index_artifact_shards(output: Path, count: int) -> None:
    """Indexa solo el primer header de cada shard; nunca descarga un TAR completo."""
    if count < 2:
        raise ValueError("count debe incluir un shard de cierre")
    output = local_output(output)

    def first_run(task: tuple[str, int]) -> dict:
        scenario, number = task
        directory, stem = ARTIFACT_SHARDS[scenario]
        shard = f"artifacts/{directory}/{stem}-artifacts-{number:05d}.tar"
        header = read_range(BASE_URL + REVISION + "/" + shard, 0, 512)
        name = header[:100].split(b"\0", 1)[0].decode("utf-8")
        match = RUN_PATTERN.search(name)
        if match is None:
            raise ValueError(f"Shard sin run identificable: {shard}")
        return {"scenario": scenario, "number": number, "shard": shard,
                "first_run": match.group()}

    tasks = [(scenario, number) for scenario in ARTIFACT_SHARDS for number in range(count)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(first_run, tasks))
    rows.sort(key=lambda row: (row["scenario"], row["number"]))
    for scenario in ARTIFACT_SHARDS:
        starts = [row["first_run"] for row in rows if row["scenario"] == scenario]
        if starts != sorted(starts):
            raise ValueError(f"Shards de {scenario} no están ordenados por run")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=["scenario", "number", "shard", "first_run"])
        writer.writeheader()
        writer.writerows(rows)


def plan_pilot(runs_index: Path, registry_path: Path, shards_index: Path,
               output: Path) -> None:
    """Elige solo por metadata; nunca abre imágenes ni anotaciones del test."""
    registry = load_registry(registry_path)
    if registry is None:
        raise ValueError("Falta registro de splits")
    with runs_index.open(newline="", encoding="utf-8-sig") as source:
        runs = list(csv.DictReader(source))
    with shards_index.open(newline="", encoding="utf-8-sig") as source:
        shard_rows = list(csv.DictReader(source))
    shards_by_scenario = {}
    for scenario in ARTIFACT_SHARDS:
        scenario_shards = sorted((row for row in shard_rows if row["scenario"] == scenario),
                                 key=lambda row: int(row["number"]))
        if not scenario_shards:
            raise ValueError(f"Sin shards para {scenario}")
        shards_by_scenario[scenario] = scenario_shards
    candidates = {}
    for scenario in ARTIFACT_SHARDS:
        scenario_shards = shards_by_scenario[scenario]
        starts = [row["first_run"] for row in scenario_shards]
        for run in runs:
            if run["scenario"] != scenario or run["source_kind"] != "multi_camera_run":
                continue
            split = registry.get(run["run_id"])
            if split not in PILOT_QUOTAS:
                continue
            position = bisect.bisect_right(starts, run["run_id"]) - 1
            if position < 0 or position == len(starts) - 1:
                continue
            candidates.setdefault((split, scenario), []).append({
                "run_id": run["run_id"], "seed": run["seed"],
                "scenario": scenario, "split": split,
                "source_shard": scenario_shards[position]["shard"],
                "cameras": list(PILOT_CAMERAS[scenario]),
            })
    selected = []
    used_seeds = set()
    for split, quotas in PILOT_QUOTAS.items():
        for scenario, needed in quotas.items():
            options = sorted(candidates.get((split, scenario), []), key=lambda x: x["run_id"])
            if len(options) < needed:
                raise ValueError(f"Pool insuficiente {split}/{scenario}: {len(options)} < {needed}")
            # Espacia los runs en el rango de shards sin depender de etiquetas.
            for rank in range(needed):
                anchor = round((rank + .5) * len(options) / needed - .5)
                order = sorted(range(len(options)), key=lambda i: (abs(i - anchor), i))
                chosen = next((options[i] for i in order if options[i]["seed"] not in used_seeds), None)
                if chosen is None:
                    raise ValueError(f"Seeds independientes insuficientes: {split}/{scenario}")
                selected.append(chosen)
                used_seeds.add(chosen["seed"])
    if len(selected) != 80 or len({row["run_id"] for row in selected}) != 80:
        raise ValueError("El piloto no tiene 80 runs independientes")
    output = local_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"dataset_revision": REVISION,
                                  "selection_basis": "runs_metadata_and_frozen_split_registry_only",
                                  "test_uninspected": True, "runs": selected},
                                 indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def choose_cameras(preferred: list[str], available: set[str]) -> list[str]:
    """Elige hasta dos vistas con par RGB/JSONL, sin abrir etiquetas ni imágenes."""
    return ([camera for camera in preferred if camera in available]
            + sorted(available - set(preferred)))[:2]


def fetch_pilot(plan_path: Path, output_dir: Path, workers: int = 8,
                splits: tuple[str, ...] = ("train", "validation", "test")) -> None:
    """Obtiene solo MP4 RGB y JSONL de cámaras seleccionadas por HTTP Range."""
    if not 1 <= workers <= 12:
        raise ValueError("workers fuera de 1..12")
    output_dir = local_output(output_dir)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("dataset_revision") != REVISION or len(plan.get("runs", [])) != 80:
        raise ValueError("Plan piloto incorrecto")
    if not splits or set(splits) - {"train", "validation", "test"}:
        raise ValueError("Splits de descarga inválidos")
    selected_runs = [run for run in plan["runs"] if run["split"] in splits]
    by_shard = {}
    for run in selected_runs:
        by_shard.setdefault(run["source_shard"], []).append(run)
    raw_dir = output_dir / "raw"
    index_dir = output_dir / "indexes"
    raw_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    def process(shard: str, runs: list[dict]) -> list[dict]:
        url = BASE_URL + REVISION + "/" + shard
        desired = {(run["run_id"], camera, suffix)
                   for run in runs for camera in run["cameras"]
                   for suffix in ("rgb.mp4", "object_detection.jsonl")}
        found = {}
        available = {}
        run_ids = {run["run_id"] for run in runs}
        max_run = max(run["run_id"] for run in runs)
        index_path = index_dir / (shard.replace("/", "__") + ".jsonl")

        # Una reanudación no vuelve a recorrer un shard cuyos pares MP4/JSONL
        # ya están completos y alineados. Los archivos parciales sí se releen.
        import cv2
        for run in runs:
            for camera in run["cameras"]:
                stem = f"{run['run_id']}.{camera}"
                video_path = raw_dir / f"{stem}.rgb.mp4"
                annotation_path = raw_dir / f"{stem}.object_detection.jsonl"
                if not video_path.is_file() or not annotation_path.is_file():
                    continue
                capture = cv2.VideoCapture(str(video_path))
                try:
                    video_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) if capture.isOpened() else 0
                finally:
                    capture.release()
                try:
                    with annotation_path.open(encoding="utf-8") as source:
                        annotation_frames = sum(1 for line in source for _ in (json.loads(line),))
                except (OSError, ValueError):
                    annotation_frames = 0
                if video_frames <= 0 or video_frames != annotation_frames:
                    continue
                for suffix, path in (("rgb.mp4", video_path),
                                     ("object_detection.jsonl", annotation_path)):
                    found[(run["run_id"], camera, suffix)] = {
                        "path": str(path), "size": path.stat().st_size,
                        "member": f"{stem}.{suffix}"}

        def download_member(key: tuple[str, str, str], entry: dict) -> None:
            run_id, camera, suffix = key
            size = entry["size"]
            cap = 512 * 1024 * 1024 if suffix == "object_detection.jsonl" else 96 * 1024 * 1024
            if size > cap:
                raise ValueError(f"Miembro supera el límite selectivo ({cap} bytes): {entry['name']}")
            path = raw_dir / f"{run_id}.{camera}.{suffix}"
            if not path.exists() or path.stat().st_size != size:
                with path.open("wb") as target:
                    cursor = entry["offset"] + 512
                    end = cursor + size
                    while cursor < end:
                        step = min(16 * 1024 * 1024, end - cursor)
                        target.write(read_range(url, cursor, step))
                        cursor += step
            found[key] = {"path": str(path), "size": size, "member": entry["name"]}

        def within_cap(key: tuple[str, str, str]) -> bool:
            entry = available[key]
            cap = 512 * 1024 * 1024 if key[2] == "object_detection.jsonl" else 96 * 1024 * 1024
            return entry["size"] <= cap

        def handle_member(offset: int, name: str, size: int) -> bool:
            match = RUN_PATTERN.search(name)
            if match and match.group() > max_run:
                return True
            if match and match.group() in run_ids:
                run_id = match.group()
                for suffix in ("rgb.mp4", "object_detection.jsonl"):
                    ending = "." + suffix
                    prefix = run_id + "."
                    if not name.endswith(ending) or prefix not in name:
                        continue
                    camera = name.split(prefix, 1)[1][:-len(ending)]
                    key = (run_id, camera, suffix)
                    entry = {"offset": offset, "name": name, "size": size}
                    available[key] = entry
                    if key in desired and key not in found and within_cap(key):
                        download_member(key, entry)
                    break
            return len(found) == len(desired)

        offset = 0
        finished = False
        if len(found) == len(desired):
            finished = True
        elif index_path.exists():
            with index_path.open(encoding="utf-8") as source:
                for line in source:
                    record = json.loads(line)
                    if record["offset"] != offset:
                        raise ValueError(f"Índice TAR discontinuo: {index_path}")
                    offset = record["next_offset"]
                    if handle_member(record["offset"], record["name"], record["size"]):
                        finished = True
                        break
        if not finished:
            with index_path.open("a", encoding="utf-8") as sink:
                for _ in range(30000):
                    header = read_range(url, offset, 512)
                    if not header.strip(b"\0"):
                        break
                    name = header[:100].split(b"\0", 1)[0].decode("utf-8")
                    size = int(header[124:136].strip(b"\0 "), 8)
                    next_offset = offset + 512 + ((size + 511) // 512) * 512
                    sink.write(json.dumps({"offset": offset, "next_offset": next_offset,
                                           "name": name, "size": size}) + "\n")
                    sink.flush()
                    if handle_member(offset, name, size):
                        break
                    offset = next_offset
        rows = []
        for run in runs:
            run_id = run["run_id"]
            cameras_with_pairs = {camera for rid, camera, suffix in available
                                  if rid == run_id and suffix == "rgb.mp4"
                                  and (rid, camera, "object_detection.jsonl") in available
                                  and within_cap((rid, camera, "rgb.mp4"))
                                  and within_cap((rid, camera, "object_detection.jsonl"))}
            cameras_with_pairs |= {camera for rid, camera, suffix in found
                                   if rid == run_id and suffix == "rgb.mp4"
                                   and (rid, camera, "object_detection.jsonl") in found}
            selected = choose_cameras(run["cameras"], cameras_with_pairs)
            if not selected:
                raise FileNotFoundError(f"Ninguna cámara RGB+JSONL en {shard} / {run_id}")
            for camera in selected:
                for suffix in ("rgb.mp4", "object_detection.jsonl"):
                    key = (run_id, camera, suffix)
                    if key not in found:
                        download_member(key, available[key])
                video = found[(run["run_id"], camera, "rgb.mp4")]
                annotation = found[(run["run_id"], camera, "object_detection.jsonl")]
                rows.append({"run_id": run["run_id"], "seed": run["seed"],
                             "scenario": run["scenario"], "split": run["split"],
                             "camera": camera, "video_path": video["path"],
                             "annotation_path": annotation["path"],
                             "source_shard": shard, "video_size": video["size"],
                             "annotation_size": annotation["size"]})
        return rows

    all_rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process, shard, runs): shard
                   for shard, runs in by_shard.items()}
        for future in as_completed(futures):
            try:
                all_rows.extend(future.result())
            except Exception:
                print(f"Fallo al extraer {futures[future]}; se cancelan tareas pendientes",
                      flush=True)
                for pending in futures:
                    pending.cancel()
                raise
            print(f"Extraído {futures[future]} ({len(all_rows)} cámaras)", flush=True)
    if len({row["run_id"] for row in all_rows}) != len(selected_runs) or len(all_rows) > 2 * len(selected_runs):
        raise ValueError(f"Piloto incompleto: {len(all_rows)} cámaras")
    with (output_dir / "pilot-catalog.csv").open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(sorted(all_rows, key=lambda row: (row["split"], row["scenario"],
                                                     row["run_id"], row["camera"])))


def temporal_test_indices(frame_count: int, limit: int) -> list[int]:
    """Índices de test fijados por tiempo, sin consultar clases ni cajas."""
    if frame_count < limit or limit < 1:
        raise ValueError("Video demasiado corto para el muestreo de test")
    return [min(frame_count - 1, int((i + .5) * frame_count / limit))
            for i in range(limit)]


def catalog_from_cache(plan_path: Path, raw_dir: Path, output: Path, split: str,
                       selected_best: Path | None = None) -> None:
    """Construye catálogo alineado; test solo tras seleccionar best.pt."""
    import cv2

    if split not in {"train", "validation", "test"}:
        raise ValueError("Split inválido")
    if split == "test" and (selected_best is None or not selected_best.is_file()
                            or selected_best.suffix != ".pt"):
        raise ValueError("Test reservado hasta disponer de best.pt seleccionado")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    selected = [run for run in plan["runs"] if run["split"] == split]
    rows = []
    for run in selected:
        prefix = run["run_id"] + "."
        pairs = {}
        for video_path in raw_dir.glob(prefix + "*.rgb.mp4"):
            camera = video_path.name[len(prefix):-len(".rgb.mp4")]
            annotation_path = raw_dir / f"{prefix}{camera}.object_detection.jsonl"
            if annotation_path.is_file() and video_path.stat().st_size > 0 and annotation_path.stat().st_size > 0:
                capture = cv2.VideoCapture(str(video_path))
                try:
                    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) if capture.isOpened() else 0
                finally:
                    capture.release()
                with annotation_path.open(encoding="utf-8") as source:
                    annotation_count = sum(1 for _ in source)
                if frame_count and frame_count == annotation_count:
                    pairs[camera] = (video_path, annotation_path)
                else:
                    print(f"Excluida cámara desalineada {run['run_id']} / {camera}: "
                          f"video={frame_count}, JSONL={annotation_count}", flush=True)
        cameras = choose_cameras(run["cameras"], set(pairs))
        if not cameras:
            raise ValueError(f"Run {run['run_id']} sin par RGB/JSONL local")
        for camera in cameras:
            video_path, annotation_path = pairs[camera]
            rows.append({"run_id": run["run_id"], "seed": run["seed"],
                         "scenario": run["scenario"], "split": split,
                         "camera": camera, "video_path": str(video_path),
                         "annotation_path": str(annotation_path),
                         "source_shard": run["source_shard"],
                         "video_size": video_path.stat().st_size,
                         "annotation_size": annotation_path.stat().st_size})
    output = local_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export_yolo(plan_path: Path, catalog_path: Path, output_dir: Path,
                split: str, frames_per_camera: int = 10) -> None:
    """Exporta un split por vez; test solo debe invocarse tras seleccionar best.pt."""
    import cv2

    if split not in {"train", "validation", "test"} or not 8 <= frames_per_camera <= 12:
        raise ValueError("Split o frames_per_camera inválidos")
    output_dir = local_output(output_dir)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("dataset_revision") != REVISION or len(plan.get("runs", [])) != 80:
        raise ValueError("Plan piloto no válido")
    selected_runs = {row["run_id"]: row for row in plan["runs"] if row["split"] == split}
    with catalog_path.open(newline="", encoding="utf-8-sig") as source:
        rows = [row for row in csv.DictReader(source) if row["split"] == split]
    if not len(selected_runs) <= len(rows) <= 2 * len(selected_runs):
        raise ValueError("Catálogo incompleto para el split")
    short_split = "val" if split == "validation" else split
    images_dir = output_dir / "images" / short_split
    labels_dir = output_dir / "labels" / short_split
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for row in rows:
        run = selected_runs.get(row["run_id"])
        if run is None or not row["camera"] or row["seed"] != run["seed"]:
            raise ValueError("Catálogo y plan no coinciden")
        capture = cv2.VideoCapture(row["video_path"])
        try:
            if not capture.isOpened():
                raise ValueError(f"Video no decodificable: {row['run_id']} / {row['camera']}")
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = capture.get(cv2.CAP_PROP_FPS)
            if width != 1920 or height != 1080 or abs(fps - 30) > .1:
                raise ValueError(f"Video fuera de formato esperado: {row['run_id']} / {row['camera']}")
            annotation_row = {**row, "width": width, "height": height}
            frames = []
            for frame_index, frame in iter_frames(annotation_row):
                items = observations(annotation_row, frame)
                valid = [item for item in items if item["target_candidate"] and item["bbox"]]
                invalid_target = sum(bool(item["target_candidate"] and not item["bbox"])
                                     for item in items)
                frames.append({"frame": frame_index,
                               "boxes": [{"class_id": CLASS_IDS[item["target_candidate"]],
                                          "target_class": item["target_candidate"],
                                          "bbox": item["bbox"], "prim_path": item["prim_path"],
                                          "task_name": item["task_name"]} for item in valid],
                               "invalid_target": invalid_target})
            if len(frames) != frame_count:
                raise ValueError(f"JSONL/video desalineados: {row['run_id']} / {row['camera']}")
            if split == "test":
                indices = temporal_test_indices(frame_count, frames_per_camera)
                # La posición fue fijada sin etiquetas. Si no hay caja válida
                # pero sí targets sin caja, se omite ese frame ambiguo sin
                # reemplazarlo por otro más favorable.
                chosen = [frames[i] for i in indices
                          if frames[i]["boxes"] or not frames[i]["invalid_target"]]
            else:
                eligible = [frame for frame in frames
                            if frame["boxes"] or not frame["invalid_target"]]
                chosen = select_frames(eligible, frames_per_camera)
                negatives = [frame for frame in eligible if not frame["boxes"]
                             and frame["frame"] not in {item["frame"] for item in chosen}]
                if negatives:
                    chosen.extend(select_frames(negatives, min(4, len(negatives))))
                    chosen.sort(key=lambda item: item["frame"])
            for frame in chosen:
                stem = f"{row['run_id']}.{row['camera']}.{frame['frame']:04d}"
                image_path = images_dir / f"{stem}.jpg"
                label_path = labels_dir / f"{stem}.txt"
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame["frame"])
                ok, image = capture.read()
                if not ok or image.shape[:2] != (height, width):
                    raise ValueError(f"Frame inválido: {stem}")
                if int(round(capture.get(cv2.CAP_PROP_POS_FRAMES))) != frame["frame"] + 1:
                    raise ValueError(f"Frame desalineado: {stem}")
                if not cv2.imwrite(str(image_path), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                    raise OSError(f"No se pudo guardar {stem}")
                lines = [f"{box['class_id']} " + " ".join(f"{value:.8f}" for value in box["bbox"])
                         for box in frame["boxes"]]
                label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
                manifest.append({"run_id": row["run_id"], "seed": row["seed"],
                                 "scenario": row["scenario"], "camera": row["camera"],
                                 "frame": frame["frame"], "split": short_split,
                                 "person_boxes": sum(box["class_id"] == 0 for box in frame["boxes"]),
                                 "forklift_boxes": sum(box["class_id"] == 1 for box in frame["boxes"]),
                                 "ignored_targets_without_box": frame["invalid_target"],
                                 "background": not bool(frame["boxes"])})
        finally:
            capture.release()
        print(f"Exportado {row['run_id']} / {row['camera']} ({len(manifest)} imágenes)", flush=True)
    with (output_dir / f"manifest-{short_split}.csv").open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=list(manifest[0]))
        writer.writeheader()
        writer.writerows(manifest)
    test_entry = "test: images/test\n" if (output_dir / "images" / "test").is_dir() else ""
    (output_dir / "data.yaml").write_text(
        f"path: {output_dir.as_posix()}\ntrain: images/train\nval: images/val\n"
        f"{test_entry}names:\n  0: person\n  1: forklift\n", encoding="utf-8")


def validate_export(plan_path: Path, dataset_dir: Path, output: Path,
                    include_test: bool = False) -> None:
    """Valida clases, cajas y separación por run/seed en el dataset local."""
    import cv2

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    selected = {row["run_id"]: row for row in plan["runs"]}
    names = ("train", "val", "test") if include_test else ("train", "val")
    totals = {}
    seen = {}
    for split in names:
        manifest_path = dataset_dir / f"manifest-{split}.csv"
        with manifest_path.open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
        if not rows:
            raise ValueError(f"Split vacío: {split}")
        counters = {"images": 0, "person_boxes": 0, "forklift_boxes": 0,
                    "backgrounds": 0, "ignored_targets_without_box": 0}
        split_runs = set()
        split_seeds = set()
        for row in rows:
            planned = selected.get(row["run_id"])
            expected = "validation" if split == "val" else split
            if planned is None or planned["split"] != expected or planned["seed"] != row["seed"]:
                raise ValueError("Imagen fuera del split reservado")
            split_runs.add(row["run_id"])
            split_seeds.add(row["seed"])
            stem = f"{row['run_id']}.{row['camera']}.{int(row['frame']):04d}"
            image = dataset_dir / "images" / split / f"{stem}.jpg"
            label = dataset_dir / "labels" / split / f"{stem}.txt"
            if not image.is_file() or not label.is_file():
                raise ValueError(f"Imagen/etiqueta faltante: {stem}")
            decoded = cv2.imread(str(image))
            if decoded is None or decoded.shape[:2] != (1080, 1920):
                raise ValueError(f"Imagen inválida: {stem}")
            actual = [0, 0]
            for line in label.read_text(encoding="utf-8").splitlines():
                values = line.split()
                if len(values) != 5 or values[0] not in {"0", "1"}:
                    raise ValueError(f"Etiqueta inválida: {stem}")
                cx, cy, bw, bh = map(float, values[1:])
                if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < bw <= 1 and 0 < bh <= 1
                        and cx - bw / 2 >= -1e-7 and cx + bw / 2 <= 1 + 1e-7
                        and cy - bh / 2 >= -1e-7 and cy + bh / 2 <= 1 + 1e-7):
                    raise ValueError(f"Caja fuera de rango: {stem}")
                actual[int(values[0])] += 1
            if actual != [int(row["person_boxes"]), int(row["forklift_boxes"])]:
                raise ValueError(f"Conteos no coinciden: {stem}")
            counters["images"] += 1
            counters["person_boxes"] += actual[0]
            counters["forklift_boxes"] += actual[1]
            counters["backgrounds"] += not any(actual)
            counters["ignored_targets_without_box"] += int(row["ignored_targets_without_box"])
        expected_runs = sum(planned["split"] == ("validation" if split == "val" else split)
                            for planned in selected.values())
        if len(split_runs) != expected_runs:
            raise ValueError(f"Runs incompletos en {split}")
        totals[split] = {**counters, "runs": len(split_runs), "seeds": len(split_seeds)}
        seen[split] = (split_runs, split_seeds)
    for left in names:
        for right in names:
            if left < right and (seen[left][0] & seen[right][0] or seen[left][1] & seen[right][1]):
                raise ValueError(f"Leakage run/seed entre {left} y {right}")
    if HOLDOUT_RUNS & selected.keys():
        raise ValueError("A/B/C entró en el piloto")
    output = local_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"dataset_revision": REVISION, "splits": totals}, indent=2) + "\n",
                      encoding="utf-8")


def contact_sheet_yolo(dataset_dir: Path, output: Path) -> None:
    """Muestra solo train/val; jamás abre imágenes de test."""
    import cv2
    import numpy as np

    panels = []
    for split in ("train", "val"):
        images = sorted((dataset_dir / "images" / split).glob("*.jpg"))
        if not images:
            raise ValueError(f"Sin imágenes {split}")
        for rank in range(6):
            image_path = images[min(len(images) - 1, int((rank + .5) * len(images) / 6))]
            image = cv2.imread(str(image_path))
            if image is None:
                raise ValueError(f"Imagen inválida: {image_path.name}")
            height, width = image.shape[:2]
            label = dataset_dir / "labels" / split / f"{image_path.stem}.txt"
            for line in label.read_text(encoding="utf-8").splitlines():
                class_id, cx, cy, bw, bh = map(float, line.split())
                x1, y1 = int((cx - bw / 2) * width), int((cy - bh / 2) * height)
                x2, y2 = int((cx + bw / 2) * width), int((cy + bh / 2) * height)
                color = (0, 230, 0) if int(class_id) == 0 else (0, 160, 255)
                cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
            image = cv2.resize(image, (480, 270))
            cv2.putText(image, f"{split} {image_path.stem[-22:]}", (5, 255),
                        cv2.FONT_HERSHEY_SIMPLEX, .45, (255, 255, 255), 1)
            panels.append(image)
    sheet = np.vstack([np.hstack(panels[i:i + 3]) for i in range(0, len(panels), 3)])
    output = local_output(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), sheet):
        raise OSError("No se pudo guardar contact sheet")


def fetch_member(shard: str, run_id: str, camera: str, output: Path, suffix: str) -> str:
    if not shard.startswith("artifacts/") or not shard.endswith(".tar") or ".." in Path(shard).parts:
        raise ValueError("Se requiere una ruta artifacts/*.tar del repositorio NVIDIA")
    if not run_id or not camera or any(c in run_id + camera for c in "/\\"):
        raise ValueError("run_id/camera inválidos")
    url = BASE_URL + REVISION + "/" + shard
    offset = 0
    for _ in range(30000):
        header = read_range(url, offset, 512)
        if not header.strip(b"\0"):
            break
        name = header[:100].split(b"\0", 1)[0].decode("utf-8")
        size = int(header[124:136].strip(b"\0 "), 8)
        if run_id in name and f".{camera}.{suffix}" in name:
            if size > 64 * 1024 * 1024:
                raise ValueError("Miembro supera el límite de descarga selectiva de 64 MiB")
            output = local_output(output)
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("wb") as target:
                cursor = offset + 512
                end = cursor + size
                while cursor < end:
                    step = min(1024 * 1024, end - cursor)
                    target.write(read_range(url, cursor, step))
                    cursor += step
            return name
        offset += 512 + ((size + 511) // 512) * 512
    raise FileNotFoundError(f"No se halló {run_id} / {camera} en {shard}")


def load_registry(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("dataset_revision") != REVISION:
        raise ValueError("Registro de splits de otra revisión")
    return data["splits"]


def check_blind_test(rows: list[dict], registry: dict[str, str] | None) -> None:
    if registry is not None:
        if any(row["run_id"] not in registry for row in rows):
            raise ValueError("Run ausente del registro de splits")
        if any(registry[row["run_id"]] == "test" for row in rows):
            raise ValueError("El test reservado debe permanecer sin inspección durante el piloto")


def reserve_splits(index: Path, output: Path, seen_runs: frozenset[str]) -> None:
    output = local_output(output)
    with index.open(newline="", encoding="utf-8-sig") as source:
        rows = [row for row in csv.DictReader(source) if row.get("source_kind") == "multi_camera_run"]
    if not rows or not {"run_id", "scenario", "seed"}.issubset(rows[0]):
        raise ValueError("Índice de runs vacío o sin run_id/scenario/seed/source_kind")
    if len({row["run_id"] for row in rows}) != len(rows):
        raise ValueError("Run duplicado en índice")
    unknown_seen = seen_runs - {row["run_id"] for row in rows}
    if unknown_seen:
        raise ValueError(f"Runs inspeccionados ausentes del índice: {sorted(unknown_seen)}")
    splits = split_runs(rows, exploration_runs=seen_runs)
    with index.open("rb") as source:
        index_hash = hashlib.file_digest(source, "sha256").hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"dataset_revision": REVISION, "algorithm": "sha256_seed_70_15_15",
                                  "runs_index_sha256": index_hash,
                                  "status": "reservation_before_label_review_for_unseen_runs",
                                  "splits": dict(sorted(splits.items()))},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_audit(catalog: Path, output_dir: Path, registry: Path | None = None) -> None:
    output_dir = local_output(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_catalog(catalog)
    check_blind_test(rows, load_registry(registry))
    result = audit(rows)
    (output_dir / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    combinations = result["combinations"]
    with (output_dir / "combinations.csv").open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=list(combinations[0]) if combinations else
                                ["source_kind", "label_class", "group", "name", "agent_type", "task_name", "asset_name",
                                 "target_candidate", "annotations", "valid_boxes", "frames", "runs", "cameras",
                                 "unique_prim_paths"])
        writer.writeheader()
        writer.writerows(combinations)
    instances = result["instances"]
    with (output_dir / "instances.csv").open("w", newline="", encoding="utf-8") as sink:
        writer = csv.DictWriter(sink, fieldnames=list(instances[0]) if instances else
                                ["scenario", "run_id", "camera", "prim_path", "label_class", "group", "name",
                                 "target_candidate", "frames_present", "frames_with_valid_box"])
        writer.writeheader()
        writer.writerows(instances)


def write_manifest(catalog: Path, output: Path, frames: int, seen_runs: frozenset[str],
                   registry: Path | None = None) -> None:
    output = local_output(output)
    rows = read_catalog(catalog)
    reserved = load_registry(registry)
    check_blind_test(rows, reserved)
    result = build_manifest(rows, frames, seen_runs, reserved)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def contact_sheet(manifest: Path, output: Path, indices: list[int]) -> None:
    import cv2  # import diferido: audit/manifest no necesitan OpenCV
    import numpy as np

    output = local_output(output)
    entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
    panels = []
    for number in indices:
        entry = entries[number]
        if not entry.get("video_path"):
            raise ValueError(f"Entrada {number} sin video_path")
        capture = cv2.VideoCapture(entry["video_path"])
        try:
            if not capture.isOpened():
                raise ValueError(f"Video no disponible para entrada {number}")
            width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if (width, height) != (entry["width"], entry["height"]):
                raise ValueError(f"Resolución no coincide en entrada {number}")
            capture.set(cv2.CAP_PROP_POS_FRAMES, entry["frame"])
            ok, image = capture.read()
            if not ok:
                raise ValueError(f"Frame no decodificable en entrada {number}")
            decoded_position = int(round(capture.get(cv2.CAP_PROP_POS_FRAMES)))
            if decoded_position != entry["frame"] + 1:
                raise ValueError(f"Frame desalineado en entrada {number}: {decoded_position}")
        finally:
            capture.release()
        for box in entry["boxes"]:
            cx, cy, bw, bh = box["bbox"]
            x1, y1 = int((cx - bw / 2) * width), int((cy - bh / 2) * height)
            x2, y2 = int((cx + bw / 2) * width), int((cy + bh / 2) * height)
            color = (0, 230, 0) if box["class_id"] == 0 else (0, 160, 255)
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 3)
            cv2.putText(image, box["target_class"], (x1, max(20, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, .7, color, 2)
        image = cv2.resize(image, (480, 270))
        cv2.putText(image, f"{entry['scenario']} {entry['camera']} f{entry['frame']}",
                    (8, 255), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2)
        panels.append(image)
    if not panels:
        raise ValueError("Sin paneles")
    while len(panels) % 3:
        panels.append(np.zeros_like(panels[0]))
    sheet = np.vstack([np.hstack(panels[i:i + 3]) for i in range(0, len(panels), 3)])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), sheet):
        raise OSError("No se pudo guardar contact sheet")


def verify_yolo(manifest: Path, output: Path, index: int) -> None:
    """Escribe solamente una muestra de etiquetas; no exporta dataset."""
    output = local_output(output)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("dataset_revision") != REVISION:
        raise ValueError("Revisión del dataset distinta de la fijada")
    entry = data["entries"][index]
    lines = [f"{box['class_id']} " + " ".join(f"{value:.6f}" for value in box["bbox"])
             for box in entry["boxes"]]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch-annotation", help="Extrae un JSONL por HTTP Range de la revisión fijada")
    fetch.add_argument("--shard", required=True)
    fetch.add_argument("--run-id", required=True)
    fetch.add_argument("--camera", required=True)
    fetch.add_argument("--output", type=Path, required=True)
    rgb = sub.add_parser("fetch-rgb", help="Extrae un solo MP4 para revisión visual, nunca el shard completo")
    rgb.add_argument("--shard", required=True)
    rgb.add_argument("--run-id", required=True)
    rgb.add_argument("--camera", required=True)
    rgb.add_argument("--output", type=Path, required=True)
    audit_cmd = sub.add_parser("audit", help="Conteos reales en un catálogo local de JSONL")
    audit_cmd.add_argument("--catalog", type=Path, required=True)
    audit_cmd.add_argument("--output-dir", type=Path, required=True)
    audit_cmd.add_argument("--registry", type=Path, help="Impide abrir runs reservados para test")
    reserve = sub.add_parser("reserve-splits", help="Reserva test por seed antes de inspeccionar etiquetas")
    reserve.add_argument("--runs-index", type=Path, required=True, help="CSV local exportado de runs.parquet")
    reserve.add_argument("--output", type=Path, required=True)
    reserve.add_argument("--seen-run", action="append", default=[])
    manifest = sub.add_parser("build-manifest", help="Manifest candidato; no exporta YOLO")
    manifest.add_argument("--catalog", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--max-frames-per-camera", type=int, default=12)
    manifest.add_argument("--seen-run", action="append", default=[], help="Run ya inspeccionado: nunca test ciego")
    manifest.add_argument("--registry", type=Path)
    preview = sub.add_parser("contact-sheet", help="Dibuja cajas candidatas en videos locales alineados")
    preview.add_argument("--manifest", type=Path, required=True)
    preview.add_argument("--output", type=Path, required=True)
    preview.add_argument("--indices", type=int, nargs="+", required=True)
    labels = sub.add_parser("verify-yolo", help="Convierte una sola entrada a etiqueta YOLO de verificación")
    labels.add_argument("--manifest", type=Path, required=True)
    labels.add_argument("--output", type=Path, required=True)
    labels.add_argument("--index", type=int, required=True)
    shard_index = sub.add_parser("index-artifact-shards", help="Lee solo el primer header de cada shard")
    shard_index.add_argument("--output", type=Path, required=True)
    shard_index.add_argument("--count-per-scenario", type=int, required=True)
    pilot = sub.add_parser("plan-pilot", help="Selecciona 80 runs sin abrir anotaciones")
    pilot.add_argument("--runs-index", type=Path, required=True)
    pilot.add_argument("--registry", type=Path, required=True)
    pilot.add_argument("--shards-index", type=Path, required=True)
    pilot.add_argument("--output", type=Path, required=True)
    pilot_fetch = sub.add_parser("fetch-pilot", help="Descarga solo MP4/JSONL elegidos, no shards")
    pilot_fetch.add_argument("--plan", type=Path, required=True)
    pilot_fetch.add_argument("--output-dir", type=Path, required=True)
    pilot_fetch.add_argument("--workers", type=int, default=8)
    pilot_fetch.add_argument("--split", choices=["train", "validation", "test"], action="append",
                             help="Limita la descarga a estos splits; por defecto todos")
    export = sub.add_parser("export-yolo", help="Exporta un split YOLO; test tras best.pt")
    export.add_argument("--plan", type=Path, required=True)
    export.add_argument("--catalog", type=Path, required=True)
    export.add_argument("--output-dir", type=Path, required=True)
    export.add_argument("--split", choices=["train", "validation", "test"], required=True)
    export.add_argument("--frames-per-camera", type=int, default=10)
    check_export = sub.add_parser("validate-export", help="Valida dataset YOLO sin test por defecto")
    check_export.add_argument("--plan", type=Path, required=True)
    check_export.add_argument("--dataset-dir", type=Path, required=True)
    check_export.add_argument("--output", type=Path, required=True)
    check_export.add_argument("--include-test", action="store_true")
    sheet_yolo = sub.add_parser("contact-sheet-yolo", help="Dibuja solo train/val")
    sheet_yolo.add_argument("--dataset-dir", type=Path, required=True)
    sheet_yolo.add_argument("--output", type=Path, required=True)
    cached_catalog = sub.add_parser("catalog-from-cache", help="Catálogo alineado desde caché local")
    cached_catalog.add_argument("--plan", type=Path, required=True)
    cached_catalog.add_argument("--raw-dir", type=Path, required=True)
    cached_catalog.add_argument("--output", type=Path, required=True)
    cached_catalog.add_argument("--split", choices=["train", "validation", "test"], required=True)
    cached_catalog.add_argument("--selected-best", type=Path,
                                help="best.pt ya elegido con validation; obligatorio para test")
    args = parser.parse_args()
    if args.command == "fetch-annotation":
        print(fetch_member(args.shard, args.run_id, args.camera, args.output, "object_detection.jsonl"))
    elif args.command == "fetch-rgb":
        print(fetch_member(args.shard, args.run_id, args.camera, args.output, "rgb.mp4"))
    elif args.command == "audit":
        write_audit(args.catalog, args.output_dir, args.registry)
    elif args.command == "reserve-splits":
        reserve_splits(args.runs_index, args.output, frozenset(args.seen_run))
    elif args.command == "build-manifest":
        write_manifest(args.catalog, args.output, args.max_frames_per_camera,
                       frozenset(args.seen_run), args.registry)
    elif args.command == "contact-sheet":
        contact_sheet(args.manifest, args.output, args.indices)
    elif args.command == "index-artifact-shards":
        index_artifact_shards(args.output, args.count_per_scenario)
    elif args.command == "plan-pilot":
        plan_pilot(args.runs_index, args.registry, args.shards_index, args.output)
    elif args.command == "fetch-pilot":
        fetch_pilot(args.plan, args.output_dir, args.workers,
                    tuple(args.split) if args.split else ("train", "validation", "test"))
    elif args.command == "export-yolo":
        export_yolo(args.plan, args.catalog, args.output_dir, args.split, args.frames_per_camera)
    elif args.command == "validate-export":
        validate_export(args.plan, args.dataset_dir, args.output, args.include_test)
    elif args.command == "contact-sheet-yolo":
        contact_sheet_yolo(args.dataset_dir, args.output)
    elif args.command == "catalog-from-cache":
        catalog_from_cache(args.plan, args.raw_dir, args.output, args.split, args.selected_best)
    else:
        verify_yolo(args.manifest, args.output, args.index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
