# Python documentation audit

Audit date: 2026-09-27. Scope: docstrings in the checked-out `doclayout/`
Python package. Behavior, security, and model accuracy are outside this audit.
The accompanying edit documents core public interfaces without changing
runtime prompts, response schemas, or executable logic.

## Method and result

An AST inventory counted public top-level classes/functions and public methods
directly inside classes. It excluded names beginning with `_` and nested local
functions. The original local pass compared its then-current `HEAD` and
working tree before reconciling a newer remote branch:

| Scope | Before | After |
| --- | ---: | ---: |
| Package symbols counted | 557 | 557 |
| Symbols with docstrings | 156 | 192 |
| Symbols without docstrings | 401 | 365 |
| Selected core-interface symbols with docstrings | 77 / 113 | 113 / 113 |

After that reconciliation, the same inventory found 556 public symbols, 192
with docstrings, and 364 without. Recounting the current checkout before this
renderer-focused pass found 557 public symbols in 135 Python modules, 192 with
docstrings. This pass moves the count to 201 documented and 356 undocumented
out of 557. The earlier table is historical; inventory counts can change as
source is reconciled. Neither count measures documentation quality.

The original focused set covers layout and geometry, page/document builders,
the PDF converter, PDF/image providers, Sol service, file/GUI exports, output
and filename helpers, security/configuration helpers, CLI entry points, and
saved field extraction/store modules. Other public APIs remain undocumented.

This pass documents nine more renderer interfaces. The
[Python API reference](python-api.md) maps conversion, layout, renderer, and
saved-field entry points. Internal methods may change.

The package-wide inventory includes simple accessors and Pydantic
response-model classes. Prioritize the remaining 356 by actual public use.
Model-response class docstrings are excluded from this edit:
their text would enter generated model request schemas. The largest remaining
gaps are in schema/block models and structure processors. A future
pass should group them by actual public use and check schema stability before
adding documentation.

## Findings and boundaries

- Existing layout, geometry, field, and GUI-export modules already had useful
  contract docstrings. The highest-value gaps in this pass were around page
  providers, conversion orchestration, export naming, and CLI boundaries.
- The new contributor path separates [first-day onboarding](onboarding.md),
  [guided exercises](tutorial.md), [developer reference](development.md),
  and the [contributor runbook](../CONTRIBUTING.md). Onboarding covers setup;
  the linked guides carry the detailed architecture and review procedures.
- Offline tests can check syntax, behavior, and fixture contracts. They do
  not show whether a new document is matched correctly, whether contours
  align on warped scans, or whether a GPU ran a live ONNX session.

Documentation claims were checked against the current source and tests.
The reader-path review for the tutorial is an author self-check, not an
independent user study.
