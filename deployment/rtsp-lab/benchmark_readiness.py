# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Separate QA control readiness from browser-facing playback readiness."""

import time


RETRYABLE_PROXY_STATUS = {500, 502, 503, 504}


class LabReadinessError(RuntimeError):
    pass


def check_lab_readiness(read_direct, read_proxy, *, sleep=time.sleep):
    """Return the initial control state and the three-attempt proxy status trace.

    Each reader returns (HTTP status, decoded control data or None).
    Transport failures at the proxy may be represented by a status of None.
    This probe reads both routes before any command mutates the laboratory.
    """
    status, initial = read_direct()
    if status != 200 or not isinstance(initial, dict) or initial.get("status") != "disabled":
        raise LabReadinessError(f"El control directo no está listo e inactivo (HTTP {status}).")

    statuses = []
    for attempt in range(3):
        status, observed = read_proxy()
        statuses.append(status)
        if status == 200:
            if not isinstance(observed, dict) or observed.get("status") != initial["status"]:
                raise LabReadinessError("El proxy y Django reportan estados de laboratorio distintos.")
            return initial, statuses
        if status is not None and status not in RETRYABLE_PROXY_STATUS:
            break
        if attempt < 2:
            sleep(attempt + 1)
    raise LabReadinessError(f"El proxy no quedó listo. Respuestas: {statuses!r}")
