"""Ingestión RTSP experimental de una sola fuente, separada del flujo offline."""

from collections import Counter, deque
from dataclasses import dataclass
import math
from threading import Condition, Event, Thread
from time import perf_counter as monotonic


@dataclass(frozen=True)
class Frame:
    index: int
    connection: int
    received: float
    pts: float | None
    image: object
    queue_depth: int = 0
    source_discontinuity: bool = False
    source_index: int | None = None
    source_ordinal: int | None = None


class TemporalSampler:
    """Select the first decoded observation in each analysis cadence slot."""

    def __init__(self, source_fps, analysis_fps):
        self.source_fps = source_fps
        self.analysis_fps = analysis_fps
        self.slot = -1
        self.previous_pts = None
        self.gap = False

    def select(self, index, pts):
        if index and (pts is None or self.previous_pts is None
                      or not 0 < pts - self.previous_pts <= 1.5 / self.source_fps):
            self.gap = True
        self.previous_pts = pts
        slot = math.floor(index * self.analysis_fps / self.source_fps + 1e-9)
        if slot == self.slot:
            return False, False
        self.slot = slot
        discontinuity, self.gap = self.gap, False
        return True, discontinuity


class Capture:
    def __init__(self, open_source, *, fps, source_fps=None, capacity=6, max_age=.5, startup_seconds=2, trace=None):
        source_fps = fps if source_fps is None else source_fps
        if not 0 < fps <= source_fps <= 60 or not 1 <= capacity <= 32 or not 0 < max_age <= 2:
            raise ValueError("Límites de captura inválidos")
        self.open_source = open_source
        self.trace = trace
        self.fps = fps
        self.source_fps = source_fps
        self.max_age = max_age
        self.startup_seconds = startup_seconds
        self.capacity = capacity
        self.stop = Event()
        self.ready = Condition()
        self.queue = deque()
        self.counts = Counter()
        self.depth = 0
        self.connection = 0
        self.connected = False
        self.thread = Thread(target=self._read, name="rtsp-capture", daemon=True)

    def _read(self):
        index = 0
        source_index = 0
        failures = 0
        while not self.stop.is_set():
            reader = None
            opening = monotonic()
            try:
                reader = self.open_source()
                with self.ready:
                    self.connection += 1
                    self.connected = True
                    self.counts["connections"] += 1
                    if self.trace:
                        self.trace("open", self.connection, monotonic(), started=opening)
                startup_deadline = monotonic() + self.startup_seconds
                start_source_index = source_index
                prior_ordinal = None
                sampler = TemporalSampler(self.source_fps, self.fps) if self.source_fps > self.fps else None
                read = getattr(reader, "read_native", reader.read) if sampler else reader.read
                # Validate every picture and its timestamp, but convert only selected ones to BGR.
                convert = getattr(reader, "to_image", None) if sampler else None
                while not self.stop.is_set():
                    # Dejar que el consumidor vacíe la ráfaga del sondeo inicial.
                    # Tras el plazo, volver a priorizar frescura con la política normal.
                    with self.ready:
                        remaining = startup_deadline - monotonic()
                        if remaining > 0 and len(self.queue) == self.capacity:
                            waiting = monotonic()
                            self.ready.wait_for(lambda: len(self.queue) < self.capacity or self.stop.is_set(),
                                                remaining)
                            if self.trace:
                                self.trace("startup_wait", self.connection, monotonic(), started=waiting,
                                           depth=len(self.queue))
                        if self.stop.is_set():
                            break
                    reading = monotonic()
                    image, pts = read()
                    received = monotonic()
                    ordinal = getattr(reader, "source_ordinal", None)
                    ordinal_gap = prior_ordinal is not None and ordinal != prior_ordinal + 1
                    prior_ordinal = ordinal
                    failures = 0
                    with self.ready:
                        self.counts["decoded"] += 1
                        if sampler:
                            if ordinal_gap:
                                sampler.gap = True
                            selected, source_gap = sampler.select(source_index - start_source_index, pts)
                        else:
                            selected, source_gap = True, ordinal_gap
                        source_index += 1
                        if not selected:
                            self.counts["sampling_skip"] += 1
                            if self.trace:
                                self.trace("decoded", self.connection, received, index=source_index - 1,
                                           pts_s=pts, read_started=reading, depth=len(self.queue))
                            continue
                        if len(self.queue) == self.capacity:
                            self._discard("queue_drop")
                        if convert:
                            image = convert(image)
                        self.queue.append(Frame(index, self.connection, received, pts, image,
                                                len(self.queue) + 1, source_gap, source_index - 1, ordinal))
                        index += 1
                        self.depth = max(self.depth, len(self.queue))
                        if self.trace:
                            self.trace("decoded", self.connection, received, index=source_index - 1,
                                       pts_s=pts, read_started=reading, depth=len(self.queue))
                        self.ready.notify()
            except (OSError, ValueError):
                if not self.stop.is_set():
                    with self.ready:
                        self.connected = False
                        failure = "read_failure" if reader else "open_failure"
                        self.counts[failure] += 1
                        if self.trace:
                            self.trace(failure, self.connection, monotonic(), started=reading if reader else opening)
            finally:
                if reader is not None:
                    reader.close()
                with self.ready:
                    self.connected = False
                    while self.queue:
                        self._discard("shutdown_drop" if self.stop.is_set() else "disconnect_drop")
            failures += 1
            self.stop.wait(min(5, .25 * 2 ** min(failures - 1, 5)))

    def __enter__(self):
        self.thread.start()
        return self

    def _discard(self, reason):
        frame = self.queue.popleft()
        self.counts[reason] += 1
        if self.trace:
            self.trace(reason, frame.connection, monotonic(), index=frame.index, depth=len(self.queue))

    def next(self, timeout=.2):
        with self.ready:
            self.ready.wait_for(lambda: self.queue or self.stop.is_set(), timeout)
            while self.queue:
                frame = self.queue[0]
                if monotonic() - frame.received <= self.max_age:
                    self.queue.popleft()
                    self.ready.notify()
                    return frame
                self._discard("expired_drop")
                self.ready.notify()
        return None

    def is_current(self, frame):
        with self.ready:
            return self.connected and self.connection == frame.connection

    def __exit__(self, *_):
        self.stop.set()
        with self.ready:
            self.ready.notify_all()
        self.thread.join(timeout=6)
        if self.thread.is_alive():
            raise RuntimeError("El lector RTSP no finalizó dentro del límite")


class Epoch:
    """Separa continuidad de evidencia y posible reutilización de identidad."""

    def __init__(self, fps):
        self.fps = fps
        self.previous = None
        self.number = 0
        self.origin = 0
        self.uses_pts = False
        self.preserve_tracking = False
        self._previous_contiguous = False

    def _isolated_drop(self, frame):
        previous = self.previous
        if (not self._previous_contiguous or frame.index != previous.index + 2
                or previous.pts is None or frame.pts is None):
            return False
        pts_delta = frame.pts - previous.pts
        return (1.5 < pts_delta * self.fps < 2.5 and pts_delta <= .25
                and 0 < frame.received - previous.received <= .25)

    def discontinuity(self, frame):
        previous = self.previous
        if previous is None:
            return "initial"
        if previous.connection != frame.connection:
            return "reconnect"
        if frame.source_discontinuity:
            return "source_sampling_gap"
        if previous.index + 1 != frame.index:
            return "queue_gap"
        if previous.pts is not None and frame.pts is not None and not (
            0 < frame.pts - previous.pts <= 1.75 / self.fps
        ):
            return "source_pts_gap"
        if self.uses_pts and frame.pts is None:
            return "missing_pts"
        if not self.uses_pts and frame.pts is not None:
            return "pts_available"
        if previous.received >= frame.received or frame.received - previous.received > .5:
            return "arrival_gap"
        return None

    def advance(self, frame):
        reason = self.discontinuity(frame)
        # El ordinal saltó dentro de la misma conexión y el reloj de origen lo corrobora.
        # La época se corta incluso cuando ByteTrack puede asociar la próxima detección.
        self.preserve_tracking = reason == "queue_gap" and self._isolated_drop(frame)
        self._previous_contiguous = reason is None
        if reason:
            self.number += 1
            self.uses_pts = frame.pts is not None
            self.origin = frame.pts if self.uses_pts else frame.received
        self.previous = frame
        timestamp = (frame.pts if self.uses_pts else frame.received) - self.origin
        return reason, timestamp
