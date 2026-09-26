# DocLayout project memory

Updated: 2026-09-26. Source: explicit user decisions in this repository's conversation.

## Downstream scope and later conversion authorization

The user finds the current PDF-to-Markdown pipeline highly accurate and wants it
preserved. That assessment is user feedback, not a measured benchmark. Downstream
classification and field extraction consume completed raw Markdown without changing
conversion code, prompts, model choices, settings, or exports.

The user authorized local implementation. The GUI now includes extraction, parallel
file jobs, SQLite/JSON persistence, and a separate review page. This authorization
did not cover publication, deployment, or upstream conversion changes. See the
[implementation guide](field-extraction.md).

The user subsequently authorized the separate PP-DocLayoutV3 integration for new
conversions and then explicitly requested Sol fallback when V3 misses, mismatches,
or fails to run. The implemented policy attempts V3 before whole-page Sol;
unaccepted matches retain Sol content/geometry, and runtime failures continue
without a layout prior with explicit fallback provenance. Conservative matching
cannot detect every visually wrong match. This later authorization does not change
the downstream raw-Markdown contract or authorize publication/deployment.

The active backend is the pinned official ONNX artifact, not Transformers.
Downloading the official Transformers weights did not switch the runtime.
CUDA readiness requires exercised kernels; its single ScatterND node is verified
on CPU. Explicit CUDA forbids a replacement CPU session, while conversion still
uses Sol if the engine fails. Saved fallback conversions remain reusable; recovery
of V3 does not automatically reconvert them. See the
[layout integration record](layout-v3-plan.md) for contracts and evidence.

## Downstream decisions

- Classifier: `gpt-6-luna`, medium reasoning effort. Return compact strict JSON only, with category, score, ambiguity, an enum reason, and at most one concise exact source quote. Generate readable fallout reasons locally.
- Field extractor: `gpt-6-sol`, medium reasoning effort. Model and effort are snapshotted and included in the cache fingerprint; historical Luna runs remain unchanged.
- Assign a category only when the classification score is >= 0.75. Exactly 0.75 passes the score gate. Scores below 0.75 always go to fallout with a reason, as do unknown or ambiguous classifications.
- When classification is enabled, only one designated category proceeds to extraction. Other confidently classified categories retain their type and skip extraction. The designated category will be supplied later.
- Category definitions are configurable. The five-category example does not set a fixed count.
- The user calls this classification accuracy; operationally it is a per-document score. Measured accuracy across labeled documents is a separate evaluation metric.
- Classification is explicitly disabled by default with zero calls. Editing the Markdown does not activate it. Explicit activation requires valid category definitions and one target; incomplete configuration fails before processing.
- Written definitions live in `doclayout/prompts/fields/`: extraction Markdown plus authoritative JSON Schema, and a general unconfigured classification template. Snapshot definitions per run; do not duplicate business fields in Python.
- Use one Sol/medium extraction call per raw Markdown document, including all fields and distinct requests. Keep `diagnoses[]` and `requested_services[]` with stated code systems rather than duplicate code lists. Missing scalars are null; unresolved conflicts/redaction require review.
- The user selected authorization-form-first source priority. Supporting forms fill blanks and compatible fuller addresses/contact names; explicit facility aliases are accepted. Apply Same As Above after resolving the source provider. Equally authoritative unresolved conflicts still require review.
- `request_date` means requested service date/date range, not today's date or Date Initiated. Single dates also populate service_start_date; no end date is invented. Document-specific user confirmations are recorded locally with provenance, never hardcoded into shared extraction prompts.
- One PDF may contain several records. Name records and exports `originalfilename_001`, `_002`, etc. Multiple procedures for one request are not separate records.
- Process all uploads with three active file jobs. Multiple files use all pages without selectors; single-file selection remains. Preserve the upstream shared three-page-request cap and PDFium lock.
- Oversized Markdown goes to review without splitting or truncation. Model input contains raw Markdown only; existing chunks are used locally for quote-to-region mapping.
- Produce validated field JSON and persist local results in SQLite. Hardcode the stable 10-column extraction-results table listed in the plan, with no category column. Business values live in `fields_json`; evidence lives in `evidence_json`. Business-field additions do not require SQL columns.
- Preserve originals, Markdown, metadata, and records under git-ignored local `conversion_results/field_extraction/`. The Extracted information page supports saved review after restart, a readable Summary with missing values hidden by default, and two-way block highlighting in Source document. Ambiguous/missing mappings are flagged rather than guessed. Browsing does not run extraction again.
- Authorized live evaluation is limited to the seven previously specified pages of four masked PDFs. Three produced records with review flags; BadgeCare failed twice in unchanged conversion with an upstream ValidationError. No general field-accuracy benchmark is established.

## Navigation and restart behavior

The sidebar uses icon-free Convert documents and Extracted information buttons,
with the active page highlighted. Navigation does not run a model.
`launch.cmd` stops a recognized DocLayout listener on port 8471 before launching.
Other applications require confirmation; failed cleanup aborts launch. Restarting
loses in-progress work and browser state, while saved results remain available.

The later Amerigroup pages 1 and 2 Sol/medium run passed local review checks. A
separate saved result records a user-confirmed surname correction with provenance.
This does not establish general model accuracy; earlier results remain historical.

## References and precedence

Documentation synchronization is code-to-docs. Google-style docstrings are approved
outside the protected conversion pipeline, but model-response classes are excluded
because their docstrings alter generated request schemas. No documentation task
authorizes changing runtime prompts, classification categories, or application logic.

The [knowledge base](classification-field-extraction-knowledge-base.md) explains the research, routing policy, schema lifecycle, storage tradeoffs, and verification gaps. These newer model and local-storage decisions supersede the older plan's open model/database recommendations for this local workflow. Databricks deployment remains a separate future proposal.
