"""Outbox local durable: snapshots del Motor, PNG y reintento sin inferencia.

No es un bus distribuido. El Backend conserva este directorio bajo MANUAL_RETENTION.
"""

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path

from operix_engine.event_publishing import (
    HttpEventSink, event_candidate_payload, publish_document_with_retries,
)


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, allow_nan=False)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


class EventOutbox:
    def __init__(self, directory, sink):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.sink = sink
        self.journal = self.directory / "candidates.ndjson"
        self.receipts_path = self.directory / "publication.json"
        self.receipts = (json.loads(self.receipts_path.read_text(encoding="utf-8"))
                         if self.receipts_path.exists() else {})

    def enqueue(self, candidates, context, evidence_png):
        """PNG durable antes del journal; journal durable antes de cualquier HTTP."""
        entries = []
        for candidate in candidates:
            payload = event_candidate_payload(candidate, context)
            key = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
            name = key + ".png"
            if evidence_png is not None:
                target = self.directory / name
                if not target.exists():
                    temporary = target.with_suffix(".tmp")
                    with temporary.open("wb") as output:
                        output.write(evidence_png)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temporary, target)
            entry = {"key": key, "payload": payload, "evidence": name,
                     "sha256": hashlib.sha256(evidence_png).hexdigest() if evidence_png else None}
            with self.journal.open("a", encoding="utf-8") as output:
                output.write(json.dumps(entry, allow_nan=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
            entries.append(entry)
        self.deliver(entries)

    def deliver(self, entries):
        for entry in entries:
            key = entry["key"]
            if self.receipts.get(key, {}).get("status") in ("published", "duplicate"):
                continue
            try:
                name = entry["evidence"]
                if name != key + ".png" or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                    raise ValueError("Nombre de evidencia inválido")
                image = (self.directory / name).read_bytes()
                if hashlib.sha256(image).hexdigest() != entry["sha256"]:
                    raise ValueError("Hash de evidencia inválido")
                result, attempts = publish_document_with_retries(self.sink, entry["payload"], image)
                self.receipts[key] = asdict(result) | {"attempts": attempts}
            except (OSError, ValueError, KeyError, TypeError):
                self.receipts[key] = {"status": "failed", "reason": "invalid_or_missing_outbox_evidence", "attempts": 0}
            atomic_json(self.receipts_path, self.receipts)

    def replay(self):
        # Una línea interrumpida nunca se interpreta como éxito ni se descarta silenciosamente.
        entries = [json.loads(line) for line in self.journal.read_text(encoding="utf-8").splitlines()]
        self.deliver(entries)
        return self.summary()

    def summary(self):
        entries = []
        if self.journal.exists():
            entries = [json.loads(line) for line in self.journal.read_text(encoding="utf-8").splitlines()]
        keys = list(dict.fromkeys(entry["key"] for entry in entries))
        done = [self.receipts[k] for k in keys if self.receipts.get(k, {}).get("status") in ("published", "duplicate")]
        return {"state": "saved" if len(done) == len(keys) else "failed",
                "candidates": len(keys), "saved": len(done), "failed": len(keys) - len(done),
                "event_ids": [r["event_id"] for r in done if r.get("event_id")],
                "retention": "MANUAL_RETENTION"}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--api-url", required=True)
    args = parser.parse_args()
    result = EventOutbox(args.directory, HttpEventSink(args.api_url)).replay()
    print(json.dumps(result))
    return 0 if result["state"] == "saved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
