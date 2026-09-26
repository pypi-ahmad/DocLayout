---
type: Quickstart
title: Quickstart
description: Set up this checkout, convert a file, open the GUI, authenticate HTTP requests, and find deeper guides.
tags: [quickstart, installation, cli, gui, api]
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-f8eb525c17b05d929e5c2c00
    resource: repo://doclayout/credentials.py
  - id: openwiki-source-15837773bd4113ac5b1f7ae1
    resource: repo://doclayout/fields.py
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-dcc182883a6f92d01cba381f
    resource: repo://doclayout/scripts/app_pages/convert.py
  - id: openwiki-source-78143bbf8e0e918bf100317b
    resource: repo://doclayout/scripts/app_pages/review.py
  - id: openwiki-source-60a85b3abffa8ceadae5f4cd
    resource: repo://doclayout/scripts/clear_gui_port.ps1
  - id: openwiki-source-e4aa4d69e867cd141e316b1d
    resource: repo://doclayout/scripts/convert.py
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-ad6ebd9d60ed27110202975f
    resource: repo://doclayout/scripts/streamlit_app.py
  - id: openwiki-source-a288c4d4a875a1308ca48472
    resource: repo://doclayout/settings.py
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-e7faa3ddaca50993ae19c88a
    resource: repo://launch.cmd
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-e44eab9a26f9187df819fc2a
    resource: repo://pytest.ini
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-154e6a78b00ef865edbb429b
    resource: repo://tests/test_cli_exports.py
  - id: openwiki-source-abd31605405249fba84ec342
    resource: repo://tests/test_entrypoints.py
  - id: openwiki-source-97c2d91c6ec415fd43007ed6
    resource: repo://tests/test_fields.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# Quickstart

DocLayout sends selected page images to GPT-6 Sol and produces structured Markdown plus other conversion exports. The Streamlit GUI can then extract business fields from raw Markdown with GPT-6 Sol at medium reasoning effort. Both stages require an endpoint that supports the configured model and request formats.

## Set up this checkout

From a PowerShell terminal in the repository root:

```powershell
uv sync --locked --group dev --extra full
$env:OPENAI_API_KEY = "your-api-key"
```

The process environment takes precedence over `.env` in the launch folder. Keep real credentials out of the repository. The base package includes PDF and image conversion; `full` adds optional Office, HTML, and EPUB support, while the development group includes GUI, server, and test dependencies.

The current checkout also includes the PP-DocLayoutV3 ONNX runtime. On first conversion it resolves and verifies pinned model files in `cache/pp-doclayoutv3`, then exercises CUDA or CPU. `auto` tries CUDA and falls back to a working CPU session; a layout engine failure continues with Sol and records that fallback. The GUI reports preparation, actual device, or fallback status. Sol still supplies the whole-page transcription, including content V3 misses; V3 is a layout prior, not OCR text. See [configuration](operations/configuration-and-testing.md) for device, cache, offline, and exact-directory settings.

## Convert and review

```powershell
uv run doclayout input.pdf output --all
uv run doclayout_gui
```

The CLI command creates conversion exports and a ZIP from one Sol extraction per selected page. It does not automatically extract business fields. In the GUI, a single upload allows one-based inclusive page selection. Multiple uploads process all pages with up to three active file jobs. The explicit Run DocLayout action converts, saves artifacts, and extracts fields from raw Markdown. Choose the Extracted information sidebar button or View extracted information below a completed result to read saved fields and source regions. Summary presents the fields; Source document supports evidence inspection. More actions contains explicit downstream extraction and export retries.

On Windows, `launch.cmd` opens port 8471 and restarts a recognized DocLayout listener on that port. It asks before stopping another application. Restarting resets the browser session and in-progress work; saved results remain available.

Classification is off by default. The category template has no business definitions yet, so it adds no model call. To activate routing later, define categories and one target, then enable the process switch described in [field extraction](workflows/field-extraction.md). The accepted score gate is inclusive at 0.75.

## Local HTTP conversion

Configure `DOCLAYOUT_API_TOKEN` with at least 32 non-whitespace ASCII characters before starting the server. Conversion requests use `Authorization: Bearer <token>`. To permit path-based input, also set `DOCLAYOUT_INPUT_ROOT` to an existing dedicated directory. Multipart upload conversion works without that path root.

```powershell
uv run doclayout_server --host 127.0.0.1 --port 8000
```

The server exposes generated documentation at `http://127.0.0.1:8000/docs`. Its `POST /doclayout` and `POST /doclayout/upload` routes return conversion outputs only. Authentication, body limits, and single-active-conversion behavior are detailed in [interfaces](interfaces/cli-gui-api.md).

## Verify locally

```powershell
uv run --no-sync python -m pytest
```

Default tests are offline and block unexpected OpenAI calls. Live integration tests require explicit selection and may incur charges. Passing offline tests checks local contracts, not model accuracy or endpoint availability.

## Find the right page

| Task | Read |
|---|---|
| Understand components and ownership | [System overview](architecture/system-overview.md) |
| Follow one PDF to exports | [Document conversion](workflows/document-conversion.md) |
| Add a source format | [Input providers](integrations/input-providers.md) |
| Understand block identity and geometry | [Document model](concepts/document-model.md) |
| Work with Sol, Luna, chat, or usage | [OpenAI processing](integrations/openai-processing.md) |
| Change output formats or persistence | [Rendering and exports](outputs/rendering-and-exports.md) |
| Change routing, evidence, or retries | [Field extraction](workflows/field-extraction.md) |
| Configure and test the checkout | [Configuration and testing](operations/configuration-and-testing.md) |
