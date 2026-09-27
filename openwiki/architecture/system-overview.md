---
type: Architecture
title: System overview
description: How DocLayout renders inputs, uses local layout guidance and Sol extraction, then builds and exports a document.
tags: [architecture, conversion, layout]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-a288c4d4a875a1308ca48472
    resource: repo://doclayout/settings.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# System overview

DocLayout's conversion boundary is `PdfConverter`. It chooses a provider for the input, builds a `Document`, runs structure and content processors, checks protected layout after each processing step, and passes the result to a renderer. PDF, image, Office, spreadsheet, HTML, and EPUB providers share this path where their optional dependencies are installed. See [input providers](../integrations/input-providers.md) and the [conversion workflow](../workflows/document-conversion.md).

`DocumentBuilder` renders selected pages at 192 DPI on the caller thread. It handles up to three pages per batch. Each rendered full-page image goes to the local PP-DocLayoutV3 service first. Successful detection supplies a bounded `given_layout` guide to the existing whole-page GPT-6 Sol request. Sol returns structured blocks with HTML and estimated boxes. The builder reconciles those blocks with layout regions, then records their source bindings in the page model. The layout service is shared and lazy; its artifact and provider checks happen when prepared or first used.

Layout execution is required by default in the current settings. An operator can set `DOCLAYOUT_LAYOUT_ALLOW_SOL_FALLBACK=true` to allow a supported V3 runtime failure to continue through the same full-page Sol request without a guide. An empty successful detection is distinct from runtime failure. Matching has no production default policy yet: absent `DOCLAYOUT_ALIGNMENT_POLICY` or per-converter policy, Sol geometry and order remain in the built page while V3 regions remain available as evidence. See [layout guidance and alignment](../integrations/layout-guidance-and-alignment.md).

After extraction, `StructureBuilder` and the processor chain organize the page. The converter checks layout invariants before and after processors, sanitizes final HTML, and records request usage. Renderers and UI exports reuse the completed document for Markdown, HTML, structured JSON, chunks, and annotations. A renderer does not make another initial extraction request. See [document model](../concepts/document-model.md) and [rendering and exports](../outputs/rendering-and-exports.md).
