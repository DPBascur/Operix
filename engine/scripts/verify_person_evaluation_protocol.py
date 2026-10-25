# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verifica protocolo, freeze y pesos por metadata/hash; nunca importa detectores."""
import argparse
import importlib.util
from importlib.metadata import version
import json
from pathlib import Path

from operix_engine.person_protocol import canonical, digest, source_digest, validate_protocol


def validate_local(protocol_path, root, primary_weights, reference_weights):
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    validate_protocol(protocol)
    if protocol_path.read_text(encoding="utf-8") != canonical(protocol).decode("utf-8"):
        raise ValueError("protocolo no canónico")
    if protocol_path.with_suffix(".sha256").read_text().split()[0] != digest(protocol):
        raise ValueError("sello de protocolo distinto")
    for package, expected in protocol["software_versions"].items():
        if version(package) != expected:
            raise ValueError("software local distinto del protocolo")
    repository = Path(__file__).resolve().parents[2]
    for relative, expected in protocol["tooling_sha256"].items():
        file = (repository / relative).resolve()
        if not file.is_relative_to(repository) or source_digest(file) != expected:
            raise ValueError("tooling distinto del protocolo congelado")
    path = Path(__file__).with_name("freeze_person_coco_holdout.py")
    spec = importlib.util.spec_from_file_location("frozen_coco_metadata", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    frozen = module.verify(root)
    if frozen["freeze_sha256"] != protocol["dataset"]["freeze_sha256"]:
        raise ValueError("dataset freeze SHA distinto")
    weights = {"CURRENT_PERSON": primary_weights, "YOLO11N_COCO_PERSON": reference_weights}
    for model, file in weights.items():
        if module.sha(file).lower() != protocol["models"][model]["sha256"]:
            raise ValueError("model SHA distinto")
    return {"protocol_state": "PERSON_EVALUATION_PROTOCOL_V1_FROZEN", "protocol_sha256": digest(protocol),
            "dataset_freeze_sha256": frozen["freeze_sha256"], "model_hashes": "PASS",
            "inference": "NOT_PERFORMED", "evaluation_status": "PERSON_MODEL_EVALUATION_NOT_STARTED"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--holdout-root", type=Path, required=True)
    parser.add_argument("--primary-weights", type=Path, required=True)
    parser.add_argument("--reference-weights", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate_local(args.protocol, args.holdout_root, args.primary_weights, args.reference_weights), indent=2))
