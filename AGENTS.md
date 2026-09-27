# DocLayout project instructions

## Preserve PDF-to-Markdown conversion

- The user is satisfied with the existing PDF-to-Markdown accuracy. Preserve its code, prompts, models, settings, interfaces, and export behavior when working on downstream classification or field extraction.
- Start the new workflow from completed raw Markdown and existing metadata. Reuse existing conversion artifacts; do not reconvert a PDF just to classify it or extract business fields.
- Changes to the upstream conversion pipeline require a separate explicit user request.

## Downstream implementation contract

- Local implementation and live tests on the seven specified pages of four masked PDFs are authorized. Publication, deployment, and upstream conversion changes are not authorized.
- Field extraction: `gpt-6-sol`, reasoning effort `medium`. Classification remains `gpt-6-luna`/medium and off by default.
- Classifier output is compact strict JSON: configured category or null, score, ambiguity flag, a reason enum (`matched`, `unknown`, `ambiguous`, `insufficient_evidence`), and at most one concise exact source quote. Generate readable fallout reasons locally; retain quote verification.
- Assign a document to a category defined in the classification prompt only when its classification score is >= 0.75. Exactly 0.75 passes the score gate. A score below 0.75, unknown type, or ambiguity goes to fallout with a reason. The number of categories is configurable; five was only an example.
- When classification is configured, only one designated category proceeds to field extraction. Other confidently assigned categories retain their classification but skip extraction. Do not invent the designated category.
- Classification is explicitly off by default (`DOCLAYOUT_CLASSIFICATION_ENABLED=false`), with zero classifier calls. Editing its template never enables it. Enabling it requires valid category definitions and one target; otherwise report a configuration error.
- Definitions live in `doclayout/prompts/fields/`, separate from conversion prompts. Load and snapshot the Markdown instructions and JSON schema per run. Send raw Markdown only to the field model; resolve evidence geometry locally from existing block IDs and metadata.
- Use one Sol/medium call for all fields and distinct requests in a document. Snapshot the extraction model/effort in the definition and fingerprint; do not reuse Luna extraction runs as Sol runs or relabel history. Name records `originalfilename_001`, `_002`, etc. Keep diagnoses and requested-services arrays; do not duplicate separate ICD/CPT/HCPCS lists.
- The main authorization form takes priority over supporting pages, independent of page order. Supporting pages fill blanks and compatible details; equally authoritative unresolved conflicts remain review issues. `request_date` means requested service date/range, never today's date, fax date, or initiation date. User-confirmed sample corrections belong only to that local result with an audit trail, not shared prompts.
- The GUI processes all uploads with three active file jobs. Multiple files use all pages without page selectors. Preserve single-file selection and the existing shared three-page API cap.
- Extracted information is a separate persistent UI page, with a readable Summary and a Source document view. Store source artifacts, JSON, and SQLite under git-ignored `conversion_results/field_extraction/`. Oversized inputs go to review without truncation or splitting.
- Sidebar navigation uses icon-free buttons with the current page highlighted. The Windows launcher automatically stops a recognized DocLayout listener on port 8471; other applications require confirmation. Restarting loses browser state and in-progress work, but preserves saved results.
- Intended outputs are validated field JSON and local SQLite storage. Hardcode stable storage columns, load business-field definitions from versioned files, and store extracted fields as JSON. The agreed extraction-results table has 10 columns and no category column; see the plan.
- Preserve source evidence. Resolve PDF coordinates from existing block metadata locally; do not invent coordinates from raw Markdown.
- Read the [implementation guide](docs/field-extraction.md) and [project memory](docs/project-memory.md) before downstream changes. Historical research recommendations do not override the implemented contract.

## Documentation maintenance

- Synchronize code-to-doc claims before editing prose. Preserve dated results and
  legal attribution; distinguish local unreleased work from published releases.
- Use Google-style docstrings in downstream and application-support code. Do not
  add docstrings to model-response Pydantic classes: their JSON schemas include
  those descriptions, so doing so changes model input.
- Keep runtime prompts and schemas unchanged during documentation-only work.
  Update diagram specifications through Archify and wiki pages through OpenWiki.

<!-- OPENWIKI:START -->

## OpenWiki

This repository has a generated `openwiki/` evidence index. It is optional just-in-time context, not required startup reading.

- Do not enumerate, preload, or search wikis at task start. Use retrieval when the user asks for it, when unfamiliar architecture or dependency behavior materially affects the task, or when source inspection leaves an important uncertainty. Stop once the question is grounded.
- When those conditions apply and OpenWiki retrieval tools are available, use `openwiki_search` for just-in-time context and `openwiki_read` for the relevant complete sections. If search returns `workspace_required`, ask which listed workspace to use and retry with its ID.
- Use `openwiki_list_workspaces` or `openwiki_list_wikis` when workspace membership itself needs to be discovered.
- If the retrieval tools are unavailable, read `openwiki/quickstart.md` and follow its links to the relevant pages.
- Treat source code and tests as authoritative. A brief's unknowns and review items are verification gaps, not automatic requirements.
- Prefer the narrowest quiet validation that proves the changed behavior. Preserve complete failure output.

The scheduled OpenWiki GitHub Actions workflow refreshes the repository wiki. Do not hand-edit generated OpenWiki pages unless explicitly asked; prefer updating source code/docs and letting OpenWiki regenerate.

<!-- OPENWIKI:END -->
