"""Generación local y acotada de extractos de un resultado confirmado."""

import hashlib
import json
import logging
import math
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from django.conf import settings
from django.db import close_old_connections, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import reverse

from .models import Event

logger = logging.getLogger(__name__)
clip_slot = threading.Lock()


def clip_directory(event):
    return Path(settings.MEDIA_ROOT) / "evidence-clips" / str(event.pk) / str(event.analysis_run_id)


def clip_info(event):
    directory = clip_directory(event)
    try:
        video = directory / "clip.mp4"
        if not video.is_file():
            return None
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        if (metadata["event_id"] != str(event.pk) or metadata["analysis_run_id"] != str(event.analysis_run_id)
                or metadata["source_sha256"] != event.source.get("video_sha256")
                or metadata["config_sha256"] != event.source.get("config_sha256")
                or metadata["event_frame"] != event.frame_index
                or metadata["event_timestamp_s"] != str(event.video_timestamp_s)
                or not 0 < video.stat().st_size == metadata["bytes"]):
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return {**metadata, "url": reverse("event-clip", kwargs={"pk": event.pk, "run": event.analysis_run_id})}


def clip_window(frame, count, fps, seconds):
    radius = math.floor(fps * seconds)
    return max(0, frame - radius), min(count, frame + radius + 1)


@receiver(post_delete, sender=Event)
def remove_event_clip(sender, instance, using, **kwargs):
    directory = clip_directory(instance)
    transaction.on_commit(lambda: shutil.rmtree(directory, ignore_errors=True), using=using)


def generate_clips(video_path, config):
    """Usa solo eventos persistidos del run y del snapshot que produjo el MP4."""
    fps, count = config["video"]["fps"], config["video"]["frames"]
    if not 0 < fps <= 120 or count < 1:
        return
    source = config["source"]
    events = Event.objects.filter(
        analysis_run_id=config["analysis_run_id"],
        source__session_id=source["session_id"], source__session_run=source["session_run"],
        source__video_sha256=source["video_sha256"], source__config_sha256=source["config_sha256"],
    ).order_by("frame_index", "id")
    root = Path(settings.MEDIA_ROOT) / "evidence-clips"
    root.mkdir(parents=True, exist_ok=True)
    remaining = settings.OPERIX_CLIP_TOTAL_BYTES - sum(p.stat().st_size for p in root.glob("*/*/clip.mp4"))
    for event in events[:settings.OPERIX_CLIP_MAX_PER_RUN]:
        if (not 0 <= event.frame_index < count or abs(float(event.video_timestamp_s) - event.frame_index / fps)
                > max(0.001, 0.25 / fps) or clip_info(event)):
            continue
        limit = min(remaining, settings.OPERIX_CLIP_MAX_BYTES)
        if limit <= 0:
            return
        start, stop = clip_window(event.frame_index, count, fps, settings.OPERIX_CLIP_WINDOW_SECONDS)
        destination = clip_directory(event)
        destination.parent.mkdir(parents=True, exist_ok=True)
        scratch = Path(tempfile.mkdtemp(prefix=".clip-", dir=root))
        try:
            output = scratch / "clip.mp4"
            script = settings.BASE_DIR.parent / "engine/scripts/extract_evidence_clip.py"
            subprocess.run([settings.OPERIX_ENGINE_PYTHON, "-B", str(script), str(video_path),
                            str(output), str(start), str(stop), str(fps), str(limit)], check=True, timeout=45,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8",
                           errors="replace")
            size = output.stat().st_size
            if not 0 < size <= limit:
                continue
            with output.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            metadata = {
                "kind": "annotated", "event_id": str(event.pk), "analysis_run_id": str(event.analysis_run_id),
                "source_sha256": source["video_sha256"], "config_sha256": source["config_sha256"],
                "event_frame": event.frame_index, "event_timestamp_s": str(event.video_timestamp_s),
                "start_frame": start, "end_frame_exclusive": stop, "fps": fps,
                "duration_s": (stop - start) / fps,
                "event_offset_s": (event.frame_index - start) / fps, "bytes": size, "sha256": digest,
            }
            (scratch / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            with transaction.atomic():
                if not Event.objects.select_for_update().filter(pk=event.pk).exists():
                    continue
                scratch.rename(destination)
            remaining -= size
        except subprocess.CalledProcessError as error:
            details = (error.stderr or "").strip().splitlines()
            logger.warning("No se pudo codificar el clip %s (%s): %s",
                           event.pk, error.returncode, details[-1] if details else "")
        except (OSError, subprocess.TimeoutExpired) as error:
            logger.warning("No se pudo guardar el clip %s: %s", event.pk, type(error).__name__)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)


def finish_clips(source_link, config):
    """Ejecutado fuera del bloqueo de sesión y después de confirmar el resultado."""
    close_old_connections()
    try:
        generate_clips(source_link, config)
    except Exception:
        logger.exception("No se pudo finalizar la generación de clips")
    finally:
        shutil.rmtree(source_link.parent, ignore_errors=True)
        close_old_connections()
        clip_slot.release()


def reserve_result(video_path, config):
    if not settings.OPERIX_CLIPS_ENABLED or not config.get("source") or not config.get("video"):
        return None
    if not clip_slot.acquire(blocking=False):
        return None
    directory = None
    try:
        directory = Path(tempfile.mkdtemp(prefix="operix-clip-source-", dir=video_path.parent.parent))
        link = directory / "annotated.mp4"
        os.link(video_path, link)
        return link
    except OSError:
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)
        clip_slot.release()
        logger.warning("No se pudo reservar el MP4 confirmado para clips")
        return None
