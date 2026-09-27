---
type: Guide
title: DocLayout quickstart
description: A task-based map of the current conversion system and its source-grounded wiki pages.
tags: [quickstart, navigation, doclayout]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-3a15c4c875a9f676af798b18
    resource: repo://doclayout/services/layout.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# DocLayout quickstart

DocLayout renders documents into page images, uses local PP-DocLayoutV3 for layout guidance, asks GPT-6 Sol to extract structured page content, and exports the resulting document. The package has CLI, Streamlit, and FastAPI entrypoints. Local V3 uses the pinned ONNX repository through PaddleOCR/PaddleX and ONNX Runtime. Start with the [system overview](architecture/system-overview.md) or follow a page through the [conversion workflow](workflows/document-conversion.md).

## Find the right page

- Input formats, page selection, and rendering: [input providers](integrations/input-providers.md).
- Model artifact, contours, reading order, matching, and fallback: [layout guidance and alignment](integrations/layout-guidance-and-alignment.md).
- Sol's whole-page structured response, optional HTML correction, and Luna chat: [Sol extraction and processing](integrations/openai-processing.md).
- Blocks, source bindings, coordinates, and protected layout: [document model](concepts/document-model.md).
- CLI flags, GUI flow, API routes, and error responses: [interfaces](interfaces/cli-gui-api.md).
- Markdown, JSON, chunks, annotations, and output metadata: [rendering and exports](outputs/rendering-and-exports.md).
- Python extras, credentials, operator controls, and test modes: [configuration and verification](operations/configuration-and-testing.md).

## Local development check

The project uses uv and `pyproject.toml` with `uv.lock`. The package advertises Python 3.10+, but local V3 requires Python 3.11+ and the `layout` extra. On a supported Windows environment, sync the locked layout and development dependencies, then run focused offline checks:

```powershell
uv sync --locked --python 3.13 --group dev --extra layout
uv run --no-sync pytest -q tests/services/test_layout.py tests/builders/test_alignment.py tests/test_layout_wiring.py
```

Default tests replace the layout engine and block unexpected OpenAI calls. Live inference tests require explicit `--run-integration`; the CPU conversion smoke test sends a billable Sol request. Synthetic checks establish execution and data preservation, not production matching thresholds or extraction accuracy.
