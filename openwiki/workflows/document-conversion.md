---
type: workflow
title: Document Conversion Workflow
description: A step-by-step trace of provider selection, page rendering, structured extraction, document building, processing, sanitization, and final rendering.
tags: [workflow, conversion, extraction, processors, concurrency]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-7fedac0f436ee48a3f44eb34
    resource: repo://tests/builders/test_document_builder.py
  - id: openwiki-source-b27514b73943dd8df7b45d32
    resource: repo://tests/converters/test_pdf_converter.py
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# Document Conversion Workflow

A conversion has one mandatory extraction request per selected page, followed by deterministic structure/process stages and optional refinement requests. Rendering starts only after the complete document has passed through the processor chain.

## 1. Construct the converter

The caller creates an artifact dictionary containing `extraction_service`, then constructs `PdfConverter` with configuration and optional processor/renderer overrides. Construction validates retired settings, registers block-class overrides, resolves processor dependencies, and chooses `MarkdownRenderer` when no renderer is supplied.

The converter keeps a configured copy of `OpenAIService` with isolated usage state. When `use_llm` is false, that service still performs mandatory page extraction, but optional LLM processors receive no active refinement service.

## 2. Normalize the input path

String paths proceed directly. A `BytesIO` input is copied to a named temporary `.pdf`, used for the duration of the call, and removed in `finally`. Provider detection examines the resulting file and instantiates the matching provider with the converter configuration.

The provider validates the requested page range and exposes each selected page as an image plus page-space geometry. Non-PDF document providers normalize their source to PDF before reaching this point.

## 3. Render pages and extract blocks

`DocumentBuilder` validates `page_concurrency` in the range 1–3 and a positive render DPI. It processes selected page IDs in batches no larger than that concurrency.

Within each batch, the builder performs these operations in order:

1. Render each page image synchronously on the caller thread.
2. Create an empty typed `PageGroup` with geometry, images, references, and `openai` extraction provenance.
3. Submit the extraction request to a thread pool.
4. After all jobs for that batch are submitted, consume futures in page order.
5. Validate each response as `ExtractedPage`.
6. Rescale every normalized 0–1000 bounding box into page coordinates, create the registered semantic block class, attach sanitized HTML, and append its ID to page reading order.

Pages are appended to the document in provider order even if later requests finish earlier. PDFium never runs in an executor thread; only API requests do. Tests record thread identities to enforce this boundary.

A blank response produces a page with empty structure. Invalid block types, empty textual blocks, malformed/overflowing boxes, and inconsistent blank flags fail schema validation and abort the conversion.

## 4. Build initial structure

`StructureBuilder` runs before processors. It associates nearby captions and footnotes with figures, pictures, and tables; converts extracted list regions into structured list items where line data exists; groups adjacent list items; and demotes regions that do not contain list markers.

This stage establishes the nested references that later processors and renderers traverse. It operates on block IDs, so regrouping does not duplicate the page's child objects.

## 5. Run processors in order

The converter executes its processor instances sequentially in `default_processors` order. Early processors relabel and normalize blocks and lines; middle processors handle structural concepts such as code, contents, footnotes, lists, headers, marginalia, and headings; optional GPT-6 Sol processors refine complex regions; final processors resolve references, blanks, and debug output.

Simple LLM processors are consolidated into a meta-processor at their position in the chain. Requests inside that processor may run concurrently, but the processor itself completes before the next processor begins. Complex LLM processors similarly finish their own bounded work before control returns to the converter.

Processor failures have two policies. Mandatory extraction failures propagate and abort the document. Optional refinement processors catch/log rewrite errors and preserve prior extraction wherever possible.

## 6. Sanitize and attach usage

After every processor finishes, the converter sanitizes any block `html` and `description` values again. This final pass prevents processor rewrites from bypassing the extraction schema's allowlist. The service usage ledger is copied onto the document so every renderer can emit consistent cost metadata.

## 7. Render and return

For a normal converter call, the converter records page count, resolves renderer dependencies, renders the full document, and returns the renderer's typed output. The file-export CLI instead calls `build_document()` directly so Markdown, HTML, JSON, chunks, annotations, and ZIP can all be derived from the same extraction.

No normal output is saved before extraction, structure building, processing, export construction, and path validation succeed. Tests preserve an existing output when extraction fails. Folder conversion handles failures per file, continues remaining work, then returns a nonzero result if any file failed.

## Ordering and concurrency invariants

- There is exactly one mandatory structured extraction call per selected page.
- Page images are rendered on the caller thread before their request is submitted.
- At most three page requests are scheduled concurrently per builder, and the service also caps requests at three per process.
- Responses may complete concurrently, but pages and block structures retain provider/result order.
- Structure building precedes every processor; processors complete sequentially; rendering follows all processors and final sanitization.
- A failed conversion does not persist a partial normal output.

## Related pages

- [System Overview](../architecture/system-overview.md)
- [Document Model and Structure](../concepts/document-model.md)
- [Input Providers and Normalization](../integrations/input-providers.md)
- [OpenAI Extraction and Refinement](../integrations/openai-processing.md)
