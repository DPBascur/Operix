"""Reloj visual 1×, independiente del avance del Motor y sin buffers de imágenes."""

from dataclasses import dataclass
import math


@dataclass
class PreviewClock:
    started_at: float | None = None
    frame_index: int | None = None
    finished: bool = False

    def select(self, *, now: float, source_fps: float, sample_fps: float,
               latest: int, total: int, completed: bool) -> int:
        """Nunca selecciona una muestra futura, ni un frame no procesado."""
        if source_fps <= 0 or sample_fps <= 0 or total <= 0 or latest < 0:
            raise ValueError("Metadata temporal de preview inválida")
        if self.started_at is None:
            self.started_at = now
        elapsed = max(0.0, now - self.started_at)
        rate = min(source_fps, sample_fps)
        available_time_index = math.floor(elapsed * source_fps + 1e-9)
        slot = math.floor(available_time_index * rate / source_fps + 1e-9)
        desired = math.ceil(slot * source_fps / rate - 1e-9)
        # La última muestra puede no caer en un slot regular (p.ej. frame 299).
        if elapsed >= (total - 1) / source_fps:
            desired = total - 1
        selected = min(latest, desired, total - 1)
        if selected < latest and selected != total - 1:
            selected = math.ceil(math.floor(selected * rate / source_fps + 1e-9)
                                 * source_fps / rate - 1e-9)
        self.frame_index = selected
        self.finished = completed and selected == total - 1 and elapsed >= total / source_fps
        return selected
