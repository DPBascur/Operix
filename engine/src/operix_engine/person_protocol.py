# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Evaluador PERSON puro: contratos y matching, sin cargar modelos ni imágenes."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import zipfile

from operix_engine.person_metrics import box_iou

PROTOCOL_ID = "PERSON_EVALUATION_PROTOCOL_V1"
DATASET_ID = "PERSON_FINAL_HOLDOUT_V2"
DATASET_SHA = "A71F2558BB5C2A8DF580B6A2908860A9A89F729487BA1C904A14F37C5ADC5339"
MODEL_HASHES = {
    "CURRENT_PERSON": "21766a9dc664fac06da3b0b457e0449f25e1696acbf8e7e39993c4b42282083f",
    "YOLO11N_COCO_PERSON": "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1",
}
INFERENCE = {"imgsz": 640, "confidence_threshold": 0.10, "nms_iou_threshold": 0.70,
             "class_filter": ["person"], "filter_stage": "after_class_aware_nms",
             "device": "cuda:0", "batch_size": 1, "seed": 0, "half": False,
             "rect": True, "augment": False, "agnostic_nms": False, "max_det": 300}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest().upper()


def source_digest(path: Path) -> str:
    """Hash del texto fuente UTF-8 con LF, independiente de core.autocrlf."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest().upper()


def validate_shape(value: object, schema: dict) -> None:
    """Valida el subconjunto cerrado de schemas del protocolo, sin dependencias.

    Soporta type/properties/required/additionalProperties/items/enum/minimum/maximum.
    No se presenta como un validador general de JSON Schema externo.
    """
    types = {"object": dict, "array": list, "string": str, "integer": int,
             "number": (int, float), "boolean": bool, "null": type(None)}
    kind = schema["type"]
    kinds = kind if isinstance(kind, list) else [kind]
    require(any(type(value) in (types[k] if isinstance(types[k], tuple) else (types[k],))
                for k in kinds), "tipo de schema inválido")
    if type(value) in (float, int):
        require(math.isfinite(value), "valor numérico no finito")
        require(value >= schema.get("minimum", -math.inf) and value <= schema.get("maximum", math.inf),
                "valor fuera del schema")
    if "enum" in schema:
        require(value in schema["enum"], "valor ajeno al enum")
    if isinstance(value, dict):
        require(set(schema.get("required", [])) <= value.keys(), "faltan campos del schema")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            require(value.keys() <= properties.keys(), "campos adicionales no permitidos")
        for key, sub in properties.items():
            if key in value:
                validate_shape(value[key], sub)
    if isinstance(value, list) and "items" in schema:
        for item in value:
            validate_shape(item, schema["items"])


def validate_protocol(protocol: dict) -> None:
    require(protocol["protocol_id"] == PROTOCOL_ID and protocol["state"] == "FROZEN", "protocolo no congelado")
    require(protocol["dataset"] == {"id": DATASET_ID, "freeze_sha256": DATASET_SHA,
            "evaluation_images": 91, "gt_boxes": 168, "positive_frames": 67,
            "negative_frames": 24, "multi_person_frames": 42}, "dataset de protocolo incorrecto")
    require(set(protocol["models"]) == set(MODEL_HASHES), "modelos no predeclarados")
    for name, model in protocol["models"].items():
        require(model["sha256"] == MODEL_HASHES[name] and model["inference"] == INFERENCE,
                "modelo/configuración no coincide con el contrato")
        require(model["role"] == ("PRIMARY_CONFIGURATION" if name == "CURRENT_PERSON" else "REFERENCE_BASELINE"),
                "rol del modelo inválido")
    require(protocol["matching"] == {"algorithm": "confidence_greedy_one_to_one_per_image",
            "prediction_order": "confidence_desc_then_stable_index_asc",
            "gt_tie_break": "annotation_id_asc", "primary_iou": .5, "secondary_iou": .75,
            "comparison": ">=", "numeric_tolerance": 0}, "matching distinto del protocolo V1")
    require(protocol["evaluation_status"] == "PERSON_MODEL_EVALUATION_NOT_STARTED", "estado de protocolo incorrecto")
    require(protocol["primary_metrics"] == ["TP", "FP", "FN", "precision", "recall", "F1"] and
            set(protocol["secondary_metrics"]) == {"iou_075", "negative_frame_false_alarm_rate",
                "positive_frame_complete_miss_rate", "multi_person_recall"}, "métricas no predeclaradas")
    validate_shape(protocol, protocol["artifact_schemas"]["protocol"])


def validate_dataset(records: list[dict], protocol: dict, freeze_sha: str) -> None:
    require(freeze_sha == protocol["dataset"]["freeze_sha256"], "dataset freeze SHA incorrecto")
    require(len(records) == protocol["dataset"]["evaluation_images"], "se esperan 91 registros")
    require(len({r["image_id"] for r in records}) == len(records) and
            len({r["image_sha256"] for r in records}) == len(records), "imagen duplicada")
    require(all(r["evaluation_included"] for r in records), "registro excluido en evaluation")
    require({r["source_group"] for r in records} == {f"HOLDOUT_PERSON_{i}" for i in range(101, 106)},
            "familias distintas de las congeladas")
    n = Counter("positive" if r["person_boxes"] else "negative" for r in records)
    require(sum(r["person_boxes"] for r in records) == protocol["dataset"]["gt_boxes"] and
            n["positive"] == protocol["dataset"]["positive_frames"] and
            n["negative"] == protocol["dataset"]["negative_frames"] and
            sum(r["person_boxes"] > 1 for r in records) == protocol["dataset"]["multi_person_frames"],
            "conteos de GT distintos del freeze")
    for row in records:
        require(len(row["ground_truth"]) == row["person_boxes"], "anotaciones GT incompletas")
        ids = [g["annotation_id"] for g in row["ground_truth"]]
        require(len(set(ids)) == len(ids) and all(type(i) is int for i in ids), "IDs GT inválidos")
        for gt in row["ground_truth"]:
            validate_box(gt["bbox_xyxy"])


def ground_truth_records(root: Path, evaluation_manifest: dict) -> list[dict]:
    """Lee solo COCO original y manifests; preserva annotation_id, sin abrir imágenes."""
    require(evaluation_manifest["freeze_sha256"] == DATASET_SHA, "dataset freeze SHA incorrecto")
    records = []
    for group in sorted({r["source_group"] for r in evaluation_manifest["records"]}):
        archive = (root / "04-exports" / group / "annotations.zip").resolve()
        require(archive.is_relative_to(root.resolve()), "export fuera del holdout")
        subset = [r for r in evaluation_manifest["records"] if r["source_group"] == group]
        require(all(hashlib.sha256(archive.read_bytes()).hexdigest().upper() == r["annotation_export_sha256"]
                    for r in subset), "export humano alterado")
        with zipfile.ZipFile(archive) as z:
            raw = z.read("annotations/instances_default.json")
        data = json.loads(raw)
        require(all(hashlib.sha256(raw).hexdigest().upper() == r["annotation_json_sha256"] for r in subset),
                "JSON humano alterado")
        require(len(data["categories"]) == 1 and data["categories"][0]["name"] == "person", "clase GT distinta")
        for row in subset:
            image = next(i for i in data["images"] if i["id"] == row["coco_image_id"])
            require(image["file_name"] == row["filename"], "imagen GT distinta")
            gt = []
            for a in data["annotations"]:
                if a["image_id"] == image["id"]:
                    x, y, w, h = a["bbox"]
                    gt.append({"annotation_id": a["id"], "bbox_xyxy": [x, y, x+w, y+h]})
            records.append({**row, "ground_truth": sorted(gt, key=lambda g: g["annotation_id"])})
    return sorted(records, key=lambda r: (r["source_group"], r["filename"]))


def validate_box(box: list) -> None:
    require(isinstance(box, list) and len(box) == 4 and
            all(type(v) in (int, float) and math.isfinite(v) for v in box) and
            box[0] < box[2] and box[1] < box[3], "bbox xyxy inválida")


def match(ground_truth: list[dict], predictions: list[dict], threshold: float,
          confidence: float = .10) -> dict:
    unmatched = {g["annotation_id"]: g for g in ground_truth}
    require(len(unmatched) == len(ground_truth), "annotation_id duplicado")
    indices = [p["stable_index"] for p in predictions]
    require(len(set(indices)) == len(indices), "stable_index duplicado")
    accepted = [p for p in predictions if p["class_name"] == "person" and p["confidence"] >= confidence]
    tp, fp, assignments = 0, 0, []
    for p in sorted(accepted, key=lambda p: (-p["confidence"], p["stable_index"])):
        options = [(box_iou(tuple(p["bbox_xyxy"]), tuple(g["bbox_xyxy"])), gid)
                   for gid, g in unmatched.items()]
        best = min(options, key=lambda x: (-x[0], x[1])) if options else None
        if best is not None and best[0] >= threshold:
            tp += 1
            del unmatched[best[1]]
            assignments.append({"prediction_index": p["stable_index"], "annotation_id": best[1], "iou": best[0]})
        else:
            fp += 1
    return {"tp": tp, "fp": fp, "fn": len(unmatched), "accepted_predictions": len(accepted),
            "assignments": assignments}


def metrics(items: list[dict]) -> dict:
    tp, fp, fn = (sum(r[k] for r in items) for k in ("tp", "fp", "fn"))
    precision = tp / (tp+fp) if tp+fp else None
    recall = tp / (tp+fn) if tp+fn else None
    # Direct count formula: zero if GT exists but none matched; null if there is no denominator.
    f1 = 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def evaluate(records: list[dict], raw: dict, protocol: dict, runtime: dict) -> dict:
    """Solo recibe datos; en esta tarea se llama exclusivamente con fixtures sintéticos."""
    validate_protocol(protocol)
    validate_shape(raw, protocol["artifact_schemas"]["raw_predictions"])
    require(raw["protocol_id"] == PROTOCOL_ID and raw["protocol_sha256"] == digest(protocol), "protocol SHA incorrecto")
    require(raw["dataset_id"] == DATASET_ID, "dataset id incorrecto")
    validate_dataset(records, protocol, raw["dataset_freeze_sha256"])
    require(raw["model_id"] in protocol["models"], "modelo no predeclarado")
    model = protocol["models"][raw["model_id"]]
    require(raw["model_sha256"] == model["sha256"], "model SHA incorrecto")
    require(raw["inference_configuration"] == model["inference"], "configuración de inferencia distinta")
    require(raw["software_versions"] == protocol["software_versions"], "software distinto del protocolo")
    frames = {f["image_id"]: f for f in raw["frames"]}
    require(len(frames) == len(raw["frames"]) == len(records) and
            set(frames) == {r["image_id"] for r in records}, "predicciones faltantes o imágenes duplicadas")
    primary, secondary, families, per_frame = [], [], {}, []
    neg_fp = complete_miss = 0
    multi = []
    for row in sorted(records, key=lambda r: (r["source_group"], r["filename"])):
        frame = frames[row["image_id"]]
        require(frame["image_sha256"] == row["image_sha256"], "SHA de imagen incorrecto")
        for p in frame["predictions"]:
            validate_box(p["bbox_xyxy"])
        first = match(row["ground_truth"], frame["predictions"], .5)
        second = match(row["ground_truth"], frame["predictions"], .75)
        primary.append(first)
        secondary.append(second)
        families.setdefault(row["source_group"], []).append(first)
        neg_fp += row["person_boxes"] == 0 and first["fp"] > 0
        complete_miss += row["person_boxes"] > 0 and first["tp"] == 0
        if row["person_boxes"] > 1:
            multi.append(first)
        per_frame.append({"image_id": row["image_id"], "family": row["source_group"],
                          "primary": first, "secondary": second})
    result = {"protocol_id": PROTOCOL_ID, "protocol_sha256": digest(protocol),
        "dataset_freeze_sha256": raw["dataset_freeze_sha256"], "model_id": raw["model_id"],
        "model_role": model["role"], "overall": metrics(primary),
        "per_family": {g: metrics(v) for g, v in sorted(families.items())},
        "secondary": {"iou_075": metrics(secondary),
            "negative_frame_false_alarm_rate": {"numerator": neg_fp, "denominator": 24, "rate": neg_fp/24},
            "positive_frame_complete_miss_rate": {"numerator": complete_miss, "denominator": 67, "rate": complete_miss/67},
            "multi_person_recall": {"frames": len(multi), "tp": sum(x["tp"] for x in multi),
                                    "gt": sum(x["tp"]+x["fn"] for x in multi), "recall": metrics(multi)["recall"]}},
        "prediction_counts": {"received": sum(len(f["predictions"]) for f in raw["frames"]),
                              "accepted_person": sum(x["accepted_predictions"] for x in primary)},
        "gt_counts": {"images": len(records), "boxes": sum(r["person_boxes"] for r in records)},
        "per_frame": per_frame, "runtime_metadata": runtime}
    validate_shape(result, protocol["artifact_schemas"]["results"])
    return result


def seal_run(output: Path, raw: dict, result: dict, protocol: dict, metadata: dict) -> dict:
    """Futuro sellado fuera de Git, sin sobrescritura y antes de inspección visual."""
    require(not output.resolve().is_relative_to(Path(__file__).resolve().parents[3]), "outputs deben quedar fuera de Git")
    require(not output.exists(), "corrida existente: nunca sobrescribir o escoger el mejor intento")
    validate_shape(raw, protocol["artifact_schemas"]["raw_predictions"])
    validate_shape(result, protocol["artifact_schemas"]["results"])
    validate_protocol(protocol)
    require(raw["model_id"] in protocol["models"], "modelo no predeclarado")
    model = protocol["models"][raw["model_id"]]
    require(raw["model_sha256"] == model["sha256"] and raw["inference_configuration"] == model["inference"]
            and raw["software_versions"] == protocol["software_versions"] and
            raw["dataset_freeze_sha256"] == DATASET_SHA and raw["dataset_id"] == DATASET_ID and
            len(raw["frames"]) == 91, "contrato de corrida distinto")
    require(result["protocol_sha256"] == raw["protocol_sha256"] == digest(protocol) and
            result["model_id"] == raw["model_id"] and result["dataset_freeze_sha256"] == DATASET_SHA,
            "resultados y predicciones no corresponden")
    receipt = {"protocol_id": PROTOCOL_ID, "protocol_sha256": digest(protocol), "dataset_id": DATASET_ID,
        "dataset_freeze_sha256": DATASET_SHA, "model_id": raw["model_id"], "model_sha256": raw["model_sha256"],
        "inference_configuration": raw["inference_configuration"], "number_of_images": len(raw["frames"]),
        "prediction_artifact_sha256": digest(raw), "metrics_artifact_sha256": digest(result),
        "status": "SEALED_VALID_RUN", "runtime": metadata}
    validate_shape(receipt, protocol["artifact_schemas"]["run_receipt"])
    output.mkdir(parents=True)
    for filename, value in (("raw-predictions.json", raw), ("metrics.json", result), ("run-receipt.json", receipt)):
        with (output / filename).open("xb") as stream:
            stream.write(canonical(value))
    return receipt


def technical_invalidation(receipt: dict, *, bug: str, correction: str, regression_tests: str) -> dict:
    """Registro posterior separado; nunca reescribe los resultados del intento fallido."""
    require(all(isinstance(v, str) and v.strip() for v in (bug, correction, regression_tests)),
            "requiere documentar bug/corrección/tests sin seleccionar por rendimiento")
    return {"status": "INVALIDATED_TECHNICAL_RUN", "original_receipt_sha256": digest(receipt),
            "protocol_sha256": receipt["protocol_sha256"], "dataset_freeze_sha256": receipt["dataset_freeze_sha256"],
            "model_id": receipt["model_id"], "model_sha256": receipt["model_sha256"],
            "inference_configuration": receipt["inference_configuration"], "bug": bug,
            "correction": correction, "regression_tests": regression_tests,
            "rerun_constraint": "same dataset, models and thresholds; original attempt remains invalidated, never best-of"}
