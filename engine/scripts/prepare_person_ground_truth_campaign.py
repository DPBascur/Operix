# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prepara fuera de Git tareas CVAT para revisión humana de PERSON."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path

from operix_engine.person_campaign import CampaignImage, plan_tasks, readiness


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def zip_add(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data)


def prepare(previous_pack: Path, test3_pack: Path, output: Path) -> dict:
    repo = Path(__file__).resolve().parents[2]
    if output.resolve().is_relative_to(repo):
        raise ValueError("las imágenes deben permanecer fuera de Git")
    if output.exists():
        raise FileExistsError("la carpeta de campaña ya existe")
    old, new = read_csv(previous_pack / "manifest.csv"), read_csv(test3_pack / "manifest.csv")
    if (len(old), len(new)) != (225, 48):
        raise ValueError("inventario de entrada inesperado")
    images: list[CampaignImage] = []
    source_paths: dict[str, Path] = {}
    for row in old:
        image_id = f'KEREMBERKE:{row["image_id"]}'
        path = previous_pack / "images" / Path(row["pack_image"]).name
        if sha256(path) != row["sha256"].upper():
            raise ValueError(f"SHA inválido: {image_id}")
        source_paths[image_id] = path
        images.append(CampaignImage(image_id, path.name, "KEREMBERKE", row["source_group"],
            int(row["width"]), int(row["height"]), row["sha256"].upper(),
            row["annotation_status"], row["preannotation_sources"],
            int(row["preannotation_boxes"]), "WEAK",
            row["annotation_status"] == "VALID_FULL_FRAME_NEGATIVE"))
    for row in new:
        frame = int(row["frame_index"])
        image_id = f"TEST3:{frame:06d}"
        path = test3_pack / "images" / row["image"]
        if sha256(path) != row["sha256"].upper():
            raise ValueError(f"SHA inválido: {image_id}")
        source_paths[image_id] = path
        images.append(CampaignImage(image_id, path.name, "TEST3", "TEST3_VIDEO",
            int(row["width"]), int(row["height"]), row["sha256"].upper(),
            "UNANNOTATED", "NONE", 0, "UNKNOWN", False, frame))
    tasks = plan_tasks(images)
    task_for = {item.image_id: task for task, members in tasks.items() for item in members}
    inventory = [{
        "image_id": item.image_id, "filename": item.filename, "source": item.source,
        "source_group": item.source_group, "width": item.width, "height": item.height,
        "annotation_status": item.annotation_status,
        "preannotation_status": "PREANNOTATION_ONLY" if item.person_box_count else "NONE",
        "preannotation_source": item.preannotation_source,
        "person_box_count": item.person_box_count,
        "negative_verified": str(item.negative_verified).lower(),
        "recommended_task": task_for.get(item.image_id, "ALREADY_VERIFIED"),
        "notes": "one video; development only" if item.source == "TEST3"
                 else "scene/sequence provenance unknown",
        "image_sha256": item.sha256, "provenance": item.provenance,
        "source_group_confidence": "STRONG" if item.source == "TEST3" else "WEAK",
        "source_reference": "local user-provided video; license unknown" if item.source == "TEST3"
                            else "https://huggingface.co/datasets/keremberke/forklift-object-detection",
        "frame_index": "" if item.frame_index is None else item.frame_index,
        "split_eligibility": "DEVELOPMENT_ONLY" if item.source == "TEST3" else "PENDING_REVIEW",
    } for item in sorted(images, key=lambda item: item.image_id)]
    columns = list(inventory[0])
    write_csv(output / "00-inventory" / "consolidated-images.csv", inventory, columns)
    groups = {"TEST3_VIDEO": {"images": 48, "temporal_group": "one video",
                              "split_eligibility": "DEVELOPMENT_ONLY", "origin_provenance": "UNKNOWN"},
              "KEREMBERKE": {"images": 225, "declared_image_level_groups": 225,
                             "scene_sequence_provenance": "WEAK"}}
    (output / "03-manifests").mkdir(parents=True)
    (output / "03-manifests" / "source-groups.json").write_text(
        json.dumps(groups, indent=2) + "\n", encoding="utf-8")
    coco = json.loads((previous_pack / "preannotations.coco.json").read_text(encoding="utf-8"))
    task_report = []
    for task_id, members in tasks.items():
        folder = output / "01-cvat-packages" / task_id
        folder.mkdir(parents=True)
        with zipfile.ZipFile(folder / "images.zip", "w") as archive:
            for item in members:
                zip_add(archive, item.filename, source_paths[item.image_id].read_bytes())
        if task_id.startswith("PERSON-REVIEW"):
            filenames = {item.filename for item in members}
            subset_images = [r for r in coco["images"] if r["file_name"] in filenames]
            if len(subset_images) != len(members):
                raise ValueError(f"COCO no cubre {task_id}")
            ids = {r["id"] for r in subset_images}
            subset = {**coco, "images": subset_images,
                      "annotations": [r for r in coco["annotations"] if r["image_id"] in ids]}
            with zipfile.ZipFile(folder / "PREANNOTATION_ONLY.coco.zip", "w") as archive:
                zip_add(archive, "annotations/instances_default.json",
                        json.dumps(subset, ensure_ascii=False).encode("utf-8"))
        ids = {r.image_id for r in members}
        write_csv(folder / "task-manifest.csv",
                  [r for r in inventory if r["image_id"] in ids], columns)
        task_report.append({"task_id": task_id, "images": len(members),
                            "source_groups": len({r.source_group for r in members}),
                            "preannotation_only": task_id.startswith("PERSON-REVIEW")})
    (output / "03-manifests" / "tasks.json").write_text(
        json.dumps(task_report, indent=2) + "\n", encoding="utf-8")
    for name in ("02-annotation-guidelines", "04-qa", "05-export-tools",
                 "06-split-planning", "07-readiness", "final"):
        (output / name).mkdir(parents=True)
    (output / "02-annotation-guidelines" / "PERSON-ANNOTATION-GUIDELINES.md").write_text(
        "# PERSON: guía breve\n\n"
        "**Única clase:** `person`. Cajas previas = PREANNOTATION_ONLY; en cada imagen "
        "VERIFY, CORRECT, DELETE y ADD MISSING.\n\n"
        "- Incluir cuerpo completo o parcial, trabajador oculto, operador distinguible dentro de "
        "forklift, persona sentada/agachada/pequeña/truncada.\n"
        "- Caja ajustada al cuerpo **visible**; no extrapolar partes ocultas ni incluir toda la cabina.\n"
        "- No etiquetar reflejos, fotos, carteles, pantallas ni maniquíes como personas.\n"
        "- Evidencia insuficiente: REVIEW_AMBIGUOUS, sin forzar label.\n"
        "- VERIFIED_NEGATIVE exige revisar el frame entero y confirmar cero personas; "
        "cero propuestas no basta.\n"
        "- Una caja por persona separable. Atributos opcionales: visibility (clear/partial/"
        "heavy_occlusion), size_context (small/medium/large), operator_context "
        "(forklift_operator/none). No crear clases nuevas.\n"
        "- Exportar COCO 1.0 y registrar estado, revisor y fecha por imagen. "
        "Ambiguos siguen pendientes.\n", encoding="utf-8")
    (output / "ADDITIONAL_PERSON_DATA_NEEDED.md").write_text(
        "# Datos PERSON adicionales necesarios\n\n"
        "TEST3 es un solo video real de desarrollo, ya inspeccionado con ambos modelos; "
        "Keremberke carece de agrupación fiable por escena. Faltan grupos industriales reales "
        "independientes con licencia clara, varias cámaras, iluminaciones, escalas, oclusiones, "
        "operadores distinguibles y fondos difíciles sin personas. No se inventa material ni "
        "se consume TEST2/REAL_HOLDOUT_V2 para elegir ejemplos.\n", encoding="utf-8")
    (output / "ANNOTATION-WORKFLOW-FOR-DANIEL.md").write_text(
        "# Anotar PERSON en CVAT\n\n"
        "1. Crea un proyecto CVAT con una única etiqueta `person`.\n"
        "2. Crea una tarea por carpeta en `01-cvat-packages/`; sube `images.zip`.\n"
        "3. Solo en `PERSON-REVIEW-*`, importa `PREANNOTATION_ONLY.coco.zip` como COCO 1.0. "
        "Son propuestas: verifica, corrige, borra y agrega cajas.\n"
        "4. Revisa cada imagen completa con la guía breve. Si dudas, marca REVIEW_AMBIGUOUS.\n"
        "5. Tras revisar los frames, exporta COCO 1.0 y confirma a Codex que "
        "la revisión humana está completa. Indica qué imágenes, si alguna, son "
        "REVIEW_AMBIGUOUS.\n"
        "6. Codex ubica y valida el export, genera los registros administrativos "
        "solo tras tu confirmación, ejecuta QA y actualiza el progreso. "
        "No necesitas editar CSV/JSON, calcular hashes ni ejecutar Python.\n\n"
        "Los 20 negativos ya verificados no se reanotan. TEST3 es una tarea completa de "
        "desarrollo, nunca un test ciego.\n", encoding="utf-8")
    (output / "05-export-tools" / "README.md").write_text(
        "Tooling versionado: `engine/scripts/prepare_person_ground_truth_campaign.py`, "
        "`process_person_cvat_export.py`, `freeze_person_evaluation.py`.\n", encoding="utf-8")
    task_state = {r["task_id"]: {"completed": False} for r in task_report}
    gate = readiness(inventory, task_state, [], False)
    (output / "07-readiness" / "readiness.json").write_text(
        json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    (output / "07-readiness" / "readiness-criteria.json").write_text(json.dumps({
        "minimum_verified_negative_images": 30,
        "rationale": "Piso operativo provisional superior a los 20 negativos ya verificados; no demuestra representatividad estadística ni sustituye auditoría de diversidad.",
        "minimum_independent_strong_positive_groups": 3,
        "group_rationale": "Mínimo estructural para train, calibration y locked evaluation separados; no basta por sí solo para calidad.",
        "requires_human_verified_positive": True,
        "requires_all_tasks_complete": True,
        "requires_qa_zero_blockers": True,
        "requires_locked_evaluation_freeze": True,
        "thresholds_are_configurable_before_model_results": True,
    }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts = Counter(r["annotation_status"] for r in inventory)
    (output / "annotation-progress.md").write_text(
        f"# Progreso PERSON\n\nTotal: {len(inventory)}; negativos verificados: "
        f"{counts['VALID_FULL_FRAME_NEGATIVE']}; positivos verificados: 0; "
        f"pendientes: {len(inventory) - counts['VALID_FULL_FRAME_NEGATIVE']}; "
        f"ambiguos revisados: 0; tareas completadas: 0/{len(tasks)}.\n",
        encoding="utf-8")
    return {"images": len(inventory), "tasks": task_report,
            "verified_negatives": counts["VALID_FULL_FRAME_NEGATIVE"],
            "pending": len(inventory) - counts["VALID_FULL_FRAME_NEGATIVE"],
            "inventory_sha256": sha256(output / "00-inventory" / "consolidated-images.csv")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-pack", type=Path, required=True)
    parser.add_argument("--test3-pack", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.previous_pack, args.test3_pack, args.output), indent=2))


if __name__ == "__main__":
    main()
