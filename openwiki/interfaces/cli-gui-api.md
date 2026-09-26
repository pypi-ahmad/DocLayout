---
type: Interface guide
title: CLI, GUI, and API interfaces
description: Entry point responsibilities, conversion outputs, GUI persistence, and authenticated HTTP limits.
tags: [cli, streamlit, fastapi, interfaces]
sources:
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-f8eb525c17b05d929e5c2c00
    resource: repo://doclayout/credentials.py
  - id: openwiki-source-3fc18d2b3bd86c90ce3a3ddd
    resource: repo://doclayout/field_store.py
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-dcc182883a6f92d01cba381f
    resource: repo://doclayout/scripts/app_pages/convert.py
  - id: openwiki-source-78143bbf8e0e918bf100317b
    resource: repo://doclayout/scripts/app_pages/review.py
  - id: openwiki-source-e4aa4d69e867cd141e316b1d
    resource: repo://doclayout/scripts/convert.py
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-ad6ebd9d60ed27110202975f
    resource: repo://doclayout/scripts/streamlit_app.py
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-05b015b57d1b77a3ae6023e9
    resource: repo://doclayout/ui/field_summary.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-abd31605405249fba84ec342
    resource: repo://tests/test_entrypoints.py
  - id: openwiki-source-51b6aa7d36018bd3566db002
    resource: repo://tests/test_field_summary.py
  - id: openwiki-source-ff268f9389aaadf9064c3be8
    resource: repo://tests/test_ui_browser.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# CLI, GUI, and API interfaces

DocLayout installs `doclayout`, `doclayout_single`, `doclayout_gui`, and `doclayout_server`. The file CLI can select standalone conversion exports or request `--all` to construct a complete bundle and ZIP from one converted document. Folder mode processes sorted files, optionally using worker processes, and reports individual failures. The legacy single-file command keeps its configured renderer path. Neither CLI runs business-field extraction automatically.

The Streamlit app has icon-free Convert documents and Extracted information sidebar buttons, with the active page highlighted. A single upload offers page selection; multiple uploads use all pages and up to three concurrent file jobs. The explicit run button starts conversion and downstream extraction. The GUI saves original bytes, raw Markdown, chunks, conversion exports, business JSON, and SQLite results. Browsing exports or saved review records does not repeat model work. The results page offers explicit extraction retry from saved Markdown and a JSON export retry that reads SQLite.

Extracted information presents grouped fields and service tables in Summary, with missing values hidden until requested. Source document links fields and PDF regions in both directions. Processing issues use readable field labels, while raw metadata stays under Technical details. Saved results can be selected across sessions, and multiple requests within one run have a separate selector.

The HTTP API exposes path-based `POST /doclayout` and multipart `POST /doclayout/upload` for conversion only. Its lifespan creates a shared service and reads a bearer token. The request guard authenticates non-GET/HEAD calls before request parsing, caps request bodies, and returns 429 with `Retry-After` while a conversion is active. Conversion runs in a cancellation-shielded worker thread so a disconnected caller does not free the busy slot early. Path access requires an existing dedicated `DOCLAYOUT_INPUT_ROOT`.

Successful HTTP responses include the chosen conversion output, base64 images, and metadata. Failure responses use HTTP codes and `detail`: validation 422, authentication 401, forbidden path 403, size limit 413, busy service 429, and conversion failure 500. The API tests exercise authenticated path/upload conversion and rejection of retired options.

Entrypoints share the converter and configuration parser but own different service lifetimes. The GUI owns persisted downstream records. CLI and HTTP output shapes remain conversion results.

All real conversion paths, including the Python converter, attempt V3 preparation before page conversion. The GUI shows “Preparing layout model…” for uncached work, then the actual CUDA/CPU state or a Sol fallback warning. Preparation runs off the UI thread once for the batch; file jobs share the engine. A failed preparation does not trigger a new download or warmup on each page. No GUI layout switch is exposed.

Normal V3 preparation or inference failure continues with Sol content, geometry, and order, recorded in output provenance. HTTP can therefore return a successful fallback conversion. The defensive 503 handler applies only if a layout exception escapes that boundary. Sol request and schema failures still fail the conversion. Saved field-only retries do not prepare V3 or reconvert pages.

## Related pages

- [Quickstart](../quickstart.md)
- [Field extraction](../workflows/field-extraction.md)
- [Rendering and exports](../outputs/rendering-and-exports.md)
