---
type: Workflow
title: Document conversion
description: Selected page rendering, Sol extraction, structure building, processing, validation, and exports.
tags: [workflow, conversion, pdf, extraction]
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-96e22e9964ec5dc995a862c1
    resource: repo://doclayout/exports.py
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-e4aa4d69e867cd141e316b1d
    resource: repo://doclayout/scripts/convert.py
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-7fedac0f436ee48a3f44eb34
    resource: repo://tests/builders/test_document_builder.py
  - id: openwiki-source-b27514b73943dd8df7b45d32
    resource: repo://tests/converters/test_pdf_converter.py
  - id: openwiki-source-154e6a78b00ef865edbb429b
    resource: repo://tests/test_cli_exports.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# Document conversion

1. The entrypoint resolves configuration, builds or borrows an extraction service, and selects a provider for the source file. `PdfConverter` can also accept `BytesIO`; it bounds the bytes, writes a temporary PDF, and removes it afterward.
2. The converter prepares the process-cached V3 engine before opening the provider. The provider validates the zero-based selected page range and supplies page geometry and rendered images. `DocumentBuilder` renders each image at 192 DPI by default on its caller thread, then schedules V3 analysis followed by one whole-page Sol structured extraction request. It accepts `page_concurrency` from 1 through 3; the service also caps simultaneous calls at three per process. Preparation or analysis failure continues without a layout prior and records Sol fallback.
3. The builder validates and sanitizes `ExtractedPage`, reconciles its normalized boxes with image-pixel V3 regions, and creates semantic blocks in page coordinates. Sol retains content and HTML semantics; accepted matches select V3 rectangles. Pages remain in provider order even if requests finish in another order. A Sol blank page has no blocks; disagreeing V3 regions remain diagnostics. Invalid Sol schema output aborts the document rather than creating a partial normal result.
4. `StructureBuilder` groups initial blocks, then `PdfConverter` runs processors sequentially. Sol refinement processors can add requests when `use_llm` is enabled. A final HTML sanitization pass covers processor output. The converter copies request usage onto the document.
5. A renderer turns the final document into a requested conversion format. The CLI export path builds one document and derives multiple formats locally. Destination checks run before writing files, so an extraction failure or unsafe output target does not replace prior normal output.

Focused tests confirm one mandatory extraction per page, the model recorded in metadata, caller-thread rendering, geometry limits, blank-page handling, and failures that preserve existing output. The GUI can persist a source and failure receipt for a failed file while allowing other batch files to continue. Its successful continuation into [field extraction](field-extraction.md) reads raw Markdown; it does not change this conversion workflow.

## Matching and saved identity

Matching requires compatible classes and a mutual-best one-to-one match with IoU at least 0.5 and a 0.10 margin over the next candidate on both sides. Strong containment of at least 0.8 identifies ambiguous split/merge components, which retain Sol boxes without splitting text or averaging geometry. Ties are rejected. These are provisional policy thresholds, not verified accuracy guarantees; a visually wrong match can still pass them.

Only contiguous matched runs follow V3 order keys. Unmatched Sol blocks remain `sol_only` anchors, and ambiguous order keys retain Sol order. Unmatched V3 detections do not create content blocks or duplicate Markdown. Normal processors may still change geometry, order, or visibility afterward.

Saved GUI conversion identity includes source bytes, filename, options, and the pipeline fingerprint, including execution and fallback policies. Historical Sol-only results are not relabeled as current V3 conversions. A saved fallback result can be reused even after V3 becomes available; actual execution is recorded in page metadata. Explicit field-only retries use saved raw Markdown and chunks without conversion.

## Related pages

- [System overview](../architecture/system-overview.md)
- [Input providers](../integrations/input-providers.md)
- [Rendering and exports](../outputs/rendering-and-exports.md)
