# Python documentation audit

Audit date: 2026-09-27. Scope: the checked-out `doclayout/` Python package.
This is a documentation audit, not a behavioral, security, or model-accuracy
audit. The accompanying edit adds docstrings only to core public interfaces;
it does not change runtime prompts, response schemas, or executable logic.

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
with docstrings, and 364 without. The earlier table remains a dated comparison,
not a claim that the merged checkout still has 557 counted symbols.

The focused set covers layout and geometry, page/document builders, the PDF
converter, PDF/image providers, Sol service, file/GUI exports, output and
filename helpers, security/configuration helpers, CLI entry points, and saved
field extraction/store modules. It is a fixed audit slice, not a claim that
all public APIs are now documented.

The package-wide count is deliberately mechanical. It includes simple
accessors and Pydantic response-model classes, so 365 is not a prioritized
to-do list. Model-response class docstrings are excluded from this edit:
their text would enter generated model request schemas. The largest remaining
gaps are in schema/block models, renderers, and structure processors. A future
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
