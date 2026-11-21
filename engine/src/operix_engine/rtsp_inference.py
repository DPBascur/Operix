"""Local, opt-in RTSP detection over a Unix stream socket."""

from __future__ import annotations

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
import errno
import json
import math
import os
from pathlib import Path
import socket
import stat
import struct
from threading import BoundedSemaphore, Condition, Event, Lock, Thread
from time import perf_counter
from uuid import UUID, uuid4

import numpy as np

from operix_engine.detection import BoundingBox, Detection


_LENGTH = struct.Struct("!I")
_REQUEST_LIMIT = 2048
_RESPONSE_LIMIT = 128 * 1024
_ROLES = ("person", "forklift")


class InferenceError(RuntimeError):
    """The frame has no usable inference result."""


class InferenceTimeout(InferenceError, TimeoutError):
    """The frame's absolute deadline elapsed."""


class InferenceBusy(InferenceError):
    """The camera/run already has a request in flight."""


class InferenceGenerationChanged(InferenceError):
    """The broker changed. This client must no longer advance the run."""


class FatalInferenceError(RuntimeError):
    """Detector state can no longer be used. The broker must exit."""


def _remaining(deadline):
    seconds = deadline - perf_counter()
    if seconds <= 0:
        raise InferenceTimeout("inference deadline elapsed")
    return seconds


def _read(sock, buffer, deadline):
    view = memoryview(buffer).cast("B")
    while view:
        sock.settimeout(_remaining(deadline))
        count = sock.recv_into(view)
        if not count:
            _remaining(deadline)
            raise InferenceError("inference connection closed")
        view = view[count:]


def _read_json(sock, limit, deadline):
    prefix = bytearray(_LENGTH.size)
    _read(sock, prefix, deadline)
    size, = _LENGTH.unpack(prefix)
    if not 0 < size <= limit:
        raise InferenceError("invalid inference message size")
    body = bytearray(size)
    _read(sock, body, deadline)
    return json.loads(body)


def _json_packet(message, limit):
    body = json.dumps(message, separators=(",", ":"), allow_nan=False).encode()
    if len(body) > limit:
        raise InferenceError("inference message too large")
    return _LENGTH.pack(len(body)) + body


def _send(sock, data, deadline):
    sock.settimeout(_remaining(deadline))
    sock.sendall(data)


def _broker_generation(value):
    if not isinstance(value, str) or len(value) != 32:
        raise ValueError("invalid broker generation")
    identifier = UUID(hex=value)
    if identifier.version != 4 or identifier.hex != value:
        raise ValueError("invalid broker generation")
    return identifier


@dataclass(frozen=True, slots=True)
class _Identity:
    camera_id: str
    run_id: str
    epoch: int
    frame_index: int
    request_id: str
    deadline: float
    height: int
    width: int
    version: int = 1

    def __post_init__(self):
        for value in (self.camera_id, self.run_id, self.request_id):
            if not isinstance(value, str) or not 1 <= len(value) <= 128 or not value.isascii():
                raise ValueError("invalid inference identifier")
        for value in (self.epoch, self.frame_index):
            if type(value) is not int or not 0 <= value < 2**63:
                raise ValueError("invalid frame identity")
        if (type(self.height) is not int or not 1 <= self.height <= 1080
                or type(self.width) is not int or not 1 <= self.width <= 1920):
            raise ValueError("invalid frame dimensions")
        if type(self.deadline) is not float or not math.isfinite(self.deadline):
            raise ValueError("invalid inference deadline")
        if type(self.version) is not int or self.version != 1:
            raise ValueError("unsupported inference protocol")

    def wire(self):
        return {name: getattr(self, name) for name in self.__slots__}


@dataclass(frozen=True, slots=True)
class InferenceResult:
    person: tuple[Detection, ...]
    forklift: tuple[Detection, ...]
    batch_size: int
    wait_ms: float
    person_ms: float
    forklift_ms: float

    def __post_init__(self):
        if type(self.batch_size) is not int or not 1 <= self.batch_size <= 4:
            raise ValueError("invalid inference batch size")
        for value in (self.wait_ms, self.person_ms, self.forklift_ms):
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("invalid inference timing")


def _encode_detection(item):
    box = item.bounding_box
    return [item.class_id, item.confidence, box.x_min, box.y_min, box.x_max, box.y_max]


def _decode_detections(rows, role):
    if not isinstance(rows, list):
        raise ValueError("invalid detection list")
    detections = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            raise ValueError("invalid detection row")
        class_id, confidence, *box = row
        if type(class_id) is not int or any(type(value) not in (int, float) for value in (confidence, *box)):
            raise ValueError("invalid detection")
        detections.append(Detection(class_id, role, confidence, BoundingBox(*box)))
    return tuple(detections)


@contextmanager
def _unix_connection(path, deadline):
    if not hasattr(socket, "AF_UNIX"):
        raise InferenceError("Unix sockets are unavailable")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(_remaining(deadline))
        sock.connect(os.fspath(path))
        yield sock


def check_ready(socket_path, *, timeout=.25):
    """Probe a live, warmed broker through its local protocol."""
    if not 0 < timeout <= 1:
        raise ValueError("readiness timeout must be between 0 and 1 second")
    deadline = perf_counter() + timeout
    probe = {"version": 1, "probe": uuid4().hex}
    try:
        with _unix_connection(socket_path, deadline) as sock:
            _send(sock, _json_packet(probe, _REQUEST_LIMIT), deadline)
            reply = _read_json(sock, _RESPONSE_LIMIT, deadline)
            if not isinstance(reply, dict):
                return False
            _broker_generation(reply.pop("generation", None))
            return reply == {**probe, "status": "ready"} and perf_counter() < deadline
    except (OSError, InferenceError, ValueError, RecursionError):
        return False


@contextmanager
def _listener(path, backlog):
    import fcntl

    path.parent.mkdir(mode=0o700, exist_ok=True)
    parent = path.parent.lstat()
    uid = os.geteuid()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != uid
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise ValueError("socket directory must be owned by the broker UID with mode 0700")
    # Keep the lock inode across restarts so all brokers contend on the same file.
    fd = os.open(path.with_name(path.name + ".lock"),
                 os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        lock = os.fstat(fd)
        if not stat.S_ISREG(lock.st_mode) or lock.st_uid != uid or stat.S_IMODE(lock.st_mode) != 0o600:
            raise ValueError("invalid inference socket lock file")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InferenceError("inference socket is owned by a running broker") from exc
        try:
            previous = path.lstat()
        except FileNotFoundError:
            previous = None
        if previous is not None:
            if not stat.S_ISSOCK(previous.st_mode) or previous.st_uid != uid:
                raise ValueError("existing inference path is not a socket owned by the broker UID")
            try:
                with _unix_connection(path, perf_counter() + .1):
                    raise InferenceError("inference socket already has a listener")
            except OSError as exc:
                if exc.errno != errno.ECONNREFUSED or not os.path.samestat(previous, path.lstat()):
                    raise
                path.unlink()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.bind(os.fspath(path))
            bound = path.lstat()
            try:
                path.chmod(0o600)
                sock.listen(backlog)
                sock.settimeout(.05)
                yield sock
            finally:
                try:
                    if os.path.samestat(bound, path.lstat()):
                        path.unlink()
                except FileNotFoundError:
                    pass
    finally:
        os.close(fd)


class InferenceClient:
    """Synchronous detection for one camera/run, using a shared perf_counter clock."""

    def __init__(self, socket_path, *, camera_id: str, run_id: str):
        self.socket_path = os.fspath(socket_path)
        self.camera_id = camera_id
        self.run_id = run_id
        self._in_flight = Lock()
        self._generation = None
        self._generation_changed = False

    def _connect(self, deadline):
        return _unix_connection(self.socket_path, deadline)

    def _reply(self, sock, identity):
        response = _read_json(sock, _RESPONSE_LIMIT, identity.deadline)
        if _Identity(**response["identity"]) != identity:
            raise InferenceError("inference response identity mismatch")
        _remaining(identity.deadline)
        generation = _broker_generation(response["generation"])
        if self._generation is None:
            if response["status"] == "ready":
                self._generation = generation
        elif generation != self._generation:
            self._generation_changed = True
            raise InferenceGenerationChanged("inference broker generation changed")
        return response

    def infer(self, frame, *, epoch: int, frame_index: int, deadline: float) -> InferenceResult:
        """Return both class channels before the absolute perf_counter deadline."""
        if not self._in_flight.acquire(blocking=False):
            raise InferenceBusy("camera/run already in flight")
        try:
            if self._generation_changed:
                raise InferenceGenerationChanged("inference broker generation changed")
            if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
                    or frame.ndim != 3 or frame.shape[2] != 3):
                raise ValueError("expected a uint8 BGR frame")
            height, width, _ = frame.shape
            identity = _Identity(self.camera_id, self.run_id, epoch, frame_index,
                                 uuid4().hex, float(deadline), height, width)
            deadline = identity.deadline
            _remaining(deadline)
            with self._connect(deadline) as sock:
                _send(sock, _json_packet(identity.wire(), _REQUEST_LIMIT), deadline)
                admission = self._reply(sock, identity)["status"]
                if admission == "busy":
                    raise InferenceBusy("camera/run already in flight")
                if admission != "ready":
                    raise InferenceError("invalid inference admission")
                _send(sock, memoryview(np.ascontiguousarray(frame)).cast("B"), deadline)
                response = self._reply(sock, identity)
            if response["status"] != "ok":
                raise InferenceError("broker could not infer frame")
            result = InferenceResult(
                _decode_detections(response["person"], "person"),
                _decode_detections(response["forklift"], "forklift"),
                response["batch_size"], response["wait_ms"], response["person_ms"], response["forklift_ms"],
            )
            _remaining(deadline)
            return result
        except InferenceError:
            raise
        except TimeoutError as exc:
            raise InferenceTimeout("inference deadline elapsed") from exc
        except OSError as exc:
            _remaining(deadline)
            raise InferenceError("inference exchange unavailable") from exc
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            raise InferenceError("invalid or unavailable inference exchange") from exc
        finally:
            self._in_flight.release()


@dataclass(eq=False, slots=True)
class _Request:
    identity: _Identity
    frame: np.ndarray
    ready_at: float
    done: Event = field(default_factory=Event)
    scheduled: bool = False
    packet: bytes | None = None

    @property
    def key(self):
        return self.identity.camera_id, self.identity.run_id


class InferenceBroker:
    """Serve two detectors on one inference thread with bounded connection workers."""

    def __init__(self, socket_path, *, person, forklift, batch_cap=1, batch_wait_s=.003,
                 max_clients=8, max_request_s=1.0, synchronize=None, fatal_detector_errors=False):
        if batch_cap not in (1, 2, 4) or not 0 <= batch_wait_s <= .020:
            raise ValueError("invalid batch cap or wait (maximum 20 ms)")
        if not batch_cap <= max_clients <= 32 or not 0 < max_request_s <= 5:
            raise ValueError("invalid connection or request lifetime limit")
        self.path = Path(socket_path)
        self.detectors = (person, forklift)
        self.batch_cap = batch_cap
        self.batch_wait_s = batch_wait_s
        self.max_clients = max_clients
        self.max_request_s = max_request_s
        self._generation = uuid4().hex
        self.synchronize = synchronize
        self.fatal_detector_errors = fatal_detector_errors
        self._changed = Condition()
        self._stopping = Event()
        self._pending = deque()
        self._active = set()
        self._accept_error = None

    def stop(self):
        """Request shutdown. The current detector call is allowed to finish."""
        self._stopping.set()
        with self._changed:
            self._changed.notify_all()

    def serve_forever(self):
        """Bind and serve until stopped or a fatal detector failure escapes."""
        if os.name != "posix" or not hasattr(socket, "AF_UNIX"):
            raise InferenceError("inference broker requires POSIX Unix sockets")
        with _listener(self.path, self.max_clients) as listener:
            with ThreadPoolExecutor(max_workers=self.max_clients) as workers:
                acceptor = Thread(target=self._accept, args=(listener, workers))
                acceptor.start()
                try:
                    self._schedule()
                finally:
                    self.stop()
                    acceptor.join()
        if self._accept_error is not None:
            raise InferenceError("inference listener failed") from self._accept_error

    def _accept(self, listener, workers):
        slots = BoundedSemaphore(self.max_clients)
        while not self._stopping.is_set():
            if not slots.acquire(timeout=.05):
                continue
            try:
                sock, _ = listener.accept()
            except TimeoutError:
                slots.release()
                continue
            except OSError as exc:
                slots.release()
                self._accept_error = exc
                self.stop()
                return
            workers.submit(self._handle, sock, slots)

    def _handle(self, sock, slot):
        request = None
        admitted = False
        try:
            with sock:
                limit = perf_counter() + self.max_request_s
                header = _read_json(sock, _REQUEST_LIMIT, limit)
                if (isinstance(header, dict) and header.keys() == {"version", "probe"}
                        and type(header["version"]) is int and header["version"] == 1
                        and isinstance(header["probe"], str) and len(header["probe"]) == 32):
                    if not self._stopping.is_set():
                        _send(sock, _json_packet(
                            {**header, "status": "ready", "generation": self._generation}, _RESPONSE_LIMIT,
                        ), limit)
                    return
                identity = _Identity(**header)
                deadline = identity.deadline
                if deadline > limit:
                    raise InferenceError("inference deadline exceeds broker limit")
                _remaining(deadline)
                key = identity.camera_id, identity.run_id
                with self._changed:
                    if self._stopping.is_set():
                        return
                    if key not in self._active:
                        self._active.add(key)
                        admitted = True
                if not admitted:
                    _send(sock, self._response(identity, "busy"), deadline)
                    return
                _send(sock, self._response(identity, "ready"), deadline)
                frame = np.empty((identity.height, identity.width, 3), dtype=np.uint8)
                _read(sock, frame, deadline)
                request = _Request(identity, frame, perf_counter())
                with self._changed:
                    if self._stopping.is_set():
                        return
                    self._pending.append(request)
                    self._changed.notify()
                while not request.done.wait(_remaining(deadline)):
                    pass
                if request.packet is not None:
                    _send(sock, request.packet, deadline)
        except (OSError, InferenceError, ValueError, TypeError, OverflowError, RecursionError):
            return
        finally:
            if admitted:
                with self._changed:
                    if request is None or not request.scheduled:
                        if request in self._pending:
                            self._pending.remove(request)
                            self._changed.notify()
                        self._active.remove(key)
            slot.release()

    def _response(self, identity, status, **fields):
        return _json_packet(
            {"identity": identity.wire(), "status": status, "generation": self._generation, **fields},
            _RESPONSE_LIMIT,
        )

    def _next_batch(self):
        with self._changed:
            while not self._stopping.is_set():
                now = perf_counter()
                ready = [request for request in self._pending if request.identity.deadline > now]
                if not ready:
                    self._changed.wait(.05)
                    continue
                first = ready[0]
                batch = [request for request in ready if request.frame.shape == first.frame.shape][:self.batch_cap]
                until = first.ready_at + self.batch_wait_s
                earliest_deadline = min(request.identity.deadline for request in batch)
                if len(batch) < self.batch_cap and now < until < earliest_deadline:
                    self._changed.wait(until - now)
                    continue
                for request in batch:
                    self._pending.remove(request)
                    request.scheduled = True
                return batch
            return []

    def _schedule(self):
        try:
            while batch := self._next_batch():
                try:
                    self._infer(batch)
                finally:
                    with self._changed:
                        for request in batch:
                            self._active.remove(request.key)
                            request.done.set()
        finally:
            self.stop()
            with self._changed:
                for request in self._pending:
                    request.done.set()

    def _infer(self, batch):
        try:
            now = perf_counter()
            if all(request.identity.deadline <= now for request in batch):
                return
            if self.synchronize is not None:
                self.synchronize()
            now = perf_counter()
            live = [request for request in batch if request.identity.deadline > now]
            if not live:
                return
            frames = tuple(request.frame for request in live)
            channels = []
            starts = []
            elapsed_ms = []
            for detector in self.detectors:
                began = perf_counter()
                rows = (detector.detect(frames[0]),) if len(frames) == 1 else detector.detect_batch(frames)
                if self.synchronize is not None:
                    self.synchronize()
                elapsed_ms.append((perf_counter() - began) * 1000)
                starts.append(began)
                if len(rows) != len(frames):
                    raise RuntimeError("detector returned the wrong batch size")
                channels.append(rows)
        except FatalInferenceError:
            raise
        except Exception as exc:
            if self.fatal_detector_errors:
                raise FatalInferenceError("detector failure stopped the broker") from exc
            for request in batch:
                request.packet = self._response(request.identity, "error")
            return
        for request, person, forklift in zip(live, *channels, strict=True):
            if request.identity.deadline <= perf_counter():
                continue
            try:
                detections = {role: [_encode_detection(item) for item in rows if item.class_name == role]
                              for role, rows in zip(_ROLES, (person, forklift), strict=True)}
                request.packet = self._response(
                    request.identity, "ok", **detections, batch_size=len(frames),
                    wait_ms=(starts[0] - request.ready_at) * 1000,
                    person_ms=elapsed_ms[0], forklift_ms=elapsed_ms[1],
                )
            except Exception:
                request.packet = self._response(request.identity, "error")
