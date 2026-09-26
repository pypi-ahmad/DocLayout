# DocLayout architecture

[Back to README](../README.md) · [Configuration](configuration.md) · [Development](development.md)

## Data flow

The local unreleased pipeline attempts PP-DocLayoutV3 on each rendered page,
then sends the same whole image to Sol with a compact `given_layout` prior.
Validated Sol blocks are matched conservatively to V3 geometry and order before
existing processors run. If V3 fails, Sol receives the image without the prior.
See the [layout integration record](layout-v3-plan.md) for source locations,
the exact matching rules, and dated runtime evidence.

### Interactive architecture and workflow diagrams

These standalone HTML diagrams show the architecture and workflows:

- [System architecture](diagrams/doclayout-architecture.html) (`architecture`): Shared conversion, GUI-only Sol field extraction, optional Luna classification, local persistence, and review.
- [Conversion workflow](diagrams/doclayout-workflow.html) (`workflow`): Current V3 prior, whole-page Sol request, block matching, and export path.
- [Chat verification sequence](diagrams/doclayout-sequence.html) (`sequence`): Grounded Luna chat request, deterministic local quote check, and audit scoring.
- [Data flow](diagrams/doclayout-dataflow.html) (`dataflow`): Page images and layout priors feed Sol; validated blocks feed local exports and document chat.
- [Processing lifecycle](diagrams/doclayout-lifecycle.html) (`lifecycle`): Layout failure continues through Sol; Sol request/schema failures terminate conversion.


## Extraction

Providers handle input formats. Office, HTML, and EPUB inputs become temporary
PDFs. The GUI keeps the prepared PDF bytes in session memory so preview and
extraction can reuse them.

The document builder renders each selected page at 192 DPI by default. PDFium
renders pages one at a time. A process-shared, batch-one V3 engine analyzes each
image, then the page worker sends that same whole image and the layout prior for Sol extraction
(without a prior when V3 fails);
the shared Sol service permits at most three concurrent requests per process.
Every selected page goes through image extraction, including pages with embedded
PDF text.

Before provider-backed conversion begins, the shared `PdfConverter.build_document`
gate calls idempotent `LayoutEngine.prepare()`. First preparation resolves the
official pinned ONNX artifact, verifies its files, and exercises a synthetic RGB
warm-up through the same output validation and provider-selection path. Warm-up
detections are discarded. Ready engines do no additional warm-up. GUI, file/folder
CLI, legacy single-file CLI, Python Pdf/OCR/Table converters and HTTP routes share
this gate. Importing modules or creating API clients does not load weights.

Sol returns ordered blocks with type, HTML, and estimated bounds normalized
to 0 to 1000. Pydantic validation rejects invalid geometry and inconsistent blank
pages. The app sanitizes HTML and reconciles confident, unambiguous V3 matches
into page-space boxes and partial order, retaining Sol-only text and geometry
otherwise. Unmatched V3 regions are metadata only, never duplicate text. Structure
processors then prepare the document for rendering. Optional refinement uses the
same Sol service. If refinement fails, the app keeps the extracted content and
records errors. A page extraction failure aborts the document.

Reconciliation preserves every validated Sol block's HTML and semantic type.
Accepted one-to-one matches use V3 rectangles. Rejected matches, including ties
and split/merge ambiguity, retain Sol geometry with `sol_only` provenance.
V3 can reorder only contiguous matched runs; Sol-only blocks anchor their positions.
The matcher cannot recognize every incorrect detection, and its thresholds are
not calibrated accuracy guarantees. Later processors can group, merge, relabel,
or hide blocks, including headers/footers; final metadata and renderers use that
processed structure rather than the initial detection list.

## Rendering and output ownership

The GUI builds one document, then renders Markdown, hierarchical JSON, and flat
chunks from it. Local code generates styled HTML from the resulting Markdown,
draws estimated boxes on copies of source images, creates a raster PDF, and
assembles the ZIP. These operations do not call a model.

The file command builds one document and uses the same Markdown-to-HTML,
annotation, and ZIP helpers as the GUI. It renders the selected representations
locally, with no extra inference for additional formats. File exports use UTF-8;
Markdown includes its crops, and HTML embeds them.

Folder conversion, the legacy single-file command, and the API select one
renderer. Their HTML comes from document blocks. Legacy CLI output has separate
metadata; the API returns metadata alongside the serialized output. The new file
command writes a separate metadata file only when selected, while its JSON and
chunks representations include metadata.

The document model stores pages, blocks, reading order, images, and metadata.
It also carries reported extraction and refinement usage into rendered metadata.
Local code prices that usage at the configured rates. Chat keeps a separate
usage record, and the GUI adds both models' costs across the browser session.
Geometry is estimated. The app does not provide character positions or calibrated
confidence scores. Rendering depends on the extracted blocks and subsequent
processing.

## Frontend state and chat

Run DocLayout is the only UI action that triggers page extraction. Results belong
to the current upload and settings; changing either clears results and chat.
Preview, raw/rendered switching, clipboard actions, and downloads reuse the
completed result. Conversion views and chat use session state. The field workflow
also saves originals, prepared previews, raw Markdown, chunks, conversion ZIPs,
and extraction runs locally. Extracted information can reopen those runs after restart.

The GUI queues all uploads with three active file jobs. Multiple uploads use all
pages; one upload retains page selection. A process-wide PDFium lock protects local
rendering, and the Sol service permits three page requests at once. V3 inference
is serialized independently of API requests and needs local model files and
memory. If layout remains unavailable after provider selection, conversion uses
whole-page Sol with explicit fallback provenance. Batch preflight checks existing conversion identities first.
Only a Run needing new conversion prepares the engine, before file jobs start;
cached-only batches and saved field retries skip preparation. Preparation runs in
a worker; the Streamlit thread displays “Preparing layout model…”, then the actual
“PP-DocLayoutV3 · CUDA” or “PP-DocLayoutV3 · CPU” state. Failed preparation shows
“Sol fallback · V3 unavailable” and file jobs continue without per-page reprobes.
Explicit Run needing new conversion may retry; passive
reruns do not. There is no layout toggle.

CUDA readiness means successful execution with verified CUDA kernels, not that
every node runs on GPU. `auto` falls back to working CPU; explicit `cuda` rejects
a failed CUDA engine without substituting CPU. Conversion then falls back to Sol.
The engine's reentrant lock serializes preparation and inference. HTTP retains
its authentication/admission checks. GUI, CLI, HTTP and library conversion catch
layout preparation/inference errors and continue with Sol. Direct low-level engine
callers still receive `LayoutModelUnavailable`. Sol errors and invalid structured
responses are not caught by the layout fallback boundary.

V3 returns rectangles, masks, class IDs/scores and model order keys. It does not
transcribe text or supply raw polygon vertices. The four-point document geometry
and annotations remain rectangular; masks and original detections remain in the
audit. Existing final block metadata reflects later processor grouping/order.
The result caption summarizes stored initial region/match counts and summed page
analysis time, including queue wait. It is not document wall-clock time.
The model's order key is retained; `observed_rank` is explicitly a derived sort.

Chat uses a separate Luna client and token usage record. The draft schema contains
statements and supporting page quotes. The application checks that each quote
exists in the identified page text after whitespace normalization, validates
answer length/style, and requests independent verification. Only approved
answers receive page citations generated by the app. Mistakes can still pass
these checks.

## Downstream classification and fields

Only the GUI batch workflow automatically invokes business-field extraction.
CLI/library conversion and HTTP conversion do not create field records. The batch
layer snapshots raw Markdown before export image renaming and passes that text to
Sol/medium for extraction. Classification remains Luna/medium when enabled.
Images and chunks are not sent to either downstream model stage.

Classification is disabled by default. When enabled with category definitions and
one target, it returns strict JSON with a category, score, ambiguity flag, enum
reason, and at most one exact quote. Assignment requires score >= 0.75, reason
`matched`, and verified evidence. Accepted non-target categories skip extraction;
unknown, ambiguous, unsupported, or low-score results fall out with local reasons.

One logical field request extracts all fields and distinct authorization requests.
Local code checks source quotes and maps unique matching blocks to existing PDF
coordinates. Missing or ambiguous mappings require review. Neither schema validation
nor quote matching establishes semantic accuracy.

SQLite stores definition snapshots, document manifests, run results, and a stable
ten-column extraction table with JSON business fields. JSON export retries make no
model calls. Field retries use saved Markdown without reconversion. Matching document
and definition fingerprints reuse existing runs, including review/failure outcomes;
explicit retry requests new extraction. See the [field guide](field-extraction.md).

## Prompts and schemas

| Resource | Purpose |
| --- | --- |
| `doclayout/prompts/system.md` | Shared Sol instructions |
| `doclayout/prompts/extraction.md` | Whole-page extraction instructions |
| `doclayout/prompts/chat-answer.md` | Document-grounded chat draft |
| `doclayout/prompts/chat-verify.md` | Independent chat verification |
| `doclayout/prompts/fields/extraction.md` | Authorization fields and evidence instructions |
| `doclayout/prompts/fields/extraction.schema.json` | Business fields and strict response envelope |
| `doclayout/prompts/fields/classification.md` | Unconfigured category template; activation is separate |
| `doclayout/processors/llm/` | Refinement prompt strings still embedded in Python |

Conversion and chat Markdown resources are loaded when their modules are imported using
`importlib.resources`. Restart the application after editing them. They are
included in the built package. `.gitattributes` preserves their bytes, and tests
check prompt fingerprints against the original strings. See [prompt-change practices](development.md#preserve-extraction-behavior)
before editing prompt content or its fingerprint expectations.

Conversion/chat schemas and request logic remain in Python. The downstream business
schema lives in JSON; field definitions are loaded and hashed for each explicit run.

## Code map and extension boundaries

| Package | Responsibility |
| --- | --- |
| `providers` | Input-format preparation and page rendering |
| `builders` | Document creation and structural relationships |
| `schema` | Pages, blocks, polygons, extraction validation |
| `processors` | Document processing and optional refinement |
| `renderers` | Markdown, HTML, hierarchical/flat JSON representations |
| `services` | Shared Sol client and request accounting |
| `layout.py` | Pinned ONNX runtime, provider checks, Sol fallback, matching and provenance |
| `ui` | Session helpers, exports, clipboard, chat, batch jobs, field review |
| `fields.py`, `field_store.py` | Markdown extraction, classification, evidence checks, SQLite/JSON persistence |
| `scripts` | CLI, Streamlit, and HTTP entry points |
| `config` | Configuration parsing, discovery, and retired-option rejection |

See [development practices](development.md#preserve-extraction-behavior) for
extension checks and safe changes to extraction, rendering, and prompts.
[Configuration](configuration.md) owns defaults and controls;
[validation](gpt6-validation.md) records observed behavior and limitations.

### Provider extension contract

Providers supply prepared pages, rendering, bounds, references, and page
selection. The builder creates blocks from structured model responses.
The former provider-line and page-line merging interfaces have been removed;
see the [changelog](../CHANGELOG.md#210-2026-09-23) for the complete retirement list.
