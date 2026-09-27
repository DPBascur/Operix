"""Lectura controlada de fuentes de video grabadas mediante OpenCV."""

from __future__ import annotations

import math
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import cv2
from numpy.typing import NDArray


class VideoSourceError(RuntimeError):
    """Indica que una fuente de video no puede procesarse de forma controlada."""


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """Propiedades informadas por OpenCV para una fuente de video."""

    width: int
    height: int
    declared_fps: float | None
    declared_frame_count: int | None
    estimated_duration_seconds: float | None

    def frame_time_seconds(self, frame_index: int) -> float | None:
        """Estima el tiempo relativo del cuadro a partir del FPS declarado."""
        if frame_index < 0:
            raise ValueError("El índice del frame no puede ser negativo")
        if (
            self.declared_fps is None
            or not math.isfinite(self.declared_fps)
            or self.declared_fps <= 0
        ):
            return None
        return frame_index / self.declared_fps


@dataclass(frozen=True, slots=True)
class VideoProcessingResult:
    """Resumen de una lectura secuencial completa."""

    metadata: VideoMetadata
    processed_frames: int
    processing_seconds: float
    warnings: tuple[str, ...] = ()


class RecordedVideoSource:
    """Fuente grabada que entrega frames secuencialmente y controla su recurso."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._capture: cv2.VideoCapture | None = None

    @property
    def is_open(self) -> bool:
        """Indica si OpenCV mantiene abierta la fuente."""
        return self._capture is not None and self._capture.isOpened()

    def open(self) -> RecordedVideoSource:
        """Valida y abre el archivo de video."""
        if self.is_open:
            return self

        if not self.path.exists():
            raise VideoSourceError(f"No existe el archivo de video: {self.path}")
        if not self.path.is_file():
            raise VideoSourceError(f"La ruta no corresponde a un archivo: {self.path}")

        capture = cv2.VideoCapture(str(self.path))
        if not capture.isOpened():
            capture.release()
            raise VideoSourceError(f"OpenCV no pudo abrir el archivo de video: {self.path}")

        self._capture = capture
        return self

    def close(self) -> None:
        """Libera el recurso asociado a OpenCV."""
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> RecordedVideoSource:
        return self.open()

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def metadata(self) -> VideoMetadata:
        """Obtiene las propiedades básicas declaradas por el backend de video."""
        capture = self._require_open()

        width = max(0, int(round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))))
        height = max(0, int(round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))))

        fps_value = capture.get(cv2.CAP_PROP_FPS)
        declared_fps = float(fps_value) if math.isfinite(fps_value) and fps_value > 0 else None

        frame_count_value = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        declared_frame_count = (
            int(round(frame_count_value))
            if math.isfinite(frame_count_value) and frame_count_value > 0
            else None
        )

        estimated_duration = None
        if declared_fps is not None and declared_frame_count is not None:
            estimated_duration = declared_frame_count / declared_fps

        return VideoMetadata(
            width=width,
            height=height,
            declared_fps=declared_fps,
            declared_frame_count=declared_frame_count,
            estimated_duration_seconds=estimated_duration,
        )

    def frames(self) -> Iterator[tuple[int, NDArray]]:
        """Entrega cada frame junto con un índice iniciado en cero."""
        capture = self._require_open()
        frame_index = 0

        while True:
            try:
                read_ok, frame = capture.read()
            except cv2.error as error:
                raise VideoSourceError(
                    f"OpenCV produjo un error al leer el frame {frame_index}: {error}"
                ) from error

            if not read_ok:
                break
            if frame is None or frame.size == 0:
                raise VideoSourceError(f"OpenCV entregó un frame vacío en el índice {frame_index}")

            yield frame_index, frame
            frame_index += 1

    def frames_with_time(self) -> Iterator[tuple[int, float | None, NDArray]]:
        """Entrega índice, tiempo relativo estimado en segundos y frame."""
        metadata = self.metadata()
        for frame_index, frame in self.frames():
            yield frame_index, metadata.frame_time_seconds(frame_index), frame

    def _require_open(self) -> cv2.VideoCapture:
        if not self.is_open or self._capture is None:
            raise VideoSourceError("La fuente de video no está abierta")
        return self._capture


def process_recorded_video(path: str | Path) -> VideoProcessingResult:
    """Abre una fuente grabada, recorre sus frames y devuelve un resumen."""
    started_at = time.perf_counter()
    processed_frames = 0

    with RecordedVideoSource(path) as source:
        metadata = source.metadata()
        for _, _frame in source.frames():
            processed_frames += 1

    processing_seconds = time.perf_counter() - started_at
    warnings = _frame_count_warnings(metadata.declared_frame_count, processed_frames)

    return VideoProcessingResult(
        metadata=metadata,
        processed_frames=processed_frames,
        processing_seconds=processing_seconds,
        warnings=warnings,
    )


def _frame_count_warnings(
    declared_frame_count: int | None,
    processed_frames: int,
) -> tuple[str, ...]:
    """Informa diferencias relevantes sin asumir que el metadato es exacto."""
    if declared_frame_count is None or declared_frame_count == processed_frames:
        return ()

    difference = declared_frame_count - processed_frames
    tolerance = max(2, math.ceil(declared_frame_count * 0.01))

    if difference > tolerance:
        return (
            "La lectura terminó antes del total declarado por OpenCV "
            f"({processed_frames} procesados de {declared_frame_count}); "
            "el contenedor o códec puede reportar un total aproximado.",
        )

    return (
        "El total de frames procesados difiere del valor declarado por OpenCV "
        f"({processed_frames} procesados, {declared_frame_count} declarados).",
    )
