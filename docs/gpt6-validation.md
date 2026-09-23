# DocLayout validation

This document separates dated model observations from offline application checks.
See [usage](usage.md) for current commands and [architecture](architecture.md) for
the pipeline. Model accuracy and deterministic software tests are different evidence.

## Recorded live run

Bounded live run on 2026-09-23, using the configured OpenAI-compatible endpoint.
This is a smoke test, not a general accuracy benchmark.

- A generated image containing "MARKER OCR TEST 4827" transcribed exactly through
  Responses with a Pydantic structured output.
- Each of the three vendored PDFs used one page extraction request at 192 DPI.
- The resulting document was rendered as Markdown, HTML, JSON, chunks and OCR JSON
  without repeating extraction.
- One additional page-correction request completed on the multi-column sample,
  reusing its existing extraction. Metadata recorded one request, zero API errors
  and 7,420 tokens. Successful execution does not establish improved accuracy.

| Sample | Blocks after processing | Elapsed seconds | Existing benchmark rules passed |
| --- | ---: | ---: | ---: |
| headers_footers_page1.pdf | 38 | 44.0 | 4/5 |
| long_tiny_text_pg36.pdf | 58 | 51.1 | 4/4 |
| multi_column_page1.pdf | 16 | 16.2 | 5/5 |

The header/footer sample retained a copyright line classified as Text.
The evaluator expected that line to be absent. Thus 13 of 14 rules passed;
header/footer classification remains a quality limitation. No new model call was
made to tune this result. Times include extraction and rendering on this machine
and endpoint and should not be treated as throughput guarantees.

Generated smoke artifacts are under the ignored
`conversion_results/gpt6_validation/` directory. Default tests mock API calls.
The explicit `--run-integration` test checks all 14 rules and can fail on the
known classification limitation or other model variation.

## Original local checks accompanying the live run

- `uv run pytest`: 82 passed, 4 skipped. Three skips are billable integration
  tests; one is an existing skipped IgnoreTextProcessor test.
- API path conversion, multipart upload, rejection of removed fields and GUI
  startup were checked with mocked extraction.
- Existing document-provider PDF handoffs were tested with generated local
  PDFs. Full Office/HTML/EPUB conversion and Modal deployment were not live-tested.
- Ruff correctness/import rules (E4, E7, E9, F, I) passed on changed Python files.
  Broad modernization rules were not used as a repository-wide gate.
- Focused ty checks passed for the new extraction, service, configuration,
  PDF provider, converters, OCR renderer, and batch/API entrypoints.
- `uv lock --check`, `uv build`, compile checks and Git whitespace checks passed.
- Runtime import checks confirmed Surya, Torch, Transformers, google-genai and
  Anthropic are absent from the environment.

These original check results are historical, not a current test-count claim.
The current offline suite also covers prompt-resource fingerprints, session
invalidation, chat verification, export artifacts, clipboard operations, and
browser downloads with mocked extraction. It does not establish live endpoint
availability or current OCR accuracy. No new live run is implied by a
documentation update.

## Documentation and publication checks (2026-09-23)

- Offline suite: **102 passed, 4 skipped**. This includes real-browser clipboard
  and download checks against mocked extraction.
- Ruff correctness/import checks (E4, E7, E9, F, I) passed across application,
  tests, benchmarks, and examples. Focused ty checks passed for the UI, Sol
  service, extraction schema, and Streamlit entry point.
- License modification comments were added to inherited application files.
  Executable syntax and all prompt resources are checked against the pre-update
  baseline; no model instructions or application behavior are intentionally changed.
- The original live measurements above were not rerun. No billable model call
  is needed for these documentation and publication checks.
- Current documentation links and headings were checked. Python and JSON examples
  parsed, PowerShell examples passed syntax checks, and the documented Python,
  CLI page-range, API filepath, and multipart examples ran with mocked inference.
- Source and wheel builds passed. An isolated wheel installation loaded the
  application and prompt resources; installed CLI help commands passed. Package
  artifacts contain the license and attribution notice and exclude local records,
  generated indexes, credentials, and conversion outputs.
- Runtime syntax for all 120 application Python files matched the pre-update
  baseline. All four Markdown prompt files remained byte-identical.
