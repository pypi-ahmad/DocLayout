---
type: Architecture
title: System overview
description: DocLayout conversion, optional GUI field routing, exports, and local state ownership.
tags: [architecture, conversion, fields, persistence]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
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
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-5e229ac8d28a91c13a465a95
    resource: repo://doclayout/ui/costs.py
  - id: openwiki-source-b27514b73943dd8df7b45d32
    resource: repo://tests/converters/test_pdf_converter.py
  - id: openwiki-source-97c2d91c6ec415fd43007ed6
    resource: repo://tests/test_fields.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
---

# System overview

DocLayout converts PDFs and other supported files into structured Markdown and related exports. The command line, GUI, and HTTP entrypoints share the conversion core. A provider renders selected pages; GPT-6 Sol returns structured page blocks; builders and processors form a typed document; renderers produce Markdown, HTML, JSON, chunks, images, and annotations. A selected page always needs a Sol request. `use_llm` adds refinement requests after initial extraction.

The GUI continues from raw Markdown into business-field extraction. It can run three independent file jobs concurrently and saves original bytes, raw Markdown, chunks, and conversion outputs. GPT-6 Sol with medium reasoning extracts all configured fields in one logical request per document. Luna/medium classification is disabled by default. When explicitly enabled with category definitions and one extraction target, an accepted score of at least 0.75 routes only that target to extraction. The score is a model output subject to local checks, not a measured accuracy rate.

The conversion document is a typed in-memory graph. Business results are separate JSON records in fixed SQLite tables managed by `FieldStore`. Evidence is checked locally against saved chunks. Existing conversion artifacts and same-definition field runs are reused; explicit field retry reads saved Markdown and chunks. Extracted information reads persisted results across browser sessions.

CLI and HTTP interfaces end at conversion exports. The HTTP server owns a shared service and a busy guard around conversion; the GUI owns its file jobs and downstream persistence. Model calls run outside SQLite transactions. The GUI reports estimated session cost subtotals by model, labeled GPT-6 Sol and GPT-6 Luna, rather than by processing stage.

Before Sol, a process-cached PP-DocLayoutV3 ONNX engine analyzes the same rendered page. Its regions are a layout prior, not a transcription. Accepted one-to-one matches retain Sol HTML and use V3 rectangles; rejected or missing matches retain Sol blocks. Engine preparation or inference failure continues with a recorded Sol fallback and no layout prior. There is no layout toggle.

Failures have distinct boundaries. Invalid Sol page extraction aborts that document; layout failure alone does not. GUI batch failures are isolated by file. Oversized field input, incomplete responses, and ungrounded evidence do not become successful records. No automatic schema-repair loop is part of conversion or field extraction.

## Explore

- [Document conversion](../workflows/document-conversion.md)
- [Classification, fields, and review](../workflows/field-extraction.md)
- [Document model](../concepts/document-model.md)
- [Interfaces](../interfaces/cli-gui-api.md)
