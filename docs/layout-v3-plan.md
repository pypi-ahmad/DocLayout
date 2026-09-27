# PP-DocLayoutV3 integration

Current local implementation: pipeline **v4**, with
[completion verification](#completion-verification-2026-09-27-local-unreleased).
The contour integration is described in
[Full decode and consumer integration](#full-decode-and-consumer-integration-2026-09-27-local-unreleased).
The release baseline and dated phase records below are historical. The v3 section
supersedes their rectangle-only guidance, exact-type matching, split/merge veto,
contiguous-run ordering, and processor/export geometry policies. It does not
supersede the Sol fallback or runtime protections.

Historical baseline status: released in v3.0.0, 2026-09-26. The local v4 work above
is unreleased. The following baseline sections record the approved
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

## Full decode and consumer integration (2026-09-27, local unreleased)

Implemented locally, without commits, publication, deployment, or restarting the
running application. Source and tests remain authoritative over historical Grok
analysis. This section records behavior, not an extraction-accuracy claim.

### Locked product rules

- Keep `PaddlePaddle/PP-DocLayoutV3_onnx`, revision
  `46bbdf188bb0a772c08aed74882ce7e51a8f1ea6`, and both hashes in section 2.
  Do not substitute the Paddle or safetensors repositories.
- Submit the same whole-page image to Sol/medium through the existing service,
  credentials, concurrency limits, and `ExtractedPage` response schema. Sol owns
  wording, HTML, semantic block types, and geometry/order for unmatched content.
- V3 owns usable matched source geometry, its separate layout class, and relative
  reading order. Preserve every Sol-only block. V3-only regions are diagnostic
  evidence, never invented HTML or duplicate extraction blocks.
- Default GPU detection retains CPU fallback. A V3 preparation/inference failure
  uses the ordinary whole-page Sol request without guide JSON. Successful pages
  do not become failures because another page falls back; valid empty detections
  remain successful. No fail-closed conversion mode, new reading model, cropped
  Sol pipeline, or GUI layout toggle was introduced.
- Classification, field definitions, model choices, score gates, saved field-only
  retries, and storage contracts are unchanged.

### Verified raw decode, not PaddleX public JSON

The raw batch-one ABI remains float32 `[N,7]` detection rows, int32 `[1]` count,
and int32 `[N,200,200]` binary masks. Row *i*, mask *i*, and the seventh column's
raw order key stay associated before and after the score filter. Count must
equal N. N=300 was observed, not imposed as a validator requirement. All tensor
rows are validated, including those subsequently filtered out. Invalid contracts
raise `LayoutContractError`, a typed layout-unavailable error. No new zero-based
or one-based requirement is imposed on raw order keys.

The reference is PaddleX revision
[`ffb64904d23708863ff5b8da312a5cbd52a7f462`](https://github.com/PaddlePaddle/PaddleX/blob/ffb64904d23708863ff5b8da312a5cbd52a7f462/paddlex/inference/models/layout_analysis/processors.py),
specifically `extract_polygon_points_by_masks`, `mask2polygon`,
`extract_custom_vertices`, and the `poly` branch of `_normalize_layout_polygon`.
The adapted algorithm is isolated in `doclayout/layout_geometry.py`, with
PaddlePaddle attribution in its header and NOTICE. No PaddleX runtime dependency
or `layout_shape_mode` configuration was added.

Preprocessing still uses RGB, OpenCV bicubic 800×800 resize, `/255`, and NCHW;
`im_shape=[[800,800]]`, `scale_factor=[[800/H,800/W]]`. Output AABBs are already
rendered-page pixels: they must not be inverse-resized again.

For contour extraction:

1. Round a copy of the raw AABB as the reference does. Retain the original
   floating AABB and its separately page-clipped version.
2. Map the rounded raw box into the page mask grid using `200/W` and `200/H`.
   Round grid endpoints, clip the grid slice to `[0,200]`, and crop the mask.
   The retained 200×200 mask is **not** region-local.
3. Resize that crop with nearest-neighbor interpolation to the rounded **raw**
   box width/height, even for a boundary-crossing box. Extract the largest
   external component (`RETR_EXTERNAL`, `CHAIN_APPROX_SIMPLE`), simplify with
   `approxPolyDP` epsilon `0.004 * perimeter`, then apply the reference custom
   concavity/sharp-corner rules. Its `max_box_w=max(x_max-y_min)` expression is
   preserved, including that unusual coordinate subtraction, across the retained
   score-filtered rows. No additional NMS or class/containment filtering is run.
4. Offset vertices by the rounded raw box origin. Preserve the reference contour,
   including out-of-page vertices with an issue. The reference keeps one component
   and omits holes; the original zero-first, row-major mask RLE retains that lost
   evidence. This is a simplified contour, not a lossless mask boundary.

`contour_status` distinguishes `not_decoded` (legacy), `valid`, `bbox_fallback`,
and `unusable`. Empty crops/masks, too few vertices, invalid polygons, and native
contour failures receive explicit reasons. A usable V3 AABB remains eligible when
its contour fails. A defensive allocation guard rejects contour resize requests
above four rendered-page pixel counts, and coordinates outside OpenCV's int32
range, retaining the AABB/mask with the specific reason. This is a memory guard,
not an evaluated accuracy threshold or a guide-size cap.

PaddleX public postprocessing additionally filters/merges detections and
sorts/updates order indices. Its public JSON IDs/order are not raw ONNX columns.
This adapter deliberately preserves original class IDs, scores, rows, masks,
order keys, and independently named `observed_rank` instead.

### Coordinate and guide contracts

`PolygonBox` still requires four corners. `LayoutRegion.contour_px` holds raw
reference vertices in rendered-image pixels. Matching/guide/export consumers
derive page-clipped polygons using Shapely; a concave intersection may produce
several components, and every component is retained. No convex hull, independent
vertex clamping, or silent `make_valid` repair substitutes another shape.

For pixel `(x,y)` and provider bounds `(px0,py0,px1,py1)`:

- Request coordinates: `(1000*x/W, 1000*y/H)`.
- Provider coordinates: `(px0+x*(px1-px0)/W, py0+y*(py1-py0)/H)`.
- Annotation pixels use the inverse provider mapping with the actual output
  image size. Nonzero and negative page origins are covered by tests.

`given_layout` version **2** contains page-local `id=r<raw row>`, row, class ID,
label, score, normalized AABB, contour components, geometry source/fallback,
raw `order_key`, `derived_rank`, and the existing semantic hint. Geometry is
rounded to three decimals **only in the request**. Degenerate rounded rings use
an explicitly identified request AABB fallback. Masks/RLE never enter the prompt.

The extraction instructions ask Sol to read the entire page, use V3 as the layout
guide, preserve outside-guide content, return its existing text/HTML and rectangle
schema, and avoid duplicate or empty detection-coverage blocks. They explicitly
describe application-side geometry assignment. The system prompt is unchanged.

There is no 512-region limit, 64-KiB limit, or silent truncation. Per-page runtime
metadata records actual compact JSON UTF-8 `guide_bytes` and `guide_vertex_count`.
A regression sends all 600 constructed regions and exceeds 64 KiB. During the
native synthetic-page probe, 57 retained regions and 265 vertices produced an
18,446-byte guide. These are payload measurements, not token counts or a context
budget guarantee; representative worst-case guides still need evaluation.

### Matching and order policy

Use polygon IoU between effective V3 contours and Sol's rectangle-as-polygon.
Unusable contours use V3 AABB IoU, with `match_metric`, `geometry_source`, and a
specific reason. Sol does not return native contours.

Family guards replace exact semantic-type equality:

| V3 labels | Sol matching family |
| --- | --- |
| abstract, aside_text, content, doc_title, figure_title, footer, footnote, header, paragraph_title, reference_content, text, vertical_text | Text, SectionHeader, PageHeader, PageFooter, Caption, Footnote, Bibliography, ListGroup, TableOfContents, Code |
| table | Table, Form |
| display_formula | Equation |
| chart, footer_image, header_image, image, seal | Picture, Figure, Diagram |
| algorithm, formula_number, inline_formula, number, reference, vision_footnote | Evidence only; no automatic semantic mapping |

Text-versus-table/image/formula pairings remain incompatible. Unsupported Sol
types, including ChemicalBlock, retain Sol geometry. A compatible class
disagreement is recorded; it never relabels a block or rewrites its HTML.

Detection score `>0.5` and candidate IoU `>=0.5` remain active **provisional**
defaults. Candidate pairs sort by descending IoU, descending V3 confidence,
ascending raw region row, then ascending Sol ordinal. Greedy reservation accepts
each Sol block and each V3 region at most once. It may choose a remaining qualified
pair after a better candidate was reserved; this is not global optimization.

Containment `>=0.8` diagnoses split/merge overlaps. Qualified competing scores
within margin `0.10` produce ambiguity warnings, and `1e-6` identifies near ties.
These no longer veto qualified assignments. A merged Sol block can contain text
outside its assigned region; that limitation is recorded without splitting text,
inventing leftover boxes, averaging geometry, or fabricating V3-only text.
Sol-only reasons distinguish empty output, unusable geometry, incompatible class,
low overlap, reserved candidates, preparation failure, and inference failure.

Matched slots in the original Sol sequence are replaced by the globally sorted
matched sequence `(raw order key, raw region row, Sol ordinal)`. Sol-only relative
order stays intact; their placement is fallback behavior. Equal/near-equal model
keys retain an uncertainty issue even though the implementation chooses a stable
order. Reordering `structure` does not renumber original block IDs.

### Processors, visibility and authoritative exports

Original source records now carry provider-page contour components/AABBs,
geometry ownership (`v3_contour`, `v3_bbox`, `sol`, or legacy), class, order key,
rank, matching evidence and issues. They retain their original block/page/region
identity through replacement, line/list/table operations and generated cells.
Derived records use `source_footprints`; inherited table evidence is not claimed
as a newly detected cell contour. Saved records lacking new fields remain readable.

Structure groups and destructive merges copy source evidence before losing
ancestry. Finalization gathers it again after processors. Groups may have several
source footprints, including multiple pages; no single authoritative group contour
is invented. Legacy JSON/chunk `bbox` and four-point `polygon` remain rectangular
bounds. Full source geometry is available in their layout metadata. Field grounding
continues using its existing rectangle interface and multi-page ambiguity guard;
it was not migrated to contour-level or field-level localization.

Header/footnote processors and optional page correction do not override pages
with matched V3 source order. Their non-order processing and fallback-page behavior
remain. Finalization sorts matched group slots by the earliest matched source on
the host page. An indivisible assembly whose source keys interleave other blocks
gets `assembled_source_order_interleaves`; the application does not divide its
HTML to force a total order. An unassembled matched block's attempted geometry
overwrite is rejected with `processor_geometry_change_ignored`.

A shared non-mutating visibility check applies explicit removal/suppression and
then matched V3 furniture labels through the existing header/footer settings.
Matched ordinary body content is not hidden merely because Sol called it a header
or a marginalia heuristic considers its position suspicious. Sol-only content
retains the existing fallback semantics. Rendering with different visibility
settings does not latch a previous render's header/footer flags.

Annotated images and the raster annotated PDF now draw the same visible source
footprints: contours when usable, V3 rectangles on contour fallback, and Sol
rectangles otherwise. Both same-page and cross-page assemblies draw all their
source footprints on the appropriate pages, with final block IDs/ordinals. Hidden
or removed historical blocks do not become duplicate overlays. V3-only detections
remain separately identifiable in layout audit metadata, not in the extracted-block
overlay. Export failures still propagate as export failures.

### Runtime, compatibility and verification limits

The process-shared serialized batch-one engine, cached hash checks, offline mode,
exercised CUDA detection/CPU retry, sticky CPU fallback, latched failures and
verified ScatterND CPU placement are retained. Explicit `cuda` forbids a replacement
CPU session; conversion can still use Sol when that engine fails. A CUDA-priority
session remains mixed CUDA/CPU execution, not entirely GPU execution. No per-page
provider reprobe was added.

Pipeline `sol-layout-v3/v3` fingerprints guide v2, decoder, matching, order and
source/visibility policies, compatibility families, changed page prompt, Shapely
version and the existing runtime/artifact contracts. The response-schema and system
prompt contracts remain unchanged. New conversions get new identities; historical
records are neither relabeled nor overwritten.

Independent fixed fixtures were produced from the cited PaddleX functions, not
DocLayout calculations, and cover non-square pages, concavity, disconnected masks
and boundary-crossing raw boxes. Offline tests also exercise malformed tensors,
mask round-trips, contour fallbacks, payload accounting/no caps, class disagreements,
one-to-one assignment, ties, global order, actual list/table/replacement lineage,
visibility, drawing, unchanged Sol requests, and mixed successful/empty/failed pages.

A native offline probe on Windows, Python 3.14.6, Shapely 2.1.2 and the existing
ONNX Runtime 1.30.0 prepared the default auto engine with cached hash-verified
weights. The selected CUDA-priority session passed its executed-kernel and ScatterND
CPU checks. A synthetic two-column page produced 300 candidates and 57 retained
valid contours. All 57 matched the independently executed reference exactly. ORT's
existing four-Memcpy-node performance warning remains visible.

No private document or billable Sol/Luna request was used for this phase. Remaining
evaluation: representative document contour quality, matching thresholds after
switching to contour IoU, split/merge correctness, furniture labels, reading order,
guide size/token cost and influence on Sol wording/HTML, and latency/memory. Synthetic
execution and passing unit tests do not establish model accuracy. There is no new
claim that contours identify individual business-field values.

Verification results for this local implementation:

- `uv run python -m pytest -q`: **429 passed, 1 skipped** (optional benchmark
  data absent), including the headless browser export/field workflow. The browser
  fixture's concurrent Windows call-log writes were serialized with a lock; the
  test now also proves both pages and second-page text are exported. Production
  request concurrency was not changed.
- After the final synthetic-cell lineage refinement, the contour, processor,
  builder and renderer suites passed again: **74 passed**. Generated cells retain
  source table evidence, without inheriting a purported cell match score/order.
- Scoped Ruff and formatting checks passed for the new geometry module, core
  layout/schema/builder/export paths and changed regression tests. A broader
  changed-file comparison found **zero new Ruff diagnostics** and 77 unchanged
  legacy diagnostics in the older processor/schema files; no broad lint cleanup
  or rule suppression was introduced.
- Targeted `ty check` passed for layout, geometry, schema and document builder.
  `uv lock --check` and `git diff --check` passed.
- The additional environment-wide `uv pip check` reports an empty orphaned
  `.venv/Lib/site-packages/psutil-7.2.2.dist-info` directory predating this work.
  `psutil` is not in the project lock; the directory was left untouched. This
  environment warning is separate from the passing model probe and tests.

Existing unrelated working-tree changes were preserved. Restart an existing app
instance when its work is complete to load the new code and process-cached engine;
no running instance was restarted by this implementation.

## Completion verification (2026-09-27, local unreleased)

This completion pass keeps the official artifact revision/hashes, complete decode,
guide v2, provisional thresholds, whole-page Sol/medium request, and response schema.
It adds diagnostics and regression coverage; it does not claim calibrated model
accuracy. No commit, publication, deployment, launcher change or application restart
was performed. Existing unrelated work and historical saved conversions remain.

### Recorded diagnostics and compatibility

Pipeline `sol-layout-v3/v4` adds `reporting_policy=initial-final-geometry-diagnostics/v1`
to the existing fingerprinted decode, guide, matching, order, source, runtime and
fallback policies. Different policy fingerprints create different conversion IDs.
Actual GPU/model availability is not part of that identity; recovery alone never
invalidates a saved fallback conversion. Field-only retries continue to use saved
raw Markdown and metadata, without conversion or model preparation.

- `layout.page_runtime` still reports **initial reconciliation**: retained/eligible
  regions (`prior_region_count` is the existing eligible count), matched, Sol-only
  and V3-only counts. New optional `geometry_counts`, `sol_only_reasons` and
  `unmatched_v3_reasons` summarize actual ownership and association outcomes.
- `execution_providers` records the exercised CPU or mixed CUDA/CPU path.
  `cpu_fallback_stage=startup|inference` is latched with successful CPU fallback;
  startup includes initialization/health checks. It is distinct from
  `failure_stage=preparation|inference`, which describes **Sol fallback** after
  unavailable V3. No extra provider inspection occurs per page.
- `layout.final_counts` reports `final_visible_structure`: visible top-level
  blocks, processor-derived blocks, and unique visible source footprints by owner.
  A cross-page footprint counts on its source page. A multipart contour is one
  footprint, not several matches; assemblies can have multiple footprints.
- Generated annotation receipts count actual contour parts, rectangles and skips
  per zero-based source page. They are saved with GUI/selected annotated exports,
  separately from reconciliation and final source-footprint counts. API render-only
  responses do not pretend annotations were generated.
- Existing GUI captions and CLI output share a metadata-only summary. API and saved
  exports carry the structured diagnostics. Legacy missing values mean **not
  recorded**, not zero, unavailable hardware, or newly inferred provenance.
- Zero raw/retained detections, all candidates filtered, unusable geometry,
  incompatible classes, insufficient overlap, reserved associations and runtime
  failure have distinct evidence/reasons. Sol-only does not imply a detector miss.
  Split/merge and tie warnings still do not veto qualified one-to-one assignments.

Elapsed page analysis includes lock/queue waiting, decoding and any preparation or
fallback inside that call. Separate readiness preparation is excluded. Summing
page timings is neither document wall-clock time nor pure inference latency.

### Bounded native evaluation

Evidence is local and ignored under `conversion_results/layout-v3-verification/`:
source hashes, CPU/auto analyses with masks/contours, guide payloads, frozen
processed-export inputs, comparison receipts, PNG/PDF overlays and review sheets.
No private source content is copied into this tracked record.

One authorized whole-page Sol request was attempted using the existing credential
resolver and service. It failed with `GPT-6 Sol request failed: APIConnectionError`;
no further inference requests were made. An unauthenticated `/models` connectivity
check reached HTTP 401, which does not establish that a full image request works.
No endpoint/model/credential substitution was made. Classification, field extraction
and optional refinement were not called.

Existing saved artifacts contain **processed exports, not raw Sol responses**.
The local comparison therefore uses their visible blocks as explicitly labeled
replay inputs. It cannot recover already-hidden furniture or original segmentation.
The historical v2 reconciliation functions were isolated from Git HEAD and compared
with current reconciliation on identical frozen inputs and identical V3 detections;
the historical policy was not installed into production. This is not a controlled
comparison of old versus new Sol guides.

| Authorized input | Page, one-based | Retained / valid contours | Replayed visible blocks | v2 / current matches | Guide UTF-8 bytes |
| --- | --- | --- | --- | --- | --- |
| Amerigroup | 1 | 11 / 11 | 7 | 6 / 6 | 3,795 |
| Amerigroup | 2 | 6 / 6 | 6 | 3 / 3 | 2,044 |
| RealSolutions 1 | 2 | 18 / 18 | 16 | 4 / 9 | 6,187 |
| RealSolutions 1 | 3 | 25 / 25 | 18 | 12 / 12 | 8,542 |
| RealSolutions 2 | 1 | 13 / 13 | 16 | 4 / 6 | 4,740 |

Both explicit CPU and auto CUDA-priority sessions executed the hash-verified
artifact. Auto passed executed-CUDA and ScatterND-on-CPU checks. CPU retained
the same per-page counts, but retained evidence was **not bit-identical** across
providers; equal counts are not numerical or accuracy equivalence. The existing
four-Memcpy-node ORT performance warning remains visible.

Controlled CUDA-startup failure exercised a real CPU session. A second analysis
reused CPU; session creation attempts were exactly CUDA then CPU. Separately,
controlled failure of both provider constructors produced visible preparation-stage
Sol fallback on two replayed pages, with no guide and no per-page preparation
reprobe. These are labeled fault-injection checks, not observed hardware outages.

Qualitative review of all five input/overlay pairs found:

- All 63 replay input blocks survived reconciliation unchanged in HTML/type. Final
  exports drew 36 contour footprints and 27 Sol rectangles, with zero skips.
  The 37 unassigned V3 regions remained diagnostic evidence. This verifies replay
  preservation, not recovery of content absent from historical exports.
- Seven newly accepted pairs arose from Form/table compatibility and split/merge
  policy changes. No obvious cross-region swap was seen in the reviewed overlays,
  but no independently annotated association truth set exists. Higher match counts
  are not evidence of higher accuracy.
- Contours generally follow major text/table regions without an obvious global
  coordinate offset. Jagged table boundaries on the RealSolutions forms cross or
  under-cover content near lower rows. Valid geometry is not exact content coverage;
  original mask evidence remains available. Thresholds were not tuned on these pages.
- v2/current relative ordering was identical on these replay inputs. Global ordering
  across unmatched blocks and ties is exercised by offline regressions, not shown
  to improve reading order on this sample.
- Furniture-on/off replay exports were identical because the saved inputs had
  already omitted hidden furniture. Offline tests verify the actual visibility
  settings and V3-label ownership; fresh document completeness remains unverified.
- Real replay did not trigger new cross-page processor assemblies. Existing actual
  list/table/replacement and cross-page lineage regressions cover those paths.

BadgeCare pages 1–2 remain unavailable in scoped saved originals. These mostly flat,
occasionally skewed forms do not establish performance on warped/curved pages.
Fresh whole-page Sol guide behavior, model accuracy, threshold calibration,
worst-case payload costs, and performance/memory benchmarking remain open.

### Verification commands and results

The complete offline suite passed **443 tests, 1 skipped** (optional benchmark).
New regressions cover multirow mask/class/order association, actual 90°/270°
non-square PDF rendering and PDF overlays, detailed counters/reasons, every policy's
cache identity, and propagated processor defects. Existing API concurrency,
saved fallback reuse, field-only retry, visibility and lineage tests remain active.

```powershell
uv run --no-sync python -m pytest -q
uv run --no-sync python -m ruff check doclayout tests benchmarks examples convert.py convert_single.py doclayout_app.py doclayout_server.py --select F,E9
uv run --no-sync python -m ruff check doclayout/layout.py doclayout/layout_geometry.py doclayout/schema/layout.py doclayout/builders/document.py doclayout/ui/batch.py doclayout/ui/exports.py doclayout/exports.py doclayout/scripts/convert_single.py tests/test_layout_contours.py tests/test_layout_runtime.py tests/test_layout_prior.py tests/test_layout_readiness.py
uv run --no-sync python -m ruff format --check doclayout/layout.py doclayout/layout_geometry.py doclayout/schema/layout.py doclayout/builders/document.py doclayout/ui/batch.py doclayout/ui/exports.py doclayout/exports.py doclayout/scripts/convert.py doclayout/scripts/convert_single.py tests/test_layout_contours.py tests/test_layout_runtime.py tests/test_layout_prior.py tests/test_layout_readiness.py
uv run --no-sync python -m ty check doclayout/layout.py doclayout/layout_geometry.py doclayout/schema/layout.py doclayout/builders/document.py doclayout/ui/batch.py doclayout/exports.py doclayout/scripts/convert.py doclayout/scripts/convert_single.py
uv lock --check
git diff --check
```

Full-rule Ruff on `scripts/convert.py` still reports its existing broad-exception
boundary; the correctness gate passes. Including `ui/exports.py` in type checks
still reports its pre-existing optional `soup.body.decode_contents` access. Neither
finding was suppressed or used to justify unrelated cleanup.

The focused five-layout-suite plus CLI-export command also passed **192 tests**:

```powershell
uv run --no-sync python -m pytest tests/test_layout.py tests/test_layout_runtime.py tests/test_layout_prior.py tests/test_layout_readiness.py tests/test_layout_contours.py tests/test_cli_exports.py -q
```

The current source distribution and wheel were built into the ignored verification
directory with `uv build --out-dir conversion_results/layout-v3-verification/dist`.
Fresh base, GUI and server environments installed that wheel with constraints
exported from the existing frozen lock. All three passed `uv pip check` and isolated
runtime imports, including contour dependencies and pipeline-v4 packaged resources.
These are installation smoke checks, not deployment or another GPU accuracy test.

Files changed in this completion pass: the layout adapter/schema and document
builder; shared/UI exports and batch summary; file/folder and single CLI reporting;
the existing contour, runtime, prior and readiness tests; README, CHANGELOG,
architecture, configuration, usage, development and this integration record.
Earlier decode/processor changes and unrelated pre-existing changes were preserved.
Private evaluation receipts and built artifacts remain ignored local files.

Exact completion-pass paths (not the entire pre-existing working-tree diff):

- Runtime/reporting: `doclayout/layout.py`, `doclayout/schema/layout.py`,
  `doclayout/builders/document.py`, `doclayout/ui/batch.py`,
  `doclayout/ui/exports.py`, `doclayout/exports.py`,
  `doclayout/scripts/convert.py`, `doclayout/scripts/convert_single.py`.
- Existing regressions: `tests/test_layout_contours.py`,
  `tests/test_layout_runtime.py`, `tests/test_layout_prior.py`,
  `tests/test_layout_readiness.py`.
- Documentation: `README.md`, `CHANGELOG.md`, `docs/architecture.md`,
  `docs/configuration.md`, `docs/usage.md`, `docs/development.md`,
  `docs/layout-v3-plan.md`.

The final full-suite rerun passed **443 passed, 1 skipped in 61.04 seconds**.
Relative file links in all seven edited Markdown files and the new completion
anchor were checked locally. No live GPU test was added to ordinary CI.
