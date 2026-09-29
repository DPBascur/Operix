# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pertenencia geométrica de cajas a zonas en el plano de imagen."""

from __future__ import annotations

import math
from dataclasses import dataclass

from operix_engine.detection import BoundingBox
from operix_engine.operational_config import Zone


_EPSILON = 1e-12  # Tolerancia numérica en coordenadas normalizadas.
_Vertex = tuple[float, float]


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    """Punto (x, y) en el plano de imagen normalizado, no en metros."""

    x: float
    y: float

    def __post_init__(self) -> None:
        if any(type(value) not in (int, float) for value in (self.x, self.y)):
            raise ValueError("Las coordenadas del punto deben ser numéricas")
        if not all(math.isfinite(value) and 0 <= value <= 1 for value in (self.x, self.y)):
            raise ValueError("Las coordenadas del punto deben ser finitas y estar en [0,1]")


def normalized_bottom_center(box: BoundingBox, width: int, height: int) -> NormalizedPoint:
    """Aproxima el apoyo de una caja xyxy y lo normaliza respecto del frame."""
    if type(width) is not int or width <= 0 or type(height) is not int or height <= 0:
        raise ValueError("width y height deben ser enteros positivos")
    if not isinstance(box, BoundingBox):
        raise TypeError("box debe ser una BoundingBox")
    if box.x_max > width or box.y_max > height:
        raise ValueError("La caja excede las dimensiones del frame")
    return NormalizedPoint((box.x_min + box.x_max) / (2 * width), box.y_max / height)


def _cross(a: _Vertex, b: _Vertex, c: _Vertex) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(point: _Vertex, a: _Vertex, b: _Vertex) -> bool:
    return (
        abs(_cross(a, b, point)) <= _EPSILON
        and min(a[0], b[0]) - _EPSILON <= point[0] <= max(a[0], b[0]) + _EPSILON
        and min(a[1], b[1]) - _EPSILON <= point[1] <= max(a[1], b[1]) + _EPSILON
    )


def _segments_intersect(a: _Vertex, b: _Vertex, c: _Vertex, d: _Vertex) -> bool:
    if any(
        _on_segment(point, start, end)
        for point, start, end in ((a, c, d), (b, c, d), (c, a, b), (d, a, b))
    ):
        return True
    return (
        (_cross(a, b, c) > 0) != (_cross(a, b, d) > 0)
        and (_cross(c, d, a) > 0) != (_cross(c, d, b) > 0)
    )


def _validate_polygon(vertices: tuple[_Vertex, ...]) -> None:
    count = len(vertices)
    if count < 3:
        raise ValueError("La zona requiere al menos tres vértices")
    for index, vertex in enumerate(vertices):
        following = vertices[(index + 1) % count]
        if math.dist(vertex, following) <= _EPSILON:
            raise ValueError("El polígono contiene un lado de longitud cero")
    for first in range(count):
        for second in range(first + 1, count):
            if second == first + 1 or (first == 0 and second == count - 1):
                continue  # Lados vecinos comparten necesariamente un vértice.
            if _segments_intersect(
                vertices[first], vertices[(first + 1) % count],
                vertices[second], vertices[(second + 1) % count],
            ):
                raise ValueError("El polígono es autointersectado")
    twice_area = math.fsum(
        vertex[0] * vertices[(index + 1) % count][1]
        - vertices[(index + 1) % count][0] * vertex[1]
        for index, vertex in enumerate(vertices)
    )
    if abs(twice_area) <= _EPSILON:
        raise ValueError("El polígono tiene área nula")
    for index, vertex in enumerate(vertices):
        preceding = vertices[index - 1]
        following = vertices[(index + 1) % count]
        if abs(_cross(preceding, vertex, following)) <= _EPSILON:
            backwards = (
                (preceding[0] - vertex[0]) * (following[0] - vertex[0])
                + (preceding[1] - vertex[1]) * (following[1] - vertex[1])
            )
            if backwards > _EPSILON:
                raise ValueError("El polígono contiene lados adyacentes superpuestos")


def point_in_zone(point: NormalizedPoint, zone: Zone) -> bool:
    """Cruce de rayos; borde y vértices cuentan como dentro."""
    if not isinstance(point, NormalizedPoint) or not isinstance(zone, Zone):
        raise TypeError("Se requieren NormalizedPoint y Zone")
    vertices = zone.polygon
    _validate_polygon(vertices)
    candidate = (point.x, point.y)
    inside = False
    for index, start in enumerate(vertices):
        end = vertices[(index + 1) % len(vertices)]
        if _on_segment(candidate, start, end):
            return True
        if (start[1] > point.y) != (end[1] > point.y):
            intersection_x = start[0] + (point.y - start[1]) * (
                end[0] - start[0]
            ) / (end[1] - start[1])
            if point.x < intersection_x:
                inside = not inside
    return inside


def bbox_in_zone(box: BoundingBox, zone: Zone, width: int, height: int) -> bool:
    """Decide pertenencia por centro inferior, no por solapamiento de áreas."""
    return point_in_zone(normalized_bottom_center(box, width, height), zone)
