"""On-demand, CPU-only proposals from surveyed square fiducials on the ground.

Layout corners are in decoded tag order, starting at the printed tag's top
left (before rotation), on the outer black border. All tags share one surveyed
coordinate system, in metres. Image points use the canonical x/width, y/height
convention. The caller must verify the physical placement and confirm the fit.
"""

from collections import Counter, defaultdict
from hashlib import blake2b
from itertools import combinations, islice

import cv2
import numpy as np

from .calibration import calibration_snapshot, contacts_in_calibrated_area, project


DICTIONARIES = frozenset({
    *(f"DICT_{size}X{size}_{count}" for size in (4, 5, 6, 7) for count in (50, 100, 250, 1000)),
    "DICT_APRILTAG_16h5", "DICT_APRILTAG_25h9", "DICT_APRILTAG_36h10", "DICT_APRILTAG_36h11",
})
MAX_FRAMES = 8
MAX_PIXELS = 3840 * 2160
MAX_MARKERS = 32
MAX_ERROR_PX = 3.0
MAX_MARKER_SPAN_PX = 4.0
MAX_ERROR_M = 0.05  # Canonical residual ceiling, also applied to unselected inliers.
MIN_DISTRIBUTED_MARKERS = 3


def _detector(dictionary):
    if not isinstance(dictionary, str) or dictionary not in DICTIONARIES:
        raise ValueError("Diccionario de marcadores no soportado")
    aruco = getattr(cv2, "aruco", None)
    if not hasattr(aruco, "ArucoDetector") or not hasattr(aruco, dictionary):
        raise ValueError("Esta instalación de OpenCV no admite el diccionario solicitado")
    codes = aruco.getPredefinedDictionary(getattr(aruco, dictionary))
    parameters = aruco.DetectorParameters()
    parameters.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
    return aruco.ArucoDetector(codes, parameters), len(codes.bytesList), codes.markerSize


def _dimensions(frame):
    if (not isinstance(frame, np.ndarray) or frame.dtype != np.uint8
            or not (frame.ndim == 2 or (frame.ndim == 3 and frame.shape[2] == 3))):
        raise ValueError("Se requieren fotogramas uint8 en gris o BGR")
    height, width = frame.shape[:2]
    if min(width, height) < 32 or width * height > MAX_PIXELS:
        raise ValueError("Dimensiones del fotograma fuera del rango admitido")
    return width, height


def _detect(frame, dimensions, detector, marker_bits):
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is None:
        return {}, set()
    ids = ids.ravel().tolist()
    duplicates = {marker_id for marker_id, count in Counter(ids).items() if count > 1}
    result = {}
    for marker_id, quad in zip(ids, corners):
        quad = quad.reshape(4, 2).astype(float)
        edge_lengths = np.linalg.norm(np.roll(quad, -1, axis=0) - quad, axis=1)
        # Keep enough pixels across the shortest dimension for decoding under foreshortening.
        if (marker_id not in duplicates and edge_lengths.min() >= 2 * (marker_bits + 2)
                and cv2.contourArea(quad.astype(np.float32)) >= (2 * (marker_bits + 2)) ** 2
                and (quad >= 2).all() and (quad <= np.asarray(dimensions) - 3).all()):
            result[marker_id] = quad
    return result, duplicates


def detect_marker_corners(frame, dictionary):
    """Return {int ID: four normalized [x, y] lists} for unambiguous complete tags."""
    dimensions = _dimensions(frame)
    detector, _, bits = _detector(dictionary)
    markers, _ = _detect(frame, dimensions, detector, bits)
    return {marker_id: (quad / dimensions).tolist() for marker_id, quad in sorted(markers.items())}


def _numbers(points, count):
    if (not isinstance(points, (list, tuple)) or len(points) != count
            or any(not isinstance(point, (list, tuple)) or len(point) != 2
                   or any(type(value) not in (int, float) or abs(value) > 10000 for value in point)
                   for point in points)):
        raise ValueError(f"Se requieren {count} pares numéricos")
    points = np.asarray(points, dtype=float)
    if not np.isfinite(points).all():
        raise ValueError("Las coordenadas deben ser finitas")
    return points


def _layout(pattern):
    if not isinstance(pattern, dict) or pattern.get("ground_plane_confirmed") is not True:
        raise ValueError("Confirme que todos los marcadores medidos están sobre el suelo")
    dictionary = pattern.get("dictionary")
    detector, capacity, bits = _detector(dictionary)
    markers = pattern.get("markers")
    if not isinstance(markers, list) or not 1 <= len(markers) <= MAX_MARKERS:
        raise ValueError(f"Declare entre 1 y {MAX_MARKERS} marcadores medidos")
    ground, winding = {}, set()
    for marker in markers:
        marker_id = marker.get("id") if isinstance(marker, dict) else None
        if type(marker_id) is not int or not 0 <= marker_id < capacity or marker_id in ground:
            raise ValueError("ID de marcador duplicado o fuera del diccionario")
        quad = _numbers(marker.get("corners_m"), 4)
        edges = np.roll(quad, -1, axis=0) - quad
        lengths = np.linalg.norm(edges, axis=1)
        adjacent = np.sum(edges * np.roll(edges, -1, axis=0), axis=1)
        contour = (quad - quad[0]).astype(np.float32)
        if (lengths.min() < .01 or lengths.max() > 1.05 * lengths.min()
                or (np.abs(adjacent) > .05 * lengths * np.roll(lengths, -1)).any()
                or not cv2.isContourConvex(contour)):
            raise ValueError("Las esquinas medidas deben formar un cuadrado en orden del código")
        winding.add(np.sign(cv2.contourArea(contour, oriented=True)))
        for previous in ground.values():
            overlap, _ = cv2.intersectConvexConvex(contour, (previous - quad[0]).astype(np.float32))
            if overlap > 1e-8 or np.linalg.norm(quad[:, None] - previous, axis=2).min() < 1e-7:
                raise ValueError("Los marcadores medidos requieren esquinas distintas y áreas sin solape")
        ground[marker_id] = quad
    if len(winding) != 1:
        raise ValueError("Todos los marcadores deben usar el mismo sentido de coordenadas")
    return dictionary, detector, bits, ground


def _controls(controls):
    if not isinstance(controls, (list, tuple)) or len(controls) > 8:
        raise ValueError("Declare hasta 8 distancias de control")
    for control in controls:
        if not isinstance(control, dict):
            raise ValueError("Distancia de control inválida")
        points = _numbers(control.get("image_points"), 2)
        distance = control.get("distance_m")
        if ((points < 0).any() or (points > 1).any() or np.linalg.norm(points[0] - points[1]) < 1e-6
                or type(distance) not in (int, float) or not 0 < distance <= 30000):
            raise ValueError("El control requiere puntos normalizados distintos y una distancia medida positiva")
        tolerance = control.get("tolerance_m", max(.02, .05 * distance))
        if "tolerance_m" in control and (type(tolerance) not in (int, float) or not 0 < tolerance < distance):
            raise ValueError("La tolerancia debe ser positiva y menor que la distancia de control")
        yield points, float(distance), float(tolerance)


def evaluate_control_distances(snapshot, control_distances, *, dimensions=None):
    """Check separately measured ground distances inside the canonical footprint.

    Default tolerance is the larger of 2 cm and 5% of the supplied measurement.
    Both endpoints must be distinct from the fitted references.
    """
    results = []
    evidence = snapshot.get("pattern_evidence", {})
    width, height = dimensions if dimensions is not None else (evidence.get("width"), evidence.get("height"))
    scale, separation = ([width, height], 3.) if width and height else (1., .002)
    for points, distance, tolerance in _controls(control_distances):
        result = dict(image_points=points.tolist(), distance_m=distance,
                      estimated_distance_m=None, absolute_error_m=None, relative_error=None,
                      tolerance_m=tolerance)
        if not contacts_in_calibrated_area(snapshot, points):
            result["status"] = "outside_footprint"
        elif np.linalg.norm((points[:, None] - snapshot["image_points"]) * scale, axis=2).min() < separation:
            result["status"] = "uses_fit_references"
        else:
            estimated = float(np.linalg.norm(project(snapshot, points[0]) - project(snapshot, points[1])))
            error = abs(estimated - distance)
            relative_error = error / distance
            result.update(estimated_distance_m=estimated, absolute_error_m=error,
                          relative_error=relative_error if np.isfinite(relative_error) else None,
                          status="pass" if error <= result["tolerance_m"] else "fail")
        results.append(result)
    return results


def _hull(points):
    return cv2.convexHull(np.asarray(points, dtype=np.float32)).reshape(-1, 2)


def _area(points):
    return cv2.contourArea(_hull(points))


def _transform(points, matrix):
    return cv2.perspectiveTransform(points.reshape(1, -1, 2), matrix)[0].reshape(points.shape)


def _canonical(pixels, ground, dimensions):
    # Reuse the canonical fit and its guards. These internal placeholders are
    # used only to run the validator and never leave the proposal module.
    return calibration_snapshot({
        "image_points": (pixels / dimensions).tolist(), "ground_points_m": ground.tolist(),
        "status": "valid", "units": "m", "source_sha256": "0" * 64,
        "version": 1, "calibrated_at": "1970-01-01T00:00:00Z", "zones_reviewed": True,
    })


def _inlier_ids(image, ground):
    ids = sorted(image)
    pixel_points = np.concatenate([image[marker] for marker in ids])
    ground_points = np.concatenate([ground[marker] for marker in ids])
    _, mask = cv2.findHomography(ground_points, pixel_points, cv2.RANSAC, MAX_ERROR_PX)
    if mask is None:
        return []
    return [marker for marker, inliers in zip(ids, mask.reshape(-1, 4)) if inliers.all()]


def _select_ids(ids, image):
    if len(ids) <= 4:
        return ids
    selected = list(max(combinations(ids, 2), key=lambda pair: _area(np.concatenate([image[i] for i in pair]))))
    while len(selected) < 4:
        additional = max((i for i in ids if i not in selected),
                         key=lambda i: _area(np.concatenate([image[j] for j in [*selected, i]])))
        selected.append(additional)
    return sorted(selected)


def _sensitivity(pixels, ground, dimensions, snapshot):
    """Largest ground shift at footprint vertices across deterministic 1 px perturbations."""
    points = pixels / dimensions
    footprint = points[cv2.convexHull(points.astype(np.float32), returnPoints=False).ravel()]
    baseline = _transform(footprint, np.asarray(snapshot["homography"]))
    max_shift = 0.
    for corner in range(len(pixels)):
        for offset in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            changed = points.copy()
            changed[corner] += np.asarray(offset) / dimensions
            matrix, _ = cv2.findHomography(changed, ground, 0)
            if matrix is None or not np.isfinite(matrix).all():
                return None
            denominators = footprint @ matrix[2, :2] + matrix[2, 2]
            if (np.abs(denominators) < 1e-8).any() or denominators.min() * denominators.max() <= 0:
                return None
            max_shift = max(max_shift, float(np.linalg.norm(_transform(footprint, matrix) - baseline, axis=1).max()))
    return max_shift if np.isfinite(max_shift) else None


def _grid(ground_hull, inverse):
    lower, upper = ground_hull.min(axis=0), ground_hull.max(axis=0)
    extent = float(max(upper - lower))
    step = max(.1, np.ceil(extent * 10 / 12) / 10) if extent < 1. else max(1., float(np.ceil(extent / 12)))
    lines = []
    for axis in (0, 1):
        other = 1 - axis
        for value in np.arange(np.ceil(lower[axis] / step) * step, upper[axis], step):
            hits = []
            for start, end in zip(ground_hull, np.roll(ground_hull, -1, axis=0)):
                if min(start[axis], end[axis]) <= value < max(start[axis], end[axis]):
                    fraction = (value - start[axis]) / (end[axis] - start[axis])
                    hits.append(start[other] + fraction * (end[other] - start[other]))
            if hits and min(hits) < max(hits):
                line = np.full((2, 2), value)
                line[:, other] = [min(hits), max(hits)]
                lines.append(_transform(line, inverse).tolist())
    return lines, step


def empty_proposal(*reasons):
    return dict(schema_version=1, status="invalid", reasons=list(reasons), dictionary=None,
                width=None, height=None, preview_frame_index=None, marker_corners={}, reference_marker_corners={},
                image_points=[], ground_points_m=[], homography=None, footprint=[], coverage=0.0,
                quality={}, grid=[], control_distances=[])


def propose_calibration(frames, pattern, control_distances=()):
    """Assess up to eight sampled frames of a single unmodified camera view.

    Missing tags and partial occlusions can be tolerated if enough complete,
    distributed tags agree across distinct frames. Invalid requests raise
    ValueError. Geometry is returned only when the canonical fit succeeds.
    """
    dictionary, detector, bits, ground = _layout(pattern)
    list(_controls(control_distances))  # Validate before processing images.
    result = empty_proposal()
    result["dictionary"] = dictionary
    observations = defaultdict(list)
    frame_markers, unique_frames, duplicate_ids = [], set(), set()
    dimensions = None
    new_indices = []
    for index, frame in enumerate(islice(frames, MAX_FRAMES + 1)):
        if index == MAX_FRAMES:
            raise ValueError(f"Se admiten hasta {MAX_FRAMES} fotogramas")
        size = _dimensions(frame)
        if dimensions is not None and dimensions != size:
            raise ValueError("Los fotogramas deben tener el mismo encuadre y dimensiones")
        dimensions = size
        digest = blake2b(np.ascontiguousarray(frame), digest_size=16).digest()
        if digest in unique_frames:
            frame_markers.append({})
            continue
        unique_frames.add(digest)
        new_indices.append(index)
        detected, duplicates = _detect(frame, size, detector, bits)
        duplicate_ids.update(duplicates & ground.keys())
        known = {marker: detected[marker] for marker in sorted(detected.keys() & ground.keys())}
        frame_markers.append(known)
        for marker, corners in known.items():
            observations[marker].append(corners)
    if dimensions is None:
        result["reasons"] = ["no_frames"]
        return result

    median_corners = {marker: np.median(samples, axis=0) for marker, samples in observations.items()}
    jitter = {marker: float(np.linalg.norm(np.asarray(samples) - median_corners[marker], axis=2).max())
              for marker, samples in observations.items()}
    span = {marker: max((float(np.linalg.norm(a - b, axis=1).max()) for a, b in combinations(samples, 2)), default=0.)
            for marker, samples in observations.items()}
    stable = {marker: corners for marker, corners in median_corners.items()
              if jitter[marker] <= MAX_ERROR_PX and span[marker] <= MAX_MARKER_SPAN_PX}
    repeated = {marker: corners for marker, corners in stable.items() if len(observations[marker]) >= 2}
    fit_input = repeated if len(repeated) >= MIN_DISTRIBUTED_MARKERS else stable
    ids = _inlier_ids(fit_input, ground) if len(fit_input) >= 2 else []
    selected = _select_ids(ids, stable)
    selected_set = set(selected)

    def preview_rank(index):
        visible = sorted(frame_markers[index].keys() & selected_set)
        deviation = sum(np.linalg.norm(frame_markers[index][marker] - stable[marker]) for marker in visible)
        return len(visible), -deviation, len(frame_markers[index])

    preview_index = max(new_indices, key=preview_rank)
    quality = dict(frames_sampled=len(frame_markers), distinct_frames=len(unique_frames),
                   frames_with_markers=sum(bool(markers) for markers in frame_markers),
                   configured_marker_count=len(ground),
                   observations_by_marker={str(marker): len(samples) for marker, samples in sorted(observations.items())},
                   max_marker_deviation_px=max(jitter.values(), default=None), max_marker_span_px=max(span.values(), default=None),
                   duplicate_marker_ids=sorted(duplicate_ids), unstable_marker_ids=sorted(median_corners.keys() - stable.keys()),
                   inlier_marker_ids=ids, rejected_marker_ids=sorted(fit_input.keys() - set(ids)),
                   control_status="not_provided" if not control_distances else "not_evaluated")
    result.update(width=dimensions[0], height=dimensions[1], preview_frame_index=preview_index,
                  marker_corners={str(marker): (corners / dimensions).tolist()
                                  for marker, corners in frame_markers[preview_index].items()}, quality=quality)
    if len(ids) < 2:
        result["reasons"] = ["insufficient_consistent_markers" if observations else "no_known_markers"]
        return result

    pixels = np.concatenate([stable[marker] for marker in selected])
    ground_points = np.concatenate([ground[marker] for marker in selected])
    try:
        snapshot = _canonical(pixels, ground_points, dimensions)
    except ValueError:
        result["reasons"] = ["canonical_fit_rejected"]
        return result
    matrix = np.asarray(snapshot["homography"])
    inverse = np.linalg.inv(matrix)
    fitted_pixels = {marker: _transform(ground[marker], inverse) * dimensions for marker in ids}
    fit_orientation = [cv2.contourArea((quad - quad[0]).astype(np.float32), oriented=True)
                       for quad in fitted_pixels.values()]
    if min(fit_orientation) <= 0:
        result["reasons"] = ["inconsistent_marker_orientation"]
        return result

    reasons = []
    frame_errors = []
    good_frames = 0
    for markers in frame_markers:
        errors = {marker: np.linalg.norm(markers[marker] - fitted_pixels[marker], axis=1)
                  for marker in ids if marker in markers}
        max_error = max((float(error.max()) for error in errors.values()), default=None)
        frame_errors.append(max_error)
        good_frames += sum(error.max() <= MAX_ERROR_PX for error in errors.values()) >= MIN_DISTRIBUTED_MARKERS
    max_pixel_error = max(error for error in frame_errors if error is not None)
    metric_errors = np.concatenate([
        np.linalg.norm(_transform(np.asarray(observations[marker]) / dimensions, matrix) - ground[marker], axis=2).ravel()
        for marker in ids
    ])
    max_metric_error = float(metric_errors.max())
    footprint_indices = cv2.convexHull((pixels / dimensions).astype(np.float32), returnPoints=False).ravel()
    footprint = (pixels / dimensions)[footprint_indices]
    coverage = float(cv2.contourArea(footprint.astype(np.float32)))
    ground_hull = _transform(footprint, matrix)
    image_centres = np.asarray([stable[marker].mean(axis=0) / dimensions for marker in ids])
    ground_centres = np.asarray([ground[marker].mean(axis=0) for marker in ids])
    centre_area = _area(image_centres)
    tag_area = max(_area(ground[marker] - ground[marker][0]) for marker in ids)
    ground_centre_area = _area(ground_centres - ground_centres[0])
    sensitivity = _sensitivity(pixels, ground_points, dimensions, snapshot)
    if (len(ids) < MIN_DISTRIBUTED_MARKERS or centre_area < .025 or coverage < .05
            or np.ptp(image_centres, axis=0).min() < .15 or ground_centre_area < 2 * tag_area):
        reasons.append("insufficient_distribution")
    if good_frames < 2 or good_frames * 2 < len(unique_frames):
        reasons.append("insufficient_temporal_support")
    if duplicate_ids:
        reasons.append("ambiguous_marker_ids")
    if quality["unstable_marker_ids"]:
        reasons.append("unstable_markers")
    if quality["rejected_marker_ids"] or any(
            np.linalg.norm(_transform(ground[marker], inverse) * dimensions - corners, axis=1).max() > MAX_ERROR_PX
            for marker, corners in stable.items() if marker not in ids):
        reasons.append("marker_layout_disagreement")
    if max_pixel_error > MAX_ERROR_PX or max_metric_error > MAX_ERROR_M:
        reasons.append("high_reprojection_error")
    if sensitivity is None or sensitivity > .10:
        reasons.append("sensitive_fit")

    controls = evaluate_control_distances(snapshot, control_distances, dimensions=dimensions)
    if controls:
        quality["control_status"] = "pass" if all(control["status"] == "pass" for control in controls) else "failed"
        if quality["control_status"] == "failed":
            reasons.append("control_distance_failed")
    grid, grid_step = _grid(ground_hull, inverse)
    quality.update(used_marker_ids=selected, supporting_frames=int(good_frames),
                   marker_centres_image_coverage=centre_area, footprint_area_m2=_area(ground_hull - ground_hull[0]),
                   frame_max_reprojection_error_px=frame_errors, max_reprojection_error_px=max_pixel_error,
                   rms_ground_error_m=float(np.sqrt(np.mean(metric_errors ** 2))), max_ground_error_m=max_metric_error,
                   max_reference_error_m=snapshot["max_reference_error_m"],
                   homography_condition=float(np.linalg.cond(matrix)), one_pixel_sensitivity_m=sensitivity,
                   grid_step_m=grid_step)
    result.update(status="requires_review" if reasons else "candidate", reasons=reasons,
                  image_points=snapshot["image_points"], ground_points_m=snapshot["ground_points_m"],
                  reference_marker_corners={str(marker): (stable[marker] / dimensions).tolist()
                                            for marker in selected if len(selected) >= MIN_DISTRIBUTED_MARKERS},
                  homography=snapshot["homography"], footprint=footprint.tolist(), coverage=coverage,
                  grid=grid, control_distances=controls)
    return result
