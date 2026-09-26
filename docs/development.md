# Developing DocLayout

[Back to README](../README.md) · [Architecture](architecture.md) · [Configuration](configuration.md)

## Environment

Use PowerShell and uv from the repository root. The package declares Python
`>=3.11,<4`; the recorded Windows checks used Python 3.14.
The checks did not cover every supported Python version.

```powershell
uv sync --locked --group dev --extra full
uv run playwright install chromium --only-shell
```

The `dev` group supplies GUI, API, test, and development tools. The `full` extra
adds Office/HTML/EPUB converters; see their [native library requirements](usage.md#installation).
End-user installs can use the `gui` or `server` extras. Wheel and pip installs do
not include the development group. Keep `pyproject.toml` and `uv.lock` together
when changing dependencies, and avoid unrelated upgrades.

Stop processes using this project's environment before an exact sync removes
packages: Windows can lock loaded `.pyd` files. If an application must remain
running, `uv sync --locked --group dev --extra full --inexact` retains extra
packages. Test removed dependencies in a fresh environment because an inexact
sync may leave packages that hide a missing dependency.

## Run the application

Use the [browser workbench](usage.md#browser-workbench),
[CLI](usage.md#command-line-conversion), or [HTTP API](usage.md#http-api)
instructions. Configure credentials through the
[process environment or launch-folder `.env`](configuration.md#credentials-and-environment).
The Windows launcher disables file watching, so restart after changing code or
prompt resources. Model calls incur endpoint charges.

## Offline checks

```powershell
uv run --no-sync python -m pytest
uv run --no-sync python -m ruff check doclayout tests benchmarks examples convert.py convert_single.py doclayout_app.py doclayout_server.py --select F,E9
uv lock --check
git diff --check
```

Sync first, then use `--no-sync` to test that environment without
changing its installed packages. Default tests block unrequested OpenAI calls.
They cover providers, structured extraction contracts, rendering, configuration,
API requests, GUI state, chat validation, credential precedence, cost accounting,
prompt fingerprints, and exports. `tests/test_security.py` uses small ordinary
fixtures and mocked models for security-policy regressions. These tests are not
an OS sandbox or adversarial security validation; no live deployment is tested.
CLI export tests cover format selection, one extraction per page, GUI-equivalent
HTML, ZIP contents, overwrite behavior, and input/output path protection.
Browser tests run Streamlit with mocked extraction. They cover clipboard downloads,
multi-file all-page processing, saved Extracted information, two-way block highlighting,
summary navigation and missing-value toggling without repeated model calls.
`tests/test_field_summary.py` covers readable labels, preserved values, partial records,
request selection, and unsuccessful runs. Field tests cover the Sol/medium extraction contract,
classification routing, quote grounding, SQLite exports, cache reuse, and retries.
`tests/test_launcher.py` checks port cleanup using mocked listeners and processes;
it does not stop a real application. Sidebar tests exercise both navigation buttons.

Layout tests use injected engines and tensor fixtures, without downloading weights.
They cover CUDA execution verification, CPU fallback, explicit CUDA failure,
ScatterND placement, initialization races, matching/order, exports, and Sol fallback
across entry points. Saved field-only retries must not prepare V3 or reconvert pages.
The [layout integration record](layout-v3-plan.md) separates these offline checks
from dated hardware observations; a passing fake-provider test is not a GPU test.

For a focused check while developing:

```powershell
uv run --no-sync python -m pytest tests/config tests/services tests/test_chat_prompts.py
uv run --no-sync python -m pytest tests/test_ui.py tests/test_ui_browser.py
uv run --no-sync python -m pytest tests/test_fields.py
uv run --no-sync python -m pytest tests/test_layout.py tests/test_layout_runtime.py tests/test_layout_prior.py tests/test_layout_readiness.py
```

Use the Ruff correctness checks above as the baseline. The repository's
pre-commit configuration also fixes and formats files with its pinned Ruff
version. Review those changes, especially around prompt literals. When reporting
a focused type check, name the paths checked.

## Documentation changes

Synchronize claims against code before editing prose. Keep Google-style docstrings
for downstream and application-support APIs, including argument types, return
values, error outcomes, and persistence/model-call effects. Layout adapter
docstrings may describe its public contracts, but documentation-only work must
preserve executable conversion behavior and runtime prompt bytes. Leave
model-response class docstrings unchanged because they affect request schemas.

Keep code examples offline unless the guide explicitly labels them billable.
Check links and anchors, run affected tests, and compare syntax trees without
docstrings when changing inline documentation. Preserve dated benchmark results;
new test runs belong in a separately dated verification note.

Update OpenWiki pages through its managed lifecycle. Do not edit claim sidecars,
generated indexes, provenance, or run state manually. Diagram JSON is the editable
source for the standalone HTML. Validate and deliver it through Archify, then inspect
desktop captures. Analysis graphs are snapshots; check their claims against source.

## Live evaluation

Benchmark PDFs and JSONL records are local-only. Follow the
[local dataset setup](../tests/data/olmocr_bench/README.md) first. Missing inputs
are skipped before an API client is created; offline tests generate temporary
documents and do not require the dataset.

Live tests make billable requests and run only when explicitly selected:

```powershell
uv run --no-sync python -m pytest tests/converters/test_olmocr_bench.py --run-integration
```

See the [benchmark guide](../benchmarks/README.md) for harness options,
[fixture provenance](../tests/data/olmocr_bench/README.md) for optional local data, and
[validation report](gpt6-validation.md) for dated results and known failures.
Offline test success does not establish model accuracy or endpoint availability.
The live fixture suite may fail on the recorded header/footer limitation or
other model variation.

## Build and package checks

Keep document inputs in `input/` or `inputs/`, and results in `output/`,
`outputs/`, or `conversion_results/`. These folders, common document formats,
datasets, and timestamped exports are ignored. Source Markdown and JSON remain
eligible for Git. Keep document exports in ignored folders.
Review `git diff --cached --name-only` before publication and do not force-add
input or output files. Ignore rules cannot remove files from earlier Git history
or previously published release assets.

```powershell
uv build
```

Inspect the generated wheel and source distribution for package code, the four
top-level Markdown prompts, both field Markdown prompts, the field JSON schema,
`LICENSE`, and `NOTICE`. Local credentials, generated
outputs, indexes, and environments must not enter distribution artifacts.

To smoke-test the installed wheel, create a separate environment outside the
checkout and install the freshly built wheel there. Run checks from outside the
repository so source imports cannot hide missing package files. Verify:

- `doclayout` and `doclayout_single` help commands;
- the GUI/API entry-point imports after installing the `gui` and `server` extras;
- resource loading for all six Markdown prompts and the field JSON schema;
- dependency consistency with `uv pip check --python <environment-python>`.

See [package installation](usage.md#installing-the-application-package) for
installation commands and dependency distinctions. Builds do not publish a
release; the current package version alone does not show whether a PyPI release exists.

GitHub releases include the wheel and source distribution. Before publishing,
test the wheel outside the checkout with base, `gui`, and `server` installations
and an isolated uv tool installation. Check the tag's commit and download assets
back for verification. PyPI publication is deferred.

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
merging interfaces are retired; see [compatibility changes](../CHANGELOG.md#210-2026-09-23).

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

Link to the guide that covers a topic instead of copying its tables. Record
changes awaiting a release under Unreleased in the changelog, and date historical
measurements. Check links, anchors, and executable examples. Run live requests
only as part of an explicit evaluation.
