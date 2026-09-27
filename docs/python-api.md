# Python API reference for contributors

[Back to README](../README.md) · [Usage example](usage.md#python-library) ·
[Architecture](architecture.md) · [Developer guide](development.md)

Use this page to find the application entry points and internal contracts that
contributors commonly extend. Internal symbols may change; check the linked
source and tests before editing them. The
[docstring audit](python-documentation-audit.md) records package-wide gaps.

## Conversion lifecycle

| Entry point | Input and result | Ownership and effects |
| --- | --- | --- |
| [`create_model_dict()`](../doclayout/models.py) | No arguments; returns the conversion artifact dictionary | Creates an owned Sol client and borrows a process-cached, lazy V3 engine. It does not prepare or download the model. |
| [`PdfConverter`](../doclayout/converters/pdf.py) | Artifacts plus optional processor paths, renderer path, and config; calling it with a PDF path or `BytesIO` returns the selected renderer's output | Validates configuration, renders provider pages, runs extraction and processors, then renders the result. Whole-page Sol requests may incur cost. |
| [`shutdown_models()`](../doclayout/models.py) | Artifact dictionary; returns `None` | Closes the owned Sol client. The shared layout engine is not closed here. |
| [`save_output()`](../doclayout/output.py) | Rendered output, directory, basename | Writes selected local output artifacts. Use an output directory, not a source directory. |

The [Python usage example](usage.md#python-library) shows the lifecycle, including
`try/finally`. The default `PdfConverter` renderer produces a
`MarkdownOutput` with `markdown`, `images`, and `metadata`; choosing a different
renderer changes that return type. Use `tests/test_entrypoints.py` and the
renderer tests to check entry-point changes without a live model request.

## Layout evidence and geometry

| Contract | Location | Interpretation |
| --- | --- | --- |
| `LayoutEngine.analyze(page_image)` | [`layout.py`](../doclayout/layout.py) | Returns `LayoutAnalysis` or raises `LayoutModelUnavailable` when called directly. Conversion catches layout preparation/inference failure and continues with Sol geometry. |
| `LayoutRegion`, `LayoutAnalysis`, `BlockLayout`, `SourceRegion` | [`schema/layout.py`](../doclayout/schema/layout.py) | Retained detection masks and contours, page runtime, accepted block geometry, and processor lineage are distinct records. |
| `transform_points()`, `region_geometry()` | [`layout_geometry.py`](../doclayout/layout_geometry.py) | Transform pixel coordinates between explicit bounds; use contour overlap where valid, with recorded rectangle fallback. |
| `reconcile()` | [`layout.py`](../doclayout/layout.py) | One-to-one association of eligible detections with Sol blocks. Keeps Sol content/type and preserves unmatched Sol blocks. |
| `layout_metadata()`, `layout_summary()` | [`layout.py`](../doclayout/layout.py) | Final visible-source metadata and a diagnostic summary; initial reconciliation counts and final processor output are different stages. |

Rendered-image pixels, normalized 0–1000 Sol coordinates, and provider page
coordinates are different frames. Preserve nonzero provider origins and scale
each axis independently. A `PolygonBox` remains four-corner; a V3 contour is
stored separately. Raw masks stay local and are not sent in the Sol guide.
`order_key` is raw model output; `observed_rank` is a derived stable sort.
See [the layout contract](layout-v3-plan.md) and
`tests/test_layout_contours.py`, `tests/test_layout_prior.py`, and
`tests/test_layout_readiness.py` before changing these paths.

## Output renderers

| Renderer | Return fields | Notes |
| --- | --- | --- |
| [`MarkdownRenderer`](../doclayout/renderers/markdown.py) | `markdown`, `images`, `metadata` | Converts the rendered HTML to Markdown; chosen by default. |
| [`HTMLRenderer`](../doclayout/renderers/html.py) | HTML output, images, metadata | Resolves child content and image references. |
| [`JSONRenderer`](../doclayout/renderers/json.py) | `children`, `block_type`, `metadata` | Keeps the processed block tree and its final geometry. |
| [`ChunkRenderer`](../doclayout/renderers/chunk.py) | `blocks`, `page_info`, `metadata` | Flattens top-level page children while retaining block HTML and page bounds. |

`BaseRenderer` in [`renderers/__init__.py`](../doclayout/renderers/__init__.py)
owns shared metadata and page-header/footer visibility settings. JSON/chunk
`polygon` fields describe the final rendered block, which may be a processor
envelope; inspect layout source footprints in metadata for V3 contour lineage.
The serialized polygon may differ from the original V3 contour.

## Saved field workflow

| Entry point | Input and result | Boundary |
| --- | --- | --- |
| [`load_definition()`](../doclayout/fields.py) | Field-definition directory and optional enablement; returns a validated `Definition` | Loads/snapshots Markdown instructions and JSON schema. Classification is off by default. |
| [`extract_fields()`](../doclayout/fields.py) | Raw Markdown, local chunks, definition, optional client and usage ledger; returns an outcome dictionary | Sends raw Markdown to the model, then verifies quotes and maps evidence locally. It does not reconvert the PDF. |
| [`FieldStore`](../doclayout/field_store.py) | Optional local root; manages document manifests, runs, SQLite records, and JSON exports | `save_result()` records a run; `run()` loads records; `export_run()` rebuilds JSON without a model request. |
| [`retry_fields()`](../doclayout/ui/batch.py) | Store, saved document ID, definition, optional client | Reuses saved raw Markdown and chunks. Do not route retries through `PdfConverter`. |

The [field extraction guide](field-extraction.md) covers routing, provenance,
and review rules. `tests/test_fields.py` checks the offline contract. Clinical
and administrative correctness still requires document-level review.

## Errors and compatibility

- Invalid converter configuration raises `ValueError`. Sol or response-validation
  failure is not a V3 miss and should not be reported as layout fallback.
- A direct layout-engine caller must handle `LayoutModelUnavailable`; normal
  conversion records a visible Sol fallback for a failed V3 page. A valid empty
  detection result is not a runtime failure.
- Old saved layout records without contours remain readable. Do not rewrite
  historical provenance when adding new metadata fields.
- Field-only retries use saved raw Markdown and metadata. They do not silently
  rerun PDF conversion if model or GPU availability changes.

For command-line and HTTP request/response formats, use [usage](usage.md);
for defaults and precedence, use [configuration](configuration.md).
