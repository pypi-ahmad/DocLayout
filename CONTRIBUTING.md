# Contributing to DocLayout

Start with the [onboarding path](docs/onboarding.md) if this is your first change.
The [developer guide](docs/development.md) has the full environment, test, build,
and release-check details. This runbook is for a normal local contribution.

## Before editing

1. Read `AGENTS.md` and the guide for the area you will change. For conversion,
   use [architecture](docs/architecture.md) and the
   [layout contract](docs/layout-v3-plan.md). For saved field extraction, read
   [field extraction](docs/field-extraction.md) and
   [project memory](docs/project-memory.md).
2. Run `git status --short` and leave unrelated work intact. Compare a proposed
   behavior change with current source and tests; historical plans and generated
   wiki pages are not the implementation.
3. Keep document inputs and exports in the ignored input/output locations listed
   in the [developer guide](docs/development.md#build-and-package-checks).
   Never commit credentials, private documents, or conversion results.

## Set up and check

From the repository root in PowerShell:

```powershell
uv sync --locked --group dev --extra full
uv run --no-sync python -m pytest
uv run --no-sync python -m ruff check doclayout tests benchmarks examples convert.py convert_single.py doclayout_app.py doclayout_server.py --select F,E9
uv lock --check
git diff --check
```

`uv run --no-sync` uses the installed environment without changing packages.
Default tests are offline and block unrequested OpenAI calls. They do not prove
model accuracy, real CUDA execution, or endpoint availability. If a focused
test fails, keep its complete failure output and fix the cause before rerunning.
Live tests can make billable requests; run them only within an explicitly
authorized evaluation scope.

## Change and review

1. Make the smallest change at the responsible layer and add or update a
   regression test for behavior changes. Keep the whole-page Sol request and
   official `PaddlePaddle/PP-DocLayoutV3_onnx` artifact contract intact unless
   the task explicitly changes that contract.
2. Run focused tests, then the offline checks above. If the change affects
   packaging, follow the [build checks](docs/development.md#build-and-package-checks).
3. Update the owning documentation page. Use Google-style docstrings for useful
   Python APIs. Do not add docstrings to model-response Pydantic classes:
   their generated request schemas include class descriptions.
4. Inspect `git diff` and `git diff --check`. Separate factual verification
   from assumptions, and report remaining live-validation gaps.

Do not manually edit generated `openwiki/` pages or diagram HTML. The
[documentation ownership map](docs/development.md#documentation-ownership)
points to the editable sources. Committing, pushing, and opening a pull request
are separate publication steps; do them only when authorized.
