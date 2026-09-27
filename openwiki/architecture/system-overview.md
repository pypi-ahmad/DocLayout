---
type: Architecture
title: System overview
description: DocLayout conversion, optional GUI field routing, exports, and local state ownership.
tags: [architecture, conversion, fields, persistence]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:39:18.635Z
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-3fc18d2b3bd86c90ce3a3ddd
    resource: repo://doclayout/field_store.py
  - id: openwiki-source-15837773bd4113ac5b1f7ae1
    resource: repo://doclayout/fields.py
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-5e229ac8d28a91c13a465a95
    resource: repo://doclayout/ui/costs.py
  - id: openwiki-source-ac5d0f22367daa23e677df71
    resource: repo://doclayout/ui/exports.py
  - id: openwiki-source-b27514b73943dd8df7b45d32
    resource: repo://tests/converters/test_pdf_converter.py
  - id: openwiki-source-97c2d91c6ec415fd43007ed6
    resource: repo://tests/test_fields.py
generated: { by: "codex", at: "2026-09-27T09:39:18.635Z" }
---

# System overview

DocLayout converts PDFs and other supported files into structured Markdown and related exports. The command line, GUI, and HTTP entrypoints share the conversion core. A provider renders selected pages; GPT-6 Sol returns structured page blocks; builders and processors form a typed document; renderers produce Markdown, HTML, JSON, chunks, images, and annotations. A selected page always needs a Sol request. `use_llm` adds refinement requests after initial extraction.

The GUI continues from raw Markdown into business-field extraction. It can run three independent file jobs concurrently and saves original bytes, raw Markdown, chunks, and conversion outputs. GPT-6 Sol with medium reasoning extracts all configured fields in one logical request per document. Luna/medium classification is disabled by default. When explicitly enabled with category definitions and one extraction target, an accepted score of at least 0.75 routes only that target to extraction. The score is a model output subject to local checks, not a measured accuracy rate.

The conversion document is a typed in-memory graph. Business results are separate JSON records in fixed SQLite tables managed by `FieldStore`. Evidence is checked locally against saved chunks. Existing conversion artifacts and same-definition field runs are reused; explicit field retry reads saved Markdown and chunks. Extracted information reads persisted results across browser sessions.

CLI and HTTP interfaces end at conversion exports. The HTTP server owns a shared service and a busy guard around conversion; the GUI owns its file jobs and downstream persistence. Model calls run outside SQLite transactions. The GUI reports estimated session cost subtotals by model, labeled GPT-6 Sol and GPT-6 Luna, rather than by processing stage.

Before Sol, a process-cached PP-DocLayoutV3 ONNX engine analyzes the same rendered page. Its regions guide layout, not transcription. Accepted one-to-one matches retain Sol HTML and semantic types while using V3 contours, or valid V3 rectangles when contours fail. Unmatched Sol blocks survive. Matched slots follow global V3 relative order, including across Sol-only blocks. Source footprints survive processor assembly and drive visible annotations. Engine preparation or inference failure continues with recorded Sol fallback and no guide. There is no layout toggle.

The local unreleased pipeline is `sol-layout-v3/v4`. Saved metadata separates initial reconciliation counts from final visible source geometry and annotation counts. A CUDA session can include CPU operations; actual providers and fallback stages are recorded. These diagnostics do not establish matching accuracy.

Failures have distinct boundaries. Invalid Sol page extraction aborts that document; layout failure alone does not. GUI batch failures are isolated by file. Oversized field input, incomplete responses, and ungrounded evidence do not become successful records. No automatic schema-repair loop is part of conversion or field extraction.

## Explore

- [Document conversion](../workflows/document-conversion.md)
- [Classification, fields, and review](../workflows/field-extraction.md)
- [Document model](../concepts/document-model.md)
- [Interfaces](../interfaces/cli-gui-api.md)
