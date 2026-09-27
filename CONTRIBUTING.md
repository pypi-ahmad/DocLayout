# Contributing to DocLayout

Start with [onboarding](docs/onboarding.md) if this is your first visit. The
[development guide](docs/development.md) has the full environment and build
reference; the [tutorial](docs/tutorial.md) is a guided practice path.

## Before changing code

1. Read the nearest `AGENTS.md` and the source and tests for the behavior you
   intend to change. Use [architecture](docs/architecture.md) to find ownership.
2. Check `git status --short --branch`. Preserve changes you did not make.
3. Decide whether the change affects conversion, layout, fields, rendering,
   configuration, or documentation. Keep a patch within that boundary.
4. If the task needs a representative document, measured accuracy, a credential,
   or a runtime choice that is unavailable, state the gap before claiming a result.

Do not treat generated `openwiki/` pages, historical diagrams, or an old plan as
authority over current source and tests. Do not hand-edit managed OpenWiki files.

## Local workflow

Run commands from the repository root in PowerShell:

```powershell
uv sync --locked --group dev --extra full
uv run --no-sync python -m pytest tests/test_fields.py
uv run --no-sync python -m ruff check doclayout tests benchmarks examples convert.py convert_single.py doclayout_app.py doclayout_server.py --select F,E9
uv lock --check
git diff --check
```

Choose the focused test for your change before running the full suite. The
[test map](docs/development.md#offline-checks) lists layout, GUI, and field
coverage. `uv run --no-sync` uses the synced environment without changing
installed dependencies. Keep `pyproject.toml` and `uv.lock` together when a
dependency change is necessary; use uv, not a second package manager.

The default tests use fixtures and block unrequested OpenAI calls. Conversion,
live model checks, and the integration benchmark can download artifacts or make
billable requests. Run them only when the task calls for live validation. Report
mocked checks, CPU/GPU execution, and evaluated quality separately.

Choose the smallest test set that exercises the changed boundary:

| Change | Start with |
| --- | --- |
| Provider, page conversion, or block assembly | `tests/providers/`, `tests/converters/`, `tests/builders/` |
| V3 decode, matching, fallback, or lineage | `tests/test_layout*.py` and affected processor/export tests |
| Rendered Markdown, JSON, or chunks | `tests/renderers/` and `tests/test_cli_exports.py` when files change |
| Saved fields or GUI retry | `tests/test_fields.py`, `tests/test_field_summary.py`, relevant UI tests |
| Documentation or docstrings | Link/command review, syntax-tree comparison, affected tests, Ruff |

The [Python API reference](docs/python-api.md) identifies entry points and
return shapes; check the source and fixtures for the current behavior.

## Change review

- Add a regression test at the owning boundary. Check the visible output as
  well as internal state when a change affects exports or the GUI.
- For renderer changes, run `tests/renderers/` and check HTML, Markdown, JSON,
  and chunk behavior where the changed path affects them. Documentation-only
  renderer edits must leave executable syntax and output schemas unchanged.
- Preserve whole-page Sol extraction, its HTML and semantic ownership, and
  unmatched content when changing layout reconciliation. A V3-only region is
  evidence, not new text.
- Keep saved field retries on existing raw Markdown. Quote verification and PDF
  block mapping are local checks, not proof that a field is semantically correct.
- Review prompt and response-schema edits separately. Prompt fingerprints and
  model-response Pydantic docstrings can change request contracts.
- For documentation, verify commands and links against source. Preserve dates
  and limitations attached to earlier live observations. The
  [Python documentation audit](docs/python-documentation-audit.md) records
  remaining docstring gaps; avoid class docstrings on model-response Pydantic
  types because those change the generated request schema.
- Before sharing a patch, review `git diff`, focused tests, Ruff, lock status,
  and `git diff --check`. Do not include `.env`, documents, exports, caches,
  or model artifacts.

For agent-assisted work, do not infer permission to commit, push, or open a pull
request from a request to edit code. Agree on delivery scope first. The
[developer guide](docs/development.md#build-and-package-checks) covers build
validation; a local build is not a published release.

## When a check fails

Keep the complete failure output. Reproduce with the smallest relevant test,
trace the responsible source and fixture, and fix failures caused by your patch.
If local model files or credentials are absent, record that as an unverified live
path rather than replacing a deterministic test with a live call. See
[troubleshooting](docs/usage.md#troubleshooting) for operator-facing failures.

| Observation | First distinction to make | Report or action |
| --- | --- | --- |
| Offline test tries an external model call | Is the test actually marked as live, or did the patch cross a mocked boundary? | Do not add credentials to make an offline test pass; restore the fixture boundary or report the live scope. |
| V3 page falls back to Sol | Preparation failure, inference failure, or valid empty detections? | Inspect page runtime metadata. Empty detections are successful inference, not a runtime failure. |
| More blocks are matched | Did content, classes, reading order, or contour alignment improve? | Keep thresholds provisional until representative fixtures or authorized live pages support a quality claim. |
| Saved field retry differs | Did it reuse the saved raw Markdown, definition snapshot, and chunks? | Reproduce from the saved artifacts; do not reconvert solely to retry fields. |
| A documentation-only patch changes a prompt or schema | Did the edit touch packaged prompts or model-response class descriptions? | Revert that part and review it as a behavior change with fingerprint tests. |
