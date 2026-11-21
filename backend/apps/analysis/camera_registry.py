"""Server-owned inventory. Browser input cannot change a network destination."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
import ipaddress


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

    @property
    def spatial_key(self):
        return hashlib.sha256(f"operix:camera:{self.id}".encode()).hexdigest()


def enabled():
    return os.environ.get("OPERIX_CAMERA_LAB_ENABLED") == "1"


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


def inventory():
    if not enabled():
        return {}
    try:
        path = Path(os.environ["OPERIX_CAMERA_LAB_MANIFEST"])
        if path.stat().st_size > 256 * 1024:
            raise ValueError("Manifest demasiado grande")
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (KeyError, OSError, ValueError):
        document = {}
    source = document.get("source", {}) if isinstance(document, dict) else {}
    items = document.get("clips", document.get("cameras", [])) if isinstance(document, dict) else document
    candidates = items.items() if isinstance(items, dict) else enumerate(items) if isinstance(items, list) else ()
    media = {}
    for key, item in candidates:
        if not isinstance(item, dict):
            continue
        filename = str(item.get("filename", item.get("file", "")))
        camera_id = item.get("id", item.get("camera_id", key if isinstance(key, str) else Path(filename).stem))
        source_hash = item.get("sha256", "")
        if isinstance(camera_id, str) and isinstance(source_hash, str) and re.fullmatch(r"[a-fA-F0-9]{64}", source_hash):
            # Only publicly safe provenance, never path/credentials supplied by the user.
            media[camera_id] = {field: item[field] for field in (
                "filename", "title", "author", "license", "license_url", "source_url",
                "scenario", "real", "sha256", "duration_s", "fps", "width", "height",
            ) if field in item}
            media[camera_id].update({
                "filename": filename, "sha256": source_hash.lower(),
                "title": source.get("title"), "author": ", ".join(source.get("authors", [])),
                "license": source.get("license"), "license_url": source.get("license_url"),
                "source_url": item.get("source_file_url", source.get("original_publication_url")),
                "duration_s": item.get("duration_seconds"), "fps": item.get("average_fps"),
                "real": item.get("footage") == "real industrial CCTV",
            })
    result = {}
    for number in (1, 2):
        id_ = f"lab-cam-{number:02}"
        suffix = f"CAM{number:02}"
        try:
            fps = float(os.environ.get(f"OPERIX_LAB_{suffix}_FPS", "12"))
            width = int(os.environ.get(f"OPERIX_LAB_{suffix}_WIDTH", "960"))
            height = int(os.environ.get(f"OPERIX_LAB_{suffix}_HEIGHT", "540"))
            if not (1 <= fps <= 30 and 16 <= width <= 1920 and 16 <= height <= 1080):
                raise ValueError("Perfil de captura inválido")
            url = approved_destination(id_)
        except ValueError:
            continue
        result[id_] = Camera(id_, f"Cámara de laboratorio {number:02}", "Reproducción continua de un video autorizado.",
                            media.get(id_), fps, width, height, "A" if number == 1 else "B", url)
    return result
