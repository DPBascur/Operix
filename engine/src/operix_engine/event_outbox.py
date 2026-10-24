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

    def enqueue(self, candidates, context, evidence_png, *, fallback_frame=None):
        """PNG durable antes del journal; journal durable antes de cualquier HTTP."""
        entries = []
        for candidate in candidates:
            payload = event_candidate_payload(candidate, context)
            key = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
            name = key + ".png"
            pending = self.directory / (key + ".pending.json")
            atomic_json(pending, {"key": key})
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
            if evidence_png is None and fallback_frame is not None:
                # Conservar solamente el frame candidato si falla el encoder; no el video.
                import numpy as np
                recovery = self.directory / (key + ".npy")
                temporary = recovery.with_suffix(".tmp")
                with temporary.open("wb") as output:
                    np.save(output, fallback_frame, allow_pickle=False)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, recovery)
                entry["recovery_sha256"] = hashlib.sha256(recovery.read_bytes()).hexdigest()
            with self.journal.open("a", encoding="utf-8") as output:
                output.write(json.dumps(entry, allow_nan=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
            entries.append(entry)
            pending.unlink(missing_ok=True)
        # También registra explícitamente una ejecución normal sin candidatos.
        if not candidates:
            self.journal.touch(exist_ok=True)
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
                if entry.get("sha256") is None and entry.get("recovery_sha256"):
                    image = self._recover_image(entry)
                else:
                    image = (self.directory / name).read_bytes()
                    if hashlib.sha256(image).hexdigest() != entry["sha256"]:
                        raise ValueError("Hash de evidencia inválido")
                result, attempts = publish_document_with_retries(self.sink, entry["payload"], image)
                self.receipts[key] = asdict(result) | {"attempts": attempts}
            except (OSError, ValueError, KeyError, TypeError):
                self.receipts[key] = {"status": "failed", "reason": "invalid_or_missing_outbox_evidence", "attempts": 0}
            atomic_json(self.receipts_path, self.receipts)

    def _recover_image(self, entry):
        """Recrear PNG desde el frame retenido, sin volver a ejecutar percepción."""
        import cv2
        import numpy as np
        path = self.directory / (entry["key"] + ".npy")
        if path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Frame de recuperación demasiado grande")
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["recovery_sha256"]:
            raise ValueError("Hash de recuperación inválido")
        frame = np.load(path, allow_pickle=False)
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3 or not all(0 < n <= 4096 for n in frame.shape[:2]):
            raise ValueError("Frame de recuperación inválido")
        for _ in range(5):
            try:
                ok, encoded = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 6])
            except cv2.error as error:
                raise ValueError("Encoder PNG no disponible") from error
            if ok and encoded.nbytes <= 2 * 1024 * 1024:
                image = encoded.tobytes()
                target = self.directory / entry["evidence"]
                temporary = target.with_suffix(".tmp")
                with temporary.open("wb") as output:
                    output.write(image)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
                return image
            frame = cv2.resize(frame, (max(1, frame.shape[1] // 2), max(1, frame.shape[0] // 2)))
        raise ValueError("PNG de recuperación no disponible")

    def _entries(self):
        entries, invalid = [], 0 if self.journal.exists() else 1
        if self.journal.exists():
            for line in self.journal.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                    key = entry["key"]
                    if not isinstance(key, str) or len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
                        raise ValueError("Identidad inválida")
                    if not isinstance(entry["payload"], dict) or entry["evidence"] != key + ".png":
                        raise ValueError("Entrada inválida")
                    entries.append(entry)
                except (ValueError, KeyError, TypeError):
                    invalid += 1
        known = {entry["key"] for entry in entries}
        invalid += sum(path.name.removesuffix(".pending.json") not in known
                       for path in self.directory.glob("*.pending.json"))
        return entries, invalid

    def replay(self):
        # Una línea interrumpida nunca se interpreta como éxito ni se descarta silenciosamente.
        entries, _ = self._entries()
        self.deliver(entries)
        return self.summary()

    def summary(self):
        entries, invalid = self._entries()
        keys = list(dict.fromkeys(entry["key"] for entry in entries))
        done = [self.receipts[k] for k in keys if self.receipts.get(k, {}).get("status") in ("published", "duplicate")]
        return {"state": "saved" if len(done) == len(keys) and invalid == 0 else "failed",
                "candidates": len(keys), "saved": len(done), "failed": len(keys) - len(done),
                "invalid_records": invalid,
                "event_ids": [r["event_id"] for r in done if r.get("event_id")],
                "retention": "MANUAL_RETENTION"}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--api-url", required=True)
    args = parser.parse_args()
    result = EventOutbox(args.directory, HttpEventSink(args.api_url, local_only=True)).replay()
    print(json.dumps(result))
    return 0 if result["state"] == "saved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
