---
type: quickstart
title: Quickstart
description: Install DocLayout with uv, configure API access, run the CLI, GUI, or local API, and find the right architecture guide for deeper work.
tags: [quickstart, installation, uv, cli, gui, api]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# Quickstart

DocLayout converts PDFs, scans, images, and optional office/document formats into structured Markdown and related exports. Every selected page is sent to the configured OpenAI-compatible endpoint for GPT-6 Sol extraction; no local model or GPU is required.

## 1. Set up the repository

For development on the current checkout:

```powershell
uv sync --locked --group dev --extra full
```

This installs the CLI, Streamlit GUI, FastAPI server, development tools, and optional DOCX/XLSX/PPTX/HTML/EPUB converters. For only the base conversion CLI, install the package without extras. The project supports Python `>=3.10,<4`.

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
uv run doclayout input.pdf output
```

The default writes timestamped Markdown and extracted image crops. To create the complete export set from the same extraction:

```powershell
uv run doclayout input.pdf output --all
```

Useful variants include:

```powershell
uv run doclayout input.pdf output --markdown --html
uv run doclayout input.pdf output --json --chunks
uv run doclayout input.pdf output --zip
uv run doclayout input.pdf output --all --page_range 0,2-4
```

CLI and API page ranges are zero-based. Extra GPT-6 Sol refinement is optional; mandatory page extraction always runs.

## 4. Use another interface

Launch the Streamlit workbench:

```powershell
uv run doclayout_gui
```

It supports page previews, selected-page extraction, Markdown/HTML/JSON/chunk views, annotations, downloads, clipboard actions, cost estimates, and verified document chat. GUI page selectors are one-based and inclusive.

Launch the local API:

```powershell
uv run doclayout_server --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` for the generated API documentation. The server accepts path-based requests at `POST /doclayout` and multipart files at `POST /doclayout/upload`.

Convert a folder or use the legacy single-output command:

```powershell
uv run doclayout documents --output_dir output --workers 1
uv run doclayout_single input.pdf --output_dir output --output_format markdown
```

## 5. Run development checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
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
| Change Markdown, HTML, JSON, chunks, annotations, or ZIPs | [Rendering and Exports](outputs/rendering-and-exports.md) |
| Change CLI, GUI, or API behavior | [CLI, GUI, and API Interfaces](interfaces/cli-gui-api.md) |
| Configure the project or run tests/benchmarks | [Configuration, Development, and Testing](operations/configuration-and-testing.md) |

## Practical boundaries

Page images are sent to the configured endpoint. Document chat sends parsed page text and recent accepted conversation turns. Requests use `store=False`, but endpoint provider policies still apply. API use can incur charges, and model-estimated regions and verified chat answers still require review for accuracy-sensitive work.
