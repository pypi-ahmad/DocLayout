---
type: operations guide
title: Configuration, Development, and Testing
description: How DocLayout separates runtime settings, converter options, dependency extras, offline tests, live integration checks, and benchmark runs.
tags: [configuration, development, testing, uv, benchmarks]
sources:
  - id: openwiki-source-442af0a8dbd7b70adaffd8e0
    resource: repo://benchmarks/inference.py
  - id: openwiki-source-af5b2fc4a0830cd3de40e530
    resource: repo://benchmarks/README.md
  - id: openwiki-source-2a4532afc0832c07abc2da10
    resource: repo://doclayout/config/crawler.py
  - id: openwiki-source-17de7dd389904e1fc58ef939
    resource: repo://doclayout/config/parser.py
  - id: openwiki-source-1046cac1b7bea28ed9ad4c24
    resource: repo://doclayout/config/validation.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-a288c4d4a875a1308ca48472
    resource: repo://doclayout/settings.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-e44eab9a26f9187df819fc2a
    resource: repo://pytest.ini
  - id: openwiki-source-ae4e170e615cd619c9fd16d5
    resource: repo://tests/config/test_config.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
generated: { by: "codex", at: "2026-09-26T10:42:04.191Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:42:04.191Z
---

# Configuration, Development, and Testing

DocLayout uses three configuration layers with different ownership: environment-backed application settings, converter configuration assembled by `ConfigParser`, and install-time dependency extras. Keeping them distinct avoids passing credentials through document configuration or installing optional format/UI/server stacks unnecessarily.

## Runtime settings and credentials

`settings.py` defines application paths, output encoding, image format, font location, resource limits, layout device/cache, and log level. These settings use Pydantic Settings and may read `local.env`; API credentials are deliberately handled elsewhere by `openai_credentials()`, which reads the process environment or the launch folder's `.env`.

Do not put API keys or endpoint URLs in converter JSON. The configuration validator rejects retired credential and provider fields. Use `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` in the environment or `.env` instead.

## Converter configuration

`ConfigParser` receives CLI, GUI, or API-derived options. It:

- preserves explicit false and zero values;
- expands debug mode into concrete debug output flags;
- parses comma-separated page ranges into zero-based IDs;
- merges values from an optional JSON file;
- converts `disable_image_extraction` into `extract_images = false`;
- validates the final dictionary before constructing a converter;
- resolves renderer, processor, and converter class choices.

Configurable class attributes are declared with type annotations across builders, processors, converters, providers, renderers, and services. `ConfigCrawler` imports implementations, gathers inherited annotations and defaults, and accepts either a plain attribute name or a class-prefixed override. `assign_config()` then applies relevant values at construction time.

Retired model, OCR, hardware, and alternate-provider settings fail closed at every configuration boundary. Validation catches direct converter dictionaries, JSON configuration, class-prefixed forms, and unknown legacy CLI options. The error explains that every page uses GPT-6 Sol and that `use_llm` only enables extra refinement.

`DOCLAYOUT_ALIGNMENT_POLICY` is optional. Without it, V3 can guide Sol but Sol geometry and order remain. A configured policy must supply all five evaluated matching values; partial or invalid values fail before inference. `DOCLAYOUT_LAYOUT_DEVICE` accepts `auto`, `cpu`, or `cuda`, and the layout cache defaults to ignored `.cache/layout`. These operator controls are not HTTP request options. Runtime V3 failures fall back to Sol with diagnostics; invalid policy, guide size, or downstream source-layout violations abort conversion.

## Dependency groups

The base installation includes PDF/image rendering, the OpenAI client, schema/rendering libraries, and the Click CLI. Optional extras add narrowly scoped surfaces:

- `full`: DOCX, XLSX, PPTX, EPUB, and WeasyPrint conversion dependencies.
- `gui`: Streamlit.
- `server`: FastAPI, multipart uploads, and Uvicorn.
- `layout`: pinned PaddleOCR/PaddleX, Hugging Face Hub, and ONNX Runtime GPU package, which can also execute on CPU (Python 3.11+).
- development group: all interface dependencies plus pytest, Playwright, Ruff, ty, pre-commit, and HTTP test support.

The package declares Python `>=3.10,<4`; the layout extra requires 3.11+. The documented Windows layout setup uses Python 3.13. Hatchling builds the package, and `uv.lock` is the reproducible dependency source for `uv sync`.

## Local development checks

From the repository root, the documented baseline is:

```powershell
uv sync --locked --python 3.13 --group dev --extra full --extra layout
uv run --no-sync python -m pytest
uv run --no-sync python -m ruff check doclayout tests benchmarks examples convert.py convert_single.py doclayout_app.py doclayout_server.py --select F,E9
uv lock --check
git diff --check
```

The test suite is rooted at `tests/` and declares `cpu`, `config`, and `integration` markers. Most tests use generated PDF/image fixtures plus a deterministic extraction service that returns schema-shaped page results. An autouse fixture blocks real Responses API parse and create calls outside integration tests, so an accidental network request fails immediately.

The tests cover provider geometry and normalization, structured extraction validation, layout cache/device behavior with a fake engine, deterministic alignment, processor invariants, renderers, export containment and collisions, credentials, usage accounting, CLI/API entrypoints, Streamlit session behavior, and an offline browser workflow. Synthetic matching values in fixtures are not production recommendations. Optional format tests may need the `full` dependencies; the browser test also needs Playwright's browser installation.

## Live checks and evidence limits

Tests marked `integration` are skipped unless `--run-integration` is passed. They are explicitly billable GPT-6 Sol checks and require configured credentials. Offline passing tests establish local control flow, schemas, sanitization, state invalidation, output shapes, and failure behavior with mocked extraction. They do not establish current API access, model quality, latency, or real-document accuracy.

Run live tests deliberately:

```powershell
uv run pytest --run-integration
```

## Benchmark harness

The benchmark tools run DocLayout against a separately obtained local olmOCR-bench dataset. `benchmarks/inference.py` extracts pages and records Markdown plus latency/failure data; `postprocess.py` and `summarize.py` prepare and aggregate results. The harness is billable, uses GPT-6 Sol and the converter's V3 attempt, defaults to one worker with no extra refinement, skips existing outputs larger than 10 bytes, and reports a nonzero exit when any request fails.

Benchmark timing includes layout startup/inference, remote API latency, and rendering. It cannot isolate local GPU performance. Its latency JSONL does not store layout provider or alignment diagnostics; use a normal metadata export for that. Results apply only to the evaluated files. Competitor scripts are independent adapters and do not change DocLayout's runtime pipeline.

## Related pages

- [Quickstart](../quickstart.md)
- [Input Providers and Normalization](../integrations/input-providers.md)
- [Layout Guidance and Alignment](../integrations/layout-guidance-and-alignment.md)
- [OpenAI Extraction and Refinement](../integrations/openai-processing.md)
- [CLI, GUI, and API Interfaces](../interfaces/cli-gui-api.md)
