# DocLayout

**From scans and images to structured Markdown.**

DocLayout converts PDFs, scans, images, and office documents into readable,
structured content. Use the browser workbench to inspect pages, copy results,
download document outputs, and ask questions about extracted text. A CLI,
Python library, and local HTTP API support scripted workflows.

## Features

- GPT-6 Sol reads every selected page, including text, tables, equations,
  headings, reading order, and estimated region coordinates.
- Markdown has a native rendered view and an exact raw view. The separate HTML
  preview uses a white page, serif typography, embedded crops, and MathML.
- Download Markdown, HTML, JSON, chunks, annotated page images, or an annotated
  PDF. The ZIP groups document outputs without the source upload or chat history.
- GPT-6 Luna answers document questions with source-quote checks and a second
  verification request before displaying accepted answers.
- Preview navigation, copying, and downloads reuse completed session results
  without repeating OCR.

## Quick start on Windows

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git,
then open PowerShell:

```powershell
git clone https://github.com/pypi-ahmad/DocLayout.git
cd DocLayout
uv sync --group dev --extra full
```

DocLayout requires Python 3.10 or newer within the declared dependency limits;
the current Windows checks use Python 3.14. Configure `OPENAI_API_KEY` in the
process environment. The SDK also reads `OPENAI_BASE_URL` for a compatible
endpoint. Do not put credentials in code, configuration JSON, or Git.

If you configured Windows user environment variables, open a new terminal so
the launcher receives them. The endpoint must support Responses, image inputs,
and structured outputs for `gpt-6-sol`; document chat also needs `gpt-6-luna`.

```powershell
.\launch.cmd
```

The launcher opens **http://localhost:8471**, stopping any previous process
listening on port 8471 first. It disables file watching; restart it after edits.

PDFs and images need no GPU or local model downloads. Office, HTML, and EPUB
conversion also needs the `full` extra and WeasyPrint's native dependencies.
See [installation and troubleshooting](docs/usage.md#installation).

## Command-line example

```powershell
uv run doclayout_single document.pdf --output_dir output
uv run doclayout_single document.pdf --page_range 0,2-4 --output_format markdown
uv run doclayout documents --output_dir output --workers 1
```

GUI Start/End pages are **1-based and inclusive**. CLI and API page ranges are
**zero-based**. Extra refinement is optional; OCR always runs through Sol.

## Documentation

| Guide | Contents |
| --- | --- |
| [Usage](docs/usage.md) | Installation, GUI, CLI, Python, API, configuration, troubleshooting |
| [Architecture](docs/architecture.md) | Extraction pipeline, model calls, renderers, prompts, session state |
| [Validation](docs/gpt6-validation.md) | Dated live observations, offline checks, known limitations |
| [Benchmarks](benchmarks/README.md) | Running a bounded extraction evaluation |
| [Deployment example](examples/README.md) | Optional Modal deployment and its verification limits |

## Accuracy, privacy, and cost

Page images are sent to the configured API endpoint. Chat sends extracted page
text and recent accepted conversation turns. Requests use `store=False`, which
does not replace the endpoint provider's own data-handling policy.

Extraction and chat can incur API charges. Model-estimated boxes are not
confidence scores. Small text, complex tables, equations, and header/footer
classification need review. Document chat verification can also miss mistakes.
There is no claim of perfect accuracy or a general benchmark ranking.

Browser results live in session memory; download them before closing or losing
the session. CLI conversion writes output files. GUI HTML is generated from
Markdown; CLI/API HTML is rendered directly from document blocks.

## Development checks

```powershell
uv run playwright install chromium --only-shell
uv run pytest
uv lock --check
uv build
```

Default tests mock model calls. Explicit live tests are billable:

```powershell
uv run pytest tests/converters/test_olmocr_bench.py --run-integration
```

Keep changes to prompts separate from organizational refactors. Prompt
fingerprint tests protect exact request text. Report problems through
[DocLayout issues](https://github.com/pypi-ahmad/DocLayout/issues), with secrets
and private document contents removed.

## References and attribution

DocLayout includes code derived from [Marker](https://github.com/datalab-to/marker),
originally developed by Vik Paruchuri and contributors. DocLayout adapts that
foundation for its extraction service, document workbench, chat, and exports.
It is an independent application and does not imply upstream endorsement.

Distributed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for
attribution and a description of modifications. The vendored benchmark fixtures
have their own [source attribution](tests/data/olmocr_bench/README.md).
