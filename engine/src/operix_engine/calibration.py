"""Calibración explícita del plano del suelo, en metros aproximados."""
import hashlib
import json
import re
from datetime import datetime

import cv2
import numpy as np

METHOD = "ground_plane_contact_edges_v1"


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


def ground_measurement(snapshot, person, equipment, width, height):
    """Distancia entre segmentos inferiores proyectados dentro del área referenciada."""
    if snapshot["status"] != "valid":
        return None
    hull = cv2.convexHull(np.asarray(snapshot["image_points"], np.float32))
    image = [[box.x_min/width, box.y_max/height] for box in (person, equipment)]
    image += [[box.x_max/width, box.y_max/height] for box in (person, equipment)]
    if any(cv2.pointPolygonTest(hull, tuple(p), False) < 0 for p in image):
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
