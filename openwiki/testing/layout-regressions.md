---
type: Testing guide
title: Layout regression evidence
description: Offline checks for V3 mask decoding, Sol reconciliation, source geometry, fallback, and saved conversion identity.
tags: [testing, layout, contours, fallback]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:44:56.859Z
sources:
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-61bafe5b03c24d7418f8fca4
    resource: repo://tests/data/layout_v3_contours.json
  - id: openwiki-source-5012927e69660b3b63fa1941
    resource: repo://tests/test_layout_contours.py
  - id: openwiki-source-e21a991204779b8d3c0240c6
    resource: repo://tests/test_layout_readiness.py
  - id: openwiki-source-b1623b7b40e27202adf3b061
    resource: repo://tests/test_layout_runtime.py
generated: { by: "codex", at: "2026-09-27T09:44:56.859Z" }
---

# Layout regression evidence

New conversions use the pinned `PaddlePaddle/PP-DocLayoutV3_onnx` artifact for layout evidence. Sol still receives the whole rendered page and supplies text and HTML. The layout test suite checks the contracts between these stages with synthetic pages, injected engines, and recorded tensor fixtures. The default test setup replaces the layout engine and blocks real OpenAI calls. Run the focused checks from the repository root:

```powershell
uv run --no-sync python -m pytest -q tests/test_layout.py tests/test_layout_runtime.py tests/test_layout_prior.py tests/test_layout_readiness.py tests/test_layout_contours.py
```

## Decode and coordinate evidence

[`test_layout_contours.py`](../../tests/test_layout_contours.py) reads [`layout_v3_contours.json`](../../tests/data/layout_v3_contours.json), whose expected vertices were captured from the named PaddleX reference independently of DocLayout's decoder. It checks non-square images, disconnected mask regions, out-of-page vertices, original masks, raw boxes, class/order association, malformed tensors, and valid-box fallback when contour extraction fails. Round-trip tests cover normalized request coordinates and provider pages with nonzero origins. Rotated PDF tests render real local fixture pages before drawing overlays.

The fixture compares the implemented contour with the reference algorithm. It does not say the detected boundary matches the visible content of an arbitrary document. The retained mask is more complete evidence than the simplified largest-component contour.

## Assignment and output evidence

[`test_layout.py`](../../tests/test_layout.py), [`test_layout_prior.py`](../../tests/test_layout_prior.py), and the contour suite check whole-page guide payloads, compatible class families, concave overlap, one-to-one reservation, split/merge warnings, and preservation of every unmatched Sol block's HTML. Matched slots follow V3 order across intervening Sol-only blocks; tied raw keys are recorded without inventing model certainty. V3-only regions stay diagnostic.

Processor tests assemble lists, paragraphs, and tables, then check that source contours and original page IDs survive replacement and cross-page merges. Annotation checks draw visible source footprints, including clipped contour components, V3 rectangle fallback, and Sol-only rectangles. Header/footer visibility still applies. Final overlay counts describe drawn parts, so they need not equal initial matches or unique final source footprints. See [rendering and exports](../outputs/rendering-and-exports.md) for the output formats.

## Failure and saved-result evidence

[`test_layout_runtime.py`](../../tests/test_layout_runtime.py) exercises CUDA detection through fake sessions and profile records, then checks sticky CPU retry, explicit CUDA behavior, hash-verified cache use, and latched preparation failures. The successful CUDA session can execute some nodes on CPU. [`test_layout_readiness.py`](../../tests/test_layout_readiness.py) checks Sol fallback across library, CLI, HTTP, and GUI entrypoints. It also checks that a processor defect propagates instead of becoming a layout miss, and that saved fallback conversions and field-only retries avoid fresh conversion. [`test_layout_prior.py`](../../tests/test_layout_prior.py) checks the shared three-request page cap. Policy fingerprint tests require a new conversion identity when decode, guide, matching, order, geometry, reporting, execution, or fallback semantics change.

[`conftest.py`](../../tests/conftest.py) skips tests marked `integration` unless `--run-integration` is explicitly supplied; ordinary tests also reject unexpected Responses API calls. The focused suite therefore proves local contracts, not model accuracy, current endpoint access, or actual CUDA performance. The [dated layout evaluation](../../docs/layout-v3-plan.md#completion-verification-2026-09-27-local-unreleased) reports bounded native observations and gaps, including unavailable warped-page evidence. Match counts alone are not an accuracy measure.

## Related pages

- [Document conversion](../workflows/document-conversion.md)
- [Configuration and testing](../operations/configuration-and-testing.md)
- [Rendering and exports](../outputs/rendering-and-exports.md)
