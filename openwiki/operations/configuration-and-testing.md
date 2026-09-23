---
type: operations guide
title: Configuration, Development, and Testing
description: How DocLayout separates runtime settings, converter options, dependency extras, offline tests, live integration checks, and benchmark runs.
tags: [configuration, development, testing, uv, benchmarks]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-af5b2fc4a0830cd3de40e530
    resource: repo://benchmarks/README.md
  - id: openwiki-source-2a4532afc0832c07abc2da10
    resource: repo://doclayout/config/crawler.py
  - id: openwiki-source-17de7dd389904e1fc58ef939
    resource: repo://doclayout/config/parser.py
  - id: openwiki-source-1046cac1b7bea28ed9ad4c24
    resource: repo://doclayout/config/validation.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-e44eab9a26f9187df819fc2a
    resource: repo://pytest.ini
  - id: openwiki-source-ae4e170e615cd619c9fd16d5
    resource: repo://tests/config/test_config.py
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# Configuration, Development, and Testing

DocLayout uses three configuration layers with different ownership: environment-backed application settings, converter configuration assembled by `ConfigParser`, and install-time dependency extras. Keeping them distinct avoids passing credentials through document configuration or installing optional format/UI/server stacks unnecessarily.

## Runtime settings and credentials

`settings.py` defines application paths, output encoding, image format, font location, artifact URL, and log level. These settings use Pydantic Settings and may read `local.env`; API credentials are deliberately handled elsewhere by `openai_credentials()`, which reads the process environment or the launch folder's `.env`.

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

## Dependency groups

The base installation includes PDF/image rendering, the OpenAI client, schema/rendering libraries, and the Click CLI. Optional extras add narrowly scoped surfaces:

- `full`: DOCX, XLSX, PPTX, EPUB, and WeasyPrint conversion dependencies.
- `gui`: Streamlit.
- `server`: FastAPI, multipart uploads, and Uvicorn.
- development group: all interface dependencies plus pytest, Playwright, Ruff, ty, pre-commit, and HTTP test support.

The project requires Python 3.10 through 3.13 and uses Hatchling for packaging. The lockfile is the reproducible dependency source for `uv sync`.

## Local development checks

From the repository root, the documented baseline is:

```powershell
uv sync
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest
```

The test suite is rooted at `tests/` and declares `cpu`, `config`, and `integration` markers. Most tests use generated PDF/image fixtures plus a deterministic extraction service that returns schema-shaped page results. An autouse fixture blocks real Responses API parse and create calls outside integration tests, so an accidental network request fails immediately.

The tests cover provider geometry and normalization, structured extraction validation, processor behavior, renderers, export containment and collisions, credentials, usage accounting, CLI/API entrypoints, Streamlit session behavior, and an offline browser workflow. Optional format tests may need the `full` dependencies; the browser test also needs Playwright's browser installation.

## Live checks and evidence limits

Tests marked `integration` are skipped unless `--run-integration` is passed. They are explicitly billable GPT-6 Sol checks and require configured credentials. Offline passing tests establish local control flow, schemas, sanitization, state invalidation, output shapes, and failure behavior with mocked extraction. They do not establish current API access, model quality, latency, or real-document accuracy.

Run live tests deliberately:

```powershell
uv run pytest --run-integration
```

## Benchmark harness

The benchmark tools run DocLayout against a separately obtained local olmOCR-bench dataset. `benchmarks/inference.py` extracts pages and records Markdown plus latency/failure data; `postprocess.py` and `summarize.py` prepare and aggregate results. The harness is billable, uses GPT-6 Sol, defaults to one worker with no extra refinement, skips existing nonempty outputs, and reports a nonzero exit when any request fails.

Benchmark timing includes remote API latency and rendering. Results apply only to the evaluated files and cannot measure local GPU performance. Competitor scripts are independent adapters and do not change DocLayout's runtime pipeline.

## Related pages

- [Quickstart](../quickstart.md)
- [Input Providers and Normalization](../integrations/input-providers.md)
- [OpenAI Extraction and Refinement](../integrations/openai-processing.md)
- [CLI, GUI, and API Interfaces](../interfaces/cli-gui-api.md)
