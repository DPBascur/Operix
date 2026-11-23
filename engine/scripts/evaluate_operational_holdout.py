# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Independent operational evaluation. Sample and seal human labels before scoring."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from operix_engine.detection import BoundingBox
from operix_engine.person_holdout import require_outside_repository, sha256_file
from operix_engine.person_metrics import box_iou


ROLES = ("person", "forklift")
MOTION = ("MOVING", "STATIONARY", "UNKNOWN")
OCCUPANCY = ("ONBOARD", "NOT_ONBOARD", "UNKNOWN")
VISIBILITY = ("CLEAR", "PARTIAL", "SMALL", "SMALL_PARTIAL")
FLOORS = {"person": .10, "forklift": .45}
REPO = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def sampling(count, fps):
    # Fixed before any inspection of the detector. Sparse samples are for AP.
    if fps <= 0 or count < math.ceil(43 * fps):
        raise ValueError("La fuente necesita al menos 43 s para el protocolo v1")
    sparse = set(round(i * (count - 1) / 11) for i in range(12))
    dense = {i: str(start) for start in (10, 40)
             for i in range(round(start * fps), round((start + 3) * fps))}
    return {i: (i in sparse, dense.get(i)) for i in sorted(sparse | dense.keys())}


def labels():
    def attr(name, values):
        return {"name": name, "input_type": "select", "mutable": True,
                "default_value": values[0], "values": list(values)}

    common = [{"name": "actor", "input_type": "text", "mutable": False,
               "default_value": "", "values": []}, attr("visibility", VISIBILITY)]
    return [
        {"name": "person", "type": "rectangle",
         "attributes": [*common, attr("occupancy", ("UNKNOWN", *OCCUPANCY[:2]))]},
        {"name": "forklift", "type": "rectangle",
         "attributes": [*common, attr("motion", ("UNKNOWN", *MOTION[:2]))]},
    ]


def evaluation_rules(source):
    # Condiciones de ensayo en imagen, idénticas entre backends.
    return {"schema_version": 1, "view_id": source, "coordinate_system": "normalized",
            "motion": {"unit": "normalized", "window_seconds": .75, "min_observations": 6,
                       "max_gap_seconds": .15, "stationary_speed": .01, "moving_speed": .03,
                       "max_position_residual": .03, "camera_fixed_confirmed": True,
                       "confirmation_seconds": .25},
            "zones": [{"zone_id": "frame", "name": "Encuadre completo", "purpose": "observation",
                       "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
            "rules": [
                {"rule_id": "presence", "version": 1, "enabled": True,
                 "parameters": {"kind": "zone_dwell", "zone_id": "frame", "class_name": "person",
                                "min_duration_s": .5}},
                {"rule_id": "proximity", "version": 1, "enabled": True,
                 "parameters": {"kind": "person_forklift_proximity", "zone_id": "frame", "distance_unit": "normalized",
                                "max_distance": .1, "minimum_duration_seconds": .25,
                                "exclude_possible_occupant": False}},
            ]}


def prepare(root, source_list):
    import cv2

    require_outside_repository(root, REPO)
    sources = sorted(load(source_list), key=lambda source: source["id"])
    if not sources or len({source["id"] for source in sources}) != len(sources):
        raise ValueError("IDs de fuente vacíos o duplicados")
    if len({source["hash"].lower() for source in sources}) != len(sources):
        raise ValueError("La lista repite el mismo video")
    destination = root / "annotation"
    if destination.exists():
        raise FileExistsError(destination)
    with TemporaryDirectory(prefix="pack-", dir=root) as folder:
        workspace = Path(folder)
        manifest = {"schema": 1, "sources": [], "frames": [], "confidence_floors": FLOORS}
        rules = {}
        for source in sources:
            id_ = source["id"]
            if not re.fullmatch(r"[A-Za-z0-9-]{1,60}", id_):
                raise ValueError("Identificador de fuente inválido")
            if not all(source.get(key) for key in ("family", "author", "license", "license_url", "url")):
                raise ValueError(f"Procedencia incompleta: {id_}")
            config_path = workspace / f"{id_}-rules.json"
            write(config_path, evaluation_rules(id_))
            rules[id_] = sha256_file(config_path).lower()
            video = (root / source["media"]).resolve()
            if not video.is_relative_to((root / "media").resolve()) or sha256_file(video).lower() != source["hash"].lower():
                raise ValueError(f"SHA o ubicación de fuente inválidos: {id_}")
            capture = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
            try:
                fps = capture.get(cv2.CAP_PROP_FPS)
                count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
                chosen = sampling(count, fps)
                with ZipFile(workspace / f"{id_}.zip", "x") as archive:
                    for index in range(max(chosen) + 1):
                        ok, frame = capture.read()
                        if not ok:
                            raise ValueError(f"Video truncado: {id_} frame {index}")
                        if index not in chosen:
                            continue
                        ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                        if not ok:
                            raise ValueError(f"No se pudo exportar {id_} frame {index}")
                        name = f"{id_}_{index:06d}.jpg"
                        payload = encoded.tobytes()
                        archive.writestr(name, payload)
                        sparse, dense = chosen[index]
                        manifest["frames"].append({"name": name, "source": id_, "index": index,
                                                   "utc_basis": "none", "time_s": index / fps,
                                                   "width": frame.shape[1], "height": frame.shape[0],
                                                   "sparse": sparse, "window": dense,
                                                   "sha256": hashlib.sha256(payload).hexdigest()})
                manifest["sources"].append({**source, "fps": fps, "frames": count,
                                            "archive_sha256": sha256_file(workspace / f"{id_}.zip").lower()})
            finally:
                capture.release()
        manifest["rule_snapshots"] = rules
        write(workspace / "manifest.json", manifest)
        write(workspace / "cvat-labels.json", labels())
        write(workspace / "review-template.json",
              {"reviewer": "", "blind": False,
               "annotation_manifest_sha256": sha256_file(workspace / "manifest.json").lower(),
               "checked_frames": {f["name"]: [] for f in manifest["frames"]},
               "reviewed_event_windows": [], "rule_snapshots": rules, "events": []})
        workspace.rename(destination)
    return {"sources": len(sources), "frames": len(manifest["frames"]),
            "sparse": sum(row["sparse"] for row in manifest["frames"]), "dir": str(destination)}


def read_cvat(exports, frames):
    annotations = {}
    for path in exports:
        binary = path.read_bytes()
        if len(binary) > 32 * 1024**2 or re.search(br"<!\s*(DOCTYPE|ENTITY)", binary, re.I):
            raise ValueError("Export CVAT inválido")
        tree = ET.fromstring(binary)
        if tree.tag != "annotations" or tree.findall("track"):
            raise ValueError("Exporte CVAT for images 1.1, anotaciones de rectángulos")
        for image in tree.findall("image"):
            name = image.get("name")
            if name not in frames or name in annotations:
                raise ValueError(f"Frame no esperado o duplicado: {name}")
            row = frames[name]
            if (int(image.get("width")), int(image.get("height"))) != (row["width"], row["height"]):
                raise ValueError(f"Dimensiones inválidas: {name}")
            boxes = [parse_box(item, row) for item in image]
            identities = {(box["role"], box["actor"]) for box in boxes if box["actor"]}
            if len(identities) != sum(bool(box["actor"]) for box in boxes):
                raise ValueError(f"Identidad repetida en {name}")
            annotations[name] = boxes
    if annotations.keys() != frames.keys():
        raise ValueError("El export debe cubrir los frames negativos y positivos")
    return annotations


def parse_box(item, frame):
    role = item.get("label")
    if item.tag != "box" or role not in ROLES:
        raise ValueError(f"Rectángulo o clase inválida: {item.tag}/{role}")
    xyxy = [float(item.get(key)) for key in ("xtl", "ytl", "xbr", "ybr")]
    BoundingBox(*xyxy)
    if xyxy[2] > frame["width"] or xyxy[3] > frame["height"]:
        raise ValueError("Caja fuera del fotograma")
    fields = {a.get("name"): (a.text or "").strip() for a in item.findall("attribute")}
    actor = fields.get("actor", "")
    if frame["window"] is not None and not re.fullmatch(r"[A-Za-z0-9-]{1,32}", actor):
        raise ValueError("Cada objeto de ventana densa requiere ID anónimo")
    visibility = fields.get("visibility", "")
    if visibility not in VISIBILITY:
        raise ValueError("Visibilidad inválida")
    key, values = ("occupancy", OCCUPANCY) if role == "person" else ("motion", MOTION)
    if fields.get(key) not in values:
        raise ValueError(f"Falta estado explícito: {key}")
    return {"role": role, "actor": actor, "xyxy": xyxy, "visibility": visibility, key: fields[key]}


def freeze(root, exports, review_path):
    require_outside_repository(root, REPO)
    pack = root / "annotation"
    manifest_path = pack / "manifest.json"
    manifest = load(manifest_path)
    digest = sha256_file(manifest_path).lower()
    for source in manifest["sources"]:
        if sha256_file(pack / f'{source["id"]}.zip').lower() != source["archive_sha256"]:
            raise ValueError("Archivo de imágenes modificado")
    review = load(review_path)
    checked = review["checked_frames"]
    frames = {row["name"]: row for row in manifest["frames"]}
    if (review.get("blind") is not True or not review.get("reviewer", "").strip()
            or review.get("annotation_manifest_sha256") != digest or frames.keys() != checked.keys()
            or any(not isinstance(tags, list) or not tags or not all(isinstance(tag, str) and tag.strip()
                                                                     for tag in tags) for tags in checked.values())):
        raise ValueError("Se requiere revisión humana ciega de cada frame, incluido cada negativo")
    windows = {(f["source"], f["window"]) for f in frames.values() if f["window"] is not None}
    if {tuple(window) for window in review["reviewed_event_windows"]} != windows:
        raise ValueError("Pendiente revisión explícita de eventos en una o más ventanas")
    annotations = read_cvat(exports, frames)
    intervals = {(f["source"], f["index"]): f for f in frames.values() if f["window"] is not None}
    rules = review["rule_snapshots"]
    if (rules != manifest["rule_snapshots"] or {source for source, _ in windows} != rules.keys()
            or any(sha256_file(pack / f"{source}-rules.json").lower() != digest
                   for source, digest in rules.items())):
        raise ValueError("Falta el SHA-256 de las reglas efectivas por fuente")
    valid_rules = {source: {(row["rule_id"], row["version"], row["parameters"]["zone_id"])
                            for row in load(pack / f"{source}-rules.json")["rules"] if row["enabled"]}
                   for source in rules}
    episodes = set()
    for event in review["events"]:
        start, end, source = event["from_frame"], event["to_frame"], event["source"]
        first, last = intervals.get((source, start)), intervals.get((source, end))
        rule = (event["rule"], event["version"], event["zone"])
        if (type(start) is not int or type(end) is not int or first is None or last is None or end < start
                or first["window"] != last["window"] or rule not in valid_rules.get(source, ())
                or type(event["version"]) is not int or not event["actors"]
                or not set(event["actors"]) <= {f'{box["role"]}/{box["actor"]}'
                                               for box in annotations[last["name"]]}):
            raise ValueError("Evento fuera del tramo anotado o sin identidad de regla/actores")
        identity = source, end, rule, tuple(sorted(event["actors"]))
        if identity in episodes:
            raise ValueError("Episodio humano duplicado")
        episodes.add(identity)
    write(root / "frozen.json", {"manifest_sha256": digest, "manifest": manifest,
                                "review_sha256": sha256_file(review_path).lower(), "review": review,
                                "exports_sha256": [sha256_file(path).lower() for path in exports],
                                "annotations": annotations})
    return {"sha256": sha256_file(root / "frozen.json").lower(), "frames": len(frames)}


def ratio(num, den):
    return num / den if den else None


def detection_scores(frames, labels_by_frame, predicted, role, minimum_iou):
    gt = {(name, i): box for name in frames for i, box in enumerate(labels_by_frame[name]) if box["role"] == role}
    available = {}
    for key, box in gt.items():
        available.setdefault(key[0], {})[key] = box
    candidates = [(name, box) for name in frames for box in predicted.get(name, ()) if box["role"] == role]
    ranked = sorted(candidates, key=lambda entry: (-entry[1]["confidence"], entry[0]))
    flags, false, selected = [], [], []
    for name, prediction in ranked:
        options = available.get(name, {})
        key = max(options, key=lambda k: box_iou(prediction["xyxy"], options[k]["xyxy"]), default=None)
        matched = key is not None and box_iou(prediction["xyxy"], options[key]["xyxy"]) >= minimum_iou
        flags.append(matched)
        if matched:
            del options[key]
        if prediction["confidence"] >= FLOORS[role]:
            if matched:
                selected.append(key)
            else:
                false.append({"frame": name, **prediction})
    recall_precision, count = [], 0
    for k, matched in enumerate(flags, 1):
        count += matched
        recall_precision.append((ratio(count, len(gt)), count / k))
    ap = None if not gt else sum(max((p for r, p in recall_precision if r >= level / 100), default=0.)
                                 for level in range(101)) / 101
    tp, fp, fn = len(selected), len(false), len(gt) - len(selected)
    negative = set(frames) - {name for name, _ in gt}
    return {"positive": len(gt), "tp": tp, "fp": fp, "fn": fn, "precision": ratio(tp, tp + fp),
            "recall": ratio(tp, len(gt)), "f1": ratio(2 * tp, 2 * tp + fp + fn), "ap_sampled": ap,
            "negative_frames": len(negative),
            "negative_frames_with_fp": len({row["frame"] for row in false} & negative),
            "false_positives": false,
            "false_negatives": [{"frame": key[0], **gt[key]} for key in sorted(gt.keys() - set(selected))]}


def match_tracks(ground_truth, tracked):
    import lap
    import numpy as np

    if not ground_truth or not tracked:
        return {}
    scale = 1 + min(len(ground_truth), len(tracked))

    def cost(truth, track):
        if truth["role"] != track["role"]:
            return 2.
        overlap = box_iou(truth["xyxy"], track["xyxy"])
        return (1 - overlap) / scale if overlap >= .5 else 2.

    # A valid match costs less than leaving a track unassigned. Within that
    # constraint rank by IoU, independent of the order of the CVAT rectangles.
    costs = np.array([[cost(truth, track) for track in tracked] for truth in ground_truth])
    _, assignment, _ = lap.lapjv(costs, extend_cost=True, cost_limit=1.)
    return {index: tracked[matched] for index, matched in enumerate(assignment) if matched >= 0}


def evaluate_temporal(frames, annotated, model, review):
    if model.get("rule_snapshots") != review["rule_snapshots"]:
        raise ValueError("La traza no utiliza las reglas congeladas")
    dense = [frame for frame in frames if frame["window"] is not None]
    expected = {f["name"] for f in dense}
    trace = model["tracking"]
    if trace.keys() != expected:
        raise ValueError("La traza debe declarar los descartes en todos los frames densos")
    stats = {role: Counter(visible=0, matched=0, switches=0, max_loss=0) for role in ROLES}
    matrices = {"motion": Counter(), "occupancy": Counter()}
    identity_map, histories, last_seen, lost = {}, {}, {}, Counter()
    by_index = {}
    for frame in dense:
        name, source, index = frame["name"], frame["source"], frame["index"]
        row = trace[name]
        epoch = row["epoch"]
        tracks = row["tracks"]
        if ((epoch is None and tracks) or (epoch is not None and (type(epoch) is not int or epoch < 1))
                or len({(t["role"], t["id"]) for t in tracks}) != len(tracks)):
            raise ValueError("Traza de tracking inválida")
        for track in tracks:
            BoundingBox(*track["xyxy"])
            if track["role"] not in ROLES or type(track["id"]) is not int or track["id"] < 1:
                raise ValueError("Identidad del track inválida")
        by_index[source, index] = (frame["window"], epoch)
        matches = identity_map[source, index] = {}
        assignments = match_tracks(annotated[name], tracks)
        for index_gt, gt in enumerate(annotated[name]):
            role, actor = gt["role"], gt["actor"]
            key = source, frame["window"], role, actor
            stats[role]["visible"] += 1
            track = assignments.get(index_gt)
            if track:
                stats[role]["matched"] += 1
                prior = histories.get(key)
                if prior and prior[0] == epoch and prior[1] != track["id"]:
                    stats[role]["switches"] += 1
                histories[key] = epoch, track["id"]
                matches[role, track["id"]] = f"{role}/{actor}"
            if track is None:
                lost[key] = lost[key] + 1 if last_seen.get(key) == index - 1 else 1
                stats[role]["max_loss"] = max(stats[role]["max_loss"], lost[key])
            else:
                lost[key] = 0
            last_seen[key] = index
            prop = "occupancy" if role == "person" else "motion"
            value = (track.get(prop, "UNREPORTED") if track else "UNMATCHED")
            matrices[prop][f'{gt[prop]}→{value}'] += 1

    observable, gaps = [], []
    for event in review["events"]:
        samples = [by_index[event["source"], index]
                   for index in range(event["from_frame"], event["to_frame"] + 1)]
        (observable if len(set(samples)) == 1 and samples[0][1] is not None else gaps).append(event)

    def equivalent(predicted, target, actors):
        return (predicted["source"] == target["source"] and predicted["rule"] == target["rule"]
                and predicted["zone"] == target["zone"] and predicted["version"] == target["version"]
                and sorted(actors) == sorted(target["actors"])
                and 0 <= predicted["frame"] - target["to_frame"] <= 2
                and by_index[predicted["source"], predicted["frame"]] ==
                by_index[target["source"], target["to_frame"]])

    pending, false, hits = list(observable), [], []
    for event in sorted(model["events"], key=lambda item: (item["source"], item["frame"])):
        key = event["source"], event["frame"]
        if key not in by_index:
            continue  # Fuera de la cobertura anotada.
        if type(event.get("epoch")) is not int or event["epoch"] != by_index[key][1]:
            raise ValueError("Evento sin época válida para su frame")
        actors = [identity_map[key].get((actor["role"], actor["id"])) for actor in event["actors"]]
        hit = next((target for target in pending if all(actors) and equivalent(event, target, actors)), None)
        if hit:
            pending.remove(hit)
            hits.append({"event": event, "delay_frames": event["frame"] - hit["to_frame"]})
        else:
            false.append(event)
    return {"tracking": {role: dict(stats[role]) for role in ROLES},
            "motion": dict(matrices["motion"]), "occupancy": dict(matrices["occupancy"]),
            "events": {"labeled_full_input": len(review["events"]), "observable": len(observable),
                       "unobservable": gaps, "matched": hits, "missed_observable": pending, "unmatched": false}}


def score(root, predictions, expected_sha):
    require_outside_repository(root, REPO)
    path = root / "frozen.json"
    if sha256_file(path).lower() != expected_sha.lower():
        raise ValueError("SHA del freeze inválido")
    frozen, model = load(path), load(predictions)
    if model.get("freeze_sha256") != expected_sha.lower() or not model.get("model_receipt"):
        raise ValueError("Predicciones sin identidad de modelo y freeze")
    labels_by_frame = frozen["annotations"]
    predicted = model["frames"]
    if predicted.keys() != labels_by_frame.keys():
        raise ValueError("Falta una predicción explícita para cada frame, incluso si está vacío")
    frames = frozen["manifest"]["frames"]
    for frame in frames:
        for box in predicted[frame["name"]]:
            bounds = BoundingBox(*box["xyxy"])
            value = box["confidence"]
            if (box["role"] not in ROLES or type(value) not in (int, float) or not 0 <= value <= 1
                    or bounds.x_max > frame["width"] or bounds.y_max > frame["height"]):
                raise ValueError("Predicción inválida")
    grouped = {"all": []}
    for f in frames:
        if f["sparse"]:
            grouped["all"].append(f["name"])
            grouped.setdefault(f["source"], []).append(f["name"])
            for tag in frozen["review"]["checked_frames"][f["name"]]:
                grouped.setdefault(f"scenario:{tag}", []).append(f["name"])
    result = {"freeze_sha256": expected_sha, "model_receipt": model["model_receipt"], "iou": .5,
            "ap_scope": "AP50 de detecciones exportadas, condicionado por el piso de score del exportador",
            "detection": {group: {role: detection_scores(sorted(set(names)), labels_by_frame, predicted, role, .5)
                                  for role in ROLES} for group, names in grouped.items()}}
    if "tracking" in model:
        result["temporal"] = evaluate_temporal(frames, labels_by_frame, model, frozen["review"])
    return result


def infer(root, expected_sha, person_weights, forklift_weights, onnx_report):
    """Replay CUDA on original pixels, using sealed frame membership and rule snapshots."""
    require_outside_repository(root, REPO)
    path = root / "frozen.json"
    if sha256_file(path).lower() != expected_sha.lower():
        raise ValueError("SHA del freeze inválido")
    frozen = load(path)
    import cv2
    import torch
    from contextlib import nullcontext
    from operix_engine.byte_tracker import ByteTrackConfig, ByteTracker
    from operix_engine.dual_perception import ClassPerceptionChannel, DualPerception
    from operix_engine.operational_config import load_operational_config
    from operix_engine.rules import RuleEngine
    from operix_engine.spatiotemporal import SpatiotemporalAnalyzer
    from operix_engine.video_event_pipeline import _visible_tracks
    from run_rtsp_pilot import PERSON_SHA, FORKLIFT_SHA

    sys.path.insert(0, str(REPO / "deployment/rtsp-lab"))
    from benchmark_backends import make_detectors, package_versions, strict_ort_sessions

    weights = {"person": person_weights, "forklift": forklift_weights}
    digests = dict(zip(ROLES, (PERSON_SHA, FORKLIFT_SHA), strict=True))
    if any(sha256_file(weights[role]).lower() != digest for role, digest in digests.items()):
        raise ValueError("El checkpoint difiere del modelo congelado")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA no disponible")
    torch.set_float32_matmul_precision("highest")
    torch.backends.cudnn.allow_tf32 = False
    specs = {role: {"confidence": FLOORS[role], "nms_iou": iou, "imgsz": 640, "class_filter": role}
             for role, iou in zip(ROLES, (.70, .55), strict=True)}
    artifacts = dict(weights)
    if onnx_report:
        report = load(onnx_report)
        protocol = report["protocol"]
        if (report["status"] != "complete" or protocol["backend"] != "ort-cuda"
                or protocol["nchw"] != [1, 3, 384, 640]):
            raise ValueError("Se requiere un recibo ONNX CUDA 1×3×384×640")
        for role in ROLES:
            artifact = onnx_report.with_name(f"{role}.onnx")
            if (report["models"][role]["checkpoint"]["sha256"] != digests[role]
                    or report["artifacts"][role]["onnx"]["sha256"] != sha256_file(artifact).lower()):
                raise ValueError(f"Artefacto ONNX no coincide con el recibo: {role}")
            artifacts[role] = artifact

    def coordinates(item):
        box = item.bounding_box
        return [box.x_min, box.y_min, box.x_max, box.y_max]

    snapshots = frozen["review"]["rule_snapshots"]
    detections, tracking, events, measurements = {}, {}, [], {}
    with strict_ort_sessions() if onnx_report else nullcontext():
        models = make_detectors(specs, artifacts, (384, 640), rect=not onnx_report)
        for source in frozen["manifest"]["sources"]:
            id_, fps = source["id"], source["fps"]
            video = (root / source["media"]).resolve()
            config_path = root / "annotation" / f"{id_}-rules.json"
            if (not video.is_relative_to((root / "media").resolve())
                    or sha256_file(video).lower() != source["hash"]
                    or sha256_file(config_path).lower() != snapshots[id_]):
                raise ValueError(f"Cambió el video o las reglas: {id_}")
            config = load_operational_config(config_path)
            pipeline = DualPerception(**{role: ClassPerceptionChannel(role, models[role][0], ByteTracker(ByteTrackConfig()))
                                        for role in ROLES})
            rules = RuleEngine(config)
            frames = {f["index"]: f for f in frozen["manifest"]["frames"] if f["source"] == id_}
            width, height = next((f["width"], f["height"]) for f in frames.values())
            analyzer = SpatiotemporalAnalyzer(width=width, height=height, fps=fps, zones=config.zones,
                                              proximity_roles=config.proximity_roles, motion=config.motion,
                                              observe_occupants=True)
            window, epoch = None, 0
            capture = cv2.VideoCapture(str(video), cv2.CAP_FFMPEG)
            measurements[id_] = []
            try:
                for index in range(max(frames) + 1):
                    ok, image = capture.read()
                    if not ok:
                        raise ValueError(f"Decodificación incompleta: {id_}/{index}")
                    frame = frames.get(index)
                    if frame is None:
                        continue
                    began = perf_counter()
                    boxes = {role: getattr(pipeline, role).detect(image) for role in ROLES}
                    name = frame["name"]
                    detections[name] = [{"role": role, "xyxy": coordinates(item), "confidence": item.confidence}
                                        for role in ROLES for item in boxes[role]]
                    if frame["window"] is None:
                        continue
                    if window != frame["window"]:
                        window, epoch = frame["window"], epoch + 1
                        pipeline.reset()
                        analyzer.reset(epoch=epoch)
                        rules.reset()
                    tracks = tuple(item for role in ROLES for item in getattr(pipeline, role).track(boxes[role]))
                    visible, _, _ = _visible_tracks(tracks, width, height)
                    spatial = analyzer.update(index, visible, timestamp_s=frame["time_s"])
                    possible = {pair[0] for pair, observation in spatial.occupant_associations.items()
                                if observation.state == "POSSIBLE_OCCUPANT"}
                    tracking[name] = {"epoch": epoch, "tracks": [
                        {"role": item.class_name, "id": item.track_id, "xyxy": coordinates(item),
                         "motion": item.motion.state if item.motion else "UNKNOWN",
                         "occupancy": "POSSIBLE_OCCUPANT" if item.identity in possible else "UNKNOWN"}
                        for item in spatial.objects]}
                    for candidate in rules.evaluate(spatial).candidates:
                        pair = getattr(candidate, "interaction", None)
                        actors = [(obj.class_name, obj.track_id) for obj in (pair.person, pair.forklift)] if pair else [
                            (candidate.class_name, candidate.track_id)]
                        events.append({"source": id_, "frame": index, "epoch": epoch, "rule": candidate.rule_id,
                                       "zone": candidate.zone_id, "version": candidate.rule_version,
                                       "actors": [{"role": role, "id": actor} for role, actor in actors]})
                    measurements[id_].append((perf_counter() - began) * 1000)
            finally:
                capture.release()
    return {"freeze_sha256": expected_sha.lower(), "rule_snapshots": snapshots,
            "model_receipt": {"backend": "onnx-cuda" if onnx_report else "pytorch-fp32-cuda",
                              "weights": digests, "artifacts": {role: sha256_file(file).lower() for role, file in artifacts.items()},
                              "versions": package_versions(), "gpu": torch.cuda.get_device_name(0)},
            "frames": detections, "tracking": tracking, "events": events, "local_frame_ms": measurements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "freeze", "score", "infer"):
        command = commands.add_parser(name)
        command.add_argument("root", type=Path)
        if name == "prepare":
            command.add_argument("source_list", type=Path)
        elif name == "freeze":
            command.add_argument("review", type=Path)
            command.add_argument("exports", type=Path, nargs="+")
        elif name == "score":
            command.add_argument("predictions", type=Path)
            command.add_argument("freeze_sha256")
            command.add_argument("output", type=Path)
        else:
            command.add_argument("freeze_sha256")
            command.add_argument("output", type=Path)
            command.add_argument("--person-weights", type=Path, required=True)
            command.add_argument("--forklift-weights", type=Path, required=True)
            command.add_argument("--onnx-report", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.root, args.source_list)
    elif args.command == "freeze":
        result = freeze(args.root, args.exports, args.review)
    else:
        require_outside_repository(args.output, REPO)
        if args.command == "infer":
            if args.output.exists():
                raise FileExistsError(args.output)
            result = infer(args.root, args.freeze_sha256, args.person_weights, args.forklift_weights, args.onnx_report)
        else:
            result = score(args.root, args.predictions, args.freeze_sha256)
        write(args.output, result)
        result = {"report": str(args.output), "sha256": sha256_file(args.output).lower()}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
