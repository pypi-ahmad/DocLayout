# Changelog

This changelog records published releases and unreleased checkout changes.
GitHub hosts release assets; PyPI publication is deferred.

## Unreleased

### Documentation

- Add a contributor runbook, first-day onboarding path, offline source tutorial,
  and Python docstring coverage audit. Document the core conversion, provider,
  export, and CLI interfaces without changing runtime behavior.
- Record the earlier local five-diagram Archify validation while retaining the
  later source-checked diagram artifacts already on `main`.

## 3.1.0 (2026-09-27)

### Compatibility

- Layout decoding now uses the pinned `PaddlePaddle/PP-DocLayoutV3_onnx` artifact
  directly. Its required runtime dependencies are in the base package rather than
  the former optional `layout` extra. First use may download verified weights.
- Accepted V3 regions can change geometry and reading order in new conversions.
  Pipeline `sol-layout-v3/v4` has a new conversion identity; saved results retain
  their original provenance and field-only retries do not reconvert PDFs.

### Changes

- Decode and retain V3 masks, class IDs, scores, boxes and raw order keys. Derive
  rendered-page contours using the documented PaddleX algorithm, with explicit
  contour-to-V3-rectangle and V3-to-Sol fallback reasons.
- Guide the existing whole-page Sol request with compact V3 regions. Deterministic
  one-to-one matching applies usable V3 geometry and relative order while keeping
  Sol text/HTML and every unmatched Sol block. Source footprints survive processing
  and appear in annotated images and PDFs; V3-only regions remain diagnostics.
- Keep CUDA auto-detection with CPU retry, sticky CPU fallback, and verified
  ScatterND CPU placement inside CUDA sessions. Preparation or inference failure
  leaves the whole-page Sol conversion visible, with per-page fallback provenance.
  Status surfaces distinguish initial matches from final visible geometry.
- Add GUI authorization-field extraction from saved raw Markdown with Sol/medium,
  source-quote checks, and local JSON/SQLite storage. Optional Luna/medium
  classification remains off by default with a 0.75 inclusive score gate.
  Multi-file uploads use three active jobs; saved field retries do not rerun
  PDF conversion. The extracted-information view links fields to PDF evidence.
- Synchronize maintained guides and OpenWiki, and extend offline layout and field
  regressions. The [dated verification record](docs/layout-v3-plan.md#completion-verification-2026-09-27-local-unreleased)
  identifies live-validation limits; passing tests alone does not establish model
  accuracy or fresh-machine GPU behavior.

## 3.0.0 (2026-09-26)

### Local layout with Sol fallback

- Attempt PP-DocLayoutV3 for GUI, CLI, API, PDF, and OCR conversion. Sol still
  transcribes the whole page and writes HTML, guided by bounded layout JSON.
- Use revision-pinned, hash-checked ONNX weights in an ignored cache and the
  optional `layout` dependency extra (Python 3.11+). Auto mode supports CPU
  fallback; explicit CUDA does not switch to CPU. V3 preparation/inference
  failures use full-image Sol extraction with visible diagnostics.
- Align validated Sol blocks before structure building. Preserve content in
  ambiguous split/merge cases and protect matched V3 rectangles and reading order
  through processing. Annotations draw rectangles, not segmentation masks.
- Show GUI preparation, actual device, and fallback status. Export layout metadata
  with model/revision, timings, detections, matching diagnostics, and region counts.
- Select `gui` and `layout` extras in the Windows launcher while preserving
  loopback binding. It stops a recognized listener on port 8471 before relaunching.

### Documentation

- Synchronize installation, conversion, API, development, benchmark, and deployment
  guides with V3 guidance and Sol fallback; update the layout diagrams.

## 2.1.1 (2026-09-24)

### Compatibility

- HTTP conversion now requires `DOCLAYOUT_API_TOKEN` and a bearer header. Filepath
  requests also require `DOCLAYOUT_INPUT_ROOT`. Errors use HTTP statuses and a
  `detail` field instead of HTTP 200 responses with `success: false`; API clients
  must update their authentication and error handling.

### Security and reliability

- Validate model table spans and expanded cell counts before rendering or
  refinement allocations, including merged HTML tables and direct callers.
- HTTP conversion now requires a separate bearer token. Server filepath access is
  disabled unless a dedicated input root is configured. Uploads and selected pages
  default to 200 MiB and 500 pages; conversion failures use HTTP error statuses.
- Added document, archive, image, and worksheet limits, embedded-only rendering
  resources, escaped spreadsheet text, and deterministic provider cleanup.
- GUI launchers bind loopback; `launch.cmd` refuses an occupied port without
  terminating its listener. See configuration for security and compatibility limits.

### Other updates

- Added a data flow image to the README and downloadable interactive data flow
  and system architecture diagrams to the architecture guide.
- Removed benchmark input files from Git tracking and package builds while
  retaining local copies. Added document/export ignore rules and optional local
  benchmark setup; tests collect without downloaded data.
- Added automatic launch-folder `.env` credentials for all entry points, with
  environment variables taking priority and one shared resolver for OCR and chat.
- Added estimated API costs at the supplied Sol/Luna rates, with a persistent
  browser-session total, CLI summaries, and token/cost metadata. Missing usage
  is flagged as partial, and reported usage survives failed extraction.
- CLI and GUI exports now use the original filename and a shared UTC timestamp
  per extraction, including ZIP entries, annotated pages, and linked crops.
- Folder conversion and `doclayout_single` use the same naming convention;
  `--skip_existing` recognizes both earlier and timestamped outputs.

## 2.1.0 (2026-09-23)

### Added

- `doclayout FILE OUTPUT_DIR` with selectable exports, `--all`, and a complete
  GUI-compatible ZIP, generated from one extraction per selected page.
- `gui` and `server` installation extras and base CLI support for HTML/MathML
  exports. The GUI launcher uses its installed Python interpreter.
- GitHub installation instructions for uv tool, manual clones, pip, uv pip,
  and versioned release wheels. PyPI publication is deferred.
- Offline CLI checks for output selection, overwrite behavior, failure handling,
  path validation, and GUI-equivalent HTML.
- Added a [configuration reference](docs/configuration.md) and
  [development guide](docs/development.md), with shared material moved out of
  other guides and replaced by links.

### Changed

- Updated documentation to match the current code and gave each topic a main
  guide. Historical validation measurements remain clearly labeled.
- Removed ten unused direct dependency declarations: `psutil`, `ftfy`,
  `jupyter`, `datasets`, `streamlit-ace`, `pytest-mock`, `apted`, `distance`,
  `lxml`, and `tabulate`. Retained dependency versions did not change; `lxml`
  remains a transitive dependency of optional document-format support.

### Removed

- Unused PDF text-layer table reconstruction, provider text utility, and image
  utility modules, plus the empty utility package initializer.
- Old frontend helpers `open_pdf`, `img_to_html`, `get_page_image`, and `page_count`.
- Provider-line interfaces `ProviderOutput`, `ProviderPageLines`,
  `get_page_lines`, and empty line storage.
- `PageGroup.merge_blocks`, its exclusive line-assignment methods/settings,
  unused `pdftext_page` cache, and unassigned deferred image loader.
- `sort_text_lines`, `Line.formatted_text`, `PolygonBox.center_distance`,
  `PolygonBox.fit_to_bounds`, `PromptData.additional_data`, and
  `Settings.DEBUG_DATA_FOLDER`.
- Unused dataset test helper, permanently skipped legacy ignore-text test,
  inactive filename/output-format markers, and unused mocker/Gemini test settings.

External extensions that use these removed interfaces must switch to current
providers and builders. Registered schema classes and configurable processors
remain available. Extraction and refinement prompt text was preserved; see
[cleanup verification](docs/gpt6-validation.md#cleanup-verification-2026-09-23).

## 2.0.0: Initial repository baseline (2026-09-23)

Package version 2.0.0 appears in the initial repository commit `038bb8c`.
This entry records that baseline without announcing a tag or package publication.

- DocLayout branding and a Streamlit document workbench with inclusive page
  selection, Markdown/raw views, HTML, estimated annotations, and copy/download/ZIP.
- GPT-6 Sol extraction and optional refinement, with GPT-6 Luna document chat
  using source-quote checks and independent verification.
- CLI, Python library, and local HTTP API, with document-format preparation
  through optional converters.
- Packaged Markdown prompts, offline/browser tests, bounded live evaluation
  fixtures, and the Windows launcher on port 8471.
- Apache-2.0 licensing, modification notices, and upstream attribution retained.

See [usage](docs/usage.md), [architecture](docs/architecture.md), and
[validation](docs/gpt6-validation.md) for behavior and verification limits.
