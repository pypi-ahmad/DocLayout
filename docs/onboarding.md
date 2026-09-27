# Developer onboarding

[Back to README](../README.md) · [Contributor runbook](../CONTRIBUTING.md) ·
[Development reference](development.md) · [Python API](python-api.md)

Start with the source map and offline exercises below. They need no API key,
model download, or sample PDF.

## First local checks

Use PowerShell in the checkout. DocLayout requires Python `>=3.11,<4`; uv
resolves and syncs the environment from `pyproject.toml` and `uv.lock`.

```powershell
git status --short --branch
uv sync --locked --group dev --extra full
uv run --no-sync python -m pytest tests/test_fields.py tests/test_layout_contours.py
uv run --no-sync python -m ruff check doclayout tests benchmarks examples convert.py convert_single.py doclayout_app.py doclayout_server.py --select F,E9
uv lock --check
```

The `full` extra enables optional document formats; some formats also need
native libraries. A failing package-index or native-library setup is an
environment issue, not evidence that extraction works or fails. See
[environment details](development.md#environment).

## Follow one page through the code

| Stage | Start here | What it owns |
| --- | --- | --- |
| Input and page rendering | [`providers/`](../doclayout/providers), [`PdfConverter`](../doclayout/converters/pdf.py) | Selected pages and rendered image bounds |
| Local layout | [`layout.py`](../doclayout/layout.py), [`layout_geometry.py`](../doclayout/layout_geometry.py) | Pinned ONNX inference, masks, contours, order, and fallback evidence |
| Whole-page reading | [`services/openai.py`](../doclayout/services/openai.py), [`schema/extraction.py`](../doclayout/schema/extraction.py) | Sol request, HTML/text, and response validation |
| Assembly | [`builders/document.py`](../doclayout/builders/document.py), [`layout.py`](../doclayout/layout.py) | Source blocks, one-to-one layout reconciliation, lineage |
| Rendering | [`renderers/`](../doclayout/renderers) | HTML assembly, Markdown conversion, JSON trees, and flat chunks |
| Download assembly | [`ui/exports.py`](../doclayout/ui/exports.py) | Annotated images/PDFs and ZIP downloads |
| Downstream fields | [`fields.py`](../doclayout/fields.py), [`field_store.py`](../doclayout/field_store.py), [`ui/batch.py`](../doclayout/ui/batch.py) | Raw-Markdown extraction, grounding, saved runs and retries |

The GUI lives under [`ui/`](../doclayout/ui) and starts at
[`scripts/streamlit_app.py`](../doclayout/scripts/streamlit_app.py). The file
CLI starts at [`scripts/convert.py`](../doclayout/scripts/convert.py); the
local HTTP API starts at [`scripts/server.py`](../doclayout/scripts/server.py).
The GUI's field workflow is not an automatic CLI/API field-export feature.
See [architecture](architecture.md) for the full flow.

## Read the right contract

- Change extraction or layout: read [architecture](architecture.md),
  [layout integration evidence](layout-v3-plan.md), and the layout tests.
  Contours are separate from the four-corner `PolygonBox` contract.
- Change fields or persistence: read [field extraction](field-extraction.md),
  `tests/test_fields.py`, and `tests/test_field_summary.py`. A saved field-only
  retry must not reconvert a page.
- Change configuration or an entrypoint: read [configuration](configuration.md),
  [usage](usage.md), and `tests/test_entrypoints.py`.
- Change a prompt: inspect its packaged file, fingerprint tests, and the
  request builder. Treat prompt bytes as behavior.

## Before your first live run

A conversion can fetch the pinned layout artifact and call Sol for each page.
Configure credentials as described in [configuration](configuration.md), use a
document you are allowed to send to the endpoint, and choose a bounded page
range. `DOCLAYOUT_LAYOUT_DEVICE=auto` verifies CUDA execution when available
and otherwise uses CPU; a provider listing is not GPU proof. The current code
records Sol fallback if layout cannot run. Test results with fixtures do not
measure real extraction accuracy.

The [zero-to-mastery tutorial](tutorial.md) continues with hands-on exercises.

## Make a first contribution

Choose a small issue or a source-backed documentation correction. Read its
test first, change the narrowest owning module or page, and run the matching
focused checks. For prose, check links and `git diff --check`; for docstrings,
also confirm the executable syntax tree is unchanged. The
[contributor runbook](../CONTRIBUTING.md) has the full review checklist.
