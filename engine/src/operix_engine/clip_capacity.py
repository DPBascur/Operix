"""Shared publication of verified clips into one media volume."""

from contextlib import contextmanager
import errno
import os
from time import monotonic, sleep


SHARED_CLIP_TOTAL_BYTES = 512 * 1024 * 1024


def stored_bytes(paths):
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except FileNotFoundError:
            continue  # A backend deletion can race the scan.
    return total


def _try_lock(stream):
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise
        return False
    return True


@contextmanager
def exclusive_file_slot(path, *, timeout_s=2):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the lock file in place so concurrent processes always lock the
    # same file. Closing the handle releases the lock, including on failure.
    with path.open("a+b") as stream:
        deadline = monotonic() + timeout_s
        while not _try_lock(stream):
            if monotonic() >= deadline:
                yield False
                return
            sleep(.05)
        yield True


def clip_bytes_remaining(root, total_bytes):
    return min(total_bytes, SHARED_CLIP_TOTAL_BYTES) - stored_bytes(root.glob("*/*/clip.mp4"))


def publish_clip(root, scratch, destination, *, total_bytes):
    # Encoding is deliberately outside the critical section. The staging
    # directory is one level deep, so only already published clips count here.
    with exclusive_file_slot(root / ".capacity.lock") as acquired:
        if not acquired:
            return "storage_busy"
        if destination.exists():
            return "existing" if (destination / "clip.mp4").is_file() else "unavailable"
        size = (scratch / "clip.mp4").stat().st_size
        if not 0 < size <= clip_bytes_remaining(root, total_bytes):
            return "disk_limit"
        destination.parent.mkdir(parents=True, exist_ok=True)
        scratch.rename(destination)
    return "saved"
