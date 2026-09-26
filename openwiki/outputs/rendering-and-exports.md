---
type: Output architecture
title: Rendering and exports
description: Conversion formats, destination safety, and separate persisted business records.
tags: [rendering, exports, markdown, sqlite]
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-96e22e9964ec5dc995a862c1
    resource: repo://doclayout/exports.py
  - id: openwiki-source-3fc18d2b3bd86c90ce3a3ddd
    resource: repo://doclayout/field_store.py
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-24f0edb7a6f534afb5bf8bd5
    resource: repo://doclayout/renderers/chunk.py
  - id: openwiki-source-4bf827c6803e4aac3683e040
    resource: repo://doclayout/renderers/json.py
  - id: openwiki-source-cdaa752a3f645f8ee144bcdd
    resource: repo://doclayout/renderers/ocr_json.py
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-ac5d0f22367daa23e677df71
    resource: repo://doclayout/ui/exports.py
  - id: openwiki-source-154e6a78b00ef865edbb429b
    resource: repo://tests/test_cli_exports.py
  - id: openwiki-source-97c2d91c6ec415fd43007ed6
    resource: repo://tests/test_fields.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# Rendering and exports

Renderers consume one completed in-memory `Document`; choosing several formats does not repeat page extraction. `document_exports()` always renders Markdown, then adds requested HTML, hierarchical JSON, flattened chunks, metadata, image crops, or annotations. A requested ZIP builds the complete GUI conversion bundle. The GUI's HTML is generated from exported Markdown and sanitized before display or download.

Conversion JSON describes block hierarchy and geometry. Chunk JSON flattens page blocks while retaining IDs, page information, bounding boxes, and assembled content. These files support evidence lookup but are not the business-field response schema. The GUI separately produces field and evidence JSON, with diagnoses and services remaining arrays.

Layout-aware exports follow processed structure, not the original V3 detection list. Metadata includes the layout manifest, device and timing, initial match counts, original regions, final block bounds/order, and source lineage. Unmatched V3 regions remain diagnostics and add no duplicate Markdown. Unmatched Sol blocks preserve their validated content and box with `sol_only` provenance, subject to the normal downstream processors.

Annotations draw rectangles around visible final structure. For cross-page merges, they retain source-page footprints rather than projecting one union onto every page. Raw V3 mask data is metadata only: neither the annotated image nor raster PDF is polygon-accurate. OCR JSON likewise reports block boxes, not invented character coordinates.

Filesystem outputs are named from a sanitized source stem and timestamp. `output_targets()` resolves every intended path before writing anything. It rejects traversal, absolute or drive-like names, output/input collisions, directories in place of files, and duplicate targets. Export construction checks image-name collisions with reserved output names and annotation paths. Focused tests show that an unsafe target leaves prior output untouched and that an input collision is rejected before extraction.

The GUI persists source bytes, raw Markdown, chunks, and conversion ZIP below the field storage root. `FieldStore` has fixed SQLite tables for documents, definitions, runs, and extraction results. Per-record fields and evidence are JSON columns, so adding a configured field does not add a database column. The extraction-results table has ten columns and no category column; classification is kept in the run result JSON. JSON export retry reads SQLite and performs no model call.

Saved sources and outputs have no automatic expiration or application-level encryption. Operators choose the output location and retention policy.

Record JSON includes the saved extraction model, reasoning effort, and definition version alongside fields and evidence. Export retry preserves those saved values; it does not relabel earlier records with the current model.

## Related pages

- [Document model](../concepts/document-model.md)
- [Field extraction](../workflows/field-extraction.md)
- [Interfaces](../interfaces/cli-gui-api.md)
