"""Return one JSON proposal from server-owned frames, video, or pinned RTSP.

Usage: python propose_calibration.py propose < request.json
The request supplies layout, optional video_path or frame_paths, and optional
expected width and height. RTSP is supplied exclusively via the environment.
The Django caller owns the source fields and the subprocess deadline.
"""

import base64
from datetime import datetime, timezone
import ipaddress
import json
import math
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

if __name__ == "__main__":
    os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
    os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"

import cv2
import numpy as np

from operix_engine.calibration_patterns import MAX_FRAMES, detect_marker_corners, empty_proposal, propose_calibration
from operix_engine.rtsp_frame_clock import ClockedReader


MAX_REQUEST_BYTES = 64 * 1024
MAX_JPEG_BYTES = 540_000  # 720,000 characters after base64 encoding.
SAMPLES = 5


def _rtsp_source():
    url = os.environ.get("OPERIX_RTSP_URL", "")
    try:
        parsed = urlsplit(url)
        allowed = ipaddress.ip_address(os.environ.get("OPERIX_RTSP_ALLOWED_IP", ""))
        if (parsed.scheme == "rtsp" and parsed.hostname and ipaddress.ip_address(parsed.hostname) == allowed
                and parsed.path.startswith("/") and not parsed.fragment and parsed.port != 0
                and not any(ord(char) <= 32 or ord(char) == 127 for char in url)):
            return url
    except ValueError:
        pass
    raise ValueError("Se requiere una fuente local del servidor o RTSP con IP autorizada")


def _file_path(value):
    if not isinstance(value, str) or not value or not Path(value).is_file():
        raise ValueError("El archivo local de la fuente no está disponible")
    return Path(value).resolve()


def _sample_capture(source, live):
    capture = cv2.VideoCapture()
    options = [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2500, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1500,
               cv2.CAP_PROP_N_THREADS, 1, cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE]
    try:
        if not capture.open(source, cv2.CAP_FFMPEG, options):
            raise OSError("No se pudo abrir la fuente")
        fps = capture.get(cv2.CAP_PROP_FPS)
        fps = min(fps, 60.) if math.isfinite(fps) and fps > 0 else 12.
        count = 0 if live else capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if math.isfinite(count) and count >= 1:
            last = min(int(count) - 1, round(fps * 2))
            targets = sorted({round(last * i / (SAMPLES - 1)) for i in range(SAMPLES)})
        else:
            stride = max(1, round(fps / 4))
            targets = range(0, SAMPLES * stride, stride)
        next_frame = 0
        for target in targets:
            while next_frame < target:
                if not capture.grab():
                    return
                next_frame += 1
            success, frame = capture.read()
            if not success or frame is None:
                return
            next_frame += 1
            yield frame
    finally:
        capture.release()


def _read_images(paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= MAX_FRAMES:
        raise ValueError(f"Se requieren entre 1 y {MAX_FRAMES} rutas a fotogramas locales")
    for value in paths:
        path = _file_path(value)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError("El archivo del fotograma excede el tamaño admitido")
        frame = cv2.imdecode(np.frombuffer(path.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise OSError("No se pudo decodificar el fotograma")
        yield frame


def _preview_jpeg(frame):
    for scale, quality in ((1., 82), (1., 65), (1., 50), (.75, 60), (.5, 60), (.25, 60)):
        preview = frame if scale == 1. else cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        success, jpeg = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if success and jpeg.nbytes <= MAX_JPEG_BYTES:
            return base64.b64encode(jpeg).decode("ascii")
    raise OSError("No se pudo codificar la vista previa")


def _clocked_capture(source, fps, dimensions, stream_id, stamps):
    reader = ClockedReader(source, fps, dimensions, stream_id)
    try:
        for _ in range(SAMPLES):
            frame, pts = reader.read_native()
            stamps.append({"captured_at": datetime.now(timezone.utc).isoformat(),
                           "ordinal": reader.source_ordinal,
                           "pts_s": pts if pts is not None and math.isfinite(pts) else None})
            yield reader.to_image(frame)
    finally:
        reader.close()


def propose(request):
    if not isinstance(request, dict):
        raise ValueError("La solicitud debe ser un objeto JSON")
    expected = tuple(request.get(axis) for axis in ("width", "height"))
    if any(value is not None and (type(value) is not int or value < 32) for value in expected):
        raise ValueError("Las dimensiones esperadas deben ser enteros positivos")
    if "video_path" in request and "frame_paths" in request:
        raise ValueError("Indique una sola fuente local")
    stamps = []
    if "clock" in request:
        clock = request["clock"]
        source = _clocked_capture(_rtsp_source(), clock["fps"], expected, clock["stream_id"], stamps)
    elif "frame_paths" in request:
        source = _read_images(request["frame_paths"])
    elif "video_path" in request:
        source = _sample_capture(str(_file_path(request["video_path"])), live=False)
    else:
        source = _sample_capture(_rtsp_source(), live=True)

    sampled = []

    def checked_frames():
        for frame in source:
            height, width = frame.shape[:2]
            if any(wanted is not None and actual != wanted for wanted, actual in zip(expected, (width, height))):
                raise ValueError("Las dimensiones capturadas no coinciden con la fuente configurada")
            sampled.append(frame)
            if "clock" not in request:
                stamps.append({"captured_at": datetime.now(timezone.utc).isoformat(),
                               "ordinal": None, "pts_s": None})
            yield frame

    try:
        if request.get("discover") is True:
            frame = next(checked_frames(), None)
            if frame is None:
                result = empty_proposal("no_frames")
            else:
                references = detect_marker_corners(frame, "DICT_4X4_50")
                reasons = () if references else ("no_known_markers",)
                result = {**empty_proposal(*reasons),
                          "status": "requires_review", "preview_frame_index": 0,
                          "width": frame.shape[1], "height": frame.shape[0],
                          "marker_corners": references}
        else:
            result = propose_calibration(checked_frames(), request.get("layout", request.get("pattern")),
                                         request.get("control_distances", ()))
    finally:
        source.close()
    preview_index = result["preview_frame_index"]
    result["preview_jpeg"] = _preview_jpeg(sampled[preview_index]) if preview_index is not None else None
    if preview_index is not None:
        result["capture_time"] = stamps[preview_index]
    return result


def _main():
    try:
        cv2.setNumThreads(2)
        if sys.argv[1:] not in ([], ["propose"]):
            raise ValueError("Comando esperado: propose")
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
        if len(raw) > MAX_REQUEST_BYTES:
            raise ValueError("La solicitud excede el tamaño admitido")
        result = propose(json.loads(raw))
        return json.dumps(result, allow_nan=False), 0
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        result = empty_proposal("invalid_request")
        result["message"] = "Se requiere una solicitud JSON válida"
    except ValueError as error:
        result = empty_proposal("invalid_request")
        result["message"] = str(error)
    except (OSError, cv2.error, np.linalg.LinAlgError):
        result = empty_proposal("capture_failed")
        result["message"] = "No se pudo procesar la fuente de calibración"
    return json.dumps(dict(result, preview_jpeg=None), allow_nan=False), 2


if __name__ == "__main__":
    # FFmpeg and OpenCV can log URLs at the native descriptor level. Only the
    # final response uses the original stdout, including on capture failures.
    with os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8") as response, open(os.devnull, "wb") as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())
        os.dup2(sink.fileno(), sys.stderr.fileno())
        payload, status = _main()
        response.write(payload + "\n")
    raise SystemExit(status)
