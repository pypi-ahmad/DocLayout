# Copyright (c) 2024 PaddlePaddle Authors. All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (see LICENSE).
# Modified for DocLayout: isolated poly decoding, explicit fallbacks and frames.
"""PaddleX mask contours and page geometry, separate from four-corner PolygonBox.

The custom-vertex algorithm follows PaddleX ffb64904d23708863ff5b8da312a5cbd52a7f462,
layout_analysis/processors.py. Raw contours are evidence; clipping is a consumer
operation. No PaddleX NMS, class filtering, box merging or order renumbering runs.
"""

import numpy as np


def custom_vertices(polygon, max_allowed_dist):
    """Apply the reference's concavity and sharp-corner heuristics unchanged."""
    poly = np.array(polygon)
    n = len(poly)
    max_allowed_dist *= 0.3
    point_info = []
    for i in range(n):
        previous, current, following = poly[(i - 1) % n], poly[i], poly[(i + 1) % n]
        incoming, outgoing = current - previous, following - current
        convex = incoming[0] * outgoing[1] - incoming[1] * outgoing[0] < 0
        v1, v2 = previous - current, following - current
        angle = np.degrees(
            np.arccos(
                np.clip(
                    np.dot(v1 / np.linalg.norm(v1), v2 / np.linalg.norm(v2)), -1.0, 1.0
                )
            )
        )
        point_info.append({"is_convex": convex, "angle": angle, "v1": v1, "v2": v2})
    concave = [i for i, info in enumerate(point_info) if not info["is_convex"]]
    preserve = set()
    if concave:
        groups = []
        current_group = [concave[0]]
        for i in range(1, len(concave)):
            if concave[i] - concave[i - 1] == 1 or (
                concave[i - 1] == n - 1 and concave[i] == 0
            ):
                current_group.append(concave[i])
            else:
                if len(current_group) >= 2:
                    groups.extend(current_group)
                current_group = [concave[i]]
        if len(current_group) >= 2:
            groups.extend(current_group)
        if len(concave) >= 2 and concave[0] == 0 and concave[-1] == n - 1:
            if 0 in groups and n - 1 in groups:
                preserve.update(groups)
        else:
            preserve.update(groups)
    kept = [
        i
        for i, info in enumerate(point_info)
        if info["is_convex"] or (i in preserve and info["angle"] >= 120)
    ]
    final = []
    for idx, current in enumerate(kept):
        following = kept[(idx + 1) % len(kept)]
        final.append(current)
        distance = np.linalg.norm(poly[current] - poly[following])
        if distance > max_allowed_dist:
            intermediate = (
                list(range(current + 1, following))
                if following > current
                else list(range(current + 1, n)) + list(range(following))
            )
            if intermediate:
                needed = int(np.ceil(distance / max_allowed_dist)) - 1
                if len(intermediate) <= needed:
                    final.extend(intermediate)
                else:
                    step = len(intermediate) / needed
                    final.extend(intermediate[int(i * step)] for i in range(needed))
    result = []
    for i in sorted(set(final)):
        info, current = point_info[i], poly[i]
        if info["is_convex"] and abs(info["angle"] - 45) < 1:
            direction = info["v1"] / np.linalg.norm(info["v1"]) + info[
                "v2"
            ] / np.linalg.norm(info["v2"])
            direction /= np.linalg.norm(direction)
            distance = (np.linalg.norm(info["v1"]) + np.linalg.norm(info["v2"])) / 2
            result.append(current + direction * distance)
        else:
            result.append(current)
    return np.asarray(result)


def mask_contour(mask, raw_box, image_size, max_box_w):
    """Decode one page-grid mask; return reference pixels or a fallback reason.

    The reference rounds the box before cropping, clips only the grid slice,
    resizes to the *raw* box, then offsets by its raw origin. Its surprising
    max_box_w expression (x_max - y_min) is deliberately supplied unchanged.
    """
    import cv2

    width, height = image_size
    rounded = np.round(raw_box)
    if np.any(np.abs(rounded) > np.iinfo(np.int32).max):
        return None, "contour_box_out_of_range"
    x0, y0, x1, y1 = rounded.astype(np.int64).tolist()
    bw, bh = x1 - x0, y1 - y0
    if bw <= 0 or bh <= 0:
        return None, "contour_degenerate_box"
    # Bound allocation for pathological raw boxes, not detections or guide size.
    if bw * bh > 4 * width * height:
        return None, "contour_resize_exceeds_four_page_pixels"
    xs = np.clip([round(x0 * 200 / width), round(x1 * 200 / width)], 0, 200)
    ys = np.clip([round(y0 * 200 / height), round(y1 * 200 / height)], 0, 200)
    cropped = mask[ys[0] : ys[1], xs[0] : xs[1]]
    if not cropped.size:
        return None, "contour_empty_crop"
    if not np.any(cropped):
        return None, "contour_empty_mask"
    resized = cv2.resize(
        cropped.astype(np.uint8), (bw, bh), interpolation=cv2.INTER_NEAREST
    )
    contours, _ = cv2.findContours(resized, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, "contour_not_found"
    contour = max(contours, key=lambda candidate: float(cv2.contourArea(candidate)))
    points = np.atleast_2d(
        cv2.approxPolyDP(contour, 0.004 * cv2.arcLength(contour, True), True).squeeze()
    )
    if len(points) < 3:
        return None, "contour_too_few_vertices"
    points = custom_vertices(points, bw if bw > max_box_w * 0.6 else max_box_w)
    # The official poly normalizer falls back to a rectangle below four points.
    if len(points) < 4:
        return None, "contour_too_few_vertices"
    points = np.asarray(points + [x0, y0], dtype=np.float32)
    if not np.isfinite(points).all():
        return None, "contour_nonfinite"
    return points.tolist(), None


def mask_from_rle(counts, size=(200, 200)):
    """Decode zero-first row-major evidence without accepting malformed runs."""
    if (
        len(size) != 2
        or any(type(v) is not int or v <= 0 for v in size)
        or not counts
        or any(type(v) is not int or v < 0 for v in counts)
        or sum(counts) != size[0] * size[1]
    ):
        raise ValueError("Invalid mask RLE")
    return np.repeat(np.arange(len(counts)) % 2, counts).astype(np.uint8).reshape(size)


def transform_points(points, source_bounds, target_bounds):
    """Map top-left coordinates between frames, including nonzero origins."""
    sx0, sy0, sx1, sy1 = source_bounds
    tx0, ty0, tx1, ty1 = target_bounds
    if sx1 <= sx0 or sy1 <= sy0 or tx1 <= tx0 or ty1 <= ty0:
        raise ValueError("Coordinate frames must have positive area")
    return [
        [
            tx0 + (x - sx0) * (tx1 - tx0) / (sx1 - sx0),
            ty0 + (y - sy0) * (ty1 - ty0) / (sy1 - sy0),
        ]
        for x, y in points
    ]


def polygon_parts(geometry):
    """Retain every polygon component; omit closing duplicate vertices."""
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [[list(point) for point in geometry.exterior.coords[:-1]]]
    return [
        part for item in getattr(geometry, "geoms", ()) for part in polygon_parts(item)
    ]


def region_geometry(region, image_size):
    """Return page-clipped contour or V3 AABB, with explicit fallback provenance."""
    from shapely.errors import GEOSException
    from shapely.geometry import Polygon, box

    width, height = image_size
    reason = "contour_not_decoded"
    if region.contour_px is not None:
        points = (
            np.asarray(region.contour_px)
            if all(len(p) == 2 for p in region.contour_px)
            else np.array([])
        )
        if (
            points.ndim != 2
            or points.shape[1] != 2
            or len(points) < 3
            or not np.isfinite(points).all()
        ):
            reason = "contour_invalid_vertices"
        else:
            polygon = Polygon(points)
            if not polygon.is_valid or polygon.area <= 0:
                reason = "contour_invalid_polygon"
            else:
                try:
                    clipped = polygon.intersection(box(0, 0, width, height))
                except GEOSException:
                    return (
                        box(*region.bbox_px),
                        "v3_bbox",
                        "contour_intersection_failed",
                    )
                if clipped.area > 0:
                    return clipped, "v3_contour", None
                reason = "contour_outside_page"
    elif region.contour_status != "not_decoded":
        reason = next(
            (i for i in region.issues if i.startswith("contour_")), "contour_unusable"
        )
    return box(*region.bbox_px), "v3_bbox", reason
