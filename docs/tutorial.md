# From first test to confident changes

[Back to README](../README.md) · [Onboarding](onboarding.md) ·
[Contributor runbook](../CONTRIBUTING.md)

The exercises start offline and trace a change through source, tests, outputs,
and verification limits. Live inference is optional; completing the exercises
does not establish model accuracy.

## 1. Establish a clean baseline

Follow [onboarding](onboarding.md#first-15-minutes) to sync the project and run
the focused field and contour tests. Record the current branch and any
pre-existing edits before touching files. Read one test failure in full before
changing implementation. The goal is to distinguish a source regression from
a missing dependency or optional native library.

## 2. Learn the coordinate frames

Layout contours are stored in page-image pixels. Sol's guide uses normalized
0–1000 coordinates. The provider document and annotation image can have other
bounds; non-square images scale each axis independently. Try the shared helper:

```powershell
uv run --no-sync python -c "from doclayout.layout_geometry import transform_points; print(transform_points([[100, 50]], (0, 0, 200, 100), (0, 0, 1000, 1000)))"
```

The result is `[[500.0, 500.0]]`. Read `transform_points` and
`region_geometry` in [`layout_geometry.py`](../doclayout/layout_geometry.py),
then run:

```powershell
uv run --no-sync python -m pytest tests/test_layout_contours.py tests/test_layout_prior.py
```

Find a test with a nonrectangular contour. Explain why its AABB alone cannot
establish polygon overlap, and where explicit rectangle-fallback provenance is
recorded. The [layout evidence record](layout-v3-plan.md) distinguishes
fixture checks from live artifacts and hardware observations.

## 3. Trace a whole-page conversion

Start at [`PdfConverter.build_document`](../doclayout/converters/pdf.py). Follow
the provider render, `LayoutEngine`, the Sol extraction service, document
builder, processors, and renderers using the
[onboarding map](onboarding.md#follow-one-page-through-the-code). Run the
offline entrypoint and renderer checks:

```powershell
uv run --no-sync python -m pytest tests/test_entrypoints.py tests/renderers/test_json_renderer.py tests/renderers/test_chunk_renderer.py
```

Check three cases in the tests: an accepted V3 match uses layout geometry/order
while preserving Sol HTML; unmatched Sol text remains once; an unmatched V3
region contributes metadata but no text. Do not infer these properties from a
successful model download alone.

## 4. Follow downstream evidence and persistence

The GUI batch workflow snapshots raw Markdown before export naming changes.
[`extract_fields`](../doclayout/fields.py) uses that Markdown for an optional
classification request and one logical field request, then local quote checks
and block mapping. [`FieldStore`](../doclayout/field_store.py) saves manifests,
runs, and record JSON. A field-only retry reads the saved Markdown and chunks;
it does not invoke page conversion.

```powershell
uv run --no-sync python -m pytest tests/test_fields.py tests/test_field_summary.py
```

In `tests/test_fields.py`, locate the fixtures for one verified quote and one
ambiguous or missing mapping. Compare the resulting `status`, `issues`, and
`locations`. A verified quote supports source presence, not semantic truth.
The [field guide](field-extraction.md) explains what reviewers see and retain.

## 5. Make and prove a small change

Choose a task in one owning module. First add a failing regression test for
the visible behavior; then make the smallest implementation change and rerun
that test. If the change affects exports, assert the serialized result or
annotated image too. If it affects prompt text, verify packaged fingerprints
and get representative evaluation input before making quality claims.

Use the [contributor runbook](../CONTRIBUTING.md#local-workflow) for final
checks. Review `git diff` to confirm only intended files changed. State which
checks are mocked, which use actual CPU/GPU inference, and which evaluate
accuracy. If no representative corpus is available, say so.

## 6. Optional, billable end-to-end validation

Only run this stage when you have approved source material, configured API
access, and a task that calls for live validation. The CLI command below can
download the pinned layout model and make Sol requests:

```powershell
uv run doclayout document.pdf output --markdown --json --chunks --metadata --page_range 0
```

Use a small authorized page, inspect the emitted metadata and files, and keep
the page and hardware details with any report. A single smoke test verifies a
path, not segmentation quality across document types. See
[usage](usage.md#command-line-conversion) and
[validation limits](gpt6-validation.md) before broader evaluation.
