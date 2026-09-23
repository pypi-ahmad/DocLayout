# DocLayout

**From scans and images to structured Markdown.**

DocLayout converts PDFs, scans, images, and office documents into readable,
structured content. In the browser workbench, you can inspect pages, copy or download results,
and ask questions about the extracted text. For scripts, use the CLI, Python
library, or local HTTP API.

## Features

- GPT-6 Sol reads every selected page, including text, tables, equations,
  headings, reading order, and estimated region coordinates.
- Markdown has a native rendered view and an exact raw view. The separate HTML
  preview uses a white page, serif typography, embedded crops, and MathML.
- Download Markdown, HTML, JSON, chunks, annotated page images, or an annotated
  PDF. The ZIP contains document outputs and excludes the source upload and chat history.
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

For supported Python versions and document-format prerequisites, see
[installation](docs/usage.md#installation). Configure API credentials in the
[process environment](docs/configuration.md#credentials-and-environment), then
launch the workbench:

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
| [Usage](docs/usage.md) | Installation, GUI, CLI, Python, API, troubleshooting |
| [Configuration](docs/configuration.md) | Settings, defaults, limits, environment, precedence |
| [Development](docs/development.md) | Setup, tests, builds, extension and prompt-change practices |
| [Changelog](CHANGELOG.md) | Current changes and compatibility history |
| [Architecture](docs/architecture.md) | Extraction pipeline, model calls, renderers, prompts, session state |
| [Validation](docs/gpt6-validation.md) | Dated live observations, offline checks, known limitations |
| [Benchmarks](benchmarks/README.md) | Running a bounded extraction evaluation |
| [Deployment example](examples/README.md) | Optional Modal deployment and its verification limits |

## Accuracy, privacy, and cost

DocLayout sends page images to the configured API endpoint. Chat sends extracted page
text and recent accepted conversation turns. Requests use `store=False`, which
does not replace the endpoint provider's own data-handling policy.

Extraction and chat can incur API charges. Model-estimated boxes are not
confidence scores. Small text, complex tables, equations, and header/footer
classification need review. Document chat verification can also miss mistakes.
There is no claim of perfect accuracy or a general benchmark ranking.

The browser keeps results in session memory. Download them before closing or
losing the session. CLI conversion writes output files. The GUI generates HTML
from Markdown; the CLI and API render HTML directly from document blocks.

## Development

See the [development guide](docs/development.md) for environment setup, offline
and browser checks, explicit live evaluation, package builds, and prompt-change
practices. The [changelog](CHANGELOG.md) records additions and retired interfaces.

Report problems through [DocLayout issues](https://github.com/pypi-ahmad/DocLayout/issues),
after removing secrets and private document contents.

## References and attribution

DocLayout includes code derived from [Marker](https://github.com/datalab-to/marker),
originally developed by Vik Paruchuri and contributors. DocLayout adapts that
foundation for its extraction service, document workbench, chat, and exports.
It is an independent application and does not imply upstream endorsement.

Distributed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) for
attribution and a description of modifications. The vendored benchmark fixtures
have their own [source attribution](tests/data/olmocr_bench/README.md).
