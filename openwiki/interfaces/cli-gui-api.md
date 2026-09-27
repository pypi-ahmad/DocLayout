---
type: Interface
title: CLI, GUI, and HTTP API
description: User entrypoints, export choices, operator layout controls, and conversion error surfaces.
tags: [cli, gui, api]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-e4aa4d69e867cd141e316b1d
    resource: repo://doclayout/scripts/convert.py
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-ad6ebd9d60ed27110202975f
    resource: repo://doclayout/scripts/streamlit_app.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-abd31605405249fba84ec342
    resource: repo://tests/test_entrypoints.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# CLI, GUI, and HTTP API

The package exposes `doclayout`, `doclayout_single`, `doclayout_gui`, and `doclayout_server`. `doclayout` converts a file to a chosen export set or processes a folder with worker processes. File exports include Markdown, HTML, hierarchical JSON, chunks, metadata, image crops, annotated pages, and a ZIP bundle. The file command validates output destinations and incompatible option combinations before conversion. Folder worker failures are reported per file. `doclayout_single` uses the shared converter with its selected renderer. See [rendering and exports](../outputs/rendering-and-exports.md).

The Streamlit workbench uploads an input, previews pages, and lets the user select pages, extra refinement, and header/footer visibility. A run validates the alignment policy before preparing the local V3 model. Preparation failure blocks extraction unless the operator enabled Sol fallback. The UI shows the actual device and fallback status, then exposes Markdown, HTML, annotations, JSON, chunks, and document chat from the completed result. The GUI launcher binds Streamlit to loopback.

The FastAPI server has authenticated `POST /doclayout` for a filepath under the configured input root and `POST /doclayout/upload` for a multipart file. Request fields are `page_range`, `use_llm`, `paginate_output`, and `output_format` (`markdown`, `json`, `html`, or `chunks`); the filepath route also requires `filepath`. Extra fields are rejected. Layout device, cache, alignment policy, and fallback are operator settings, not request fields. Successful responses include output, images, and metadata. A fatal `LayoutError` returns sanitized HTTP 503 with a safe error code; a successful explicitly permitted Sol fallback returns HTTP 200 with degraded-mode metadata. See [configuration and testing](../operations/configuration-and-testing.md).
