# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adaptador de YOLO11 para el contrato de detección de Operix."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from operix_engine.detection import BoundingBox, Detection


@dataclass(frozen=True, slots=True)
class YoloDetectorConfig:
    """Configuración mínima y reproducible del adaptador YOLO11."""

    weights_path: Path
    confidence_threshold: float = 0.25
    device: Literal["cuda", "cpu"] = "cuda"
    image_size: int = 640
    iou_threshold: float = 0.70

    def __post_init__(self) -> None:
        weights_path = Path(self.weights_path).expanduser()
        object.__setattr__(self, "weights_path", weights_path)
        if not weights_path.is_file():
            raise ValueError(f"No existe el archivo local de pesos: {weights_path}")
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("confidence_threshold debe estar entre 0 y 1")
        if self.device not in ("cuda", "cpu"):
            raise ValueError("device debe ser 'cuda' o 'cpu'")
        if self.image_size <= 0:
            raise ValueError("image_size debe ser positivo")
        if not 0 <= self.iou_threshold <= 1:
            raise ValueError("iou_threshold debe estar entre 0 y 1")


class YoloDetector:
    """Ejecuta YOLO11 sobre frames sin filtrar ni reinterpretar clases."""

    def __init__(
        self,
        config: YoloDetectorConfig,
        model_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        if model_factory is None:
            from ultralytics import YOLO

            model_factory = YOLO
        self._model = model_factory(str(config.weights_path), task="detect")

    @property
    def class_names(self) -> dict[int, str]:
        names = self._model.names
        if isinstance(names, Mapping):
            return {int(class_id): str(name) for class_id, name in names.items()}
        return {class_id: str(name) for class_id, name in enumerate(names)}

    def detect(self, frame: NDArray[np.uint8]) -> tuple[Detection, ...]:
        self._validate_frame(frame)
        results = self._model.predict(
            source=frame,
            conf=self.config.confidence_threshold,
            device=self.config.device,
            imgsz=self.config.image_size,
            iou=self.config.iou_threshold,
            save=False,
            show=False,
            verbose=False,
        )
        if len(results) != 1:
            raise RuntimeError(f"YOLO devolvió {len(results)} resultados para un frame")
        return self._convert_result(results[0])

    def _convert_result(self, result: Any) -> tuple[Detection, ...]:
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return ()

        coordinates = self._as_list(boxes.xyxy)
        confidences = self._as_list(boxes.conf)
        class_ids = self._as_list(boxes.cls)
        names = self.class_names

        detections = []
        for xyxy, confidence, class_id_value in zip(
            coordinates,
            confidences,
            class_ids,
            strict=True,
        ):
            class_id = int(class_id_value)
            detections.append(
                Detection(
                    class_id=class_id,
                    class_name=names.get(class_id, f"class_{class_id}"),
                    confidence=float(confidence),
                    bounding_box=BoundingBox(*(float(value) for value in xyxy)),
                )
            )
        return tuple(detections)

    @staticmethod
    def _as_list(values: Any) -> list[Any]:
        if hasattr(values, "detach"):
            values = values.detach()
        if hasattr(values, "cpu"):
            values = values.cpu()
        return values.tolist()

    @staticmethod
    def _validate_frame(frame: NDArray[np.uint8]) -> None:
        if not isinstance(frame, np.ndarray):
            raise TypeError("El frame debe ser un numpy.ndarray")
        if frame.dtype != np.uint8:
            raise ValueError("El frame debe usar dtype uint8")
        if frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("El frame debe tener forma (alto, ancho, 3) en BGR")
        if frame.size == 0:
            raise ValueError("El frame no puede estar vacío")
