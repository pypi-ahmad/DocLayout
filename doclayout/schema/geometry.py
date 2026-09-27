"""Contour records and affine coordinate conversion, independent of inference."""

import math
from dataclasses import dataclass
from typing import Literal

Contour = tuple[tuple[float, float], ...]
Frame = tuple[float, float, float, float]
GeometrySource = Literal["native_contour", "rectangle_fallback"]
GUIDE_FRAME: Frame = (0, 0, 1000, 1000)


def image_frame(size: tuple[int, int]) -> Frame:
    return (0, 0, size[0], size[1])


def convert_points(points, source: Frame, target: Frame) -> Contour:
    """Map pixels, guide, page or annotation coordinates, including origins."""
    if not all(math.isfinite(v) for v in (*source, *target)):
        raise ValueError("Coordinate frames must be finite")
    if (
        source[2] <= source[0]
        or source[3] <= source[1]
        or target[2] <= target[0]
        or target[3] <= target[1]
    ):
        raise ValueError("Coordinate frames must have positive area")
    return tuple(
        (
            target[0]
            + (x - source[0]) * (target[2] - target[0]) / (source[2] - source[0]),
            target[1]
            + (y - source[1]) * (target[3] - target[1]) / (source[3] - source[1]),
        )
        for x, y in points
    )


def convert_bbox(bbox, source: Frame, target: Frame) -> Frame:
    a, b = convert_points(((bbox[0], bbox[1]), (bbox[2], bbox[3])), source, target)
    return (*a, *b)


def rectangle_contour(bbox) -> Contour:
    x0, y0, x1, y1 = bbox
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def validate_contour(contour, bbox, size, geometry_source) -> Contour:
    """Reject unsupported geometry; never repair or simplify native contours."""
    from shapely.geometry import Polygon

    points = tuple(tuple(float(v) for v in point) for point in contour)
    if geometry_source not in ("native_contour", "rectangle_fallback"):
        raise ValueError("Missing or unsupported geometry provenance")
    if any(len(p) != 2 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError("Contour coordinates must be finite pairs")
    if len(set(points)) < 3:
        raise ValueError("Contour has fewer than three distinct points")
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError("Contour must be a simple polygon with positive area")
    epsilon = 1e-6
    x0, y0, x1, y1 = bbox
    if any(
        not (
            -epsilon <= x <= size[0] + epsilon
            and -epsilon <= y <= size[1] + epsilon
            and x0 - epsilon <= x <= x1 + epsilon
            and y0 - epsilon <= y <= y1 + epsilon
        )
        for x, y in points
    ):
        raise ValueError("Contour lies outside its page or bounding box")
    if geometry_source == "rectangle_fallback" and points != rectangle_contour(bbox):
        raise ValueError("Rectangle fallback does not match its bounding box")
    return tuple((point[0], point[1]) for point in points)


@dataclass(frozen=True, slots=True)
class LayoutGeometry:
    contour: Contour
    geometry_source: GeometrySource
    region_order: int
    coordinate_space: Literal["page"] = "page"
