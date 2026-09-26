# Changelog

This changelog records published releases and unreleased checkout changes.
GitHub hosts release assets; PyPI publication is deferred.

## Unreleased

These changes are present in the working checkout; this entry does not establish
that they have been committed, pushed, or included in a release.

- Added explicit whole-page Sol fallback when V3 preparation or inference fails.
  Missing/rejected V3 matches retain Sol blocks and boxes; GUI/logs and saved
  per-page provenance report unavailable layout without invented device/order.
  New fingerprints include the fallback policy; historical artifacts and saved
  field-only retries remain unchanged.

- Assigned PP-DocLayoutV3's single ScatterND operation to CPU within CUDA sessions,
  with verified placement and fail-closed provider selection. Avoids the upstream
  CUDA duplicate-index warning path without hiding warnings or changing weights;
  new conversion identities record the execution policy.

- Added local PP-DocLayoutV3 ONNX analysis before whole-page Sol
  transcription across GUI, CLI, Python and HTTP conversion. Sol receives a
  compact layout prior; validated content/HTML is retained through conservative
  geometry/order matching, with unmatched detections kept as diagnostics.
- Added process-cached preparation before new conversion: verified first-run
  downloads, exercised CUDA detection with CPU fallback in `auto`, strict explicit
  `cuda` failure, and clear GUI preparing/actual-device/error states. Saved-only
  work avoids preparation; no layout toggle or launcher dependency change.
- Added layout provenance, initial region/match counts and page timing in result
  metadata, with rectangular annotations and separate raw masks. Pipeline-v2
  identity separates new conversions from historical saves. Accuracy improvement,
  polygon-accurate exports, speed and hardware fit are not established.

- Added GUI authorization-field extraction from completed raw Markdown with
  `gpt-6-sol` and medium reasoning, file-defined prompts/schema, source-quote
  checks, and local JSON/SQLite storage.
- Added multi-file uploads with three active file jobs, all-page batch processing,
  and a persistent Extracted information page with readable summaries and two-way PDF block highlighting.
- Added optional Luna/medium classification with compact strict JSON, enum reasons,
  one evidence quote, and an inclusive 0.75 score threshold. It remains disabled
  by default; category definitions and one extraction target are still required.
- Added saved-artifact reuse, explicit field retries without reconversion, and
  JSON-export retries without model calls. These downstream actions do not rerun
  PDF-to-Markdown conversion; the separate V3 integration above changes new conversions.
- Updated repository guides, generated documentation, and downstream docstrings.
- Synchronized current documentation with V3/Sol fallback, engine-versus-conversion
  failure behavior, cache reuse, and rectangular export limits. Historical live
  observations remain dated; documentation checks do not establish accuracy gains.
- Added icon-free sidebar navigation buttons with an active-page indicator.
- Extraction prioritizes the main authorization form, uses requested service dates,
  and avoids duplicate evidence warnings. Model and reasoning effort are included
  in definition snapshots and cache fingerprints; historical runs remain unchanged.
- The Windows launcher restarts an existing DocLayout listener on port 8471.
  Other applications require confirmation before termination. Saved results remain;
  browser sessions and in-progress work do not survive a restart.

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
