# Markdown field extraction and review

After conversion, the local GUI extracts authorization fields from the completed
Markdown. This does not change conversion internals, prompts, models, the CLI, or
the HTTP API. The CLI, Python converter, and HTTP endpoints do not run this field
workflow automatically. Its model settings are separate from Sol page conversion
and Luna chat.

## Use the GUI

1. Open **Convert documents** and upload files. One file retains page selection.
   Multiple files use all pages; three file jobs run and the remainder wait.
   Existing conversion still permits three page API requests across the process.
   PDF rendering uses local CPU/RAM and remains protected by the existing lock.
2. Click **Run DocLayout**. Each completed Markdown document proceeds to field
   extraction. A failed file does not stop the batch. Existing conversion tabs and
   downloads remain available for each selected result.
3. Click **View extracted information** beside the selected result, or open
   **Extracted information** in the sidebar to browse saved results. The button
   opens that document's saved run. For multiple requests, use the **Request** selector.
   **Summary** groups member, provider, date, priority, and other information into
   readable sections, with diagnoses and requested services in tables. Missing
   values are hidden unless **Show missing information** is enabled; **Not found**
   is not automatically an error. Explicit negative values remain visible as **No**.
4. Check **Items to check** for saved review reasons. Open **Source document** to
   inspect quotes and original PDF regions. Hover either side or click to select.
   **Jump to field** uses readable labels and navigates to supporting pages.
5. Use **Download data (JSON)** for the original saved record. **Technical details**
   contains raw JSON and processing metadata. Under **More actions**, **Extract again**
   explicitly makes new API calls from saved Markdown without reconversion.
   **Retry JSON export** makes no model calls.
   Ordinary navigation, previews, and downloads do not call models.

Distinct requests become `originalfilename_001.json`, `_002.json`, and so on.
Multiple procedures for one request stay in one record. Per-document/run folders
prevent same-filename collisions. Unsupported candidates keep a review status.
Even schema-valid JSON with an exact quote may contain an incorrect value.

## Definitions and API behavior

The directory `doclayout/prompts/fields/` is separate from conversion prompts:

- `extraction.md` defines the selected fields, provider roles, request grouping,
  missing/conflicting values, and exact-quote requirements.
- `extraction.schema.json` defines business keys/types and a fixed response envelope:
  `records` and `document_issues`. Each record has `fields`, `evidence`, and `issues`.
  Keep objects strict, all keys required, and unavailable scalar values nullable.
- `classification.md` is a general template without invented categories.

`gpt-6-sol`, medium reasoning, receives the complete raw Markdown and strict schema
in one logical Responses API call. No PDFs, images, or chunk JSON are supplied to
the field model. Definitions are snapshotted and hashed per run; edits affect the
next explicit run, not historical records. Business fields are not duplicated in
Python or expanded into database columns.

The definition includes request, member, referring/servicing provider, facility,
service-date, diagnosis, procedure, selected-option, priority, and note fields.
Keep `diagnoses[]` and `requested_services[]`; code systems are stated values,
including ICD-10/CPT/HCPCS, not model lookups. Missing scalars are null; empty
collections are allowed. False urgency requires an explicit negative/routine
selection. Redaction, unresolved conflicts, and uncertain request boundaries require review.

The main authorization form takes priority over supporting forms, regardless of
page order. Supporting pages fill blanks and compatible details, including fuller
addresses/contact names and explicitly linked facility aliases. Same As Above
copies the resolved source provider. Unresolved conflicts between equally
authoritative sources remain review issues; names and identifiers are never repaired
by guessing.

`request_date` is displayed as **Requested service date** and means the stated
service date/range, not today's date, a fax timestamp, or Date Initiated. A single
service date also populates `service_start_date`; `service_end_date` stays null.

Extraction model and reasoning effort are included in the definition snapshot and
fingerprint. Sol runs do not reuse cached Luna results. Historical records retain
their original model, values, and evidence; retries create new runs.

Quotes are checked against Markdown with whitespace normalization. The application
resolves geometry locally from existing block IDs and page bounds. Missing or
ambiguous mappings are flagged without invented boxes. Highlighting is block-level,
not exact word-level. Existing chunk exports remain unchanged; original page indices
are obtained from block IDs where the legacy chunk `page` property differs.
Quotes must preserve exact HTML tag order; role headings distinguish identical
participation checkboxes. A rejected quote produces a specific warning without an
additional no-verified-quote warning for that same failure. Independent issues remain.

Requests use `store=false`, a 180-second timeout, 32,768 output tokens, and at most
two SDK transport retries. No automatic repair or verifier-model call is made.
The complete serialized request has a conservative 900,000-byte safety budget,
configurable downward using `DOCLAYOUT_FIELD_MAX_INPUT_BYTES`. This byte budget is
not the model's token capacity. Oversized inputs and incomplete responses go to
review without truncation or splitting.

## Classification remains off

`DOCLAYOUT_CLASSIFICATION_ENABLED` defaults to `false`. Editing the template does
not enable classification; no classifier requests are made while disabled.

For future configuration, put one category identifier under `## Extraction target`.
Under `## Categories`, add each identifier as a `###` heading followed by its
definition and inclusion/exclusion criteria. Explicitly set
`DOCLAYOUT_CLASSIFICATION_ENABLED=true` in the launching process and restart.
Enabled but incomplete definitions produce a configuration error.

Configured classification uses `gpt-6-luna` with medium reasoning on raw Markdown.
Its strict JSON response contains only `category` (configured identifier or null),
`score`, `ambiguous`, `reason`, and `quotes`. The reason is one of `matched`,
`unknown`, `ambiguous`, or `insufficient_evidence`; quotes contains at most one
concise exact source quote. No free-text explanation or surrounding prose is requested.
Readable fallout reasons are generated locally, not supplied by the model.

Assignment requires a defined category, score **>= 0.75**, a verified quote,
reason `matched`, and no ambiguity. Otherwise it
falls out with a reason. Only the extraction target proceeds; other accepted types
are `classified_no_extraction`. The score is self-assessed confidence, not measured
accuracy or a verified probability.

Classifier-enabled fingerprints additionally include the classifier model, medium
effort, and response contract version. Changing only the classifier model leaves
disabled-classification fingerprints unchanged. Historical saved classification
results remain readable without migration or model calls.

## Run outcomes and retries

New conversions attempt V3 layout analysis before Sol transcription. Layout
failure does not prevent field extraction when Sol conversion succeeds. Saved
conversion provenance distinguishes V3 matches, Sol-only blocks, and unavailable
layout. Field retries consume the saved raw Markdown and chunks without preparing
V3, rendering pages, or changing historical geometry. A saved fallback conversion
is not automatically replaced when the local engine becomes available.

| Status | Meaning |
| --- | --- |
| `success` | At least one record; no recorded grounding or document issues |
| `needs_review` | Grounding/document issues, no request found, oversized input, refusal, or incomplete response |
| `fallout` | Classification cannot support assignment at the required threshold |
| `classified_no_extraction` | An accepted category is not the extraction target |
| `failed` | Provider, parsing, schema-validation, or processing failure |

`success` means the application checks passed; it does not mean the values were
clinically verified.
Document identity includes original bytes, filename, conversion options, and the
conversion pipeline fingerprint (including layout execution/fallback policies).
A matching saved document and definition reuses its run, including review or failed
outcomes. Use explicit retry to request a new field run. A definition change uses
the saved Markdown, not another conversion. A failed conversion has no completed
document manifest and can be attempted again by Run DocLayout.

## Persistence and privacy

The default root is `conversion_results/field_extraction/`, under the configured
output directory. It retains local `results.sqlite3`, original upload bytes,
preview sources, raw Markdown, grounding metadata, conversion ZIPs, and record JSON.
Saved review works after restart. The directory is ignored by Git but is not
encrypted by the application. Apply suitable local access controls and retention;
there is no automatic deletion or external synchronization. Keep SQLite on local
storage, not a shared network drive.

SQLite uses WAL and short serialized writes; model calls do not hold database
transactions. The extraction table has ten columns: `id`, `document_id`, `status`,
`fields_json`, `evidence_json`, `model`, `reasoning_effort`, `definition_version`,
`created_at`, `error_json`. There is no category column. Separate tables hold
documents, definition snapshots, and processing runs. JSON is exported from committed
records and can be regenerated without another extraction.

The existing resolver consumes `OPENAI_API_KEY` and `OPENAI_BASE_URL`. Credentials
are never copied to prompts, artifacts, or browser code. `store=false` alone does
not establish zero retention or regulatory compliance.

## Verification

Earlier local verification on 2026-09-25: 235 tests passed and one integration test was
skipped. Ruff, formatting, type checks, and affected documentation links passed.
Browser tests covered batch upload, hidden batch page controls, record downloads,
saved review after reload, two-way highlighting, and no repeated conversion calls.

The earlier authorized live smoke test produced one record each for Amerigroup and both
RealSolutions samples. Those historical runs remain `needs_review`, including source conflicts,
redaction, and ambiguous block mappings. Local revalidation mapped 76 of 79,
42 of 71, and 40 of 40 verified quotes respectively; no model was called for that
revalidation. BadgeCare failed on both attempts in the unchanged conversion stage:
`GPT-6 Sol request failed: ValidationError`. Its downstream extraction could not be
verified. These observations are not a general accuracy benchmark.

Machine-readable live receipts remain in the ignored output directory as
`smoke-report.json` and `grounding-report.json`. The three successful extraction
attempts and their review candidates are available in Extracted information.

### Sol extraction follow-up (2026-09-25)

After the model/prompt update, the full suite passed with 269 tests and one skip.
Focused extraction and summary tests passed (55 tests); affected Python files passed
Ruff and type checks. One new Sol/medium extraction used the existing Amerigroup
pages 1–2 raw Markdown, with classification disabled and no PDF reconversion.
The new model run (`48354a9ca05f42b2a360011d41de4c2c`) had zero review issues,
compared with 43 in the reviewed historical run. It retained seven diagnosis codes
and four CPT codes and used the requested service date for `request_date`.

A separate local result (`f6caca27e5f5426082b3c17b4972c15d`) applies the user's
document-specific surname confirmation. Its run metadata records the original run,
before/after value, reason, and source quote; no additional model call was made.
All evidence in that result passed exact quote validation and unique block mapping;
the exported JSON matched SQLite. Saved raw Markdown, chunks, and historical result
exports were unchanged. These checks demonstrate this sample's behavior, not a
general extraction-accuracy guarantee. Generated wiki/diagram snapshots were not refreshed.

```powershell
uv run python -m pytest tests/test_fields.py tests/test_ui.py tests/test_ui_browser.py -q
```

The following checker is explicitly billable. It uses only the seven approved
pages: BadgeCare Plus 1–2, Amerigroup 1–2, RealSolutions 1 pages 2–3, and
RealSolutions 2 page 1. Completed artifacts are reused.

```powershell
uv run python -m doclayout.scripts.check_field_samples --input-dir "PATH_TO_MASKED_PDFS"
# Local evidence revalidation only; no model calls:
uv run python -m doclayout.scripts.check_field_samples --input-dir "PATH_TO_MASKED_PDFS" --revalidate-saved
```

## Sources

- [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering)
- [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)
- [GPT-6 Sol](https://developers.openai.com/api/docs/models/gpt-6-sol)
- [PDFium threading constraints](https://pypdfium2.readthedocs.io/en/stable/python_api.html#incompatibility-with-threading)
