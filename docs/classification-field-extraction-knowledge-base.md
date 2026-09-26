# Knowledge base: classification and field extraction after Markdown

Researched: 2026-09-25. Historical research with a current implementation note.

For the later upstream conversion changes, see the [V3 integration record](layout-v3-plan.md).
V3/Sol fallback provenance accompanies new saved conversions; downstream requests
still use raw Markdown, and field-only retries never rerun layout or conversion.

## Implemented decisions take precedence

See the [implementation guide](field-extraction.md) and [project memory](project-memory.md).
Extraction instructions and JSON Schema are now written and loaded from a separate
downstream directory. Sol/medium receives raw Markdown only; chunk metadata stays
local for evidence mapping. Classification is explicitly off by default. Populating
its template does not activate it. Future activation requires configured categories
and one extraction target, using Luna/medium and an inclusive score gate of 0.75.
The classifier returns compact strict JSON with an enum reason and at most one
exact source quote; readable fallout reasons are generated locally. The older
Sol classifier and Luna extractor selections in the research below are superseded.

Local SQLite retains the ten-column extraction-results table with JSON business
fields, not generated SQL columns. The GUI processes every upload with three active
file jobs, supports multiple requests per PDF, and includes persistent two-way
field/PDF review on a separate page. Oversized inputs are flagged without splitting.

The research below records earlier thinking. Its recommendations on activation,
prompt readiness, grounding input, and long documents no longer describe the
implemented workflow; the decisions above supersede them.

## Decisions and boundaries

The existing PDF-to-Markdown pipeline is outside this feature's change scope. Consume its completed raw Markdown and existing provenance metadata. Classification is before business-field extraction, but after PDF transcription. The classification gate therefore saves unnecessary field-extraction work, not the cost of generating Markdown.

| Stage | User-selected model | Reasoning effort | Definition |
| --- | --- | --- | --- |
| Classification and routing decision | `gpt-6-sol` | `medium` | Future classification Markdown prompt |
| Business-field extraction | `gpt-6-luna` | `medium` | Future extraction Markdown prompt for the one designated category |

The official catalog lists both model IDs and medium effort support. The Responses API uses `reasoning.effort`; specify it explicitly rather than relying on defaults. This is capability evidence, not evidence of task accuracy or availability on the user's configured endpoint. No fallback model is approved by these decisions. [Model catalog](https://developers.openai.com/api/docs/models), [reasoning guide](https://developers.openai.com/api/docs/guides/reasoning).

The existing repository already uses these identifiers and medium effort in `doclayout/services/openai.py` and `doclayout/ui/chat.py`. Those are separate existing behaviors and must not be changed to implement the future stages.

## Proposed workflow

1. Discover a completed Markdown artifact and its source identity. Preserve all available pages and conversion-completion metadata.
2. Check that classification definitions and routing configuration are valid. Empty, missing, or placeholder-only definitions mean `not_configured`; make no classification call.
3. Ask Sol to classify the Markdown using the configured type definitions. Require a structured result containing a type identifier or unknown result, confidence, concise justification, and source evidence.
4. Apply the classification gate locally: the type must be defined in the prompt, its score must be a finite number in [0, 1] and >= 0.75, and the result and evidence must pass validation. Exactly 0.75 passes the score gate. Do not round the score before comparing it. Failed or ambiguous assignments always go to fallout with a reason.
5. Apply a separate extraction gate: only the one configured target category may proceed. Other confidently classified categories retain their classification and receive `classified_no_extraction`. For the target, resolve the configured extraction prompt and schema version. The model must not invent paths or database names. A missing or empty extraction definition blocks extraction as `not_configured`.
6. Ask Luna to extract only the configured fields from the original Markdown, with existing block metadata when grounding is required. Do not use the classifier's summary as a substitute for the document.
7. Validate field structure, types, evidence, and business rules. Persist accepted results in SQLite and publish the corresponding JSON export.

The classifier selects a type. Application routing checks that the type is defined,
meets the inclusive threshold, and matches the one extraction target. A high score
cannot make an undefined type eligible. Five categories was only an example; the
prompt may define a different number. At the time of this research, neither the
categories nor the extraction target had been supplied. A confidently classified
non-target document skips extraction because its category is outside the target,
not because its score is low.

## Prompts remain undefined for now

This research does not create or populate business prompt files. Future names such as `classification.md` and `extraction/<type>.md` are illustrative; their paths remain undecided. They must be separate from the current PDF transcription prompts, including `doclayout/prompts/extraction.md`.

The future classifier definition should describe allowed types, inclusion/exclusion criteria, distinctions between similar types, and when to return unknown or ambiguous. The extraction definition should contain field identifiers and descriptions, plus explicit types, formats, required/missing rules, repeated-value cardinality, and evidence requirements where needed.

Documents are input data, not instructions. Document text must not redefine the allowed types, threshold, requested fields, or routing configuration. Empty prompts must never mean “infer any type and extract whatever seems useful.”

## Routing and fallout

| Outcome | Future handling |
| --- | --- |
| Designated extraction category, score >= 0.75, valid evidence, configured extraction definition | Call Luna with the target definition |
| Another defined category, score >= 0.75, valid evidence | Retain classification; skip extraction with reason: non-target category |
| Score < 0.75 | Fallout: classification threshold not met |
| Unsupported or unknown type | Fallout: unsupported or unknown |
| Mixed document types or conflicting classification | Fallout: ambiguous; no automatic splitting without a later decision |
| Empty, incomplete, or unusable Markdown | Record input-quality failure; do not silently accept partial content |
| Invalid model output, refusal, timeout, or incomplete response | Record classification failure; bounded retry only where appropriate |
| Missing classification definitions, missing target selection, or missing target extraction definition | Record configuration blocker; no extraction |
| Field validation fails after accepted classification | Record extraction failure/review status separately from classification fallout |

Fallout preserves the original artifacts, attempts, and reasons for review or reprocessing; it is not deletion. No extracted business record should be fabricated for a skipped document. Missing fields in a valid extraction are `null` with an appropriate status, distinct from absent processing.

## Meaning of the 0.75 threshold

The user-selected gate is greater than or equal to 0.75 for assigning any category, independently of whether that category is the extraction target. The user calls this classification accuracy. Operationally, a per-document model score is distinct from measured accuracy across labeled examples and is not a verified probability of correctness. Published research found that calibration can fail to generalize to new tasks; therefore no general model capability establishes calibration on this document collection. [Calibration research](https://www.anthropic.com/research/language-models-mostly-know-what-they-know).

Before automatic production routing, use labeled documents containing each allowed type, confusing neighbors, unrelated documents, incomplete Markdown, and mixed packets. Measure precision among accepted documents, false acceptance of unsupported types, rejection of eligible documents, and score calibration by type. Keep threshold selection and evaluation data separate. Any later calibrated score must have its own version and an explicit definition of which score the gate uses.

## Can SQLite handle fields that do not exist yet?

Yes. SQLite supports JSON text and functions for validating JSON syntax and reading properties. Different records can carry different JSON keys while the surrounding table retains a stable structure. That means the database does not need a relational column for every future business field. JSON validity is not business-schema validation. [SQLite JSON functions](https://www.sqlite.org/json1.html).

Recommended design: a fixed operational schema with versioned JSON payloads. These are conceptual record groups, not implemented tables:

| Record group | Stable information | Variable content |
| --- | --- | --- |
| Documents | Document ID, source references, Markdown hash, completion status | Existing provenance metadata |
| Definition versions | Type ID, prompt hash, schema version, activation state | Prompt snapshot and field/schema definition |
| Classification attempts | Document ID, model, effort, status, score, route, timestamps | Classification evidence and result JSON |
| Extraction attempts/results | Document ID, classification attempt, definition version, status | Validated fields and evidence JSON |

Prompt and schema hashes must preserve historical interpretation. A retry should not overwrite a prior result under a different definition. Document identity plus stage, model/settings, definition version, and deliberate attempt identity support duplicate prevention and reprocessing. Use database uniqueness rules and transactions, not hashes alone.

SQLite is a reasonable local first choice if writes are short and serialized. It permits many readers but one writer at a time; numerous writers across machines or direct shared-network-file access favor a client/server database instead. Unknown field names are not themselves a reason to reject SQLite. [Appropriate SQLite uses](https://www.sqlite.org/whentouse.html).

WAL mode can allow readers and a writer to operate concurrently, but still permits only one writer and requires processes on the same host. Keep model calls outside write transactions. WAL is not a solution for distributed Databricks workers sharing one SQLite file. [SQLite WAL](https://www.sqlite.org/wal.html).

## What can be generated automatically later?

The future application can initialize its stable SQLite tables automatically. New business fields can then appear inside JSON payloads without changing those tables.

For a new prompt version, the recommended definition lifecycle is:

1. Read the user's field names and descriptions.
2. If the Markdown includes explicit structured type/cardinality rules, compile them deterministically into a JSON Schema. If it is free-form prose only, generate a proposed schema and surface unresolved types or meanings for review.
3. Validate and approve that definition version once, before batch processing. Do not infer a new schema separately for each document.
4. Request schema-constrained extraction and validate the returned data locally.
5. Store the resulting keys, values, and evidence in the JSON payload under that version.

Field name plus description alone can be ambiguous: an identifier may need leading zeros, an amount may need a currency, and a field may represent one value or a list. Avoid guessing these into permanent relational columns. Missing/ambiguous type decisions should block definition activation or remain explicit in the draft schema.

Structured Outputs can constrain response shape, but refusals and incomplete responses need separate handling, and schema conformity does not prove correct values. Pin the reviewed schema rather than asking the model to invent fields on every call. [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Automatic per-type SQL columns are possible as a later projection of approved definitions, but require deliberate migration rules for renaming fields, changing types, nested lists, old versions, and index maintenance. They are optional. Start with JSON storage; add approved query views or indexes for frequently queried fields when actual usage is known.

## JSON exports, evidence, and recovery

Recommend SQLite as the authoritative committed result and JSON files as reproducible exports of that exact payload. A database commit and a filesystem write do not form one shared transaction: track export status and retry failed exports without rerunning the model. Retain classification records and fallout reasons even when no field JSON exists.

For PDF highlighting, carry existing grounded chunks alongside raw Markdown. Return exact quotes and block IDs, verify quotes locally, and resolve page numbers and coordinates from trusted existing metadata. Raw Markdown alone cannot recreate missing geometry. Preserve the existing plan's block-level evidence contract; no upstream parser change is implied.

Long documents must not be silently truncated. If context limits require segmentation, account for every section and reconcile document-level classification before routing. Treat unresolved disagreement or mixed types as fallout; retain cross-section evidence during field extraction.

## Verification before future implementation is accepted

- Empty prompts produce no downstream model calls and no invented business schema.
- Classification uses Sol/medium; extraction uses Luna/medium; neither changes upstream settings.
- Threshold boundaries, unknown types, invalid scores, missing routes, and refusals route correctly.
- Only the one configured target category reaches extraction. Other valid categories are stored as classified without extraction. Category count is not fixed at five.
- A score below 0.75 always falls out with a reason; a valid score of exactly 0.75 or higher permits category assignment but does not override the extraction-target restriction.
- Representative held-out samples establish classification and field accuracy, latency, and cost. No such measurements have been performed here.
- New field definitions work without editing the stable database schema; earlier results remain readable under their original versions.
- Retries, concurrent attempts, interrupted writes, and export failures do not create unintended duplicate accepted records.
- Existing PDF-to-Markdown behavior and its artifacts remain unchanged.

## Sources and refresh scope

Research used official OpenAI and SQLite documentation plus original confidence-calibration research, collected through web retrieval and Firecrawl search. All links above were consulted on 2026-09-25. Recheck endpoint-specific model support, output-schema compatibility, and the installed SQLite runtime at implementation time.

Local evidence: [earlier downstream plan](post-markdown-extraction-plan.md), [project memory](project-memory.md), [existing Sol service](../doclayout/services/openai.py), and [existing Luna chat](../doclayout/ui/chat.py). This document supersedes earlier open model/database recommendations for the local downstream feature; Databricks remains a separate future deployment decision.

Reproduction: research the same linked sources for a reference knowledge base on prompt-defined document classification, confidence gating, schema-constrained extraction, and SQLite JSON storage. Update this Markdown only; do not run billable document evaluations or alter application code as part of a research refresh.
