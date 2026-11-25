# SPDX-License-Identifier: AGPL-3.0-or-later
"""Choose one checkpoint using validation reports before independent inference."""
import argparse
import json
from pathlib import Path

from evaluate import eligibility
from prepare import digest


def select(reports):
    common = None
    variants = []
    for report in reports:
        data = json.loads(report.read_bytes())
        if data["split"] != "validation":
            raise ValueError("Only sealed validation reports can select a checkpoint")
        settings = data["settings"]
        comparable = {key: value for key, value in settings.items() if key != "detector_sha256"}
        comparable["baselines"] = {key: settings["detector_sha256"][key] for key in ("person", "forklift")}
        if common is not None and common != comparable:
            raise ValueError("All candidates must use the same data, thresholds policy and input geometry")
        common = comparable
        readiness = eligibility(data["baseline"], data["candidate"])
        checks = readiness["checks"]
        scores = (readiness["passed"], sum(value for key,value in checks.items() if key.startswith("person_")),
                  data["candidate"]["forklift"]["operating_point"]["f1"] or 0,
                  data["candidate"]["person"]["ap50"])
        variants.append({"report": str(report.resolve()), "validation_sha256": digest(report),
                         "checkpoint_sha256": settings["detector_sha256"]["candidate"],
                         "validation_checks": checks, "rank": list(scores)})
    return {"selection_basis": "validation gates, PERSON gates passed, FORKLIFT F1, PERSON AP50",
            "selected": max(variants, key=lambda item: item["rank"]), "compared": variants}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(select(args.report), stream, indent=2, allow_nan=False)
