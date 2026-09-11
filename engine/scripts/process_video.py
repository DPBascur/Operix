"""Interfaz CLI mínima para procesar una fuente de video grabada."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from operix_engine.video_processor import VideoSourceError, process_recorded_video


def _optional_number(value: int | float | None, decimals: int = 2) -> str:
    if value is None:
        return "no disponible"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{decimals}f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Procesa secuencialmente un archivo de video con OpenCV.",
    )
    parser.add_argument("video", type=Path, help="Ruta al archivo de video")
    args = parser.parse_args()

    try:
        result = process_recorded_video(args.video)
    except VideoSourceError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    metadata = result.metadata
    print(f"Resolución: {metadata.width}x{metadata.height}")
    print(f"FPS declarado: {_optional_number(metadata.declared_fps)}")
    print(f"Frames declarados: {_optional_number(metadata.declared_frame_count)}")
    print(
        "Duración estimada (s): "
        f"{_optional_number(metadata.estimated_duration_seconds)}"
    )
    print(f"Frames procesados: {result.processed_frames}")
    print(f"Tiempo de procesamiento (s): {result.processing_seconds:.3f}")

    for warning in result.warnings:
        print(f"Advertencia: {warning}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
