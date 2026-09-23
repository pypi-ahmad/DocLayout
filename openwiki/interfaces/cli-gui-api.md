---
type: interface guide
title: CLI, GUI, and API Interfaces
description: The responsibilities, state, lifecycle, and output behavior of DocLayout's command-line, Streamlit, and FastAPI entrypoints.
tags: [cli, streamlit, fastapi, interfaces, lifecycle]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-67bc4fcd658b5dbb5cb95cc0
    resource: repo://doclayout/scripts/convert_single.py
  - id: openwiki-source-e4aa4d69e867cd141e316b1d
    resource: repo://doclayout/scripts/convert.py
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-ad6ebd9d60ed27110202975f
    resource: repo://doclayout/scripts/streamlit_app.py
  - id: openwiki-source-852c65645159b1b6c9ad63af
    resource: repo://doclayout/ui/documents.py
  - id: openwiki-source-ff268f9389aaadf9064c3be8
    resource: repo://tests/test_ui_browser.py
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# CLI, GUI, and API Interfaces

DocLayout exposes the same conversion core through four installed commands. Each interface owns configuration translation and service lifetime, but they differ in persistence, concurrency, and how results are delivered.

| Command | Interface | Result path |
|---|---|---|
| `doclayout` | File export or folder batch CLI | Selected files, full bundle, or legacy renderer output |
| `doclayout_single` | Legacy single-file CLI | One configured renderer output in an output folder |
| `doclayout_gui` | Streamlit workbench | Session state, previews, downloads, clipboard, and document chat |
| `doclayout_server` | FastAPI service | JSON response containing output text, base64 images, and metadata |

## File and folder CLI

For a file input, `doclayout` requires a destination and supports individual export flags, `--all`, or the legacy `--output_format` option. These selection modes are mutually exclusive. It validates intended output paths before creating the API service or extracting the document, renders all requested formats from one document, writes them, prints an estimated cost, and closes the service in `finally`.

For a folder, the command sorts direct child files, optionally divides them into deterministic chunks, applies a maximum count, and processes them sequentially or in spawned worker processes. Each worker creates and closes its own service and can issue up to three API requests. A failed file is reported while remaining tasks continue; the command exits with a summary error if any document failed.

`doclayout_single` keeps the earlier configuration-driven behavior: it creates a service, runs one configured converter and renderer, saves the result, reports cost, and always closes the service.

## Streamlit workbench

The launcher checks for the `gui` extra and runs the packaged application headlessly with file watching disabled. The application caches model artifacts for the Streamlit process, while document and chat state live in `st.session_state`.

An upload is hashed from its bytes and filename. A new upload clears prior extraction, scope, preview, and chat state. `prepare_upload()` detects the provider, counts pages, and eagerly converts optional document formats into stored PDF bytes so later reruns do not repeat office-format normalization.

The extraction scope includes the upload hash, selected page range, refinement option, and header/footer option. Changing any part clears the result and chat without making another model call. Only the explicit **Run DocLayout** button extracts pages. The browser test verifies that switching tabs and downloading exports does not repeat extraction, and changing scope invalidates existing downloads before another run.

One conversion builds Markdown, hierarchical JSON, chunks, per-page chat text, annotations, HTML, and a ZIP. Debug artifacts are forced off and all temporary inputs remain inside a temporary directory. Pages with detected OCR errors or no text are omitted from chat context. Chat history and chat usage are cleared with the document scope and its requests are added to the session cost ledger.

## FastAPI service

The API lifespan creates one service artifact and one `asyncio.Lock`, then closes and removes both at shutdown. The lock serializes conversion because PDFium use and the surrounding conversion are not exposed concurrently through this process.

`POST /doclayout` accepts a strict JSON model with a filesystem path, page range, refinement flag, pagination flag, and one of four output formats. Unknown fields receive a 422 response. `POST /doclayout/upload` accepts the same fields as form values plus a file. It ignores the upload filename as a path, retains only its suffix, writes bytes under a fixed name in a temporary directory, and converts there.

Successful API responses contain `success`, the requested format, serialized output text, base64-encoded images, and renderer metadata. Conversion failures are returned as `success: false` with an error string, while malformed request fields use HTTP 422.

## Shared configuration and cleanup

All interfaces use `ConfigParser` to turn Click or request options into converter configuration, processor selection, renderer selection, page ranges, and output locations. Removed options are rejected rather than silently ignored.

CLI commands own short-lived service instances and close them in `finally`. The Streamlit process and API lifespan own long-lived artifacts. Individual converters use isolated configured service copies, so usage from one conversion does not leak into the next even when the underlying HTTP client is reused.

## Related pages

- [Quickstart](../quickstart.md)
- [Rendering and Exports](../outputs/rendering-and-exports.md)
- [OpenAI Extraction and Refinement](../integrations/openai-processing.md)
- [Configuration, Development, and Testing](../operations/configuration-and-testing.md)
