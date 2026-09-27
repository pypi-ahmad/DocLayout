import math

import pytest

from doclayout.schema.geometry import (
    GUIDE_FRAME,
    convert_bbox,
    convert_points,
    image_frame,
    rectangle_contour,
    validate_contour,
)


def test_many_point_roundtrips_non_square_frames_with_origins():
    points = tuple(
        (
            300 + 100 * math.cos(i * math.tau / 127),
            600 + 250 * math.sin(i * math.tau / 127),
        )
        for i in range(127)
    )
    pixels, page, annotation = (
        image_frame((600, 1200)),
        (25, 50, 325, 450),
        image_frame((900, 1600)),
    )
    for target in (GUIDE_FRAME, page, annotation):
        restored = convert_points(
            convert_points(points, pixels, target), target, pixels
        )
        assert len(restored) == 127
        for actual, expected in zip(restored, points, strict=True):
            assert actual == pytest.approx(expected)
    bbox = (200, 350, 400, 850)
    assert convert_bbox(
        convert_bbox(bbox, pixels, page), page, pixels
    ) == pytest.approx(bbox)


@pytest.mark.parametrize(
    "points",
    [
        ((0, 0), (1, 1)),
        ((0, 0), (1, 1), (2, 2)),
        ((0, 0), (4, 4), (0, 4), (4, 0)),
        ((0, 0), (4, 0), (float("nan"), 4)),
        ((0, 0), (11, 0), (0, 4)),
    ],
)
def test_malformed_geometry_is_rejected_without_repair(points):
    with pytest.raises(ValueError):
        validate_contour(points, (0, 0, 10, 10), (10, 10), "native_contour")


def test_fallback_must_be_explicit_and_exact():
    box = (1, 2, 8, 9)
    points = rectangle_contour(box)
    assert validate_contour(points, box, (10, 10), "rectangle_fallback") == points
    assert validate_contour(points, box, (10, 10), "native_contour") == points
    with pytest.raises(ValueError):
        validate_contour(points[:-1], box, (10, 10), "rectangle_fallback")
