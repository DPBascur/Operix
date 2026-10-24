# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Salida opcional de EventCandidate hacia el contrato HTTP de eventos v1.

El módulo no importa Django ni conoce la persistencia del Backend.
"""

from __future__ import annotations

import json
import math
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Literal, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from operix_engine.rules import EventCandidate, PairEventCandidate
from operix_engine.candidate_transport import candidate_payload


def deterministic_analysis_run_id(
    *,
    video_sha256: str,
    weights_sha256: str,
    config_sha256: str,
    detector: Mapping[str, object],
    tracker: Mapping[str, object],
) -> UUID:
    """Identifica el mismo análisis sin rutas locales ni reloj civil."""
    hashes = (video_sha256, weights_sha256, config_sha256)
    if any(not re.fullmatch(r"[0-9a-fA-F]{64}", value) for value in hashes):
        raise ValueError("La identidad requiere tres SHA-256 válidos")
    document = {
        "profile": "video-event-v1",
        "video_sha256": video_sha256.lower(),
        "weights_sha256": weights_sha256.lower(),
        "config_sha256": config_sha256.lower(),
        "detector": dict(detector),
        "tracker": dict(tracker),
    }
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return uuid5(NAMESPACE_URL, "operix:analysis:" + canonical)


@dataclass(frozen=True, slots=True)
class EventContext:
    """Datos de la ejecución y del medio, no producidos por EventCandidate."""

    analysis_run_id: UUID
    view_id: str
    recording_started_at: datetime
    source: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.analysis_run_id, UUID):
            raise TypeError("analysis_run_id debe ser UUID")
        if not isinstance(self.view_id, str) or not self.view_id.strip():
            raise ValueError("view_id debe ser texto no vacío")
        if (
            not isinstance(self.recording_started_at, datetime)
            or self.recording_started_at.utcoffset() is None
        ):
            raise ValueError("recording_started_at requiere zona horaria explícita")


def _api_seconds(value: float, *, decimal_places: int = 3) -> str:
    if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Los segundos del candidato deben ser finitos y no negativos")
    try:
        rounded = Decimal(str(value)).quantize(Decimal(1).scaleb(-decimal_places))
    except InvalidOperation as error:
        raise ValueError("Los segundos no caben en el contrato API") from error
    if rounded > Decimal("999999999.999999999"):
        raise ValueError("Los segundos no caben en el contrato API")
    return format(rounded, f".{decimal_places}f")


def event_candidate_payload(candidate: EventCandidate | PairEventCandidate, context: EventContext) -> dict[str, object]:
    """Mapea el candidato y contexto explícito al POST /api/v1/events/."""
    if not isinstance(candidate, (EventCandidate, PairEventCandidate)):
        raise TypeError("candidate debe ser EventCandidate o PairEventCandidate")
    if not isinstance(context, EventContext):
        raise TypeError("context debe ser EventContext")
    timestamp = _api_seconds(candidate.timestamp_s)
    occurred_at = context.recording_started_at + timedelta(seconds=candidate.timestamp_s)
    common = {
        "analysis_run_id": str(context.analysis_run_id),
        "view_id": context.view_id,
        "occurred_at": occurred_at.isoformat(),
        "video_timestamp_s": timestamp,
        "frame_index": candidate.frame_index,
        "event_type": candidate.parameters["kind"],
        "rule_id": candidate.rule_id,
        "rule_version": candidate.rule_version,
        "rule_parameters": dict(candidate.parameters),
        "zone_id": candidate.zone_id,
    }
    if context.source:
        common["source"] = dict(context.source)
    if isinstance(candidate, PairEventCandidate):
        data = candidate_payload(candidate)
        return common | {
            "interaction": data["interaction"],
            "observations": {"normalized_distance": data["observed_normalized_distance"],
                             "duration_s": data["observed_duration_s"]},
            "episode": {"started_frame_index": data["started_frame_index"],
                        "started_timestamp_s": data["started_timestamp_s"], "timestamp_s": data["timestamp_s"]},
        }
    # No reducir a milisegundos una duración que decide un límite temporal.
    dwell = _api_seconds(candidate.observed_dwell_time_s, decimal_places=9)
    return common | {
        "track_id": candidate.track_id,
        "class_name": candidate.class_name,
        "observed_inside": candidate.observed_inside,
        "observed_dwell_time_s": dwell,
    }


@dataclass(frozen=True, slots=True)
class PublishResult:
    status: Literal["published", "skipped", "failed", "duplicate"]
    http_status: int | None = None
    event_id: str | None = None
    reason: str | None = None


class EventSink(Protocol):
    def publish(
        self, candidate: EventCandidate, context: EventContext, evidence_png: bytes | None = None
    ) -> PublishResult: ...


class NoopEventSink:
    """Permite procesar candidatos sin exigir que el Backend esté disponible."""

    def publish(
        self, candidate: EventCandidate, context: EventContext, evidence_png: bytes | None = None
    ) -> PublishResult:
        return PublishResult("skipped")


def publish_with_retries(
    sink: EventSink, candidate: EventCandidate, context: EventContext,
    evidence_png: bytes | None = None, *, max_attempts: int = 3,
) -> tuple[PublishResult, int]:
    """Reintentos acotados del mismo candidato; no cambia su identidad ni evidencia."""
    return _retry_operation(lambda: sink.publish(candidate, context, evidence_png), max_attempts)


def publish_document_with_retries(sink, payload, evidence_png, *, max_attempts=3):
    return _retry_operation(lambda: sink.publish_document(payload, evidence_png), max_attempts)


def _retry_operation(operation, max_attempts):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError("max_attempts debe estar entre 1 y 3")
    known_event_id = None
    for attempt in range(1, max_attempts + 1):
        result = operation()
        known_event_id = result.event_id or known_event_id
        transient = result.reason in {"timeout", "network_error", "evidence_network_error"} or (
            result.http_status in {429, 500, 502, 503, 504}
        )
        if result.status != "failed" or not transient or attempt == max_attempts:
            if result.event_id is None and known_event_id:
                result = PublishResult(result.status, result.http_status, known_event_id, result.reason)
            return result, attempt
        time.sleep(0.1 * attempt)
    raise AssertionError("Bucle de publicación sin resultado")  # pragma: no cover


class _NoEventRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpEventSink:
    """Reintenta fallos; la API decide si un candidato ya fue persistido."""

    def __init__(self, api_base_url: str, *, timeout_s: float = 5.0, local_only: bool = False) -> None:
        parsed = urlparse(api_base_url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OPERIX_API_BASE_URL debe ser una URL HTTP(S) sin credenciales")
        if local_only and (parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}):
            raise ValueError("La publicación web solo permite API local")
        if not isinstance(timeout_s, (int, float)) or not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("OPERIX_API_TIMEOUT_S debe ser positivo y finito")
        self._events_url = api_base_url.rstrip("/") + "/events/"
        self._timeout_s = float(timeout_s)
        self._completed: dict[tuple, tuple[str, str]] = {}
        self._opener = build_opener(_NoEventRedirect()) if local_only else None

    def _request(self, request):
        return (self._opener.open(request, timeout=self._timeout_s) if self._opener else
                urlopen(request, timeout=self._timeout_s))

    def publish(
        self, candidate: EventCandidate, context: EventContext, evidence_png: bytes | None = None
    ) -> PublishResult:
        try:
            payload = event_candidate_payload(candidate, context)
        except (TypeError, ValueError, KeyError, OverflowError):
            return PublishResult("failed", reason="invalid_payload")
        return self.publish_document(payload, evidence_png)

    def publish_document(self, payload: Mapping[str, object], evidence_png: bytes | None = None) -> PublishResult:
        """Reenvía un snapshot durable sin reconstruir ni reevaluar candidatos."""
        try:
            key = tuple(str(payload.get(field)) for field in (
                "analysis_run_id", "view_id", "rule_id", "rule_version", "frame_index", "zone_id",
                "track_id", "class_name")) + (json.dumps(payload.get("interaction"), sort_keys=True),)
            snapshot = json.dumps({k:v for k,v in payload.items() if k != "occurred_at"},
                                  sort_keys=True, allow_nan=False)
        except (TypeError, ValueError):
            return PublishResult("failed", reason="invalid_payload")
        if key in self._completed and self._completed[key][0] == snapshot:
            return PublishResult("duplicate", event_id=self._completed[key][1], reason="already_attempted_in_this_session")
        try:
            request = Request(
                self._events_url,
                data=json.dumps(payload, allow_nan=False).encode("utf-8"),
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                method="POST",
            )
            with self._request(request) as response:
                status = response.status
                body = response.read()
        except HTTPError as error:
            return PublishResult("failed", http_status=error.code, reason="http_error")
        except (TimeoutError, socket.timeout):
            return PublishResult("failed", reason="timeout")
        except URLError as error:
            reason = (
                "timeout"
                if isinstance(error.reason, (TimeoutError, socket.timeout))
                else "network_error"
            )
            return PublishResult("failed", reason=reason)
        except OSError:
            return PublishResult("failed", reason="network_error")
        except (TypeError, ValueError, KeyError, OverflowError):
            return PublishResult("failed", reason="invalid_payload")

        if status not in (200, 201):
            return PublishResult("failed", http_status=status, reason="unexpected_status")
        try:
            document = json.loads(body)
            if status == 200 and document.get("created") is not False:
                return PublishResult("failed", http_status=status, reason="unexpected_status")
            event_id = str(UUID(document["id"]))
        except (AttributeError, UnicodeError, ValueError, TypeError, KeyError):
            return PublishResult("failed", http_status=status, reason="invalid_response")
        already_exists = status == 200
        if evidence_png is not None and not (already_exists and document.get("evidence_url")):
            if not isinstance(evidence_png, bytes) or not evidence_png.startswith(b"\x89PNG\r\n\x1a\n"):
                return PublishResult("failed", event_id=event_id, reason="invalid_evidence")
            boundary = uuid4().hex
            parts = []
            for name, value in (
                ("frame_index", str(payload["frame_index"])),
                ("video_timestamp_s", str(payload["video_timestamp_s"])),
            ):
                parts.append(
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
                    f"{value}\r\n".encode("ascii")
                )
            parts.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
                'filename="frame.png"\r\nContent-Type: image/png\r\n\r\n'.encode("ascii")
            )
            body = b"".join(parts) + evidence_png + f"\r\n--{boundary}--\r\n".encode("ascii")
            upload = Request(
                f"{self._events_url}{event_id}/evidence/",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Accept": "application/json"},
                method="POST",
            )
            try:
                with self._request(upload) as response:
                    upload_status = response.status
            except HTTPError as error:
                return PublishResult("failed", http_status=error.code, event_id=event_id, reason="evidence_http_error")
            except (TimeoutError, socket.timeout, URLError, OSError):
                return PublishResult("failed", event_id=event_id, reason="evidence_network_error")
            if upload_status not in (200, 201):
                return PublishResult("failed", http_status=upload_status, event_id=event_id, reason="evidence_unexpected_status")
        self._completed[key] = (snapshot, event_id)
        return PublishResult(
            "duplicate" if already_exists else "published",
            http_status=status,
            event_id=event_id,
            reason="already_exists" if already_exists else None,
        )
