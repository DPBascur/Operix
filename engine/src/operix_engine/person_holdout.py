# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contratos puros para adquirir un holdout PERSON aislado de entrenamiento."""

from __future__ import annotations

import hashlib
import csv
import json
import re
from pathlib import Path


CANDIDATE = "LOCKED_EVALUATION_CANDIDATE"
FROZEN = "LOCKED_EVALUATION_FROZEN"
GROUP_PATTERN = re.compile(r"HOLDOUT_PERSON_[0-9]{3,}")
RIGHTS_BASES = {"USER_ORIGINAL_RECORDING", "EXPLICIT_PERMISSION", "CC_BY_VERIFIED",
                "OTHER_VERIFIED_LICENSE"}


def validate_final_source(meta: dict) -> None:
    """La declaración y su referencia deben revisarse humanamente antes del freeze."""
    required = ("source_family", "recorded_by", "camera_or_source",
                "location_context_general", "provenance_reference", "rights_evidence")
    if any(not isinstance(meta.get(key), str) or not meta[key].strip() or meta[key].strip().upper() in
           {"UNKNOWN", "UNVERIFIED", "TBD", "PENDING"} for key in required):
        raise ValueError("procedencia final incompleta")
    if meta.get("provenance_status") != "KNOWN_PROVENANCE" or (
            meta.get("rights_basis") not in RIGHTS_BASES or
            meta.get("rights_status") != "RIGHTS_CONFIRMED" or
            meta.get("consent_or_permission_status") != "CONFIRMED"):
        raise ValueError("procedencia o derechos finales no confirmados")


def audit_exclusions(root: Path, records: list[dict], video_hashes: set[str]) -> dict:
    """Registro local explícito: campaña (incluye TEST3), YouTube y training/development."""
    policy_path = root / "holdout-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if (policy.get("protocol_version") != "PERSON_FINAL_HOLDOUT_V2" or
            policy.get("training_development_coverage_confirmed") is not True or
            policy.get("no_model_access_attested") is not True):
        raise ValueError("cobertura de exclusiones/acceso a modelos sin confirmar")
    entries = policy.get("exclusion_manifests", [])
    if {entry.get("role") for entry in entries} != {
            "campaign", "youtube_diagnostic", "training_development"}:
        raise ValueError("faltan registros de exclusión obligatorios")
    current_images = {row["image_sha256"].upper() for row in records}
    current_groups = {row["source_group"] for row in records}
    current_families = {row["source_family"] for row in records if row.get("source_family")}
    checked = []
    for entry in entries:
        if not isinstance(entry.get("path"), str) or not entry["path"]:
            raise ValueError("registro de exclusión pendiente")
        path = Path(entry["path"])
        if not path.is_absolute() or sha256_file(path) != entry.get("sha256"):
            raise ValueError("registro de exclusión ausente o alterado")
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not {"image_sha256", "source_group"} <= set(reader.fieldnames or []):
                raise ValueError("registro de exclusión sin SHA/grupo")
            excluded = list(reader)
        if any((row["image_sha256"].upper() in current_images or
                row["source_group"] in current_groups or
                row.get("source_family", "") in current_families or
                row.get("video_sha256", "").upper() in video_hashes)
               for row in excluded):
            raise ValueError("leakage con material excluido")
        checked.append({"role": entry["role"], "sha256": entry["sha256"],
                        "records": len(excluded)})
    return {"policy_sha256": sha256_file(policy_path), "exclusions": checked}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_source_group(group: str) -> str:
    if not GROUP_PATTERN.fullmatch(group):
        raise ValueError("source_group debe seguir HOLDOUT_PERSON_###")
    return group


def sample_indices(frame_count: int, fps: float, *, sample_count: int | None = None,
                   interval_seconds: float | None = None) -> tuple[int, ...]:
    """Muestreo temporal fijo, sin consultar detecciones ni contenido del frame."""
    if frame_count < 1 or fps <= 0 or (sample_count is None) == (interval_seconds is None):
        raise ValueError("indica exactamente un tamaño o intervalo y video válido")
    if sample_count is not None:
        if not 1 <= sample_count <= frame_count:
            raise ValueError("sample_count fuera de rango")
        if sample_count == 1:
            return (frame_count // 2,)
        return tuple(round(i * (frame_count - 1) / (sample_count - 1))
                     for i in range(sample_count))
    if interval_seconds is None or interval_seconds <= 0:
        raise ValueError("interval_seconds debe ser positivo")
    step = max(1, round(interval_seconds * fps))
    return tuple(range(0, frame_count, step))


def require_outside_repository(output: Path, repository: Path) -> None:
    if output.resolve().is_relative_to(repository.resolve()):
        raise ValueError("videos y anotaciones del holdout deben permanecer fuera de Git")


def guard_holdout_assignment(source_groups: set[str], assignments: dict[str, str]) -> None:
    """Impide asignar grupos reservados a train/calibration u otros usos."""
    conflicts = {group: assignments[group] for group in source_groups
                 if group in assignments and assignments[group] != "LOCKED_EVALUATION"}
    if conflicts:
        raise ValueError(f"source_groups reservados fuera de LOCKED_EVALUATION: {conflicts}")


def group_manifests(root: Path) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / "01-ingested").glob("*.json"))]


def verify_frozen(root: Path) -> dict:
    """Comprueba que el freeze y todos los artefactos que referencia siguen intactos."""
    freeze = json.loads((root / "06-freeze" / "freeze.json").read_text(encoding="utf-8"))
    frozen_json = root / "final" / "locked-evaluation-manifest.json"
    frozen_csv = root / "final" / "locked-evaluation-manifest.csv"
    if freeze.get("status") != FROZEN or not freeze.get("independence_attested") or (
            sha256_file(frozen_json) != freeze.get("manifest_json_sha256") or
            sha256_file(frozen_csv) != freeze.get("manifest_csv_sha256")):
        raise ValueError("freeze o manifests alterados")
    payload = json.loads(frozen_json.read_text(encoding="utf-8"))
    if freeze.get("protocol_version") == "PERSON_FINAL_HOLDOUT_V2":
        if sha256_file(root / "holdout-policy.json") != freeze["exclusion_audit"]["policy_sha256"]:
            raise ValueError("política de exclusión alterada")
    with frozen_csv.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if rows != payload.get("records") or len(rows) != freeze.get("images") or (
            set(freeze.get("source_groups", [])) != {r["source_group"] for r in rows}):
        raise ValueError("registros del freeze inconsistentes")
    if ({source["source_group"] for source in freeze.get("sources", [])} !=
            set(freeze["source_groups"]) or
            len(freeze.get("sources", [])) != len(freeze["source_groups"])):
        raise ValueError("fuentes del freeze inconsistentes")
    for source in freeze.get("sources", []):
        group = validate_source_group(source["source_group"])
        manifest_path = root / "01-ingested" / f"{group}.json"
        if sha256_file(manifest_path) != source["source_manifest_sha256"]:
            raise ValueError(f"metadata de origen alterada: {group}")
        meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        video = (root / meta["stored_video"]).resolve()
        export = root / "04-exports" / group / "annotations.zip"
        if not video.is_relative_to(root.resolve()) or (
                sha256_file(video) != source["source_video_sha256"] or
                sha256_file(export) != source["export_sha256"]):
            raise ValueError(f"video/export alterado: {group}")
        if (sha256_file(root / "04-exports" / group / "review.csv") !=
                source["review_sha256"] or
                sha256_file(root / "04-exports" / group / "completion.json") !=
                source["completion_sha256"] or
                sha256_file(root / "final" / group / "verified-manifest.csv") !=
                source["verified_manifest_sha256"] or
                sha256_file(root / "05-qa" / f"{group}.json") != source["qa_sha256"]):
            raise ValueError(f"revisión/QA alterados: {group}")
    for row in rows:
        group = row["source_group"]
        name = row["filename"]
        if Path(name).name != name or row["evaluation_status"] != FROZEN or (
                sha256_file(root / "02-frame-samples" / group / name) != row["image_sha256"] or
                sha256_file(root / "final" / group / "labels" /
                            (Path(name).stem + ".txt")) != row["label_sha256"]):
            raise ValueError(f"frame/label alterado: {group}/{name}")
    if freeze.get("protocol_version") == "PERSON_FINAL_HOLDOUT_V2":
        current_audit = audit_exclusions(root, rows,
            {source["source_video_sha256"] for source in freeze["sources"]})
        if current_audit != freeze["exclusion_audit"]:
            raise ValueError("auditoría de exclusiones alterada")
    return freeze


def acquisition_readiness(root: Path, *, minimum_groups: int = 3) -> dict:
    status_path = root / "dataset-status.json"
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        if status.get("role") == "DIAGNOSTIC_ONLY":
            return {"decision": "PERSON_YOUTUBE_DIAGNOSTIC_SET_PRESERVED",
                    "reason": "NOT_LOCKED_EVALUATION"}
    groups = group_manifests(root)
    if not groups:
        return {"decision": "PERSON_HOLDOUT_ACQUISITION_READY", "groups": 0,
                "reason": "pipeline preparado; faltan videos independientes"}
    if len({item.get("source_group") for item in groups}) != len(groups) or any(
        item.get("evaluation_status") != CANDIDATE or item.get("role") != "HOLDOUT_ONLY"
        for item in groups):
        return {"decision": "PERSON_HOLDOUT_BLOCKED", "groups": len(groups),
                "reason": "metadata duplicada o aislamiento inválido"}
    frozen = root / "06-freeze" / "freeze.json"
    if frozen.exists():
        try:
            verify_frozen(root)
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return {"decision": "PERSON_HOLDOUT_BLOCKED", "groups": len(groups),
                    "reason": f"freeze inválido: {exc}"}
        return {"decision": "PERSON_EVALUATION_READY", "groups": len(groups),
                "reason": "freeze íntegro y atestación registrada"}
    completed = 0
    positives = negatives = 0
    completed_records = []
    for item in groups:
        group = item["source_group"]
        verified = root / "final" / group / "verified-manifest.csv"
        qa_path = root / "05-qa" / f"{group}.json"
        if not verified.is_file() or not qa_path.is_file():
            continue
        try:
            qa = json.loads(qa_path.read_text(encoding="utf-8"))
            with verified.open(newline="", encoding="utf-8") as stream:
                records = list(csv.DictReader(stream))
            if (not qa.get("completed") or qa.get("blocking_issues") != 0 or
                    sha256_file(verified) != qa.get("verified_manifest_sha256") or
                    sha256_file(root / "04-exports" / group / "annotations.zip") !=
                    qa.get("export_sha256") or
                    sha256_file(root / "04-exports" / group / "review.csv") !=
                    qa.get("review_sha256") or
                    sha256_file(root / "04-exports" / group / "completion.json") !=
                    qa.get("completion_sha256") or
                    any(row["annotation_status"] not in {"HUMAN_VERIFIED", "VERIFIED_NEGATIVE"}
                        for row in records)):
                raise ValueError("QA, recibo o manifest incompletos/alterados")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return {"decision": "PERSON_HOLDOUT_BLOCKED", "groups": len(groups),
                    "reason": f"grupo {group}: {exc}"}
        completed += 1
        completed_records.extend({**row, "source_family": item.get("source_family", "")}
                                 for row in records)
        positives += sum(row["annotation_status"] == "HUMAN_VERIFIED" for row in records)
        negatives += sum(row["annotation_status"] == "VERIFIED_NEGATIVE" for row in records)
    if completed == len(groups) and len(groups) >= minimum_groups:
        try:
            for meta in groups:
                validate_final_source(meta)
            if len({meta["source_family"] for meta in groups}) < minimum_groups:
                raise ValueError("familias independientes insuficientes")
            audit_exclusions(root, completed_records, {meta["sha256"] for meta in groups})
        except (OSError, ValueError, KeyError) as exc:
            return {"decision": "PERSON_HOLDOUT_BLOCKED", "reason": str(exc)}
        if not positives or not negatives:
            return {"decision": "PERSON_HOLDOUT_BLOCKED", "groups": len(groups),
                    "reason": "se requieren positivos y negativos humanos"}
        return {"decision": "PERSON_HOLDOUT_READY_TO_FREEZE", "groups": len(groups),
                "completed_groups": completed,
                "reason": "candidato; freeze todavía exige QA, hashes e independencia"}
    return {"decision": "PERSON_HOLDOUT_PARTIAL", "groups": len(groups),
            "completed_groups": completed, "minimum_groups": minimum_groups}
