---
type: quickstart
title: Quickstart
description: Install DocLayout with uv, configure API access, run the CLI, GUI, or local API, and find the right architecture guide for deeper work.
tags: [quickstart, installation, uv, cli, gui, api]
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-70991026f1538e8215a8789e
    resource: repo://docs/development.md
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
generated: { by: "codex", at: "2026-09-26T10:42:04.191Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:42:04.191Z
---

# Quickstart

DocLayout converts PDFs, scans, images, and optional office/document formats into structured Markdown and related exports. Every selected page is sent to the configured OpenAI-compatible endpoint for GPT-6 Sol transcription. The converter also attempts local PP-DocLayoutV3 for layout guidance. GPU acceleration is optional; when V3 cannot run, Sol can still process the full page image and the result records fallback. Applying V3 boxes/order requires an evaluated alignment policy.

## 1. Set up the repository

For development on the current checkout:

```powershell
uv sync --locked --python 3.13 --group dev --extra full --extra layout
```

This installs the CLI, Streamlit GUI, FastAPI server, development tools, optional document converters, and the V3 runtime. The package declares Python `>=3.10,<4`; the `layout` extra requires 3.11+. The V3 model weights are downloaded to the ignored cache only when absent and verified before use. A base CLI install can still run with Sol fallback when local V3 dependencies are absent.

## 2. Configure API access

Set credentials in the terminal that will launch DocLayout:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
# Optional for a compatible custom endpoint:
$env:OPENAI_BASE_URL = "https://your-endpoint.example/v1"
```

You can instead copy `.env.example` to `.env` in the launch folder. Environment values take precedence per variable. Keep `.env` private and restart the application or terminal after changing credentials.

## 3. Convert a file

From this checkout:

```powershell
uv run --extra layout doclayout input.pdf output
```

The default writes timestamped Markdown and extracted image crops. To create the complete export set from the same extraction:

```powershell
uv run --extra layout doclayout input.pdf output --all
```

Useful variants include:

```powershell
uv run --extra layout doclayout input.pdf output --markdown --html
uv run --extra layout doclayout input.pdf output --json --chunks
uv run --extra layout doclayout input.pdf output --zip
uv run --extra layout doclayout input.pdf output --all --page_range 0,2-4
```

CLI and API page ranges are zero-based. Extra GPT-6 Sol refinement is optional; mandatory page extraction always runs.

## 4. Use another interface

Launch the Streamlit workbench:

```powershell
uv run --extra gui --extra layout doclayout_gui
```

It supports page previews, selected-page extraction, Markdown/HTML/JSON/chunk views, annotations, downloads, clipboard actions, cost estimates, and verified document chat. GUI page selectors are one-based and inclusive.

Launch the local API:

```powershell
uv run --extra server --extra layout doclayout_server --host 127.0.0.1 --port 8000
```

Set a separate `DOCLAYOUT_API_TOKEN` before launching the API, then open `http://127.0.0.1:8000/docs` for generated API documentation. Path-based requests at `POST /doclayout` also need `DOCLAYOUT_INPUT_ROOT`; multipart uploads use `POST /doclayout/upload`. Both require a bearer token. Layout runtime fallback can return a successful response with diagnostics; fatal layout errors return HTTP 503.

Convert a folder or use the legacy single-output command:

```powershell
uv run --extra layout doclayout documents --output_dir output --workers 1
uv run --extra layout doclayout_single input.pdf --output_dir output --output_format markdown
```

## 5. Run development checks

```powershell
uv run --no-sync python -m pytest
uv run --no-sync python -m ruff check doclayout tests benchmarks examples convert.py convert_single.py doclayout_app.py doclayout_server.py --select F,E9
uv lock --check
git diff --check
```

The default tests are offline and block unrequested OpenAI calls. Live integration checks are billable and require the explicit `--run-integration` option.

## Find the right page

| Task | Read |
|---|---|
| Understand the component boundaries | [System Overview](architecture/system-overview.md) |
| Trace one conversion in execution order | [Document Conversion Workflow](workflows/document-conversion.md) |
| Add or modify blocks and groups | [Document Model and Structure](concepts/document-model.md) |
| Add a source type or debug normalization | [Input Providers and Normalization](integrations/input-providers.md) |
| Work on extraction, refinements, chat, credentials, or cost | [OpenAI Extraction and Refinement](integrations/openai-processing.md) |
| Work on V3 inference, matching, device behavior, or fallback | [Layout Guidance and Alignment](integrations/layout-guidance-and-alignment.md) |
| Change Markdown, HTML, JSON, chunks, annotations, or ZIPs | [Rendering and Exports](outputs/rendering-and-exports.md) |
| Change CLI, GUI, or API behavior | [CLI, GUI, and API Interfaces](interfaces/cli-gui-api.md) |
| Configure the project or run tests/benchmarks | [Configuration, Development, and Testing](operations/configuration-and-testing.md) |

## Practical boundaries

Page images are sent to the configured endpoint. Document chat sends parsed page text and recent accepted conversation turns. Requests use `store=False`, but endpoint provider policies still apply. API use can incur charges, and V3/Sol regions and verified chat answers still require review for accuracy-sensitive work. No production matching thresholds are supplied by default.
