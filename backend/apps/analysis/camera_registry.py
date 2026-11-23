"""Server-owned inventory. Browser input cannot change a network destination."""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
from unicodedata import category, normalize
from urllib.parse import unquote, urlsplit, urlunsplit
import ipaddress


MEDIA_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,126}\.mp4")
MEDIA_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SHA256 = re.compile(r"[a-fA-F0-9]{64}")


def display_text(value):
    if not isinstance(value, str) or len(value) > 512:
        return None
    text = normalize("NFKC", value).strip()
    if any(c in "/\\%<>" or category(c)[0] == "C" or category(c) in {"Zl", "Zp"} for c in text):
        return None
    return text or None


def public_link(value):
    if (not isinstance(value, str) or len(value) > 2048
            or any(c.isspace() or category(c)[0] == "C" or c == "\\" for c in value)):
        return None
    try:
        link = urlsplit(value)
        if link.scheme not in {"http", "https"} or "@" in link.netloc or link.port not in (None, {"http": 80, "https": 443}[link.scheme]):
            return None
        host = link.hostname or ""
        try:
            address = ipaddress.ip_address(host)
            if not address.is_global or address.is_multicast or address.is_reserved:
                return None
        except ValueError:
            if (len(host) > 253 or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host)
                    or host.endswith((".localhost", ".localdomain", ".local", ".internal", ".lan",
                                      ".home", ".home.arpa", ".test", ".invalid", ".onion"))):
                return None
        path = normalize("NFKC", unquote(link.path, errors="strict"))
        if ("//" in path or re.search(r"(?:^|/)(?:\.{1,2}(?:/|$)|[A-Za-z]:)", path)
                or any(c in "\\%<>@" or category(c)[0] == "C" for c in path)):
            return None
        # Query strings and fragments can carry access tokens.
        return urlunsplit((link.scheme, link.netloc, link.path, "", ""))
    except (UnicodeError, ValueError):
        return None


def public_provenance(source):
    if not isinstance(source, dict) or not source:
        return None
    safe = {}
    for key, pattern in (("filename", MEDIA_FILENAME), ("media_id", MEDIA_ID), ("sha256", SHA256)):
        value = source.get(key)
        if isinstance(value, str) and pattern.fullmatch(value):
            safe[key] = value.lower() if key == "sha256" else value
    for key in ("title", "author", "license", "scenario", "footage"):
        safe[key] = display_text(source.get(key))
    for key in ("source_url", "license_url"):
        safe[key] = public_link(source.get(key))
    for key in ("duration_s", "fps", "width", "height"):
        value = source.get(key)
        safe[key] = value if type(value) in (int, float) and 0 < value < 1e12 and math.isfinite(value) else None
    safe["real"] = source.get("real") is True
    if not safe["title"]:
        safe["title"] = safe.get("filename")
    return safe


@dataclass(frozen=True)
class Camera:
    id: str
    name: str
    description: str
    provenance: dict | None
    expected_fps: float
    width: int
    height: int
    profile: str
    url: str
    source_fps: float | None = None

    @property
    def capture_fps(self):
        return self.expected_fps if self.source_fps is None else self.source_fps

    @property
    def spatial_key(self):
        return hashlib.sha256(f"operix:camera:{self.id}".encode()).hexdigest()


def enabled():
    return os.environ.get("OPERIX_CAMERA_LAB_ENABLED") == "1"


def managed():
    return enabled() and bool(os.environ.get("OPERIX_CAMERA_LAB_CONTROL_DIR"))


def automatic(camera):
    return managed() and urlsplit(camera.url).hostname == "mediamtx"


def capacity():
    raw = os.environ.get("OPERIX_CAMERA_LAB_CAPACITY", "2")
    return int(raw) if raw in {"1", "2", "3"} else 1


def approved_destination(camera_id):
    # IP cameras are an explicit server configuration, with IP literals pinned per slot.
    key = camera_id.replace("-", "_").upper()
    url = os.environ.get(f"OPERIX_{key}_RTSP_URL")
    if not url:
        return f"rtsp://mediamtx:8554/{camera_id}"
    try:
        parsed = urlsplit(url)
        permitted = ipaddress.ip_address(os.environ[f"OPERIX_{key}_ALLOWED_IP"])
        ip = ipaddress.ip_address(parsed.hostname)
        if (parsed.scheme == "rtsp" and ip == permitted and ip.is_private
                and not (ip.is_loopback or ip.is_link_local or ip.is_unspecified)
                and not parsed.fragment and parsed.path.startswith("/")
                and parsed.port != 0 and not any(ord(c) <= 32 or ord(c) == 127 for c in url)):
            return url
    except (ValueError, KeyError, TypeError):
        pass
    raise ValueError("Destino RTSP fuera del registro autorizado")


def media_registry():
    """Return the catalog and the media IDs assigned by the legacy manifest."""
    if not enabled():
        return {}, {}
    try:
        path = Path(os.environ["OPERIX_CAMERA_LAB_MANIFEST"])
        if path.stat().st_size > 256 * 1024:
            raise ValueError("Manifest demasiado grande")
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (KeyError, OSError, ValueError):
        document = {}
    source = document.get("source") if isinstance(document, dict) else None
    source = source if isinstance(source, dict) else {}
    items = document.get("clips", document.get("cameras", [])) if isinstance(document, dict) else document
    candidates = items.items() if isinstance(items, dict) else enumerate(items) if isinstance(items, list) else ()
    media, defaults, repeated_ids, repeated_slots = {}, {}, set(), set()
    for key, item in candidates:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename", item.get("file", ""))
        if not isinstance(filename, str) or not MEDIA_FILENAME.fullmatch(filename):
            continue
        media_id = item.get("id", item.get("camera_id", key if isinstance(key, str) else Path(filename).stem))
        source_hash = item.get("sha256", "")
        if (not isinstance(media_id, str) or not MEDIA_ID.fullmatch(media_id)
                or not isinstance(source_hash, str) or not SHA256.fullmatch(source_hash)):
            continue
        if media_id in media:
            repeated_ids.add(media_id)
        authors = source.get("authors")
        provenance = {
            "filename": filename, "sha256": source_hash.lower(),
            "title": item.get("title", source.get("title") or filename),
            "author": item.get("author", ", ".join(a for a in authors if isinstance(a, str))
                               if isinstance(authors, list) else None),
            "license": item.get("license", source.get("license")),
            "license_url": item.get("license_url", source.get("license_url")),
            "source_url": item.get("source_file_url", item.get("source_url", source.get("original_publication_url"))),
            "scenario": item.get("scenario"), "footage": item.get("footage"),
            "real": item.get("footage") in ("real industrial CCTV", "real recorded logistics trial"),
        }
        for field, alias in (("duration_s", "duration_seconds"), ("fps", "average_fps"),
                             ("width", "width"), ("height", "height")):
            provenance[field] = item.get(alias, item.get(field))
        media[media_id] = public_provenance(provenance)
        slot = item.get("camera_id", media_id)
        if slot in ("lab-cam-01", "lab-cam-02"):
            if slot in defaults:
                repeated_slots.add(slot)
            defaults[slot] = media_id
    return ({key: item for key, item in media.items() if key not in repeated_ids},
            {slot: key for slot, key in defaults.items() if slot not in repeated_slots and key not in repeated_ids})


def inventory(registry=None):
    if not enabled():
        return {}
    media, defaults = media_registry() if registry is None else registry
    result = {}
    for number in (1, 2):
        id_ = f"lab-cam-{number:02}"
        suffix = f"CAM{number:02}"
        try:
            fps = float(os.environ.get(f"OPERIX_LAB_{suffix}_FPS", "12"))
            source_fps = float(os.environ.get(f"OPERIX_LAB_{suffix}_SOURCE_FPS", str(fps)))
            width = int(os.environ.get(f"OPERIX_LAB_{suffix}_WIDTH", "960"))
            height = int(os.environ.get(f"OPERIX_LAB_{suffix}_HEIGHT", "540"))
            if not (1 <= fps <= source_fps <= 30 and 16 <= width <= 1920 and 16 <= height <= 1080):
                raise ValueError("Perfil de captura inválido")
            url = approved_destination(id_)
        except ValueError:
            continue
        result[id_] = Camera(id_, f"Cámara de laboratorio {number:02}", "Reproducción continua de un video autorizado.",
                            media.get(defaults.get(id_)), fps, width, height, "A" if number == 1 else "B", url,
                            source_fps)
    return result
