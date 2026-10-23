# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Congela un evaluation manifest PERSON independiente; jamás sobrescribe un freeze."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from operix_engine.person_campaign import freeze_payload


def freeze(campaign: Path) -> dict:
    qa = json.loads((campaign / "04-qa" / "qa-summary.json").read_text(encoding="utf-8"))
    if qa["blocking_issues"] or qa["completed_tasks"] != qa["total_tasks"]:
        raise ValueError("QA/tareas incompletas; no se puede congelar evaluation")
    plan = json.loads((campaign / "06-split-planning" / "split-plan.json").read_text(encoding="utf-8"))
    if plan["status"] != "CANDIDATE_NOT_FROZEN":
        raise ValueError("split de grupos no está listo")
    with (campaign / "final" / "verified-manifest.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    payload = freeze_payload(rows, plan["groups"])
    target = campaign / "final" / "frozen-evaluation.json"
    with target.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    return {"path": str(target), "manifest_sha256": payload["manifest_sha256"],
            "images": len(payload["images"]), "source_groups": len(payload["source_groups"])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.campaign), indent=2))


if __name__ == "__main__":
    main()
