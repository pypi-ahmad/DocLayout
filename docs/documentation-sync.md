# Documentation sync verification

## September 26, 2026 — Archify diagram refresh

The five interactive diagrams were delivered from their JSON specifications.
The workflow now shows V3 before the whole-page Sol request and block matching
after validation. The data-flow legend spacing was adjusted. No runtime code,
prompts, model assets, or static PNGs changed in this diagram pass. The earlier
September 26 record below describes its own prior delivery and remains dated
evidence, not the status of these refreshed artifacts.

All five latest specifications pass 9/9 showcase checks with zero errors and
warnings. Their visual-check receipts pass viewport containment at 1440×900,
1600×1000, 1920×1080, and 2048×1320. Light and dark screenshots at the smallest
and largest sizes were inspected. Architecture, sequence, and data flow pass
perceptual review. Workflow still has excess right-side whitespace, and lifecycle
still has an empty recovery lane. Two focused correction rounds did not resolve
those two composition issues; further changes stopped under Archify's repair
limit. The lifecycle fallback-branch attempt was reverted to its last valid
specification, so its existing note, rather than a new branch, describes V3
failure continuing through Sol.

| Type | Specification SHA-256 | Artifact SHA-256 | Visual review | Correction rounds |
|---|---|---|---|---:|
| Architecture | `3087d910fff96e8ff561e1df1b18f0acc778b69fa2558a1fce444c106d87d437` | `b838c2e0f3a9e1f9980de698c7f2a41a61329678ca003062ad4e4f75e4825859` | Passed | 0 |
| Workflow | `7d9a68c2a5a7e8f0361453c48b47c5a505795260e555d3e36020acf76b4bf88c` | `e789661db1cd4d9681eba0ba81922515bcc2e06b46c083bea094e49ef512e1d0` | Failed: excess right-side whitespace | 2 |
| Sequence | `a3c6146c4a9f81e96fa8fa6c3ff85ab7890d5f825cdd44f5bc27e8fce4031b3b` | `253ee24894963a4472e42719ea02100c8940ad2f990abd3084c60580aff49fbd` | Passed | 0 |
| Data flow | `b37589c06657a0e7bee49d36adb9df3c6a03623d3ac5454e0464a504804a0f16` | `f0ac8c80e154b3afbbaab004b24e3670e04ebc5e476a40fd62b5ddc3a92d2973` | Passed | 1 |
| Lifecycle | `7d01ab4c1ec6ade5f0aa6c16bd1e4b88a02db36d0017a4b2c0305fe064d0db61` | `60adf8c1bfb2cd2e061a0131af0bd611e8cafd94dbd5dbcce5a8e5ff3e37441e` | Failed: empty recovery lane | 2 |

## September 26, 2026 — V3/Sol documentation sync

This pass describes the current local, unreleased checkout. It changes prose,
targeted docstrings, and managed documentation artifacts, not runtime behavior.
The September 25 records below remain historical evidence, not current results.

### Scope and preservation

Updated README, architecture, usage, configuration, development, field extraction,
project memory, layout implementation record, Unreleased notes, `.env.example`
comments, example/benchmark guides, fixture guidance, and the knowledge index.
Historical research and validation pages now distinguish their dated results
from the current V3 pipeline. Legal attribution and project instructions were
reviewed and preserved. The requested documentation skills kept this code-to-doc:
source contracts first, task-oriented guides next, then plain-language review.

The docs now distinguish V3 misses/rejected matches from engine failure, explain
Sol fallback, and record the limits of accepted matches, rectangular annotations,
processor changes, saved fallback reuse, and raw-Markdown-only field retries.
They describe the active ONNX backend rather than treating downloaded Transformers
weights as an installed runtime. No new accuracy or hardware-performance claim
was made.

Only docstrings changed in `doclayout/layout.py`, `doclayout/models.py`,
`doclayout/ui/batch.py`, and `doclayout/ui/exports.py`. A pre/post comparison found
identical executable ASTs in all 134 package Python files after stripping
docstrings. File hashes confirm that prompts, schemas, tests, dependency metadata,
`uv.lock`, `launch.cmd`, and unrelated pre-existing changes were untouched by this
pass. No commit, push, deployment, model download, live conversion, or app restart
was performed.

### Verification

| Check | Result |
|---|---|
| `uv run --no-sync python -m pytest -q` | 391 passed, 1 skipped in 92.19 seconds; offline |
| Ruff check and format check on the four docstring-edited modules | Passed; four files already formatted |
| `uv run --no-sync ty check` on those modules | One pre-existing error in `ui/exports.py:51`; full diagnostic below |
| ty on layout, models, and batch | Passed |
| Scoped public documentation | 46/46 public classes, top-level functions, and public methods have docstrings across those four files; excludes private/nested/dunder symbols, not a repository-wide coverage claim |
| Markdown links | 261 local file/heading links across 37 non-prompt Markdown files; no broken targets |
| Python documentation example | One code block parsed successfully; not executed against a document or API |
| CLI help | `doclayout --help`, `doclayout_single --help`, and `python benchmarks/inference.py --help` passed through `uv run --no-sync` |
| Knowledge bundle | OKF validation passed with no errors or warnings |
| Managed wiki | Ten page jobs reconciled; OpenWiki finish returned complete |
| Whitespace | `git diff --check` passed |

The first benchmark-help recheck used a nonexistent script name and exited 2;
the actual documented `benchmarks/inference.py --help` passed. No benchmark ran.
The bounded external-reference check read the official ONNX Runtime CUDA and
Transformers V3 documentation and used `hf models info` to confirm the pinned
ONNX repository's file listing. It did not download weights or establish hardware
compatibility beyond the existing evidence.

The unchanged type-check failure is:

```text
error[unresolved-attribute]: Attribute `decode_contents` is not defined on `None` in union `Tag | None`
  --> doclayout\ui\exports.py:51:22
   |
51 |     return "<div>" + soup.body.decode_contents() + "</div>"
   |                      ^^^^^^^^^^^^^^^^^^^^^^^^^

Found 1 diagnostic
```

### Archify delivery and limits

All five delivered HTML artifacts pass 9/9 showcase structural checks with zero
errors and warnings. Current visual-check receipts pass containment at 1440×900,
1600×1000, 1920×1080, and 2048×1320. Light/dark screenshots at the smallest and
largest sizes were inspected. Those automated passes do not prove visual polish.

Architecture and sequence pass visual review. Data flow has tight legend spacing;
lifecycle retains an empty renderer-generated recovery lane. Workflow retains
excess right-side whitespace and remains a pre-V3 snapshot: its content update
hit Archify's two-round repair limit, so this pass restored the prior specification
and labeled its links as historical. Use the current architecture/data-flow docs
for V3 behavior. A separate diagram-composition repair is the next step for these
remaining visual defects. Existing static PNG and ignored-artifact policy remain
unchanged; generated HTML was not edited by hand.

```json
[
  {
    "diagram_type": "architecture",
    "output": "D:/HCSC/DocLayout/docs/diagrams/doclayout-architecture.html",
    "specification_sha256": "3087d910fff96e8ff561e1df1b18f0acc778b69fa2558a1fce444c106d87d437",
    "artifact_sha256": "b838c2e0f3a9e1f9980de698c7f2a41a61329678ca003062ad4e4f75e4825859",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "passed",
    "correction_rounds": 0
  },
  {
    "diagram_type": "dataflow",
    "output": "D:/HCSC/DocLayout/docs/diagrams/doclayout-dataflow.html",
    "specification_sha256": "9cf0ec810fe5ba8d64d657a1449f84ea7a770ad5406eddc214155652fe4befe6",
    "artifact_sha256": "02ee23a2e2cdb07871288104c92acd2f929b2871ef714c57736e2fcc6d1b55e2",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "failed: tight legend spacing",
    "correction_rounds": 1
  },
  {
    "diagram_type": "lifecycle",
    "output": "D:/HCSC/DocLayout/docs/diagrams/doclayout-lifecycle.html",
    "specification_sha256": "7d01ab4c1ec6ade5f0aa6c16bd1e4b88a02db36d0017a4b2c0305fe064d0db61",
    "artifact_sha256": "60adf8c1bfb2cd2e061a0131af0bd611e8cafd94dbd5dbcce5a8e5ff3e37441e",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "failed: empty recovery lane",
    "correction_rounds": 1
  },
  {
    "diagram_type": "sequence",
    "output": "D:/HCSC/DocLayout/docs/diagrams/doclayout-sequence.html",
    "specification_sha256": "a3c6146c4a9f81e96fa8fa6c3ff85ab7890d5f825cdd44f5bc27e8fce4031b3b",
    "artifact_sha256": "253ee24894963a4472e42719ea02100c8940ad2f990abd3084c60580aff49fbd",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "passed",
    "correction_rounds": 1
  },
  {
    "diagram_type": "workflow",
    "output": "D:/HCSC/DocLayout/docs/diagrams/doclayout-workflow.html",
    "specification_sha256": "85dbd2f57a85dc7ece8a961e35c4e39bc3d731dba46968a144c6bba89e0e0c10",
    "artifact_sha256": "9fafa88ce4e920fe1a216f2ce8fb931745fe7f9f7ee733e79124055adfc82b88",
    "validation": "9/9 showcase; 0 errors; 0 warnings; prior content retained",
    "visual_review": "failed: excess right-side whitespace",
    "correction_rounds": 2
  }
]
```

## September 25, 2026 — historical pass

This is the record of the September 25, 2026 code-to-docs pass on the local checkout.
No release or publication took place as part of that pass.

## Scope

Updated the README, operating guides, architecture, configuration, development guidance, field guide, project instructions, knowledge index, unreleased notes, examples, and benchmark boundaries. The managed OpenWiki update completed all ten pages, including the new field-extraction workflow. Historical research, dated live observations, licenses, and attribution were preserved.

Google-style docstrings were added to downstream and support modules. No executable behavior, runtime prompts, or response schemas changed during this pass. The PDF-to-Markdown implementation was left untouched. Pydantic response-model class docstrings were excluded because they can change generated request schemas.

## Checks

| Check | Result |
|---|---|
| Offline suite | 248 passed, 1 skipped; no paid model calls |
| Executable syntax | All 131 Python files matched the pre-pass AST hashes after removing docstrings |
| Scoped public documentation | 37/37 public classes, functions, and methods documented across eight edited modules; excludes private/nested helpers and response-schema classes |
| Relative Markdown links | 200 file targets and 47 heading anchors checked, no missing targets |
| CLI and benchmark help | Both entrypoints returned successfully |
| Knowledge bundle | OKF validation passed without errors or warnings |
| Focused Ruff correctness | `F` and `E9` checks passed |
| Full focused Ruff style | Existing `SIM117` in `ui/costs.py` and `C408` in `usage.py` remain; verified in the pre-existing source |
| Whitespace | `git diff --check` passed |
| OpenWiki lifecycle | `finish` returned `complete` |

The relative-link counts were measured before this report was added. External URLs
were not revalidated. Mocked tests cannot establish live endpoint access, model
accuracy, or current latency.

## Diagram receipts

All three regenerated artifacts passed 9/9 showcase checks with zero composition errors or warnings. SHA-256 values below were checked against the delivered files. HTML files for workflow and lifecycle remain local generated artifacts under the repository's existing ignore rules; their specifications are the maintained inputs.

### Architecture

```text
diagram_type: architecture
output: D:/HCSC/DocLayout/docs/diagrams/doclayout-architecture.html
specification_sha256: 9cd92e9e61d68e279e88285108c4a4cbfd6b345730ddc1641796ad6d673f422a
artifact_sha256: 19f46d687ae1930dabbb1639b53311054f504851b36a3cad9a3895ba22aed9a6
validation: 9/9 showcase, 0 errors, 0 warnings
visual_review: passed
correction_rounds: 1
```

Desktop containment passed at 1440×900, 1600×1000, 1920×1080, and 2048×1320. Light/dark screenshots were inspected at the smallest and largest sizes.

### Workflow

```text
diagram_type: workflow
output: D:/HCSC/DocLayout/docs/diagrams/doclayout-workflow.html
specification_sha256: eefba65bcbb5ddf9050587f413f0cd49b6b4b4474903ba7beb1ab5797bcbefa0
artifact_sha256: 5d973b7f2f973b6c5e23ec4a9d99858ab55711265fca5b9cffcabae1ef78a69a
validation: 9/9 showcase, 0 errors, 0 warnings
visual_review: failed
correction_rounds: 2
```

The 1440×900 view is 907 pixels high, leaving seven pixels of vertical overflow. The diagram also uses its horizontal space unevenly. It is not visually accepted as a first-screen desktop composition.

### Lifecycle

```text
diagram_type: lifecycle
output: D:/HCSC/DocLayout/docs/diagrams/doclayout-lifecycle.html
specification_sha256: bcccf4b2e238fdeb6871f2e0b3c18f4690f526d79835c5dcf8724b80a15bcede
artifact_sha256: 0fcdcc11359fc95076da8dc64a37af821fb345c44d1a916528b3c6fc9518f5ad
validation: 9/9 showcase, 0 errors, 0 warnings
visual_review: failed
correction_rounds: 2
```

The 1440×900 view is 1223 pixels high. Other measured desktop sizes also overflow; an empty renderer-provided recovery lane consumes space. This artifact is not visually accepted.

Archify's two-round correction limit stopped further diagram repair. The last structurally valid artifacts remain available, with their visual limitations recorded rather than hidden. A separate diagram-layout pass is the remaining work if first-screen containment is required for both views.

## Follow-up sync: Sol extraction, navigation, and launcher (2026-09-25)

This pass updated current claims in maintained guides, unreleased notes, project
instructions, the knowledge index, and eight managed OpenWiki pages. Historical
research and published release notes retain their original models and behavior.
The current implementation notes explain which decisions supersede that history.
The humanizer pass simplified changed prose without changing technical identifiers.

Nine missing public docstrings were added in the upload/rendering support modules.
Across the 13 audited downstream/support modules, 55 of 55 eligible public symbols
now have docstrings. Four response-model classes were deliberately excluded:
Evidence, Statement, Draft, and Verification. Their docstrings can change generated
model schemas. This is scoped coverage, not a claim about every symbol in the repo.

### Current checks

| Check | Result |
| --- | --- |
| Full offline suite | 276 passed, 1 failed, 1 skipped; stale browser navigation locator described below |
| Focused fields, UI, summaries, launcher | 81 passed |
| Executable preservation | All 132 package Python ASTs unchanged after removing docstrings |
| Runtime resources | All six Markdown prompts and the field JSON schema byte-identical to the start of this pass |
| Documentation links | 42 Markdown files; 197 local links and 47 anchors checked; no missing targets |
| CLI and benchmark help | Both Click CLI help invocations and benchmark help passed |
| Support-module Ruff correctness | F and E9 checks passed |
| Support-module type check | One pre-existing optional-attribute diagnostic, reproduced below |
| OKF | Version 0.2 bundle validation passed without errors or warnings |
| OpenWiki | Eight page jobs completed; next-page and finish both returned complete |
| Diagrams | Five artifacts delivered with 9/9 showcase checks, zero composition errors/warnings; only architecture passed desktop visual acceptance |

Link counts were measured before adding this text. No paid extraction calls,
application restart, dependency change, commit, or publication occurred. This pass
did not modify workflows or verify that the locally present scheduled workflow is
deployed or enabled on GitHub. External URLs were not revalidated.

### Existing verification failures

The browser test still requests a link although the current sidebar uses buttons.
The relevant failure was:

```text
tests/test_ui_browser.py:290
page.get_by_role("link", name="Convert documents", exact=True).click()
playwright._impl._errors.TimeoutError: Locator.click: Timeout 30000ms exceeded.
Call log:
  - waiting for get_by_role("link", name="Convert documents", exact=True)
1 failed, 276 passed, 1 skipped in 69.49s
```

The scoped type check reported:

```text
error[unresolved-attribute]: Attribute `decode_contents` is not defined on `None` in union `Tag | None`
  --> doclayout/ui/exports.py:50:22
return "<div>" + soup.body.decode_contents() + "</div>"
Found 1 diagnostic
```

The documentation-only changes did not alter either failing expression. The next
code-maintenance task is to update the browser locator to the button role and
handle or narrow the optional HTML body type.

### Refreshed diagram receipts

Architecture contains the updated field model and results-page name. Its light
and dark captures were inspected at 1440×900 and 2048×1320; automated containment
also passed at 1600×1000 and 1920×1080. The other four specifications were unchanged
and their refreshed outputs retained their previous hashes.

At 1440×900, workflow is 907 pixels high, lifecycle 1223, dataflow 1318, and sequence
1515. Workflow fits the larger checked viewports; lifecycle, dataflow, and sequence
also overflow there. These artifacts pass structural validation but are not
accepted as first-screen desktop layouts. No layout redesign was attempted in
this content-sync pass; the earlier workflow/lifecycle repair limits remain
recorded above. Their visual-check sidecars contain current viewport measurements.

```json
[
  {
    "type": "architecture",
    "output": "D:\\HCSC\\DocLayout\\docs\\diagrams\\doclayout-architecture.html",
    "specification_sha256": "e2b46bee3afeabb1859ede6045d765025711f7a5d02e694c8a5ba825eaefa431",
    "artifact_sha256": "bed2b0ddbeb254d3aa65b2b8e88d506d5656f5a706af623432dc2c5ae61bdfcd",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "passed",
    "correction_rounds": 0
  },
  {
    "type": "workflow",
    "output": "D:\\HCSC\\DocLayout\\docs\\diagrams\\doclayout-workflow.html",
    "specification_sha256": "eefba65bcbb5ddf9050587f413f0cd49b6b4b4474903ba7beb1ab5797bcbefa0",
    "artifact_sha256": "5d973b7f2f973b6c5e23ec4a9d99858ab55711265fca5b9cffcabae1ef78a69a",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "failed: desktop overflow",
    "correction_rounds": 0
  },
  {
    "type": "lifecycle",
    "output": "D:\\HCSC\\DocLayout\\docs\\diagrams\\doclayout-lifecycle.html",
    "specification_sha256": "bcccf4b2e238fdeb6871f2e0b3c18f4690f526d79835c5dcf8724b80a15bcede",
    "artifact_sha256": "0fcdcc11359fc95076da8dc64a37af821fb345c44d1a916528b3c6fc9518f5ad",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "failed: desktop overflow",
    "correction_rounds": 0
  },
  {
    "type": "dataflow",
    "output": "D:\\HCSC\\DocLayout\\docs\\diagrams\\doclayout-dataflow.html",
    "specification_sha256": "d4831b0c1a70c399ab523c2da31be16078e08c9d05488db6d53e355145a54804",
    "artifact_sha256": "a854c5191c36134c5e227792428ae35cfe781feb8ab9f8dd74ad279fed9cabfd",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "failed: desktop overflow",
    "correction_rounds": 0
  },
  {
    "type": "sequence",
    "output": "D:\\HCSC\\DocLayout\\docs\\diagrams\\doclayout-sequence.html",
    "specification_sha256": "3fe2716e0eef2be96c0142695d80700f9e13b51327ac784385b774a6d7c77422",
    "artifact_sha256": "8c782672c01f2d6996460cfdc1e24f212de8560ed37c4f976329ed79222970fd",
    "validation": "9/9 showcase; 0 errors; 0 warnings",
    "visual_review": "failed: desktop overflow",
    "correction_rounds": 0
  }
]
```
