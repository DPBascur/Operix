"""Calibración explícita del plano del suelo, en metros aproximados."""
import hashlib
import json
import re
from datetime import datetime
from functools import lru_cache
from sys import float_info

import cv2
import numpy as np

from .framing import REFERENCE

METHOD = "ground_plane_contact_edges_v1"


def _normalized_point(point):
    return (isinstance(point, list) and len(point) == 2
            and all(type(axis) in (int, float) and 0 <= axis <= 1 for axis in point))


def _confirmed_pattern(snapshot, evidence):
    fields = {"dictionary", "width", "height", "marker_corners", "capture_signature",
              "preview_sha256", "provenance", "layout", "quality", "control", "image_transform"}
    if not isinstance(evidence, dict) or not fields <= evidence.keys() or evidence.keys() - fields - {"capture"}:
        raise ValueError("Trazabilidad del patrón incompleta")
    if "capture" in evidence:
        capture = evidence["capture"]
        if (not isinstance(capture, dict) or set(capture) != {"camera_id", "run_id", "epoch", "emission_id",
                "source_sha256", "captured_at", "ordinal", "pts_s", "width", "height"}
                or any(capture[key] != evidence[key] for key in ("width", "height"))):
            raise ValueError("Trazabilidad del fotograma incompleta")
    if (evidence["image_transform"] != "native_frame"
            or any(type(evidence[key]) is not int or not 16 <= evidence[key] <= 4096 for key in ("width", "height"))):
        raise ValueError("Dimensiones de la referencia inválidas")
    if any(not isinstance(evidence[key], str) or not re.fullmatch(r"[a-f0-9]{64}", evidence[key])
           for key in ("capture_signature", "preview_sha256")):
        raise ValueError("Huella de captura inválida")
    if not isinstance(evidence["provenance"], str) or not 1 <= len(evidence["provenance"].strip()) <= 250:
        raise ValueError("Registre cómo se midió la disposición del patrón")
    markers = evidence["marker_corners"]
    if (not isinstance(markers, dict) or not 3 <= len(markers) <= 4
            or not all(isinstance(key, str) and re.fullmatch(r"0|[1-9][0-9]{0,2}", key)
                       and isinstance(corners, list) and len(corners) == 4
                       and all(_normalized_point(p) for p in corners) for key, corners in markers.items())):
        raise ValueError("Esquinas del patrón inválidas")
    if (not isinstance(evidence["layout"], dict) or not isinstance(evidence["quality"], dict)
            or not isinstance(evidence["dictionary"], str) or len(evidence["dictionary"]) > 32):
        raise ValueError("Disposición o indicadores del patrón inválidos")
    control = evidence["control"]
    inputs = {"image_points", "distance_m", "tolerance_m", "provenance"}
    if not isinstance(control, dict) or not inputs <= control.keys():
        raise ValueError("Declare una distancia de comprobación medida de forma independiente")
    points = control["image_points"]
    distance, tolerance = control["distance_m"], control["tolerance_m"]
    provenance = control["provenance"]
    if (not isinstance(points, list) or len(points) != 2 or not all(map(_normalized_point, points))
            or points[0] == points[1] or type(distance) not in (float, int) or not 0 < distance <= 10000
            or type(tolerance) not in (float, int) or not 0 < tolerance < distance
            or not isinstance(provenance, str) or not 1 <= len(provenance.strip()) <= 250):
        raise ValueError("Medida, tolerancia o puntos de comprobación inválidos")
    if not contacts_in_calibrated_area(snapshot, points):
        raise ValueError("La medida de comprobación debe quedar dentro del área calibrada")
    dimensions = np.array([evidence["width"], evidence["height"]])
    offsets = (np.asarray(points)[:, None] - np.asarray(snapshot["image_points"])) * dimensions
    if np.min(np.linalg.norm(offsets, axis=2)) < 3:
        raise ValueError("Use puntos de comprobación distintos de las referencias del patrón")
    a, b = (project(snapshot, point) for point in points)
    observed = float(np.linalg.norm(a - b))
    error = abs(observed - distance)
    if error > tolerance:
        raise ValueError(f"La medida de comprobación difiere {error:.3f} m y supera la tolerancia declarada")
    return {**evidence, "control": {**{key: control[key] for key in inputs},
            "observed_m": observed, "absolute_error_m": error, "relative_error": error / distance}}


def calibration_snapshot(data):
    if not isinstance(data, dict) or data.get("status") not in {"valid", "invalid"}:
        raise ValueError("Estado de calibración inválido")
    for key in ("image_points", "ground_points_m"):
        points = data.get(key)
        if (not isinstance(points, list) or not 4 <= len(points) <= 16
                or any(not isinstance(p, list) or len(p) != 2
                       or any(type(v) not in (int, float) for v in p) for p in points)):
            raise ValueError("Referencias requieren pares numéricos, sin booleanos")
    image = np.asarray(data.get("image_points"), dtype=float)
    ground = np.asarray(data.get("ground_points_m"), dtype=float)
    if (image.ndim != 2 or image.shape[1:] != (2,) or not 4 <= len(image) <= 16
            or ground.shape != image.shape or not np.isfinite(image).all()
            or not np.isfinite(ground).all() or (image < 0).any() or (image > 1).any()
            or np.abs(ground).max() > 10000):
        raise ValueError("Se requieren 4–16 correspondencias finitas, imagen [0,1] y suelo en metros")
    for points in (image, ground):
        if len(np.unique(points, axis=0)) != len(points) or np.linalg.matrix_rank(points-points.mean(0)) < 2:
            raise ValueError("Referencias duplicadas o colineales")
    matrix, _ = cv2.findHomography(image, ground, method=0)
    if matrix is None or not np.isfinite(matrix).all() or np.linalg.cond(matrix) > 1e8:
        raise ValueError("Homografía singular o mal condicionada")
    matrix = matrix / matrix[2, 2] if abs(matrix[2, 2]) > 1e-12 else matrix / np.linalg.norm(matrix)
    denominators = image @ matrix[2,:2] + matrix[2,2]
    if np.min(denominators) <= 1e-8 <= np.max(denominators) or np.min(np.abs(denominators)) < 1e-8:
        raise ValueError("El horizonte cruza el área de referencias")
    projected = cv2.perspectiveTransform(image[None], matrix)[0]
    residual = float(np.linalg.norm(projected-ground, axis=1).max())
    if not np.isfinite(residual) or residual > .05:
        raise ValueError("Las referencias no ajustan un plano (error > 0,05 m)")
    if (data.get("units") != "m" or not isinstance(data.get("source_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", data["source_sha256"]) or data.get("zones_reviewed") is not True
            or type(data.get("version")) is not int or data["version"] < 1
            or not isinstance(data.get("calibrated_at"), str)):
        raise ValueError("Declare fuente, versión, fecha, metros y revisión explícita de zonas")
    try:
        date = datetime.fromisoformat(data["calibrated_at"].replace("Z", "+00:00"))
        if date.tzinfo is None: raise ValueError("Falta zona horaria")
    except ValueError as error:
        raise ValueError("Fecha de calibración inválida") from error
    result = {key: data[key] for key in ("status", "source_sha256", "version", "calibrated_at", "units", "zones_reviewed")}
    result.update(method=METHOD, image_points=image.tolist(), ground_points_m=ground.tolist(),
                  homography=matrix.tolist(), max_reference_error_m=residual,
                  validity_policy="STATIC_VIEW_HUMAN_CONFIRMED")
    if "framing_reference" in data:
        if data["framing_reference"] != REFERENCE:
            raise ValueError("Referencia de encuadre no soportada")
        result["framing_reference"] = REFERENCE
    if "pattern_evidence" in data:
        result["pattern_evidence"] = _confirmed_pattern(result, data["pattern_evidence"])
        result["validity_policy"] = "GROUND_PATTERN_CONTROL_HUMAN_CONFIRMED"
    result["sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return result


def project(snapshot, point):
    matrix = np.asarray(snapshot["homography"])
    value = matrix @ np.array([*point, 1.])
    if abs(value[2]) < 1e-8:
        raise ValueError("Punto sobre el horizonte del plano")
    result = value[:2] / value[2]
    if not np.isfinite(result).all():
        raise ValueError("Proyección no finita")
    return result


def _cross(start, end, point):
    return ((end[0] - start[0]) * (point[1] - start[1])
            - (end[1] - start[1]) * (point[0] - start[0]))


@lru_cache(maxsize=64)
def _reference_hull(references):
    """Return the counterclockwise convex hull without downcasting references."""
    def half(points):
        chain = []
        for point in points:
            while len(chain) >= 2 and _cross(chain[-2], chain[-1], point) <= 0:
                chain.pop()
            chain.append(point)
        return chain[:-1]

    ordered = sorted(references)
    hull = half(ordered) + half(reversed(ordered))
    return tuple(zip(hull, hull[1:] + hull[:1]))


def contacts_in_calibrated_area(snapshot, points):
    edges = _reference_hull(tuple(map(tuple, snapshot["image_points"])))
    # Allow roundoff in normalized coordinates without expanding the region
    # by an operational tolerance.
    return len(edges) >= 3 and all(
        _cross(start, end, point) >= -4 * float_info.epsilon * (
            abs(end[0] - start[0]) + abs(end[1] - start[1]))
        for point in points
        for start, end in edges
    )


def ground_measurement(snapshot, person, equipment, width, height):
    """Distancia entre segmentos inferiores proyectados dentro del área referenciada."""
    if snapshot["status"] != "valid":
        return None
    image = [[box.x_min/width, box.y_max/height] for box in (person, equipment)]
    image += [[box.x_max/width, box.y_max/height] for box in (person, equipment)]
    if not contacts_in_calibrated_area(snapshot, image):
        return None  # No extrapolar fuera de la región calibrada.
    a, c, b, d = [project(snapshot, p) for p in image]
    candidates = []
    def nearest(p, x, y):
        delta = y-x
        t = float(np.clip(np.dot(p-x, delta) / max(np.dot(delta, delta), 1e-20), 0, 1))
        return x+t*delta
    # Incluir la intersección evita sobreestimar segmentos que se cruzan.
    coefficients = np.column_stack((b-a, -(d-c)))
    if abs(np.linalg.det(coefficients)) > 1e-12:
        t, u = np.linalg.solve(coefficients, c-a)
        if 0 <= t <= 1 and 0 <= u <= 1:
            candidates.append((a+t*(b-a), a+t*(b-a)))
    candidates += [(p, nearest(p, c, d)) for p in (a,b)]
    candidates += [(nearest(p, a, b), p) for p in (c,d)]
    left, right = min(candidates, key=lambda pair: float(np.linalg.norm(pair[0]-pair[1])))
    inverse = np.linalg.inv(np.asarray(snapshot["homography"]))
    endpoints = []
    for p in (left,right):
        v = inverse @ np.array([*p,1])
        endpoints.append(np.clip(v[:2]/v[2], 0., 1.).tolist())
    return {"method": METHOD, "units": "m", "distance": float(np.linalg.norm(left-right)),
            "person_anchor": endpoints[0], "equipment_target": endpoints[1], "calibration": snapshot}
