---
type: Integration
title: Input providers and page rendering
description: How supported files become page images and page coordinate frames for the shared conversion path.
tags: [providers, rendering, inputs]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
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
  - id: openwiki-source-aa58b2614cdad072afd30d5c
    resource: repo://tests/providers/test_pdf_provider.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# Input providers and page rendering

`PdfConverter` selects a provider after `check_file` has applied input limits. The registry detects image, PDF, EPUB, DOCX, XLSX, and PPTX content, then tries HTML parsing and finally the filename extension. Converted-document providers create a temporary PDF and use the same PDF rendering path. Their context manager removes the temporary file after conversion or on failure. These document formats require their optional conversion libraries. See [configuration and testing](../operations/configuration-and-testing.md).

`PdfProvider` validates a zero-based page selection, removes duplicate page numbers while retaining order, and rejects empty, out-of-range, or over-limit selections. It renders selected pages with PDFium under `PDFIUM_LOCK`, checks render pixel limits, and returns RGB images. Its page rectangle starts at the rendered top-left corner, including for rotated pages. The 192 DPI request comes from `DocumentBuilder`; the provider converts it to PDFium's scale. Tests check ordinary rendering and rotated page dimensions.

`ImageProvider` exposes one page. It validates source pixels and accepts only `[0]` as an explicit page range. When the builder requests 192 DPI, it treats the source as 96 DPI and returns a resized copy, subject to render pixel limits. Both image and PDF providers return a page bounding box for mapping Sol and V3 geometry. The same returned full-page image goes to layout inference and to Sol extraction. See [document conversion](../workflows/document-conversion.md).
