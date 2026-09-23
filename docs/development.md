# Developing DocLayout

[Back to README](../README.md) · [Architecture](architecture.md) · [Configuration](configuration.md)

## Environment

Use PowerShell and uv from the repository root. The package declares Python
`>=3.10,<4`; the recorded Windows checks used Python 3.14.
The checks did not cover every supported Python version.

```powershell
uv sync --locked --group dev --extra full
uv run playwright install chromium --only-shell
```

The `dev` group supplies GUI, API, test, and development tools. The `full` extra
adds Office/HTML/EPUB converters. Their native library requirements are covered
in [installation](usage.md#installation). An ordinary wheel or pip install does
not install dependency groups. Keep `pyproject.toml` and `uv.lock` together when
changing dependencies; use `uv add` and `uv remove` without unrelated upgrades.

Stop processes using this project's environment before an exact sync removes
packages: Windows can lock loaded `.pyd` files. If an application must remain
running, `uv sync --locked --group dev --extra full --inexact` retains extra
packages. To check that removed dependencies are no longer required, run tests
in a fresh environment. An inexact sync retains
packages that could hide a missing dependency.

## Run the application

Use the [browser workbench](usage.md#browser-workbench),
[CLI](usage.md#command-line-conversion), or [HTTP API](usage.md#http-api)
instructions. Configure credentials through the
[process environment](configuration.md#credentials-and-environment).
The Windows launcher disables file watching, so restart after changing code or
prompt resources. Model calls incur endpoint charges.

## Offline checks

```powershell
uv run --no-sync pytest
uv run --no-sync ruff check doclayout tests benchmarks examples convert.py convert_single.py doclayout_app.py doclayout_server.py --select F,E9
uv lock --check
git diff --check
```

Sync first, then use `--no-sync` to test that environment without
changing its installed packages. Default tests block unrequested OpenAI calls.
They cover providers, structured extraction contracts, rendering, configuration,
API requests, GUI state, chat validation, prompt fingerprints, and exports.
The browser test uses a real browser and local Streamlit process with mocked
extraction; it verifies clipboard/download behavior and avoids repeated OCR.

Run the relevant subset while developing, for example:

```powershell
uv run --no-sync pytest tests/config tests/services tests/test_chat_prompts.py
uv run --no-sync pytest tests/test_ui.py tests/test_ui_browser.py
```

Use the Ruff correctness checks above as the baseline. The repository's
pre-commit configuration also runs autofixes and formatting, using its own pinned
Ruff version. Review those changes, especially around prompt literals. An
unrelated patch does not need broad formatting changes. When you run focused type checks,
report the paths checked; their results apply only to that subset.

## Live evaluation

Live tests make billable requests and run only when explicitly selected:

```powershell
uv run --no-sync pytest tests/converters/test_olmocr_bench.py --run-integration
```

See the [benchmark guide](../benchmarks/README.md) for harness options,
[fixture provenance](../tests/data/olmocr_bench/README.md) for included data, and
[validation report](gpt6-validation.md) for dated results and known failures.
Offline test success does not establish model accuracy or endpoint availability.
The live fixture suite may fail on the recorded header/footer limitation or
other model variation.

## Build and package checks

```powershell
uv build
```

Inspect the generated wheel and source distribution for package code, all four
Markdown prompt resources, `LICENSE`, and `NOTICE`. Local credentials, generated
outputs, indexes, and environments must not enter distribution artifacts.

To smoke-test the installed wheel, create a separate environment outside the
checkout and install the freshly built wheel there. Run checks from outside the
repository so source imports cannot hide missing package files. Verify:

- `doclayout` and `doclayout_single` help commands;
- the GUI/API entry-point imports after installing their required dependencies;
- resource loading for all four prompts;
- dependency consistency with `uv pip check --python <environment-python>`.

See [package installation](usage.md#installing-the-application-package) for
installation commands and dependency distinctions. Builds do not publish a
release; the current package version alone does not show whether a PyPI release exists.

## Preserve extraction behavior

Keep UI/export organization separate from extraction and refinement changes.
The [architecture guide](architecture.md#prompts-and-schemas) maps prompt resources
and explains their loading. During refactors, preserve their bytes, whitespace,
and placeholders, including refinement prompts embedded in Python. Do not update
fingerprint expectations merely to make an unintended prompt change pass.

Evaluate intentional prompt changes separately, and state which documents
the evaluation covers and where its results are limited. Compare extraction
output, tables, reading order, and formatting where affected; report mocked and
live checks separately.

Classes can be used through configuration discovery, schema registration,
framework callbacks, and public imports. Check those paths before removing code.
Providers supply page rendering, bounds, references, and page selection; the
builder creates structured blocks from model responses. Use current base classes
and implementations when extending the app. The old provider-line and page-line
merging interfaces are retired; see [compatibility changes](../CHANGELOG.md#unreleased).

## Documentation ownership

| Document | Owns |
| --- | --- |
| README | Overview, quick start, navigation, project attribution |
| Usage | Installation and GUI/CLI/Python/API workflows, troubleshooting |
| Configuration | Defaults, limits, input mechanisms, precedence, supported controls |
| Architecture | Data flow, responsibilities, state, prompt locations |
| Development | Setup, checks, builds, extension and change practices |
| Changelog | Changes and compatibility history |
| Validation | Dated observations and verification limits |
| Benchmark/example/fixture guides | Their specific workflows and provenance |

Link to the guide responsible for a topic to avoid duplicating its tables or
procedures. Update the changelog's Unreleased section for relevant changes and preserve historical
measurements as dated evidence. Check relative links, anchors, and executable
examples without making live requests unless that evaluation is intended.
