"""Admission limits for RTSP lab input and evidence."""

from contextlib import closing
from dataclasses import dataclass
import math
import re
import sqlite3
from time import time

from operix_engine.clip_capacity import SHARED_CLIP_TOTAL_BYTES
from operix_engine.rules import PairEventCandidate


BENCHMARK_EVENT_LIMIT = 20
MAX_PENDING = 3
RATE_WINDOW_SECONDS = 60
DEFAULT_STORAGE_BYTES = 512 * 1024 * 1024


class InvalidEventPolicy(ValueError):
    pass


@dataclass(frozen=True)
class EventPolicy:
    mode: str = "operational"
    events_per_minute: int = 6
    dedup_seconds: int = 120
    png_total_bytes: int = DEFAULT_STORAGE_BYTES
    clip_total_bytes: int = SHARED_CLIP_TOTAL_BYTES
    clip_retention_days: int = 0

    @classmethod
    def from_env(cls, env):
        prefix = "OPERIX_RTSP_LAB_"
        mode = env.get(prefix + "EVENT_POLICY", "operational")
        if mode == "benchmark":
            return cls(mode=mode)
        if mode != "operational":
            raise InvalidEventPolicy(prefix + "EVENT_POLICY")

        def integer(name, default, minimum, maximum):
            key = prefix + name
            try:
                value = int(env.get(key, default))
            except ValueError:
                raise InvalidEventPolicy(key) from None
            if not minimum <= value <= maximum:
                raise InvalidEventPolicy(key)
            return value

        return cls(
            events_per_minute=integer("EVENTS_PER_MINUTE", 6, 1, 120),
            dedup_seconds=integer("EVENT_DEDUP_SECONDS", 120, 1, 3600),
            png_total_bytes=integer("PNG_TOTAL_BYTES", DEFAULT_STORAGE_BYTES, 0, 2**40),
            clip_total_bytes=min(integer("CLIP_TOTAL_BYTES", SHARED_CLIP_TOTAL_BYTES, 0, 2**40),
                                 SHARED_CLIP_TOTAL_BYTES),
            clip_retention_days=integer("CLIP_RETENTION_DAYS", 0, 0, 3650),
        )

    @property
    def event_limit(self):
        return BENCHMARK_EVENT_LIMIT if self.mode == "benchmark" else None

    def status(self):
        operational = self.mode == "operational"
        return {
            "mode": self.mode,
            "event_limit": self.event_limit,
            "events_per_minute": self.events_per_minute if operational else None,
            "rate_scope": "camera" if operational else None,
            "rate_window_seconds": RATE_WINDOW_SECONDS if operational else None,
            "dedup_seconds": self.dedup_seconds if operational else None,
            "max_pending": MAX_PENDING,
            "png_total_bytes": self.png_total_bytes if operational else None,
            "clip_total_bytes": self.clip_total_bytes,
            "clip_retention_days": self.clip_retention_days,
        }


class CameraRateBudget:
    """Durable publication reservations shared across runs in the media volume."""

    def __init__(self, media_root, camera_id, *, clock=time):
        if not isinstance(camera_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", camera_id):
            raise InvalidEventPolicy("OPERIX_RTSP_LAB_CAMERA_ID")
        self.path = media_root / ".rtsp-lab-rate.sqlite3"
        self.camera_id = camera_id
        self.clock = clock

    def reserve(self, limit):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise OSError("Invalid RTSP rate budget path")
        with closing(sqlite3.connect(self.path, timeout=.25)) as db, db:
            # Count and reserve in the same write transaction, before attempting
            # registration. A crash cannot refund an already attempted event.
            db.execute("BEGIN IMMEDIATE")
            now = self.clock()
            if not math.isfinite(now) or now < 0:
                raise OSError("Invalid RTSP rate budget clock")
            db.execute("CREATE TABLE IF NOT EXISTS reservations (camera_id TEXT NOT NULL, expires_at REAL NOT NULL)")
            db.execute("DELETE FROM reservations WHERE expires_at <= ?", (now,))
            count, = db.execute("SELECT COUNT(*) FROM reservations WHERE camera_id = ?", (self.camera_id,)).fetchone()
            if count >= limit:
                return False
            db.execute("INSERT INTO reservations VALUES (?, ?)", (self.camera_id, now + RATE_WINDOW_SECONDS))
            return True


def episode_key(candidate):
    if isinstance(candidate, PairEventCandidate):
        return candidate.episode_key
    # Zone rules emit one candidate at the frame that opens an episode.
    return (candidate.rule_id, candidate.rule_version, (candidate.class_name, candidate.track_id),
            candidate.zone_id, candidate.frame_index, candidate.epoch)


class EventAdmission:
    def __init__(self, policy, *, rate_budget=None):
        if policy.mode == "operational" and rate_budget is None:
            raise InvalidEventPolicy("Operational event policy requires a camera rate budget")
        self.policy = policy
        self.rate_budget = rate_budget
        self.episodes = {}

    def has_quota(self, submitted):
        limit = self.policy.event_limit
        return limit is None or submitted < limit

    def suppress(self, candidate, *, now, submitted, pending):
        if not self.has_quota(submitted):
            return "quota"
        if self.policy.mode == "benchmark":
            return "backpressure" if pending >= MAX_PENDING else None

        while self.episodes:
            oldest = next(iter(self.episodes))
            if self.episodes[oldest] > now - self.policy.dedup_seconds:
                break
            del self.episodes[oldest]
        key = episode_key(candidate)
        if key in self.episodes:
            return "episode_duplicate"
        if pending >= MAX_PENDING:
            return "backpressure"
        try:
            reserved = self.rate_budget.reserve(self.policy.events_per_minute)
        except (OSError, sqlite3.Error):
            return "rate_unavailable"
        if not reserved:
            return "rate_limit"
        self.episodes[key] = now
        return None
