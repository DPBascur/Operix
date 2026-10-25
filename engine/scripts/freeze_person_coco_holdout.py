# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Congela COCO humano con deduplicación binaria explícita, sin decodificar imágenes."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import zipfile


SCHEMA = "PERSON_COCO_PREFREEZE_V1"
POLICY = "FIRST_STABLE_OCCURRENCE_BY_FAMILY_AND_FRAME"
FINAL = "final/holdout-freeze-manifest.json"
EVALUATION = "final/person-evaluation-manifest.json"
RECEIPT = "06-freeze/person-final-holdout-v2-freeze.json"
REGISTER = "06-freeze/frozen-exclusion-register.json"
EXCLUDED_USES = ["training", "fine_tuning", "calibration", "confidence_threshold_selection",
                 "nms_threshold_selection", "rule_threshold_selection", "model_selection",
                 "development_diagnostics", "performance_tuning"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def canonical_bytes(value: object) -> bytes:
    """UTF-8, claves ordenadas, sin espacios, sin NaN y un LF terminal."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), "referencia fuera del root")
    return path


def deduplicate(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """No elimina archivos ni cajas; la identidad binaria decide, nunca un modelo."""
    ordered = sorted(records, key=lambda r: (r["source_group"], r["filename"]))
    require(len({(r["source_group"], r["filename"]) for r in ordered}) == len(ordered),
            "identificadores de frame repetidos")
    seen, final, excluded = {}, [], []
    for row in ordered:
        digest = row["image_sha256"].upper()
        if digest in seen:
            retained = seen[digest]
            # Incluso bytes idénticos requieren coherencia de las anotaciones humanas.
            require(row["human_boxes"] == retained["human_boxes"],
                    "anotaciones humanas incompatibles en imágenes idénticas")
            excluded.append({**row, "evaluation_included": False,
                             "exclusion_reason": "EXACT_SHA256_DUPLICATE",
                             "retained_record": retained["filename"]})
        else:
            kept = {**row, "evaluation_included": True}
            final.append(kept)
            seen[digest] = kept
    return final, excluded


def counts(records: list[dict]) -> dict:
    return {"frames": len(records), "positive_frames": sum(r["person_boxes"] > 0 for r in records),
            "negative_frames": sum(r["person_boxes"] == 0 for r in records),
            "person_boxes": sum(r["person_boxes"] for r in records),
            "multi_person_frames": sum(r["person_boxes"] > 1 for r in records),
            "max_persons_per_frame": max((r["person_boxes"] for r in records), default=0)}


def validate_coco(data: dict, records: list[dict]) -> dict[str, list]:
    cats, images, annotations = (data[k] for k in ("categories", "images", "annotations"))
    require(len(cats) == 1 and cats[0]["name"] == "person", "categoría distinta de person")
    for objects in (cats, images, annotations):
        ids = [o["id"] for o in objects]
        require(all(type(i) is int and i >= 0 for i in ids) and len(set(ids)) == len(ids),
                "IDs inválidos o duplicados")
    by_name = {im["file_name"]: im for im in images}
    by_id = {im["id"]: im for im in images}
    require(len(by_name) == len(images) == len(records) and
            set(by_name) == {r["filename"] for r in records}, "cobertura COCO incorrecta")
    boxes = {name: [] for name in by_name}
    for ann in annotations:
        require(ann["image_id"] in by_id and ann["category_id"] == cats[0]["id"],
                "referencia de anotación inválida")
        im = by_id[ann["image_id"]]
        b = ann["bbox"]
        require(isinstance(b, list) and len(b) == 4 and
                all(type(v) in (int, float) and math.isfinite(v) for v in b), "bbox no finita")
        x, y, w, h = b
        require(x >= 0 and y >= 0 and w > 0 and h > 0 and x+w <= im["width"] and
                y+h <= im["height"] and ann.get("iscrowd", 0) == 0, "geometría/persona inválida")
        require(b not in boxes[im["file_name"]], "caja humana duplicada exacta")
        boxes[im["file_name"]].append(b)
    for row in records:
        im = by_name[row["filename"]]
        require(im["id"] == row["coco_image_id"] and
                all(type(im[k]) is int and im[k] == int(row[k]) for k in ("width", "height")),
                "metadata de imagen no coincide")
        require(len(boxes[row["filename"]]) == row["person_boxes"], "conteo humano no coincide")
        boxes[row["filename"]].sort()
    return boxes


def verify(root: Path) -> dict:
    """Valida el recibo y TODOS los inputs sellados, incluidos manifests de exclusión."""
    receipt = load(root / RECEIPT)
    manifest = load(root / FINAL)
    evaluation = load(root / EVALUATION)
    require(receipt["schema"] == manifest["schema"] == SCHEMA and manifest["state"] == "FROZEN",
            "schema/estado inválido")
    require((root / FINAL).read_bytes() == canonical_bytes(manifest), "serialización no canónica")
    require(sha(root / FINAL) == receipt["PERSON_FINAL_HOLDOUT_V2_FREEZE_SHA256"], "freeze alterado")
    expected = [r for r in manifest["frame_records"] if r["evaluation_included"]]
    require(evaluation["records"] == expected and len(expected) == len({r["image_sha256"] for r in expected}),
            "evaluation manifest no coincide o contiene duplicados")
    require(counts(expected) == manifest["evaluation_counts"], "conteos congelados inconsistentes")
    require(evaluation["freeze_sha256"] == sha(root / FINAL), "evaluation sin vínculo al freeze")
    for relative, digest in receipt["sealed_files_sha256"].items():
        require(sha(inside(root, relative)) == digest, f"artefacto sellado alterado: {relative}")
    for relative, digest in manifest["original_inputs_sha256"].items():
        require(sha(inside(root, relative)) == digest, f"input original alterado: {relative}")
    for entry in manifest["leakage_audit"]["manifests"]:
        path = inside(root.parent, entry["manifest"])
        require(sha(path) == entry["sha256"], "manifest externo alterado")
    return {"state": "PERSON_FINAL_HOLDOUT_V2_FROZEN", "evaluation_images": len(expected),
            "freeze_sha256": sha(root / FINAL), "evaluation_status": "PERSON_MODEL_EVALUATION_NOT_STARTED"}


def freeze(root: Path, attestation_path: Path) -> dict:
    root = root.resolve()
    repository = Path(__file__).resolve().parents[2]
    require(not root.is_relative_to(repository), "datos deben estar fuera de Git")
    targets = [root / p for p in (FINAL, EVALUATION, RECEIPT, REGISTER)]
    if any(p.exists() for p in targets):
        raise FileExistsError("freeze existente/parcial: no sobrescribir; requiere revisión/versionado")
    candidate = load(root / "final/candidate-qa-manifest.json")
    require(candidate["dataset_id"] == "PERSON_FINAL_HOLDOUT_V2", "dataset incorrecto")
    for relative, digest in candidate["original_inputs_sha256"].items():
        require(sha(inside(root, relative)) == digest, f"input original alterado: {relative}")
    qa_path = root / "05-qa/final-coco-audit/coco-integrity-qa.json"
    require(sha(qa_path) == candidate["qa_sha256"], "QA anterior alterado")
    qa = load(qa_path)
    require(all(i["code"] == "EXACT_DUPLICATE_FRAME_BYTES" for i in qa["issues"]),
            "QA contiene bloqueos ajenos a deduplicación")
    attestation = load(attestation_path)
    require(attestation_path.resolve().is_relative_to(root), "atestación debe archivarse dentro del holdout")
    require(attestation["dataset_id"] == candidate["dataset_id"] and
            attestation["annotator"] and attestation["attestor"] and attestation["declared_at_utc"],
            "atestación incompleta")
    required = ("manual_annotations", "no_model_generated_annotations", "no_model_assisted_box_generation",
                "no_automatic_box_correction", "no_project_model_access_before_freeze",
                "controlled_development_independence_attested", "local_registry_coverage_attested")
    require(all(attestation.get(k) is True for k in required), "falta atestación humana requerida")
    require(set(attestation["excluded_uses"]) == set(EXCLUDED_USES), "usos excluidos incompletos")
    require(attestation["external_pretraining_independence_claimed"] is False,
            "no puede atestarse independencia de pretraining externo")
    records = [dict(r) for r in candidate["frame_records"]]
    sources = candidate["families"]
    require(len(sources) == len({s["source_family"] for s in sources}) == 5, "faltan cinco familias")
    require(set(attestation["source_groups"]) == {s["family"] for s in sources}, "atestación de familias incompleta")
    for source in sources:
        group = source["family"]
        subset = [r for r in records if r["source_group"] == group]
        archive = root / "04-exports" / group / "annotations.zip"
        require(sha(archive) == source["export_sha256"], "export alterado")
        with zipfile.ZipFile(archive) as z:
            require(z.testzip() is None and z.namelist() == ["annotations/instances_default.json"], "ZIP inválido")
            raw = z.read("annotations/instances_default.json")
        require(hashlib.sha256(raw).hexdigest().upper() == source["json_sha256"], "JSON COCO alterado")
        boxes = validate_coco(json.loads(raw), subset)
        for row in subset:
            # Only coordinates for duplicate-consistency checking, stored outside Git.
            row["human_boxes"] = boxes[row["filename"]]
            require(row["annotation_export_sha256"] == source["export_sha256"] and
                    row["annotation_json_sha256"] == source["json_sha256"], "vínculo COCO de frame inválido")
    evaluated, excluded = deduplicate(records)
    require(len(records) == len(evaluated)+len(excluded), "partición inconsistente")
    require(len(excluded) == len(records)-len({r["image_sha256"] for r in records}), "deduplicación inconsistente")
    audit_path = root / "05-qa/final-coco-audit/independence-documentary-audit.json"
    require(sha(audit_path) == candidate["documentary_audit_sha256"], "auditoría anterior alterada")
    leakage = load(audit_path)
    require(leakage["matching_rows"] == 0, "auditoría previa encontró leakage")
    hashes = {r["image_sha256"].upper() for r in records} | {r["video_sha256"].upper() for r in records}
    names = {r["filename"].casefold() for r in records}
    identities = {r[k] for r in records for k in ("source_group", "source_family", "source_reference")}
    checked_rows = 0
    for entry in leakage["manifests"]:
        path = inside(root.parent, entry["manifest"])
        require(not any(x in str(path).lower() for x in ("test2", "real_holdout", "real-holdout")),
                "referencia protegida no permitida")
        require(sha(path) == entry["sha256"], "manifest de desarrollo alterado")
        with path.open(encoding="utf-8-sig", newline="") as stream:
            previous = list(csv.DictReader(stream))
        require(len(previous) == entry["rows"], "conteo de manifest previo distinto")
        checked_rows += len(previous)
        for row in previous:
            values = [v for v in row.values() if isinstance(v, str) and v]
            require(not any(v.upper() in hashes or v in identities or
                            Path(v.replace("\\", "/")).name.casefold() in names for v in values),
                    "coincidencia de hash/nombre/identidad con desarrollo")
    require(checked_rows == leakage["rows_compared"], "cobertura del registro inconsistente")
    timestamp = datetime.now(timezone.utc).isoformat()
    all_records = sorted(evaluated+excluded, key=lambda r: (r["source_group"], r["filename"]))
    manifest = {"schema": SCHEMA, "dataset_id": candidate["dataset_id"], "state": "FROZEN",
        "original_sampled_records": len(records), "unique_evaluation_images": len(evaluated),
        "deduplicated_records": len(excluded), "original_counts": counts(records),
        "evaluation_counts": counts(evaluated), "families": sources, "frame_records": all_records,
        "exact_duplicate_policy": POLICY, "annotation_policy_version": candidate["annotation_policy_version"],
        "deduplication_decisions": [{"retained_record": r["retained_record"],
                                     "excluded_record": r["filename"], "image_sha256": r["image_sha256"],
                                     "reason": r["exclusion_reason"]} for r in excluded],
        "deduplication_basis": "exact binary duplicate removal before locked evaluation; no model results used",
        "annotation_policy": attestation["annotation_policy"],
        "provenance_state": candidate["provenance_status"], "rights_state": candidate["rights_status"],
        "independence_state": "ATTESTED_WITHIN_CONTROLLED_OPERIX_DEVELOPMENT",
        "attestation": attestation, "attestation_sha256": sha(attestation_path),
        "candidate_manifest_sha256": sha(root / "final/candidate-qa-manifest.json"),
        "original_inputs_sha256": {**candidate["original_inputs_sha256"],
                                   "final/candidate-qa-manifest.json": sha(root / "final/candidate-qa-manifest.json"),
                                   qa_path.relative_to(root).as_posix(): sha(qa_path),
                                   audit_path.relative_to(root).as_posix(): sha(audit_path),
                                   attestation_path.resolve().relative_to(root).as_posix(): sha(attestation_path)},
        "qa_references": {"structural_geometry_category": candidate["qa_sha256"],
                          "documentary_audit": candidate["documentary_audit_sha256"]},
        "leakage_audit": {"manifests": leakage["manifests"], "rows_rechecked": checked_rows,
                          "matches": 0, "coverage_limitations": leakage["coverage_limitations"]},
        "frozen_at_utc": timestamp, "tools": {"tool": SCHEMA, "python": platform.python_version(),
                                              "script_sha256": sha(Path(__file__))},
        "evaluation_protocol_state": "PERSON_EVALUATION_PROTOCOL_V1_NOT_YET_FROZEN",
        "evaluation_status": "PERSON_MODEL_EVALUATION_NOT_STARTED",
        "post_freeze_changes_require": "PERSON_FINAL_HOLDOUT_V3_OR_NEW_IDENTIFIER"}
    frozen_bytes = canonical_bytes(manifest)
    freeze_sha = hashlib.sha256(frozen_bytes).hexdigest().upper()
    evaluation = {"dataset_id": candidate["dataset_id"], "freeze_sha256": freeze_sha,
                  "records": evaluated, "counts": counts(evaluated),
                  "model_access_allowed": False, "evaluation_status": manifest["evaluation_status"]}
    register = {"dataset_id": candidate["dataset_id"], "state": "FROZEN", "freeze_sha256": freeze_sha,
                "excluded_uses": EXCLUDED_USES, "model_access_allowed": False,
                "original_sampled_records": len(records), "evaluation_images": len(evaluated),
                "families": sorted({r["source_group"] for r in records}), "records": all_records}
    outputs = {FINAL: frozen_bytes, EVALUATION: canonical_bytes(evaluation), REGISTER: canonical_bytes(register)}
    receipt = {"schema": SCHEMA, "state": "PERSON_FINAL_HOLDOUT_V2_FROZEN",
               "PERSON_FINAL_HOLDOUT_V2_FREEZE_SHA256": freeze_sha,
               "sealed_files_sha256": {p: hashlib.sha256(b).hexdigest().upper() for p, b in outputs.items()}}
    # All gates pass before writing; receipt written last. Partial outputs cannot be overwritten.
    for relative, content in {**outputs, RECEIPT: canonical_bytes(receipt)}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(content)
    return verify(root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--attestation", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify and args.attestation is None:
        parser.error("--attestation es obligatorio para freeze")
    print(json.dumps(verify(args.root) if args.verify else freeze(args.root, args.attestation), indent=2))
