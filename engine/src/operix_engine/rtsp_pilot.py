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


class Capture:
    def __init__(self, open_source, *, fps, capacity=6, max_age=.5):
        if not math.isfinite(fps) or not 0 < fps <= 60 or not 1 <= capacity <= 32 or not 0 < max_age <= 2:
            raise ValueError("Límites de captura inválidos")
        self.open_source = open_source
        self.fps = fps
        self.max_age = max_age
        self.capacity = capacity
        self.stop = Event()
        self.ready = Condition()
        self.queue = deque()
        self.counts = Counter()
        self.depth = 0
        self.connection = 0
        self.thread = Thread(target=self._read, name="rtsp-capture", daemon=True)

    def _read(self):
        index = 0
        failures = 0
        while not self.stop.is_set():
            reader = None
            try:
                reader = self.open_source()
                with self.ready:
                    self.connection += 1
                    self.counts["connections"] += 1
                while not self.stop.is_set():
                    image, pts = reader.read()
                    received = monotonic()
                    failures = 0
                    with self.ready:
                        self.counts["decoded"] += 1
                        if len(self.queue) == self.capacity:
                            self.queue.popleft()
                            self.counts["queue_drop"] += 1
                        self.queue.append(Frame(index, self.connection, received, pts, image, len(self.queue) + 1))
                        index += 1
                        self.depth = max(self.depth, len(self.queue))
                        self.ready.notify()
            except (OSError, ValueError):
                if not self.stop.is_set():
                    with self.ready:
                        self.counts["read_failure" if reader else "open_failure"] += 1
            finally:
                if reader is not None:
                    reader.close()
                with self.ready:
                    self.counts["disconnect_drop" if not self.stop.is_set() else "shutdown_drop"] += len(self.queue)
                    self.queue.clear()
            failures += 1
            self.stop.wait(min(5, .25 * 2 ** min(failures - 1, 5)))

    def __enter__(self):
        self.thread.start()
        return self

    def next(self, timeout=.2):
        with self.ready:
            self.ready.wait_for(lambda: self.queue or self.stop.is_set(), timeout)
            while self.queue:
                frame = self.queue.popleft()
                if monotonic() - frame.received <= self.max_age:
                    return frame
                self.counts["expired_drop"] += 1
        return None

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=6)
        if self.thread.is_alive():
            raise RuntimeError("El lector RTSP no finalizó dentro del límite")


class Epoch:
    """Nunca reenumera huecos. Usa una única base de tiempo por época."""

    def __init__(self, fps):
        self.fps = fps
        self.previous = None
        self.number = 0
        self.origin = 0
        self.uses_pts = False

    def advance(self, frame):
        previous = self.previous
        reason = None
        if previous is None:
            reason = "initial"
        elif previous.connection != frame.connection:
            reason = "reconnect"
        elif previous.index + 1 != frame.index:
            reason = "queue_gap"
        elif previous.pts is not None and frame.pts is not None and not (
            0 < frame.pts - previous.pts <= 1.75 / self.fps
        ):
            reason = "source_pts_gap"
        elif self.uses_pts and frame.pts is None:
            reason = "missing_pts"
        elif not self.uses_pts and frame.pts is not None:
            reason = "pts_available"
        elif previous.received >= frame.received or frame.received - previous.received > .5:
            reason = "arrival_gap"
        if reason:
            self.number += 1
            self.uses_pts = frame.pts is not None
            self.origin = frame.pts if self.uses_pts else frame.received
        self.previous = frame
        timestamp = (frame.pts if self.uses_pts else frame.received) - self.origin
        return reason, timestamp
