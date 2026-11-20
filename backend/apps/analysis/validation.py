import json
import os
import subprocess

from django.conf import settings


def validate_spatial(document, source_sha256, root):
    try:
        payload = json.dumps(document, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("Configuración JSON inválida") from error
    if len(payload) > 65536:
        raise ValueError("Configuración demasiado grande")
    try:
        checked = subprocess.run(
            [settings.OPERIX_ENGINE_PYTHON, "-B", str(root / "engine/scripts/validate_spatial_config.py"),
             source_sha256],
            input=payload, capture_output=True, text=True, encoding="utf8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=20,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise ValueError("No se pudo validar la configuración con el Motor") from error
    if checked.returncode:
        raise ValueError(checked.stderr.strip()[-400:] or "Configuración inválida")
    try:
        return json.loads(checked.stdout)
    except ValueError as error:
        raise ValueError("No se pudo leer la configuración validada") from error
