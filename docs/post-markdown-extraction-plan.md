# Plan: field extraction after Markdown generation

Date: 2026-09-23. Implementation update: 2026-09-25.

Conversion update, 2026-09-26: the separately authorized
[V3/Sol pipeline](layout-v3-plan.md) applies to new conversions. It does not
change this downstream workflow's saved-Markdown input or field-only retries.

## Current implementation contract

Local implementation was explicitly authorized. The [implementation guide](field-extraction.md)
describes the implemented local GUI workflow and runtime configuration:

- Preserve PDF-to-Markdown internals and exports. Feed only completed raw Markdown
  to Sol/medium, with all fields and distinct requests in one call per document.
- Written Markdown instructions and JSON Schema live in the separate downstream
  definitions directory. Keep diagnosis/service lists and stated code systems.
- Classification is explicitly off by default, not activated by editing its file.
  Future Luna/medium routing uses compact strict JSON with an enum reason and at
  most one exact source quote. It requires a defined category with score >= 0.75
  and exactly one extraction target.
- Process all uploads, with three active file jobs. Multiple files use all pages;
  a single file keeps page selection. Oversized Markdown goes to review unsplit.
- One PDF may produce multiple records named originalfilename_001, _002, etc.
  Retain the ten-column extraction table and JSON business payloads.
- Persist source artifacts locally and provide a separate Extracted information page with
  two-way block highlighting. Resolve geometry locally; flag ambiguous mappings.
- Live tests were authorized only for the seven selected pages of four masked PDFs.

## Historical research retained below

The sections below preserve earlier research: Databricks proposals,
recommendations to pass grounding metadata to the model, and notes from before
implementation was authorized. They are historical, not runtime instructions.
The contract above and implementation guide supersede conflicting recommendations.
Databricks deployment and word-level coordinate inference are not implemented.

## Purpose and boundary

Add a separate pipeline that reads the Markdown already produced by DocLayout,
extracts specified fields, validates the results, and stores them in a database.

Preserve the current PDF-to-Markdown implementation, CLI, prompts, model settings,
and export behavior. The new work starts at the completed Markdown output. It must
not require changes to the existing conversion path or rerun PDF conversion when
Markdown is already available.

The intended upstream workflow accepts incoming PDFs and converts all pages.
Users do not need to select pages. The downstream pipeline must consider all
available Markdown content; it must not silently truncate long documents.

## What we agreed today

- Implementation will happen later; this document records the plan only.
- Field extraction is a separate step after Markdown generation.
- A persistent `.md` prompt defines the required fields, their descriptions, and
  extraction instructions.
- The same prompt is reused for incoming documents until deliberately updated.
- Validated extracted fields are stored in a database.
- Azure Databricks is the proposed deployment environment discussed today.

The model, database, and operational choices below are recommendations to confirm
when implementation begins, rather than already implemented capabilities.

## Proposed workflow

```mermaid
flowchart TD
    A[Existing DocLayout conversion] --> B[Completed Markdown output]
    B --> C[Discover unprocessed documents]
    P[Persistent field extraction prompt.md] --> D[Extract structured fields]
    C --> D
    D --> E[Validate fields and supporting evidence]
    E --> F[Save validated results to database]
    E --> G[Record failures or items needing review]
```

1. Read completed Markdown from the existing output location. Preserve a reference
   to its source PDF and existing metadata when available.
2. Load the persistent extraction prompt and the agreed output schema.
3. Check processing records to identify new documents or explicitly requested
   reprocessing.
4. Extract the requested fields as structured JSON.
5. Validate the JSON structure, field types, required rules, and source evidence.
6. Save successful results and record processing status. Keep failed or ambiguous
   results available for retry or review.

## Bidirectional field-to-PDF grounding

The future extraction UI should connect every supported extracted field to its
source region in the original document. The interaction should work in both
directions:

- Hovering over or selecting an extracted field highlights its supporting region
  on the corresponding PDF page.
- Hovering over or selecting a grounded PDF region highlights the extracted
  fields supported by that region.
- Selecting either side may lock the selection and scroll the other view to the
  matching field or page.

The downstream extractor must therefore consume grounded blocks rather than
plain Markdown alone. Use the existing chunk output, or an equivalent internal
representation, to provide block IDs, page numbers, text, bounding boxes, and
polygons alongside the content presented to the model. Each extracted value must
return one or more evidence references containing at least:

```json
{
  "field": "Invoice total",
  "value": "$1,250.00",
  "evidence": [
    {
      "block_id": "page/0/Table/4",
      "page": 1,
      "quote": "Total: $1,250.00",
      "bbox": [420, 690, 550, 730],
      "polygon": [[420, 690], [550, 690], [550, 730], [420, 730]]
    }
  ]
}
```

Treat model-returned coordinates as untrusted references. Resolve coordinates
locally from the returned block ID and verify that the quoted evidence occurs in
that block before linking the field to the PDF. Reject or flag missing, invalid,
or mismatched evidence. Support multiple evidence blocks when a field depends on
several locations or pages, and allow one source block to support several fields.

The first implementation should highlight the smallest available supporting
block, such as a paragraph, table, or form region. Exact word-level highlighting
requires word coordinates and character alignment between recognized text,
rendered Markdown, and the PDF. Treat that as a later enhancement rather than a
requirement for initial block-level grounding.

## Persistent extraction prompt

Use two separate downstream definition files, loaded by the application:

- `extraction.md`: field meanings, business extraction rules, evidence rules,
  missing/conflicting values, and handling of “Same As Above”.
- `extraction.schema.json`: authoritative field names, types, nested objects,
  arrays, and permitted `null` values.

Their directory remains to be decided. Neither file is created by this planning
update. They must not replace the current PDF-to-Markdown prompts. Keep these
definitions out of Python source and version both files together. Each
`definition_version` must resolve to the exact prompt and schema snapshots.

The prompt should specify:

- Field names, descriptions, data types, and formats.
- Rules for repeated values, tables, and multiple entities in one document.
- How to resolve conflicting values and distinguish missing from ambiguous data.
- Evidence requirements, such as an exact source excerpt and a page reference
  when the existing Markdown or metadata supports one.
- Instructions to treat document content as data and return only the requested
  structured result.

Missing values should be `null`; the model must not invent values. Page references
must not be fabricated when the existing output does not retain page information.

Keep the prompt persistent across documents and version deliberate changes. Store
its version or content hash with every extraction. Maintain a versioned output
schema alongside it so validation has a stable contract. The schema is a separate
JSON file. Business-field changes affect the versioned JSON payload, not the
stable database columns.

## Selected extraction field scope

The user selected these groups after review of the specified BadgeCare and
Amerigroup pages. Insurance fields and optional clinical/device sections are
excluded. These are definition requirements, not generated runtime prompts.

| Group | Selected fields |
| --- | --- |
| Request | `request_date`, `provider_return_fax`, `authorization_reference_number` when supplied |
| Member | `first_name`, `last_name`, `date_of_birth`, `member_id`, `contact_phone`, `address`, `city`, `state`, `postal_code` |
| Referring provider | `name`, `npi`, `provider_id`, `tax_id`, `specialty`, `participation_status`, `contact_name`, `phone`, `fax`, `address`, `city`, `state`, `postal_code` |
| Servicing provider | Same provider fields, stored in a separate object |
| Servicing facility | `name`, `npi`, `provider_id`, `tax_id`, `participation_status`, `contact_name`, `phone`, `fax`, `address`, `city`, `state`, `postal_code` |
| Requested service dates | `service_start_date`, `service_end_date`, `scheduled_service_datetime` when separately stated |
| Diagnoses | Repeated codes, stated code system, descriptions only when provided; explicitly support ICD-10 |
| Procedures/services | Repeated codes, stated code system, modifiers, requested units/visits, frequency, duration, original request text; explicitly support CPT |
| Service selections | `service_types[]`, `places_of_service[]`; multiple selected options allowed |
| Priority | `expedited_requested`, `priority_evidence` |
| Other information | `additional_information` |

The subsequent discussion proposed explicit `icd10_codes[]` and `cpt_codes[]`.
Keep HCPCS Level II distinct from CPT (for example, the sample's `B9002`). A
separate `hcpcs_codes[]` was recommended. Final schema authoring should settle
whether these are the canonical lists or projections of `diagnoses[]` and
`requested_services[]`; do not maintain conflicting duplicate lists.

Preserve identifiers/codes as strings, dates by their stated role, and quantities
with the corresponding service. Keep requested dates separate from historical
encounters. Missing values are `null`; obscured or conflicting evidence needs a
review status. Resolve explicit “Same As Above” references with evidence for both
the reference and the source. A blank urgency selection does not prove an
explicit negative. Every accepted value must retain its source evidence.

## Classification activation and routing

- Missing or empty `classification.md`: bypass classification and send every
  completed Markdown document to the extraction stage; record that classification
  was bypassed, without inventing a category or score.
- Valid category definitions present: classify with Sol/medium and assign a
  category only at a score >= 0.75. Exactly 0.75 passes. Low scores, unknown types,
  and ambiguity go to fallout with a reason.
- With classification enabled, only one designated category reaches extraction;
  other confidently classified categories retain their result and skip extraction.
- Nonempty but invalid definitions are configuration errors, not permission to
  silently bypass. Missing target selection also blocks configured routing.
- Empty or invalid extraction instructions/schema mean extraction is not
  configured, even if classification was bypassed. Do not guess fields or call the
  extractor until both extraction files are valid.
- Snapshot definitions for each processing run. Edits apply to the next run and
  do not change the meaning of in-progress or historical results.

## Stable local extraction-results table

Hardcode the stable table structure in future application migrations. Load
business-field definitions from the Markdown and JSON Schema files instead of
duplicating them in application code. Store variable fields in JSON text.

| Column | Purpose |
| --- | --- |
| `id` | Unique extraction result ID |
| `document_id` | Reference to the source document |
| `status` | Success, failed, or needs review |
| `fields_json` | Selected business fields and code lists |
| `evidence_json` | Quotes, page references, and block IDs linked to field paths |
| `model` | Extraction model used |
| `reasoning_effort` | Selected effort, currently `medium` |
| `definition_version` | Exact extraction prompt and schema version |
| `created_at` | Extraction timestamp |
| `error_json` | Failure or validation details, when applicable |

This is a 10-column extraction-results table, not the total column count of the
database. No category column is required in this table. Document tracking,
definition versions, and classification attempts are separate record groups.
Additional extracted business fields require a definition version change rather
than new SQL columns. Preserve the definition version even when classification
is bypassed. Generate the downloadable JSON from the committed validated result;
track and retry export failures without rerunning extraction.

## Model recommendation

- Keep the existing PDF-to-Markdown model and configuration unchanged.
- Evaluate `gpt-6-luna` first for Markdown-to-fields extraction at volume.
- Compare `gpt-6-sol` on difficult documents and consider it as a fallback for
  defined validation failures or as the primary extractor if measured accuracy
  requires it.

No accuracy, throughput, or cost comparison for this new extraction task has been
performed. Select the production model using representative documents with known
correct fields. Valid JSON alone does not establish correct extraction, and model
self-reported confidence must not be the sole fallback criterion.

For documents exceeding the usable context budget, process bounded sections and
reconcile their results across the whole document. Preserve section provenance
and handle fields or tables spanning section boundaries.

## Storage recommendation

For Databricks, use Delta tables managed through Unity Catalog for extracted
records and processing records. Store PDFs, Markdown, and the persistent prompt
in approved file storage, such as Azure storage exposed through Unity Catalog
volumes.

Proposed record groups:

| Record group | Contents |
| --- | --- |
| Documents | Document identifier, source location, Markdown location and content hash |
| Extraction results | Validated business fields, supporting evidence, document identifier, extraction version |
| Processing attempts | Status, timestamps, model, prompt hash, schema version, errors, available token usage |

Use document/content identity and extraction configuration versions to define
reprocessing and duplicate handling. Coordinate concurrent attempts and use
controlled merges; a hash alone does not prevent simultaneous duplicate writes.
Keep historical results distinguishable when the prompt or schema changes.

Alternative destinations remain possible:

- PostgreSQL or Azure SQL if a separate application needs frequent record updates.
- SQLite for a local installation with serialized writes.
- DuckDB for local analytical use with coordinated writes.

Delta tables are the proposed Databricks destination, not a requirement for the
existing DocLayout application.

## Databricks execution

Package the downstream stage separately and invoke it through a Databricks Python
job. Confirm runtime and dependency compatibility before deployment.

Use a schedule or a file-arrival trigger on the completed Markdown location.
A trigger signals that work may be available; the job still needs processing
records to discover pending documents. Define a completion signal or equivalent
handoff check to avoid reading partially written outputs, without changing the
current conversion implementation.

Configure model credentials through the deployment's approved secret mechanism.
Keep credentials out of the prompt, Markdown, logs, and source code. Hosting on
Databricks does not by itself establish model availability through Azure OpenAI;
verify the selected API endpoint and network access separately.

Bound request concurrency across jobs, retry transient failures, and retain
document-level status so interrupted runs can resume. Confirm expected daily
volume, latency, API limits, and budget before choosing worker counts.

## Future implementation sequence

1. Confirm fields, schema, representative documents, evidence requirements, and
   the destination database.
2. Build the independent Markdown-to-JSON stage and persistent prompt loading.
3. Add validation, long-document handling, processing records, and database writes.
4. Compare Luna and Sol against known correct results; define failure and review
   rules from the measured outcomes.
5. Package and configure the Databricks job, storage access, credentials, and
   operational monitoring.
6. Verify restart behavior, duplicate handling, concurrency, and end-to-end volume
   processing before production use.

## Acceptance criteria for future work

- Existing DocLayout conversion behavior and implementation remain unchanged.
- Existing Markdown can be processed without reopening or reconverting its PDF.
- One persistent prompt applies consistently across a batch.
- All Markdown sections are considered, including long documents.
- Missing or unsupported fields are not invented; invalid results are flagged.
- Stored results can be traced to their source, prompt, schema, and model.
- Every accepted field has locally verified evidence linking it to one or more
  source blocks, pages, and PDF coordinates.
- The review UI supports field-to-PDF and PDF-to-field highlighting using those
  verified evidence links.
- Retries and concurrent jobs do not create unintended duplicate business records.
- Measured field accuracy, processing time, and API cost meet agreed targets.

## Decisions still needed

- Exact business fields and whether a PDF represents one or multiple records.
- Expected document sizes, daily volume, and processing deadlines.
- Final database and the consumers that will query its records.
- Prompt ownership, schema change policy, and reprocessing policy.
- Model endpoint, production model choice, and fallback/review rules.
- Storage paths, retention requirements, and job completion handoff.
- Location and packaging of the separate downstream implementation.
- Whether initial highlighting stops at block-level regions or also requires
  word-level coordinate alignment.

## References consulted during planning

- [Databricks Python script tasks](https://learn.microsoft.com/en-us/azure/databricks/jobs/python-script)
- [Databricks file-arrival triggers](https://learn.microsoft.com/en-us/azure/databricks/jobs/file-arrival-triggers)
- [Delta Lake in Databricks](https://docs.databricks.com/aws/en/delta)
- [OpenAI model guidance](https://developers.openai.com/api/docs/models)

Recheck platform capabilities and model availability when implementation begins.
