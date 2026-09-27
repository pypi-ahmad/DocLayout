"""Real installed postprocessor tests with synthetic masks, without model weights."""

from types import SimpleNamespace

import numpy as np
import pytest

from doclayout.services import layout


@pytest.fixture
def native_decoder(monkeypatch):
    monkeypatch.setenv("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    monkeypatch.setenv(
        "PADDLE_PDX_CACHE_HOME",
        str(__import__("pathlib").Path(".cache/layout/paddlex").resolve()),
    )
    native = pytest.importorskip("paddlex.inference.models.layout_analysis.processors")
    original_helpers = (
        native._rect_from_box,
        native._normalize_layout_polygon,
        native.extract_polygon_points_by_masks,
        native.LayoutAnalysisProcess.apply,
    )
    post = native.LayoutAnalysisProcess(labels=["text"], scale_size=[800, 800])
    layout._observe_native_decoder(
        SimpleNamespace(paddlex_predictor=SimpleNamespace(post_op=post))
    )
    assert original_helpers == (
        native._rect_from_box,
        native._normalize_layout_polygon,
        native.extract_polygon_points_by_masks,
        native.LayoutAnalysisProcess.apply,
    )
    return native, post


def decode(post, mask, *, score=0.9):
    output = {"boxes": np.array([[0, score, 0, 0, 800, 800, 0]], dtype=float)}
    if mask is not None:
        output["masks"] = mask
    return post(
        [output],
        [{"ori_img_size": [800, 800]}],
        threshold=0.5,
        layout_shape_mode="poly",
        skip_order_labels=[],
        filter_overlap_boxes=False,
    )


@pytest.mark.parametrize("kind", ["empty", "rectangle", "concave"])
def test_official_decode_and_actual_fallback_provenance(native_decoder, kind):
    native, post = native_decoder
    original = native._rect_from_box
    masks = np.zeros((1, 200, 200), dtype=np.uint8)
    if kind != "empty":
        masks[:, 20:160, 20:70] = 1
        if kind == "concave":
            masks[:, 110:160, 20:160] = 1
    expected = decode(
        native.LayoutAnalysisProcess(labels=["text"], scale_size=[800, 800]),
        masks.copy(),
    )
    actual = decode(post, masks.copy())
    assert native._rect_from_box is original
    box = actual[0][0]
    assert box["geometry_source"] == (
        "rectangle_fallback" if kind == "empty" else "native_contour"
    )
    np.testing.assert_array_equal(
        box["polygon_points"], expected[0][0]["polygon_points"]
    )
    assert box["coordinate"] == expected[0][0]["coordinate"]
    assert box["order"] == 1
    if kind == "concave":
        assert len(box["polygon_points"]) > 4
    region = layout._regions([{"boxes": actual[0]}], (800, 800))[0]
    assert len(region.contour) == len(box["polygon_points"])


def test_missing_masks_is_not_an_empty_success(native_decoder):
    _, post = native_decoder
    with pytest.raises(layout.LayoutCapabilityError):
        decode(post, None, score=0)
    assert len(decode(post, np.zeros((1, 200, 200)), score=0)[0]) == 0


@pytest.mark.parametrize(
    "mask",
    [np.zeros((1, 200)), np.zeros((2, 200, 200)), np.full((1, 200, 200), np.nan)],
)
def test_malformed_masks_are_not_degenerate_fallback(native_decoder, mask):
    with pytest.raises(layout.LayoutGeometryError):
        decode(native_decoder[1], mask)


@pytest.mark.parametrize(
    "error", [layout.LayoutCapabilityError, layout.LayoutGeometryError]
)
def test_logical_failures_do_not_retry_on_cpu(error):
    from unittest.mock import Mock

    runtime = layout._Runtime(
        model=SimpleNamespace(predict=Mock(side_effect=error("invalid"))),
        provider=layout.CUDA_PROVIDER,
    )
    with pytest.raises(error):
        runtime.predict(np.zeros((8, 8, 3)), "auto")
    assert runtime.provider == layout.CUDA_PROVIDER
    runtime.model.predict.assert_called_once()
