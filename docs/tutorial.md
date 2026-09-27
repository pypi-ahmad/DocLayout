# DocLayout: zero-to-mastery tutorial

Work through these offline exercises in order. They teach the code and test
contracts; they do not measure document-extraction accuracy. Use PowerShell
from the repository root. If setup is new, complete
[onboarding](onboarding.md) first.

## Level 1: Find the public entry points

```powershell
uv run --no-sync doclayout --help
uv run --no-sync doclayout_single --help
```

Find the corresponding `[project.scripts]` entries in `pyproject.toml` and
the Click commands in `doclayout/scripts/`. The file CLI selects exports;
folder conversion uses its existing renderer path. Both reach a converter, but
the GUI's saved field-extraction workflow is separate. Read
[usage](usage.md) before making a real conversion: it needs credentials and
can incur API charges.

## Level 2: Decode a tiny mask

The ONNX layout result retains a compressed, row-major mask. Run this local
example; it has no model or network dependency:

```powershell
uv run --no-sync python -c "from doclayout.layout_geometry import mask_from_rle; print(mask_from_rle([2, 2], (2, 2)).tolist())"
```

Expected output: `[[0, 0], [1, 1]]`. The runs alternate background and
foreground, starting with background. The real decode associates each mask
with its detection row, class, score, box, and raw reading-order key; see
`doclayout/layout.py`. Verify this against the independent fixture:

```powershell
uv run --no-sync python -m pytest tests/test_layout_contours.py -k decode_matches_independent_paddlex_reference
```

The fixture tests the implemented contour contract, not live-model accuracy.

## Level 3: Change coordinate frames

Contours originate in rendered-page pixels. Sol receives normalized guide
coordinates, while saved annotations may use provider page coordinates. Test
a nonzero target origin:

```powershell
uv run --no-sync python -c "from doclayout.layout_geometry import transform_points; print(transform_points([[0, 0], [200, 100]], (0, 0, 200, 100), (10, 20, 410, 220)))"
```

Expected output: `[[10.0, 20.0], [410.0, 220.0]]`. Open
`tests/test_layout_contours.py` and find the nonzero-origin and rotated-page
cases. Do not interpret a page-grid mask as a local crop mask.

## Level 4: Follow a page through reconciliation

Trace `DocumentBuilder` in `doclayout/builders/document.py` into the layout
matching functions in `doclayout/layout.py`. Sol reads the entire page and
provides text/HTML. Qualified V3 matches supply geometry and relative order.
Unmatched Sol blocks keep their text and geometry; unmatched V3 detections
remain diagnostic evidence without fabricated text. A V3 preparation or
inference failure falls back to a whole-page Sol request and records why.

```powershell
uv run --no-sync python -m pytest tests/test_layout_prior.py tests/test_layout_readiness.py tests/test_layout_contours.py
```

Locate tests for split/merge preservation, global matched order, page-furniture
visibility, and mixed success/fallback pages. A higher match count alone does
not establish better associations.

## Level 5: Check final outputs and saved fields

Follow the assembled `Document` through `doclayout/exports.py` and
`doclayout/ui/exports.py`. Annotations use final visible structure and source
lineage: V3 contours where usable, V3 rectangles on contour fallback, and Sol
rectangles for Sol-only blocks. Then read `doclayout/fields.py`: the optional
GUI field workflow starts from saved raw Markdown and metadata. Retrying fields
must not reconvert the PDF.

```powershell
uv run --no-sync python -m pytest tests/test_cli_exports.py tests/test_fields.py
```

Compare the [field guide](field-extraction.md) with its tests. Exact evidence
quotes and block-level boxes are different from word-level grounding.

## Level 6: Propose a change safely

Write down the owning module, relevant existing test, expected behavior,
fallback, and output metadata before editing. Add one regression test, make
the smallest implementation change, run the focused tests, and finish with
the [offline checks](development.md#offline-checks). Update the owning guide
and [contributor checklist](../CONTRIBUTING.md) as needed.

For a real-document accuracy study, use only an authorized fixture set and
report false matches, missed associations, contour alignment, order, and text
preservation separately. A mocked pass is not a live CUDA or model evaluation.

## Level 7: Trace a failure without losing the document

Use the existing mixed-page test as a capstone:

```powershell
uv run --no-sync python -m pytest tests/test_layout_prior.py -k mixed_page_failure_keeps_sol_box_and_successful_v3_match -v
```

In the test and implementation, identify the successful page's V3 geometry,
the failed page's Sol geometry, and the metadata that distinguishes them.
Then locate the final annotation path and explain why it cannot draw a V3
contour for the failed page. Check that the Sol request still contains the
whole-page image and that failure handling does not catch an invalid Sol
response or processor defect. If you can trace those facts to source and a
specific assertion, you can investigate a layout regression without
relabeling every fallback block as a detector miss.
