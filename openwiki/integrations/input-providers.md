---
type: Integration guide
title: Input providers and normalization
description: File detection, page rendering, optional source normalization, resource limits, and cleanup.
tags: [providers, pdf, images, normalization]
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-c0def149d0f62564f4806923
    resource: repo://doclayout/providers/converted.py
  - id: openwiki-source-de7b9fa19ea13aa3e3f3869f
    resource: repo://doclayout/providers/image.py
  - id: openwiki-source-2bf7d45aff033d7b87a17558
    resource: repo://doclayout/providers/pdf.py
  - id: openwiki-source-4c3a42078ee20de7168b9f84
    resource: repo://doclayout/providers/registry.py
  - id: openwiki-source-6188cdfc089804761aa67459
    resource: repo://tests/providers/test_document_providers.py
  - id: openwiki-source-aa58b2614cdad072afd30d5c
    resource: repo://tests/providers/test_pdf_provider.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# Input providers and normalization

Providers give `DocumentBuilder` page images, page geometry, and references while keeping file-format handling outside the builder. `provider_from_filepath()` checks file limits, then binary signatures for images, PDF, EPUB, DOCX, XLSX, and PPTX. It attempts HTML parsing and finally checks the extension, with `PdfProvider` as the last fallback. Detection is not proof that an arbitrary malformed file can be converted.

`PdfProvider` validates zero-based page ranges, records page sizes after rotation, and renders through PDFium under a process-wide reentrant lock. The rendering path checks pixel limits and closes document, page, and bitmap resources. It does not read embedded PDF text for the Sol extraction path; selected pages become images. Tests check invalid ranges and that a rotated page's reported geometry matches its rendered image.

`ImageProvider` represents one native image as one page. Above 96 DPI, it returns a Lanczos-upscaled copy; at lower DPI it returns a native-size copy. It validates page zero and closes its source image on `close()`.

Optional document formats normalize to temporary PDFs before using the PDF provider. The `full` extra supplies their conversion libraries. `ConvertedPdfProvider` removes its temporary PDF on explicit close, context-manager exit, or failed initialization; its destructor is a fallback. The provider test verifies that the normalized formats delegate rendering to the PDF provider.

Provider rendering stays on the calling thread within `DocumentBuilder`. Each worker analyzes the rendered image with V3, then sends that same whole-page image to Sol; layout failure removes the prior, not the Sol request. Conversion may use multiple page requests concurrently, but PDFium access remains serialized. The page owns the rendered image on success. On failure, the builder waits for workers before closing all images it rendered.

## Related pages

- [Document conversion](../workflows/document-conversion.md)
- [Configuration and testing](../operations/configuration-and-testing.md)
