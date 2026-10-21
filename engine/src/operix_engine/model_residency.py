# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Prototipo opt-in: residencia de detectores, nunca de estado temporal.

Solo se usa desde el experimento serial; la API sigue lanzando procesos nuevos.
No admite configuración nueva una vez completo el par para acotar memoria GPU.
"""

from operix_engine.yolo_detector import YoloDetector


class ResidentDetectors:
    def __init__(self, factory=YoloDetector):
        self._factory = factory
        self._detectors = {}

    def __call__(self, config):
        if config not in self._detectors:
            if len(self._detectors) >= 2:
                raise ValueError("El worker residente requiere reinicio para cambiar los modelos/configuración")
            self._detectors[config] = self._factory(config)
        return self._detectors[config]
