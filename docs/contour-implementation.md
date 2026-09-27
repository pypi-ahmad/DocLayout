# PP-DocLayoutV3 contour implementation

Verified locally on 2026-09-27. This record supplements the existing repository
research report; it is not an accuracy evaluation.

## Artifact and runtime

- Repository: `PaddlePaddle/PP-DocLayoutV3_onnx`.
- Revision: `46bbdf188bb0a772c08aed74882ce7e51a8f1ea6`.
- Required files: `inference.onnx` and `inference.yml`; existing pinned sizes,
  SHA-256 verification, cache locking and initialization protections are retained.
- Installed path verified on native Windows with Python 3.13.15, PaddleOCR 3.7.0,
  PaddleX 3.7.2 and ONNX Runtime GPU 1.30.0 using its CPU provider.
- Shapely 2.1.2 is now an explicit layout-extra dependency for validation; the
  lock update introduces no resolved package-version changes.

## Decode and data contract

The existing service invokes official preprocessing/postprocessing with
`layout_shape_mode="poly"`, batch size one and `skip_order_labels=[]`. NMS and
overlap-filter settings are unchanged. There is no custom mask or order decoder.

An instance-local adapter executes copies of the installed native functions with
private bindings for their rectangle factory. It identifies an actual official
rectangle-fallback return by object identity. Native four-point contours remain
`native_contour`; point count alone never determines provenance. Installed package
files and shared module globals are not modified. The adapter fails closed on
unsupported PaddleX versions or postprocessor types.

Segmentation output is required even when no detections survive filtering.
Missing capability and malformed geometry have distinct errors and do not cause
an automatic GPU-to-CPU retry. Valid empty-mask fallback remains distinguishable
from malformed output. Successful empty detections preserve unmatched Sol content.

Each region retains original class ID/label, confidence, image-pixel bbox,
arbitrary-length contour, dense one-based order and geometry provenance.
Contours must be finite, simple, positive-area polygons inside their bbox and
page (with only a floating-point roundoff allowance). No repair, clipping or
application-level simplification is performed. Native contours may lie strictly
inside a detection bbox; their bounds need not equal the detector's rectangle.

Shared affine helpers preserve x/y scale and coordinate origins between image,
0–1000 guide, page and annotation frames. The existing four-corner `PolygonBox`
contract remains unchanged. Matched blocks carry a separate immutable
page-coordinate `layout_geometry`, linked by region order. Sol-only blocks have
no V3 geometry. V3-only evidence stays in metadata without invented text.

Guides include full contour coordinates and provenance. The existing 512-region
and 64-KiB UTF-8 limits cover the complete JSON payload; overflow raises rather
than dropping regions or simplifying contours. The extraction prompt fingerprint
was updated. Sol HTML ownership, model IDs and chat behavior are unchanged.

Source snapshots protect all bindings, including filtered and Sol-only blocks,
and independent snapshots protect V3-only evidence. JSON/OCR records preserve
`layout_geometry`; chunks collect member geometries by source ID without making
a synthetic group contour. Annotations draw accepted native contours and retain
rectangles for official fallbacks and unmatched Sol blocks. No raw masks enter
application JSON.

## Failure policy

Successful V3 execution is required by default. The operator-only setting
`DOCLAYOUT_LAYOUT_ALLOW_SOL_FALLBACK=true` explicitly permits Sol-only extraction
after runtime failure. There is no GUI toggle or HTTP override. Auto-device mode
retains sticky CPU fallback after a GPU runtime failure; explicit CUDA remains
strict. Guide overflow and downstream invariant violations still abort.

## Verification

- Full offline suite: **546 passed, 3 skipped**. The skipped integration tests
  were not run; no billable Sol or Luna calls were made.
- Following final invariant hardening: **144 focused tests passed**, including
  new unmatched-evidence protection cases.
- Core changed geometry/service/alignment/builder modules passed focused Ruff
  and `ty` checks; `uv lock --check --offline` and `git diff --check` passed.
- A broader renderer/UI type check reports 13 diagnostics outside changed lines;
  these pre-existing typing issues were not refactored as part of this change.
- Installed native decoder tests use synthetic masks, without model inference:
  empty masks produce identified rectangle fallbacks; nonempty rectangular and
  concave masks retain official contour output unchanged. Tests also cover
  missing/malformed masks and no CPU retry for logical decoder failures.
- Mocked pipeline regressions cover 97-point contour preservation, coordinate
  conversions, exports/group members, guide byte limits, protected geometry
  mutation, and default versus opted-in runtime-failure behavior.

Cached-model inference ran locally with socket connections blocked, without
downloads or Sol calls. Inputs were synthetic, not representative evaluation data:

| Input | Provider | Accepted regions | Contour points per region |
| --- | --- | ---: | --- |
| Existing synthetic page | CPU | 4 | 5, 4, 4, 7 |
| Same page rotated 5 degrees | CPU | 5 | 15, 10, 15, 9, 10 |
| Same page with sinusoidal vertical warp | CPU | 4 | 19, 7, 12, 14 |
| White 600 × 800 page | CPU | 0 | Successful empty result |

All accepted regions in these live probes had native contour provenance. These
checks establish execution and data preservation, not accuracy, category coverage
or threshold calibration. Fresh GPU execution and representative real-world
curved-page evaluation remain unverified. No commits or publication were made.
