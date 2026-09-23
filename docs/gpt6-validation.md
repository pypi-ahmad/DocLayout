# DocLayout validation

This report separates live extraction observations from offline application
checks. See [development](development.md) for verification commands,
[usage](usage.md) for workflows, and [architecture](architecture.md) for the pipeline.

## Checks for changes now on main (2026-09-23)

- With `DOCLAYOUT_BENCH_DIR` pointing to an empty local directory, the offline
  suite passed: **155 passed, 1 skipped**. The optional live benchmark skipped
  before creating an API client. No model calls were made.
- The three benchmark PDFs and their JSONL rules are no longer tracked. Local
  copies remain usable, and a fresh checkout collects the tests without them.
- Package builds excluded input documents, dataset records, and generated
  output folders. The installed wheel read `.env` from its launch folder for
  extraction and chat in a mocked check. It did not make an API request.
- Cost tests cover both supplied rate tables, cached tokens, incomplete usage,
  failed requests, per-conversion isolation, and GUI session totals.

The live observations below predate these changes. They are on `main`, but have
not been published as a new GitHub release.

## Version 2.1.0 installation and CLI checks (2026-09-23)

- Offline suite: **130 passed, 3 skipped**. The skips require explicitly enabled,
  billable integration calls. No live model calls were made for this release.
- File-command tests cover individual exports, the full bundle, ZIP-only output,
  GUI export parity, one extraction per page, overwrites, conflicting options,
  input protection, and failures that preserve existing outputs.
- Wheel and source builds passed. A base wheel installed outside the checkout
  produced every CLI export with mocked extraction, without Streamlit or FastAPI.
- Local wheel installation succeeded with pip, uv pip, and an isolated uv tool
  directory. Dependency checks passed for base, GUI tool, and combined extras
  environments. Installed command help and version checks passed.
- The installed GUI tool returned a healthy Streamlit response. The installed
  server returned its OpenAPI schema. These startup checks made no model calls.
- Distributions include the license and attribution notice. All four Markdown
  prompts match the original baseline byte for byte. Ruff correctness checks,
  lockfile consistency, documentation links, and Git whitespace checks passed.

These checks establish packaging and deterministic application behavior. They do
not repeat the live extraction observations below or validate full Office
conversion on a newly configured machine.

## Recorded live run

A limited live smoke test ran on 2026-09-23 using the configured
OpenAI-compatible endpoint. It does not establish general extraction accuracy.

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
The evaluator expected that line to be absent, so 13 of 14 rules passed;
header/footer classification remains a quality limitation. No new model call was
made to tune this result. Times include extraction and rendering on this machine
and endpoint. They do not guarantee throughput elsewhere.

Generated smoke artifacts are under the ignored
`conversion_results/gpt6_validation/` directory. Default tests mock API calls.
With the optional local PDFs and JSONL rules installed, the explicit
`--run-integration` test checks all 14 rules. It can fail on the known
classification limitation or other model variation.

## Original local checks accompanying the live run

- `uv run pytest`: 82 passed, 4 skipped. Three skips are billable integration
  tests; one is an existing skipped IgnoreTextProcessor test.
- API path conversion, multipart upload, rejection of removed fields and GUI
  startup were checked with mocked extraction.
- Existing document-provider PDF handoffs were tested with generated local
  PDFs. Full Office/HTML/EPUB conversion and Modal deployment were not live-tested.
- Ruff correctness/import rules (E4, E7, E9, F, I) passed on changed Python files.
  The checks did not require the whole repository to pass broad modernization rules.
- Focused ty checks passed for the new extraction, service, configuration,
  PDF provider, converters, OCR renderer, and batch/API entrypoints.
- `uv lock --check`, `uv build`, compile checks and Git whitespace checks passed.
- Runtime import checks confirmed Surya, Torch, Transformers, google-genai and
  Anthropic are absent from the environment.

These counts describe the original checks.
The current offline suite also covers prompt-resource fingerprints, session
invalidation, chat verification, export artifacts, clipboard operations, and
browser downloads with mocked extraction. It does not establish live endpoint
availability or current OCR accuracy. Updating documentation does not rerun those live checks.

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

## Cleanup verification (2026-09-23)

After the [unused-code cleanup](../CHANGELOG.md#210-2026-09-23):

- The complete offline suite passed in a fresh environment: **102 passed,
  3 skipped**. The three remaining skips are explicitly enabled, billable
  integration tests; the permanently skipped legacy ignore-text test was removed.
- Ruff correctness/import checks (`F,E9`), Git whitespace checks, and isolated
  dependency consistency checks passed.
- The wheel built and installed successfully. All four console entry points
  imported, both conversion CLI help commands passed, prompt resources matched
  source, and retired modules were absent from the wheel.
- All four Markdown prompts stayed byte-identical. Embedded refinement prompt
  string values were unchanged. No retained dependency versions were upgraded.
- Exact sync of the existing environment encountered a locked `psutil` binary.
  An inexact sync kept extra packages there. The suite also passed in the fresh
  environment using only the reduced declared dependency set.

The cleanup checks covered offline application and packaging behavior. They
included no live model evaluation; the earlier live measurements remain historical.
Follow the [development guide](development.md) to repeat checks.

## Documentation reorganization checks (2026-09-23)

- Focused configuration, service, prompt, and entry-point tests: **26 passed**.
- All 10 documentation files passed local link/anchor checks; Python/JSON
  examples parsed, and 21 PowerShell examples passed syntax checks.
- CLI help and the component inventory ran successfully. Offline checks verified
  the documented defaults, JSON/flag argument-order behavior, explicit false
  values, and the Python usage example with mocked conversion.
- A before/after snapshot confirmed that all 171 existing non-documentation
  files and runtime prompts present at the start of this documentation task
  remained unchanged. Earlier cleanup deletions were preserved.

These checks made no live model calls and did not repeat the complete suite;
the full-suite result above belongs to the cleanup verification.
