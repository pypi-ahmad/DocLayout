# Python documentation audit

Audit date: 2026-09-27. Scope: the checked-out `doclayout/` Python package.
This is a documentation audit, not a behavioral, security, or model-accuracy
audit. The accompanying edits add docstrings to core and renderer interfaces.
Runtime prompts, response schemas, and executable logic are unchanged.

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

After that reconciliation, one inventory found 556 public symbols, 192 with
docstrings, and 364 without. A later renderer-focused pass reported 201
documented and 356 undocumented symbols out of 557. These are dated counts;
the denominator differed by one between passes. Neither count measures
documentation quality.

The original focused set covers layout and geometry, page/document builders,
the PDF converter, PDF/image providers, Sol service, file/GUI exports, output
and filename helpers, security/configuration helpers, CLI entry points, and
saved field extraction/store modules. Other public APIs remain undocumented.

[Python API reference](python-api.md) maps conversion, layout, renderer, and
saved-field entry points. Internal methods may change.

The package-wide count includes simple accessors and Pydantic response-model
classes. Model-response class docstrings are excluded from these edits because
their text would enter generated model request schemas. Prioritize remaining
symbols by actual public use and check schema stability before adding docstrings.

## Renderer follow-up

The current AST inventory counts 222 documented public symbols out of 556 in
the package, leaving 334 undocumented. In `doclayout/renderers/`, 36 of 45
counted symbols have docstrings.
The remaining nine are Pydantic output-model classes. This pass also documents
the renderers' `__call__` methods, which the inventory excludes with other
dunder methods. No output-model class docstrings or field definitions changed.

| Scope | After earlier reconciliation | Current checkout |
| --- | ---: | ---: |
| Package symbols with docstrings | 192 / 556 | 222 / 556 |
| Renderer symbols with docstrings | 6 / 45 | 36 / 45 |

The largest remaining groups by this mechanical count are LLM processors
(72 undocumented symbols) and schema block models (70). Those counts include
simple methods and do not rank the value or safety of adding each docstring.

## Follow-up verification

On Windows with Python 3.13.15, `tests/renderers/` passed 12 tests. The focused
mixed-page fallback regression passed once; 13 other tests in that module were
excluded by its `-k` selector. Ruff's `F,E9` selection passed for the renderer
package, and `uv lock --check` passed. Both offline commands printed in the
tutorial produced their stated values. Removing docstrings from the before and
after syntax trees left the six changed renderer modules identical.

A package-import doctest check found zero executable docstring examples, so it
does not add behavioral coverage. The author self-checked the reader path:
onboarding supplies offline setup, the source map points to renderer owners and
tests, the tutorial's mixed-page capstone has assertions to compare, and its
live run is explicitly optional and billable. This was not an independent
reader study or a live inference evaluation.

## Earlier findings and boundaries

- Existing layout, geometry, field, and GUI-export modules already had useful
  contract docstrings. The original pass focused on page
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
