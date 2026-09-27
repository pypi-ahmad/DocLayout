# New contributor onboarding

This is a first-day route through the checkout. It does not require API
credentials or a document upload.

## 1. Prepare the Windows environment

Install Git and [uv](https://docs.astral.sh/uv/getting-started/installation/),
then open PowerShell at the repository root. The package supports Python
`>=3.11,<4`; the recorded Windows checks used Python 3.14.

```powershell
uv sync --locked --group dev --extra full
uv run --no-sync python -m pytest tests/test_layout_contours.py tests/test_cli_exports.py
```

The first command needs a reachable package index or a populated uv cache.
The tests use fixtures and mocked services; they do not download model weights
or make OpenAI requests. A passing result shows the local test environment is
ready, not that live extraction is accurate.

## 2. Follow one page through the code

Read the [architecture guide](architecture.md), then trace these modules:

| Question | Start here |
| --- | --- |
| Who renders source pages? | `doclayout/providers/pdf.py` and `image.py` |
| Who prepares and decodes local layout? | `doclayout/layout.py` and `layout_geometry.py` |
| Who sends the whole page to Sol? | `doclayout/builders/document.py` and `services/openai.py` |
| Who assembles and refines blocks? | `doclayout/converters/pdf.py` and `processors/` |
| Who writes file and GUI exports? | `doclayout/exports.py` and `ui/exports.py` |
| Who reuses saved Markdown for fields? | `doclayout/fields.py` and `field_store.py` |

The [layout integration record](layout-v3-plan.md) gives the verified ONNX
decode and fallback policy. The [field extraction guide](field-extraction.md)
explains the separate saved-result workflow. Source and tests take precedence
over either document when behavior has changed.

## 3. Make a safe first contribution

Choose a small issue or an in-scope documentation correction. Read its test
first, change the narrowest owning module or page, and run the matching focused
tests. For a prose-only change, check links and `git diff --check`; for Python
docstrings, also verify the executable syntax tree did not change. The
[contributor runbook](../CONTRIBUTING.md) gives the complete review checklist.

You are ready to work independently when you can identify the source owner,
run the offline checks, explain whether a test used mocks or live services,
and show that unrelated files stayed untouched. Continue with the
[zero-to-mastery tutorial](tutorial.md) for hands-on exercises.
