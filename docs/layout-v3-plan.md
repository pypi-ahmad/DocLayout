# PP-DocLayoutV3 integration

Status: implemented locally, unreleased, 2026-09-26. This records the approved
design and its bounded verification, not a claim of improved extraction accuracy.
Source and tests take precedence over earlier proposals, including the Grok
hypotheses. Pipeline v2 adds a layout prior to the packaged page prompt;
the system prompt and `ExtractedPage` response schema remain unchanged.
The latest user-approved policy uses Sol when V3 misses, has no accepted match,
or cannot run. Earlier phase records below describe the former fail-closed
conversion behavior; the Sol-fallback completion section supersedes that policy.

## 1. Data flow and insertion points

The shared path is now: provider-rendered page image → local V3 evidence → the
existing whole-page Sol request with compact `given_layout` JSON → `ExtractedPage` validation → conservative
geometry/order reconciliation → DocLayout blocks → existing structure and
document processors → final provenance → renderers. V3 never transcribes text,
adds a Sol request, crops the Sol input, or changes the response schema.
On V3 preparation/inference failure, the same whole-page Sol request runs without
`given_layout`, and validated Sol content, boxes and order are retained explicitly.

| Concern | Authoritative source location and behavior |
| --- | --- |
| PDF rendering and coordinates | [`providers/pdf.py:15–95`](../doclayout/providers/pdf.py#L15): process-wide PDFium lock; rotated-page size establishes top-left `[0,0,width,height]`; `get_images` renders at DPI/72 and closes PDFium page/bitmap objects after obtaining RGB images |
| Image inputs | [`providers/image.py:47–77`](../doclayout/providers/image.py#L47): image provider rendering, image-size page bounds, provider cleanup |
| Image lifetime and insertion | [`builders/document.py:23–135`](../doclayout/builders/document.py#L23): 192 DPI default, three-page batches; V3 and Sol borrow the same image; low/high-resolution page fields retain it on success; executor waits before failure cleanup closes rendered images |
| Sol request and cap | [`services/openai.py:33–133`](../doclayout/services/openai.py#L33): unchanged shared semaphore of three, PNG encoding at `process_images`, Responses structured parse, Sol/medium, `store=False`; the builder appends layout data to the existing input-text prompt |
| Validation | [`schema/extraction.py:71–126`](../doclayout/schema/extraction.py#L71): allowed types, HTML checks/sanitization, finite normalized 0–1000 bounds, positive area, blank-page consistency; validation precedes reconciliation |
| Geometry | [`layout.py`](../doclayout/layout.py), `page_box`/`reconcile`: normalized Sol → rendered pixels → page coordinates; [`schema/polygon.py:144–176`](../doclayout/schema/polygon.py#L144): existing rescale and intersection-percentage helper, which is **not** IoU |
| Identity versus order | [`schema/groups/page.py:99–140`](../doclayout/schema/groups/page.py#L99): child insertion assigns IDs and indexed lookup; only `structure` is reordered. Never sort `children` to implement reading order |
| Shared conversion | [`converters/pdf.py:175–205`](../doclayout/converters/pdf.py#L175): builder, structure builder, ordered processors, sanitation, final provenance, renderer |
| Markdown | [`renderers/markdown.py`](../doclayout/renderers/markdown.py), `MarkdownRenderer.__call__`: renders final document structure through HTML, then Markdown |
| JSON and chunks | [`renderers/json.py:51–84`](../doclayout/renderers/json.py#L51), [`renderers/chunk.py:67–119`](../doclayout/renderers/chunk.py#L67): final tree or flattened top-level blocks; original page ID comes from the page-ID component, not its numeric block suffix |
| Metadata and annotations | [`renderers/__init__.py:121–145`](../doclayout/renderers/__init__.py#L121), [`ui/exports.py`](../doclayout/ui/exports.py), `annotations`: layout audit plus final block metadata; overlays use final visible top-level structure, ordinal and block ID, on copied images |
| GUI and three-file cap | [`scripts/app_pages/convert.py`](../doclayout/scripts/app_pages/convert.py), [`ui/batch.py:284`](../doclayout/ui/batch.py#L284): three file workers, all pages for multiple files, existing selected-page range for one file; readiness callback runs on the UI thread |
| GUI conversion | [`ui/documents.py:107`](../doclayout/ui/documents.py#L107): one prepared document, multiple local renderers; [`scripts/common.py:37`](../doclayout/scripts/common.py#L37): cached model dictionary |
| CLI and library | [`scripts/convert.py:21,65,172`](../doclayout/scripts/convert.py#L21), [`scripts/convert_single.py`](../doclayout/scripts/convert_single.py), [`converters/pdf.py:98,175,205`](../doclayout/converters/pdf.py#L98): all converge on the shared converter |
| HTTP | [`scripts/server.py`](../doclayout/scripts/server.py), `_convert_pdf`/`_run`: same converter; ordinary V3 failures become Sol fallback. The defensive HTTP 503 handler applies only if a layout exception escapes that boundary |
| Lifecycle | [`models.py:7–20`](../doclayout/models.py#L7): API-client ownership remains separate from the borrowed process-level layout engine; [`layout.py`](../doclayout/layout.py), `get_layout_engine`/`close`: lazy singleton, serialized inference, process-exit release |
| Reuse and retries | [`ui/batch.py:45,81,148,175`](../doclayout/ui/batch.py#L45): saved conversion manifest/load, raw-Markdown-only field retry, fingerprinted conversion identity; [`output.py`](../doclayout/output.py), `output_exists`: CLI skip requires matching pipeline metadata |
| Configuration and launch | [`settings.py:10–36`](../doclayout/settings.py#L10), [`config/parser.py`](../doclayout/config/parser.py), [`pyproject.toml`](../pyproject.toml); [`launch.cmd:14–22`](../launch.cmd#L14): unchanged recognized-listener handling and frozen uv launch on 127.0.0.1:8471 |
| Prompt regression guards | [`tests/builders/test_document_builder.py:12`](../tests/builders/test_document_builder.py#L12) page-prompt fingerprint; [`tests/services/test_service_init.py:39`](../tests/services/test_service_init.py#L39) system fingerprint and request contract |

Minimal runtime insertion is the builder worker immediately before Sol, and
reconciliation immediately after validation. The additional touches preserve
provenance through processors and expose final geometry consistently; they do
not replace the conversion or downstream field pipelines.

## 2. Adapter and evidence

Use direct ONNX Runtime with the official
[PaddlePaddle ONNX repository](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx),
not a converted third-party weight file or a new PaddleOCR runtime dependency.
Pin revision `46bbdf188bb0a772c08aed74882ce7e51a8f1ea6` and verify both artifacts:

| File | SHA-256 |
| --- | --- |
| `inference.onnx` (130,502,049 bytes) | `45bf71750b00739a41fc209f132eb104a4d6b5bb29483c9078164d8b87cf28ba` |
| `inference.yml` | `506fcfac13b3b546ae40d7886b44126420f392adb694e3f8bb6a6286a1f90fdc` |

The [pinned YAML](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_onnx/blob/46bbdf188bb0a772c08aed74882ce7e51a8f1ea6/inference.yml)
defines 800×800 non-aspect-preserving resize, interpolation 2, normalization,
permutation, 25 labels, and a drawing threshold of 0.5. The official
[PaddleOCR inference-engine guide](https://www.paddleocr.ai/main/en/version3.x/inference_deployment/local_inference/inference_engine.html)
and [layout module guide](https://www.paddleocr.ai/main/en/version3.x/module_usage/layout_analysis.html)
describe higher-level APIs. Their postprocessing output is not the raw ONNX ABI.
PaddleX commit `c50f5da858020db473a2285f089bb8c7bbd6afdc` was inspected:
[`processors.py`](https://github.com/PaddlePaddle/PaddleX/blob/c50f5da858020db473a2285f089bb8c7bbd6afdc/paddlex/inference/models/layout_analysis/processors.py)
derives contours from masks and sorts/reindexes detections. This adapter does
neither contour extraction nor PaddleX's full high-level postprocessing.

The isolated probe, then the installed adapter, observed this batch-one contract:

| Tensor | Observed contract |
| --- | --- |
| `image` | float32 `[1,3,800,800]`, RGB, OpenCV bicubic resize, values divided by 255 |
| `im_shape` | float32 `[[800,800]]` |
| `scale_factor` | float32 `[[800/H,800/W]]`, original rendered image dimensions |
| `fetch_name_0` | float32 `[N,7]`: raw class ID, score, x0, y0, x1, y1, order key; boxes already in original rendered-image pixels |
| `fetch_name_1` | int32 `[1]`, candidate count |
| `fetch_name_2` | int32 `[N,200,200]`, binary page-grid masks |

Observed N was 300 on the official sample and five available authorized sample
pages. The validator checks dimensions, dtypes, counts, finite coordinates,
integer class range, score range and binary masks. It does not assume output
rows are reading order. The order key is observed model output, not verified
human reading order. Masks are observed; arbitrary polygon vertices are **not**
returned by this raw API. Paper capabilities alone establish neither this ABI
nor accuracy on the user's documents.

Windows AMD64 uses pinned `onnxruntime-gpu==1.30.0`, which also supplies the CPU
provider. Other platforms select pinned CPU ORT; those platforms were not tested.
Do not install both distributions into one environment. Python minimum is now
3.11; native checks used Python 3.14.6. The official
[CUDA provider requirements](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)
and [installation guide](https://onnxruntime.ai/docs/install/)
must be checked for the pinned release: current CUDA-provider guidance describes
CUDA 13 for ORT 1.27+, while generic installation examples can lag. No assumption
that any installed CUDA version will work is encoded. CPU and CUDA execution
were exercised on this Windows machine; GPU was an RTX 4060 Laptop GPU, driver
617.14. This is not a latency or memory-fit benchmark. DirectML/TensorRT are not
selected: they need separate evidence and deployment choices.

## 3. Region contract and explicit mapping

[`schema/layout.py`](../doclayout/schema/layout.py) is a local audit schema,
separate from model-response classes. Each page records original zero-based page
ID, `(W,H)`, actual exercised provider, candidate/filtered counts and warnings.
Each retained region records raw row, class ID, label, score, geometry kind
`rectangle_with_mask`, raw and page-clipped pixel rectangles, order key, stable
observed rank, eligibility/issues, `(200,200)` mask size and zero-first row-major
binary RLE. The mask grid spans the rendered page; it is not a polygon or a
region-local crop. Pixel geometry is never confused with PDF points. Regions
below the score cutoff are counted, not persisted individually.

The following mapping is an explicit matching-compatibility policy, **not** a
relabeling instruction. Sol's semantic type always wins. Picture/Figure/Diagram
are a compatible visual family; other mapped types require an exact match.

| ID | Artifact label | Matching BlockType | Limitation |
| --- | --- | --- | --- |
| 0 | abstract | Text | Does not create a special abstract section |
| 1 | algorithm | none | Pseudocode need not be Code |
| 2 | aside_text | Text | Sidebar semantics are not independently represented |
| 3 | chart | Figure | Visual-family match only |
| 4 | content | TableOfContents | Provisional semantic interpretation; review on real samples |
| 5 | display_formula | Equation | Does not synthesize formula text |
| 6 | doc_title | SectionHeader | Keeps Sol heading level/content |
| 7 | figure_title | Caption | Does not infer caption ownership |
| 8 | footer | PageFooter | Later marginalia rules still apply |
| 9 | footer_image | Picture | No text-footer relabeling |
| 10 | footnote | Footnote | Later footnote ordering still applies |
| 11 | formula_number | none | Unsafe standalone semantic mapping |
| 12 | header | PageHeader | Later header rules still apply |
| 13 | header_image | Picture | No text-header relabeling |
| 14 | image | Picture | Visual-family match only |
| 15 | inline_formula | none | Must not detach inline content |
| 16 | number | none | May be list, page or formula numbering |
| 17 | paragraph_title | SectionHeader | Keeps Sol heading level/content |
| 18 | reference | none | Citation marker is not safely a DocLayout Reference object |
| 19 | reference_content | Bibliography | Requires Sol's Bibliography type |
| 20 | seal | Picture | Does not imply handwriting or decoded seal text |
| 21 | table | Table | Form is deliberately not compatible |
| 22 | text | Text | Does not relabel lists/forms |
| 23 | vertical_text | Text | Orientation remains an audit/quality limitation |
| 24 | vision_footnote | none | No safe meaning established from artifact label alone |

Unsupported classes remain reviewable V3 evidence, never automatic DocLayout
blocks. All 25 IDs come from the pinned YAML, not another model's taxonomy.

## 4. Deterministic matching

For rendered image `(W,H)`, Sol normalized coordinates become
`[x0*W/1000,y0*H/1000,x1*W/1000,y1*H/1000]`. Both detectors are compared in that
same top-left pixel frame. For provider page bounds `(px0,py0,px1,py1)`, map x to
`px0 + x*(px1-px0)/W` and y analogously. No second inverse-resize is applied to
ONNX boxes. Clip effective V3 bounds to the image, retain the raw box, and reject
zero/negative-area results from matching.

Policy constants are versioned in [`layout.py`](../doclayout/layout.py):

1. Retain V3 score **> 0.5**. This follows the artifact's drawing cutoff as an
   initial filter, not a calibrated confidence guarantee.
2. Compute true rectangle intersection-over-union for eligible, compatible
   pairs. Candidate IoU must be **>= 0.5**. This is an uncalibrated conservative
   starting threshold, not a verified optimal value.
3. Identify strong containment edges where intersection/min(area) **>= 0.8**.
   If any endpoint has multiple strong neighbors, reject that entire connected
   component as a possible split/merge. No slicing or duplication of Sol HTML.
4. Accept only mutual-best pairs with both row and column margins **>= 0.10**
   above the runner-up (missing runner-up = 0). Tolerance is `1e-6`; equal or
   near-equal alternatives are ambiguous. Never greedily force a second choice
   after another assignment is removed. This guarantees at most one match per
   Sol block and per V3 region.
5. A match replaces geometry only and records Sol ordinal/bbox, match row/IoU,
   resulting box and original block lineage. Otherwise status is `sol_only`:
   preserve Sol text, HTML, type and geometry without truncation.
6. Reorder only consecutive runs of confidently matched Sol blocks by observed
   V3 order key. Sol-only blocks anchor their positions. A run with near-equal
   keys retains original Sol order and gets an ambiguity issue. Stable audit
   ranking uses raw row as tie-breaker; raw row does not establish reading order.
7. Unmatched V3 regions remain metadata with `unmatched_v3`; no new rendered
   blocks, placeholder OCR, or duplicate Markdown. Sol blank/V3 nonempty is a
   recorded disagreement, not permission to invent content.

These choices intentionally leave some order and geometry Sol-only. Splits,
merges and ambiguous labels need annotated evaluation before relaxing the policy.

## 5. Processors and output consistency

The processor sequence remains authoritative
([`converters/pdf.py:69–96`](../doclayout/converters/pdf.py#L69)).
`StructureBuilder` groups captions/lists and unions geometry
([`builders/structure.py:36–201`](../doclayout/builders/structure.py#L36));
footnotes move down ([`processors/footnote.py:21`](../doclayout/processors/footnote.py#L21));
headers move up ([`processors/page_header.py:18`](../doclayout/processors/page_header.py#L18));
list continuation/indentation changes structure
([`processors/list.py:31–112`](../doclayout/processors/list.py#L31)).
Line merges ([`schema/text/line.py:87`](../doclayout/schema/text/line.py#L87)),
table splitting/synthetic cells ([`processors/llm/llm_table.py`](../doclayout/processors/llm/llm_table.py)),
cross-page table merges ([`processors/llm/llm_table_merge.py:293–374`](../doclayout/processors/llm/llm_table_merge.py#L293)),
and optional page correction ([`processors/llm/llm_page_correction.py:191`](../doclayout/processors/llm/llm_page_correction.py#L191))
can supersede initial boxes/order. Reference insertion also changes child structure
([`processors/reference.py:52`](../doclayout/processors/reference.py#L52)).

Block replacement, line/table merge and generated table-cell paths now carry
lineage. Finalization collects group lineage **after** processors without
re-sorting or changing their geometry. Metadata distinguishes original detector
evidence from final type/bbox/structure, removed/ignored flags, geometry source,
and final page structure order. IDs remain stable even when reading order moves.
Markdown, JSON and chunks all consume the final document, not separate V3 sorts.
Annotations show the same visible top-level sequence as chunks, rather than all
historical children; hierarchical JSON still exposes nested blocks.

`PolygonBox` requires four points ([`schema/polygon.py:11–45`](../doclayout/schema/polygon.py#L11)).
It cannot faithfully store a many-vertex contour, a binary mask, or geometry on
multiple pages. This integration uses rectangle envelopes and stores masks
separately; it never calls an envelope an exact polygon. Existing cross-page
table behavior is retained, but metadata marks multiple source pages and keeps
each original footprint. Annotations draw those footprints on their own pages.
Field grounding keeps verified quotes but declines a single invented location
for a multi-page merged block ([`fields.py`](../doclayout/fields.py), `ground_records`).
Custom processors that invent geometry without known ancestry need their own
lineage hook; no general provenance inference is claimed.

## 6. Provider selection, ownership and concurrency

One lazy `LayoutEngine` exists per process. The engine lock covers initialization,
inference and fallback; batch size is one even with three file workers and three
page futures. Sol's independent shared three-request semaphore is unchanged.
There is no per-page engine, GPU worker pool, or import-time model download.

`auto` attempts a CUDA-priority session with CPU support for unsupported graph
nodes. Shared conversion entry points call idempotent `prepare()` before provider
construction. Readiness requires inference on a synthetic white RGB 800×800 image,
validated output (discarded after this check),
and an ORT profile containing executed CUDA kernels. Provider enumeration or a
CUDA environment variable alone is insufficient. Health profiles use unique
owned cache paths and are deleted after inspection. A CPU-only/silently fallen
back session does not count as CUDA-ready. See official
[ORT session/provider API](https://onnxruntime.ai/docs/api/python/api_summary.html).

In `auto` mode, CUDA initialization, health-check or later inference failure triggers a new CPU
session and the same page is exercised there. CPU success is latched for that
engine; warnings and actual provider are persisted. Failure of both paths is
caught at the conversion boundary: Sol proceeds without a layout prior, with
`sol_fallback` page provenance. A failed engine is latched until an explicit GUI
Run needing new conversion retries it;
operators can restart CLI/HTTP processes after repairing configuration. API
clients can close without destroying the process-shared engine.

## 7. Downloads, settings, failure and readiness

| Setting | Default | Behavior |
| --- | --- | --- |
| `DOCLAYOUT_LAYOUT_DEVICE` | `auto` | `auto`, `cuda` or `cpu`; explicit `cuda` forbids a replacement CPU session. Conversion uses Sol if the engine fails; no GUI toggle |
| `DOCLAYOUT_LAYOUT_CACHE_DIR` | `<BASE_DIR>/cache/pp-doclayoutv3` | Writable dedicated Hugging Face cache |
| `DOCLAYOUT_LAYOUT_MODEL_DIR` | unset | Exact directory for pinned `inference.onnx` and `inference.yml`; overrides the Hub cache for artifact resolution |
| `DOCLAYOUT_LAYOUT_OFFLINE` | `false` | True prohibits network resolution of missing weights |

These are Pydantic settings (process environment or `local.env`), not credential
`.env` entries. Restart after changes. `auto` still works on a CPU-only Windows
machine if its CPU session succeeds; GPU DLL installation is not required for
the CPU path. Native CUDA execution remains installation-specific.

The first uncached conversion resolves the pinned files locally, then downloads only
missing files if online, verifies SHA-256 and labels, and initializes/tests the
provider. Warm cache resolution is local-first; repeated pages reuse the session.
No inference promise is made by merely downloading files. Offline misses, corrupt
files and total runtime failure are typed engine errors. Conversion records
`sol_fallback` and continues through Sol rather than failing silently or presenting
an unavailable model as an empty successful detection.
The GUI prepares on the first explicit Run needing an uncached conversion, before
dispatching file jobs. It shows “Preparing layout model…” while the worker loads,
then “PP-DocLayoutV3 · CUDA” or “PP-DocLayoutV3 · CPU” for the actual device.
Preparation failure shows “Sol fallback · V3 unavailable”; new jobs use Sol while
saved jobs remain reusable. Status rendering stays on the UI thread. Opening
the GUI, saved-only batches, previews, downloads and field-only retries do not
initialize weights. No progress percentage or speculative memory estimate is shown.

For a pre-populated deployment use the official
[Hub download mechanism](https://huggingface.co/docs/huggingface_hub/guides/download)
with the exact repository, revision, files and configured cache directory. Windows
without symlink privileges can use a less space-efficient cache; see official
[cache limitations](https://huggingface.co/docs/huggingface_hub/how-to-cache#limitations).
Do not delete a broad cache to repair this model: repair only the identified
pinned artifacts, with the application stopped. `launch.cmd` is unchanged and
does not preload models or claim readiness at server startup.

## 8. Saved conversions and history

Pipeline `sol-layout-v3/v2` fingerprints artifact revision/hashes, mapping,
thresholds, execution/fallback policies, relevant installed runtime versions, device policy, rendering DPI,
conversion prompt/schema hashes, the `given_layout` protocol version, and a hash of conversion options. Raw options
and credentials are not copied into the public manifest. GUI document identity
adds that fingerprint to the original bytes, filename and options identity.
The saved metadata records actual providers separately from requested policy.
GUI input-option fingerprint and converter-effective-option fingerprint are
computed at their respective boundaries; they are not asserted to be identical.

Existing V3-v1 and Sol-only saved conversions keep their IDs/files. Sol-only saves are labeled
`legacy-sol-only` on load when no pipeline manifest exists. A new Run under the
V3 pipeline gets a new identity; it does not relabel or overwrite a historical
field-store conversion. Field-only retries continue using that saved conversion's
`raw.md` and chunks, including legacy results, without layout or Sol conversion.
CLI `--skip_existing` requires matching metadata; explicit CLI export into an
existing destination retains its existing overwrite semantics, so use a new
destination when retaining old CLI exports. There is no migration of history.

## 9. Files, verification and open evidence

Implementation files: `layout.py`, `schema/layout.py`, builder/converter,
`models.py`, `settings.py`, `schema/blocks/base.py`, `schema/document.py`,
`schema/groups/page.py`, `schema/text/line.py`, LLM table/table-merge processors,
renderer metadata/chunks/OCR geometry description, `ui/batch.py`,
`scripts/app_pages/convert.py`, `ui/exports.py`, `fields.py`, `output.py`,
`scripts/convert.py`, `scripts/server.py`, `pyproject.toml` and `uv.lock`.
Tests: `tests/test_layout.py`, offline fixtures in `tests/conftest.py`,
browser fixture/navigation selector in `tests/test_ui_browser.py`, plus existing
builder/service/processor/renderer/UI/field/launcher regressions.

Bounded verification covers tensor/preprocess contracts, actual pixel scale,
provider health/failure/fallback, one-engine serialized access, score/IoU
boundaries, split/merge/tie handling, text preservation, blank-page disagreement,
image ownership, request/prompt invariants, final chunk/overlay order, cache
hash/offline behavior, pipeline identity, entry-point Sol fallback, the defensive
HTTP 503 handler, and multi-page grounding.
Offline tests never download weights or call Sol.

Earlier initial-phase verification: full `uv run --no-sync python -m pytest -q` completed with
**307 passed, 1 skipped** (optional benchmark data absent), including the browser
workflow. Focused Ruff checks passed for the new adapter/schema/tests and changed
builder/UI/field paths; focused ty checks passed for adapter/schema/builder/batch.
`uv lock --check` and `git diff --check` passed. A broader Ruff pass over touched
legacy modules still reports 121 diagnostics (principally legacy typing/style);
ty also reports the existing optional `soup.body.decode_contents` access in
`ui/exports.py:51`. These were not treated as authorization for unrelated cleanup.
The browser regression's old link selector was updated to the existing button
navigation; navigation behavior itself was not changed. Baseline file hashes
confirmed conversion prompts/schema, Sol service, launcher, generated wiki and
diagrams remained unchanged, and no pre-existing file was removed.

Native adapter observations on 2026-09-26:

| Input | Pages (one-based) | Regions >0.5, CPU / CUDA |
| --- | --- | --- |
| Official `layout.jpg`, 760×865 | 1 | 13 / 13 |
| Masked Amerigroup_1.pdf | 1, 2 | 11, 6 / 11, 6 |
| Masked_Amerigroup_RealSolutions_1.pdf | 2, 3 | 18, 25 / 18, 25 |
| Masked_Amerigroup_RealSolutions_2.pdf | 1 | 13 / 13 |

Both providers returned 300 candidates per tested page and valid boxes/masks/order
keys. CUDA execution was confirmed by profiling; equal retained counts are not
proof of numerical equivalence or accuracy. Native CUDA emitted the upstream
ScatterND warning about correctness when indices are duplicated. Its impact on
these model outputs remains unverified. The local probes read saved originals
without changing historical outputs or making new Sol/field calls.

Remaining release/evaluation work: locate the two authorized BadgeCare pages
(not found among the scoped saved originals), run the complete seven-page
end-to-end Sol comparison, review overlays and text/order differences against
human labels, calibrate thresholds and ambiguous class mappings, investigate
the ScatterND warning, and measure cold/warm latency and peak memory before
making performance or hardware-fit claims. No polygon accuracy, reading-order
accuracy, speedup, or extraction improvement is established here. Windows ARM,
other operating systems, DirectML and alternate model revisions remain untested.

## Runtime-only follow-up

Historical phase record: the later Sol fallback completion supersedes references
to mandatory layout success at conversion entry points. Direct engine calls still
raise typed errors.

That phase preserved the existing page wiring, matching policy, prompts, model
IDs, credentials, field workflow and export structures. It did not repeat the
earlier native hardware probe. Its changes were limited to the runtime, local
result type, settings, focused tests and these runtime notes. The subsequent v2
integration below changes page requests and adds runtime export metadata.

`LayoutEngine.analyze(page_image)` now returns a page-independent
`LayoutAnalysis`: image size, retained regions, candidate/filtered counts, pinned
model ID/revision, actual device/provider, warnings and `elapsed_ms`. Elapsed time
uses a monotonic clock and includes lock waiting, first-run preparation and
fallback, not just inference. `order_key_source="model_output"` labels the raw
order key; `observed_rank_source="derived_sort"` labels the existing stable audit
rank. Rectangles, raw/clipped bounds and mask RLE retain their existing meanings;
no polygon vertices or missing reading-order values are fabricated.

The existing `infer(image, page_id)` method adapts this result back to the same
`PageRegions` shape. That phase did not add timing/model fields to exports;
v2 records them separately in `layout.page_runtime`.
`LayoutModelUnavailable` is the public typed error;
`LayoutUnavailableError` remains an alias so existing conversion error handlers
need no changes.

An explicit `cuda` request now fails if CUDA cannot initialize, execute, or
produce a verified kernel profile. It never changes to CPU, including after a
later runtime failure. `auto` retains exercised CPU fallback; `cpu` never tries
CUDA. CUDA verification requires an executed Node kernel event, not merely a
provider name in a session-level profile event. The first successful inference
also supplies the first result; subsequent pages reuse the session without
profiling again. A failed native session is released before its replacement is
allocated. Terminal failure remains latched until an explicit retry.

Required runtime imports are checked before downloading artifacts. Importing the
package or creating the lazy engine does not import ONNX Runtime/Hub/YAML or
download weights. A missing dependency or native loader failure raises an
actionable typed error when analysis starts. NumPy and OpenCV were already base
dependencies; all existing runtime dependency pins and the uv lock are retained.
No optional layout extra, additional package, or new lockfile was introduced.

When `DOCLAYOUT_LAYOUT_MODEL_DIR` is set, existing files in that exact directory
are hash-checked before any missing file is downloaded there. A complete directory
works offline and does not contact the Hub. Empty paths, a non-directory target,
corrupt artifacts, malformed labels, download failures and unsupported output
contracts fail explicitly. Existing invalid files are not silently overwritten.
Hub locking/completion behavior handles downloads; the engine lock ensures one
preparation for concurrent file jobs. Hashing and resolution happen once, not
once per page. CUDA health-profile scratch files still use the app cache, so a
complete read-only model directory needs a separate writable cache for profiling.

Verification for this follow-up: **64 layout/runtime tests passed**, plus
**75 builder/service/renderer/field regressions**. Focused Ruff and ty checks
passed. The new tests use fake artifacts, sessions and an injected analyzer;
they do not download model weights or call Sol/Luna. They cover cold/warm
downloads, initialization races, explicit CUDA failure, automatic fallback,
CPU failure, dependency errors before downloads, model-directory precedence,
exact parsing/class IDs, pixel scaling, timing and legacy-result compatibility.
Earlier hardware observations above remain historical evidence, not verification
of the follow-up's stricter CUDA profile gate. The ScatterND warning, quality,
latency and memory questions remain open.

## Whole-page layout-prior integration (v2)

Historical phase record: see the Sol fallback completion for current conversion
failure handling. The prompt and matching details below remain relevant.

The builder now calls `LayoutEngine.analyze` once on each rendered image before
Sol. `layout.extraction_prompt` appends a compact JSON object with `given_layout`
protocol version 1, `full_page_normalized_0_1000` coordinates, rectangle geometry,
and eligible regions. Each region carries its raw row, class ID, label, score,
normalized clipped rectangle, observed order key and nullable mapped BlockType
hint. Regions are sorted by order key then raw row for deterministic serialization;
the prompt explicitly says ties and row IDs do not establish reading order.
All eligible regions are included, with no top-k truncation. Masks, model timing,
credentials and document text are not inserted into this JSON. Pixel evidence
is not modified or rounded by serialization.

The packaged extraction prompt describes these as fallible layout hints. Sol
still sees the same whole-page image and supplies visible content, semantic types,
heading levels and table HTML. It must avoid duplicate overlapping content and
include content missed by V3 with its own bounds. False detections do not justify
invented text. Document text remains untrusted. An empty detection list is an
explicit empty prior, not a runtime bypass. Layout failure precedes that page's
Sol call. The service signature, model/medium settings, credential flow, request
cap, `store=false`, system prompt and response schema are unchanged.

Validation/sanitization and the matching policy in section 4 remain unchanged.
`PageRegions` and the legacy `infer` return shape are preserved. New
`layout.page_runtime`, keyed by original page ID, records model ID/revision,
actual device/provider, elapsed milliseconds, order-source labels, retained and
prior region counts, and matched/Sol-only/unmatched-V3 counts. Counts explicitly
describe `initial_reconciliation`, before grouping, merges or hiding. Elapsed time
includes first-run preparation and lock waiting. Final geometry, structure and
lineage remain in the existing final block audit, after processors.

Exports continue using rectangle envelopes, not contour-accurate polygons.
Hidden headers/footers may remain empty HTML entries in hierarchical JSON/chunks;
Markdown and annotations omit their visible content. Tests compare common block
IDs, bounds and order rather than requiring identical counts across renderers.
Grouped blocks retain their original sources while exposing the final union box.

The pipeline is `sol-layout-v3/v2`; its fingerprint includes the prior protocol
version and updated packaged prompt hash. New GUI conversions do not reuse
legacy Sol-only or V3-v1 identities. Historical conversion files are not migrated
or relabeled. Field-only retries, previews and downloads still consume saved
artifacts without layout inference or PDF reconversion. No runtime dependency,
launcher, UI toggle, generated wiki/diagram or field-prompt change is part of v2.

Changed files for this phase: `doclayout/layout.py`,
`doclayout/builders/document.py`, `doclayout/schema/layout.py`,
`doclayout/prompts/extraction.md`, `tests/test_layout_prior.py`,
`tests/test_layout.py`, `tests/builders/test_document_builder.py`,
`tests/conftest.py`, `tests/test_ui_browser.py`, `tests/test_fields.py`, and this
plan. A before/after hash comparison found no other changed files or removals.

Verification uses offline fake analyzers and mocked Responses calls: prior
coordinates/all-class hints, actual whole-image request payload, shared API cap,
two-column order, preserved sanitized heading/table HTML, empty priors, ambiguous
matches, split/merge policy, processor grouping/order, rectangular overlays,
final JSON/chunk bounds, runtime provenance, historical save separation and
field-only retry isolation. These tests cannot establish model transcription
quality, threshold calibration or reading-order accuracy. No new native CUDA
probe, model download or billable Sol/Luna call was made for this phase.

Final v2 checks: `uv run --no-sync python -m pytest -q` passed with **356 passed,
1 skipped** (optional benchmark data absent), including the browser workflow.
The focused layout/runtime/builder/service/renderer/field selection passed
**154 tests**. Focused `uv run --no-sync python -m ruff check`, Ruff formatting
checks and `uv run --no-sync ty check` passed on the changed Python paths (ty:
layout adapter/schema, document builder and batch integration). `git diff --check`
passed. These results supersede neither the dated native probe nor its open
CUDA ScatterND, threshold-calibration, latency and memory limitations.

## Entry-point readiness completion (2026-09-26, local unreleased)

Historical phase record: this describes the former conversion-blocking readiness
policy. The later Sol fallback completion replaces that behavior; GUI, CLI,
library and HTTP conversion now continue through Sol when layout is unavailable.

`LayoutEngine.prepare()` now exercises the existing validated inference path on
one owned synthetic white RGB 800×800 image, closes it, and discards its output.
A reentrant lock serializes concurrent preparation and analysis; a ready session
is reused without another warm-up. This supersedes the earlier first-real-page
initialization description for supported conversion entry points. It verifies
provider execution on the probe, not real-document quality or future stability.

`PdfConverter.build_document` prepares the injected or process-cached engine
before constructing the document provider. The GUI, file/folder/single CLIs,
Python PDF/OCR/table converters and HTTP conversions converge on that gate.
HTTP preparation failure returns a sanitized 503; CLI/library callers retain the
typed layout failure. API startup remains lazy. Existing Sol requests, prompts,
schemas, pipeline-v2 identity and downstream fields are unchanged.

GUI batch preflight uses the same saved-conversion identity as each file job.
Only an explicit Run with uncached work prepares the engine, on a worker thread;
the UI thread renders loading, actual-device or failure status. Saved-only batches
and field retries do not prepare. If preparation fails, uncached jobs receive
failure receipts while cached jobs can continue. Three file workers and the
independent shared three-page Sol cap remain unchanged. Stored metadata supplies
inexpensive region/match counts and summed page-analysis time. In this path the
separate warm-up is excluded from page timing; queue waiting and later fallback
remain included. Annotations are labeled rectangular block bounds.

Files changed in this phase: `doclayout/layout.py`,
`doclayout/converters/pdf.py`, `doclayout/ui/batch.py`,
`doclayout/scripts/app_pages/convert.py`, `doclayout/scripts/server.py`,
`tests/conftest.py`, `tests/test_fields.py`, `tests/test_ui_browser.py`,
`tests/test_layout_runtime.py`, new `tests/test_layout_readiness.py`,
`.env.example`, `docs/architecture.md`, `docs/configuration.md`, `docs/usage.md`,
`CHANGELOG.md`, and this record. A beginning/end hash comparison found only these
16 files changed and no removals. Dependencies, lockfile, launcher, conversion
prompts/schemas and generated diagrams/wiki were not changed in this phase.

Verification:

- `uv run --no-sync python -m pytest -q`: **375 passed, 1 skipped** (optional
  benchmark data absent), including offline browser readiness, GUI failure/retry,
  CLI/API/library failure paths, initialization races, provider fallback, output
  provenance/annotations, concurrency caps and saved-field retry isolation.
- Focused readiness/runtime/security selection: **89 passed**.
- Scoped Ruff checks and formatting pass on the changed Python paths excluding
  existing lint findings in `converters/pdf.py` (12 legacy typing/default findings)
  and `scripts/server.py` (one unchanged broad-exception boundary).
- `uv run --no-sync ty check` passes for layout, converter, batch and GUI modules.
  Adding the server module reports one diagnostic at the unchanged
  `anyio.to_thread.run_sync` call (`unresolved-attribute`); it remains outside this
  readiness patch. `git diff --check` passes.

No native model download/inference, CUDA hardware check, masked-PDF comparison
or billable Sol/Luna call was performed. Synthetic fakes establish control flow,
not hardware fitness, latency, memory requirements, order accuracy or Markdown
improvement. Earlier native-probe limitations remain open; no GPU test was added
to CI. Nothing was committed, published or deployed.

## ScatterND CUDA workaround (2026-09-26, local unreleased)

The installed ONNX Runtime 1.30.0 CUDA ScatterND constructor emits the
`reduction=none` warning without inspecting runtime indices. Its compute path
does not consult the session's deterministic-compute setting. The warning is
not evidence that this model produced duplicate indices or caused missed boxes.
See the versioned upstream
[constructor](https://github.com/microsoft/onnxruntime/blob/v1.30.0/onnxruntime/core/providers/cuda/tensor/scatter_nd.h)
and [compute implementation](https://github.com/microsoft/onnxruntime/blob/v1.30.0/onnxruntime/core/providers/cuda/tensor/scatter_nd.cc).

The adapter now uses ORT's supported
[name-based layer assignment](https://github.com/microsoft/onnxruntime/blob/v1.30.0/docs/annotated_partitioning/PartitioningWithAnnotationsAndMemoryConstraints.md#name-based-layer-assignment-no-model-modification):
`session.name_based_layer_assignment=cpu(ScatterND)`. No model bytes, operator
semantics, logging severity, dependencies or Sol prompts are changed. Before
CUDA inference, recorded graph assignments must contain exactly one ScatterND
and assign it to CPU. Otherwise CUDA is rejected: `auto` exercises CPU through
the existing fallback, while explicit `cuda` fails. Other eligible operations
remain on CUDA, with the existing executed-kernel health check. This avoids the
CUDA-specific warning path; it does not prove duplicate indices are absent or
that detection accuracy improves.

The manifest records `execution_policy=onnx-cuda-scatternd-cpu/v1`, separating
new conversion identities from earlier placement. Historical artifacts are not
modified, and field-only retries continue using saved Markdown.

Native checks used only a synthetic white RGB 800×800 image and already cached,
hash-verified weights. Recorded placement showed 1,250 CUDA nodes and 150 CPU
nodes, including `ScatterND.0` on CPU. Two repeated mixed-provider runs had
bit-identical raw outputs. Comparison with an all-CPU run had equal count output
but nonidentical box/mask tensors; this was not an accuracy or numerical-parity
validation. The patched engine separately passed explicit-CUDA preparation and
two page analyses (zero retained regions on both blank images), confirming
executed CUDA kernels and no ScatterND warning. ORT's four-Memcpy-node performance
warning remains visible; transfer overhead has not been benchmarked. No real
document or Sol/Luna call was used, and no Transformers comparison was run.

Focused offline verification: **149 passed** across runtime, matching, layout
prior, readiness and field tests, including placement rejection, automatic CPU
fallback, explicit-CUDA failure, profile cleanup and fingerprint separation.
Scoped Ruff, formatting, ty and `git diff --check` passed. Changed files are
`doclayout/layout.py`, `tests/test_layout_runtime.py`, `tests/test_layout.py`,
`docs/configuration.md`, `CHANGELOG.md` and this record. Restart the app to replace
an already prepared process-cached session; this patch does not terminate it.

## Sol fallback completion (2026-09-26, local unreleased)

The user explicitly replaced mandatory V3 success with Sol fallback for missed,
mismatched or unavailable layout. The shared converter still attempts preparation;
if it fails, a conversion-local fallback engine avoids repeated preparation/page
probes. Page-time V3 exceptions are caught only around layout analysis. Sol calls,
schema validation, sanitization, rendering and field failures retain their existing
error behavior. Successful V3 pages still use the existing matching policy; failed
pages send the whole image with the unchanged page prompt and no prior JSON.

Missing/low-overlap, incompatible-class, ambiguous and split/merge matches keep
Sol content, validated geometry and original order. This does not detect every
visually wrong but geometrically accepted V3 box; thresholds remain provisional.
No extra transcription call, prompt/schema change or new model is introduced.

Fallback pages record `status=sol_fallback`, `failure_stage=preparation|inference`,
`provider=unavailable`, null actual device and order-source fields, zero V3 counts,
and a non-sensitive warning. Blocks retain `sol_only` with `layout_unavailable`;
final exported bounds and annotations use Sol geometry subject to existing
processors. Available pages retain their real V3 device/order metadata. GUI status,
saved result summaries and CLI/library logs expose fallback; backend exception
details are not displayed. The direct engine API still raises typed failures.

The new `fallback_policy=sol-on-layout-failure/v1` participates in conversion
fingerprints. Historical strict-V3/Sol-only results are not relabeled. Completed
fallback conversions are reusable saved results and are not silently reconverted
when V3 recovers. Explicit field-only retries continue using saved raw Markdown.
Three file jobs, the shared three-page request cap, exports, credentials and
Sol/Luna model settings are unchanged. No real model or billable API call was
made for this phase.

Fallback verification: `uv run --no-sync python -m pytest -q` passed with
**391 passed, 1 skipped** (optional benchmark data absent). Offline coverage
includes preparation failure in CLI/API/library/GUI, inference failure, mixed
successful/failed pages, sanitized HTML, final JSON/chunk bounds and annotations,
missed/incompatible/low-overlap matches, propagated Sol errors and image cleanup,
no preparation reprobes, fingerprint separation and saved-field retry behavior.
Scoped Ruff and formatting passed; the touched converter's focused F/E9 check
passed (its unrelated legacy lint findings remain). Type checks passed for layout,
layout schema, builder, converter, batch and GUI modules; `git diff --check` passed.
A working-tree hash comparison found only the intended 15 files changed and no
removals. Dependencies, model weights, Sol prompts/response schema, field definitions,
launcher and generated diagrams/wiki were unchanged. The running app was not
restarted; restart it when in-progress work is complete to reload process state.
