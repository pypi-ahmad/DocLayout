---
type: Workflow
title: Classification, fields, and review
description: Markdown-only Sol extraction, optional Luna routing, local evidence checks, saved runs, and explicit retries.
tags: [fields, classification, grounding, sqlite, review]
sources:
  - id: openwiki-source-3fc18d2b3bd86c90ce3a3ddd
    resource: repo://doclayout/field_store.py
  - id: openwiki-source-15837773bd4113ac5b1f7ae1
    resource: repo://doclayout/fields.py
  - id: openwiki-source-a5f451942951e89c5cc3ac8f
    resource: repo://doclayout/prompts/fields/classification.md
  - id: openwiki-source-f9ad6c3a550e71ab6aa1818c
    resource: repo://doclayout/prompts/fields/extraction.md
  - id: openwiki-source-9859ea909075322f3cad112e
    resource: repo://doclayout/prompts/fields/extraction.schema.json
  - id: openwiki-source-78143bbf8e0e918bf100317b
    resource: repo://doclayout/scripts/app_pages/review.py
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-51b6aa7d36018bd3566db002
    resource: repo://tests/test_field_summary.py
  - id: openwiki-source-97c2d91c6ec415fd43007ed6
    resource: repo://tests/test_fields.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# Classification, fields, and review

This workflow starts after GUI conversion saves raw Markdown and chunk JSON. It does not read the original PDF for field extraction. The extraction instructions live in `doclayout/prompts/fields/extraction.md`; a fixed JSON Schema describes request, member, separate provider/facility roles, service dates, diagnoses, services, selected options, priority, and notes. ICD-10 and CPT values are captured only when stated, with no code-system or description lookup.

## Routing

The classification template currently has no business categories or extraction target. Classification defaults to disabled and makes no call. Editing its Markdown does not switch it on. To enable it, set `DOCLAYOUT_CLASSIFICATION_ENABLED=true` and define one extraction target among the configured categories. The number of categories is not fixed.

Enabled classification uses Luna with medium reasoning and strict closed JSON: a configured category or null, score, ambiguity flag, reason enum, and at most one quote. Local checks require a finite score of at least 0.75, an unambiguous matched category, and a quote present in raw Markdown. A qualifying target goes to extraction. A qualifying other category becomes `classified_no_extraction`; rejected classification becomes `fallout` with reasons. The model's score is a routing signal, not measured accuracy.

## Extraction and evidence

One logical Sol/medium request extracts all records and configured fields. The complete raw Markdown is subject to a byte limit; it is never silently truncated. The response must be complete JSON that passes the configured schema. The prompt requires an exact source quote for each populated field leaf, including false booleans and array items. Missing values are null or empty arrays; uncertain boundaries and unresolved conflicts become issues.

The main authorization form takes priority over supporting forms, regardless of page order. Supporting pages fill blanks or compatible fuller details. Equally authoritative unresolved conflicts stay null with an issue. Explicit Same As Above links copy the resolved source provider. `request_date` means requested service date or date range, never today's date or the initiation date; a single date does not imply an end date. These are prompt instructions, not independent proof that each model answer followed them.

Quotes preserve Markdown and HTML exactly, apart from local whitespace normalization. Participation evidence includes role context so identical checked options can map uniquely. Local validation deduplicates identical field/reason warnings and avoids adding a missing-quote warning for an already rejected quote, while retaining independent issues.

Local grounding checks quotes against raw Markdown and uniquely matches readable quotes to saved chunks. It derives page and block IDs and accepts only finite boxes inside page bounds. Missing or ambiguous mapping produces `needs_review`. A complete accepted result is `success`; response or provider failures become `needs_review` or `failed` according to the caught error. These checks make evidence inspectable but cannot guarantee the model chose the correct clinical or administrative meaning.

## Persistence and retries

`FieldStore` uses SQLite tables for documents, definitions, runs, and extraction results. It stores field/evidence JSON in fixed columns; there is no dynamic column per prompt field and no extraction-results category column. Definition fingerprints include extraction model and reasoning effort, so a Sol run does not reuse a Luna extraction result. Matching saved runs, including review or failed results, are reused until explicit retry. Field retry reads saved `raw.md` and `chunks.json` without repeating Sol conversion. Export retry recreates record JSON from SQLite without a model call. Extracted information loads saved results and source regions across sessions, with readable Summary and Source document views.

The GUI processes at most three files concurrently and isolates failures per file. Source bytes and derived artifacts remain local without automatic expiry. Mocked field tests cover the inclusive 0.75 gate, invalid classification JSON, quote grounding, persistence, cache reuse, and retry behavior. They do not measure live accuracy.

New conversions may supply V3-selected geometry or recorded Sol fallback geometry; the field request still receives only raw Markdown. A successful Sol fallback conversion can proceed to fields normally. Field-only retry never prepares V3, downloads weights, or reconverts the PDF. Local grounding refuses a single-page location for a block whose layout lineage spans multiple source pages, leaving it for review rather than inventing coordinates.

## Related pages

- [Document conversion](document-conversion.md)
- [Interfaces](../interfaces/cli-gui-api.md)
- [Configuration and testing](../operations/configuration-and-testing.md)
