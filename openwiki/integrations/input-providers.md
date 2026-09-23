---
type: integration guide
title: Input Providers and Normalization
description: How DocLayout detects supported files and normalizes PDFs, images, and optional document formats into page images and geometry for extraction.
tags: [providers, input, pdf, images, normalization]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-a7f62e8435d39c3daa6c1a23
    resource: repo://doclayout/providers/document.py
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
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# Input Providers and Normalization

Providers isolate source-format handling from the conversion pipeline. Regardless of the original file type, `DocumentBuilder` receives an object that exposes a page range, rendered images, page geometry, and page references.

## Provider selection

`provider_from_filepath()` first inspects file signatures for images, PDF, EPUB, DOCX, XLSX, and PPTX. If no binary signature matches, it attempts to parse the file as HTML. Its final fallback uses the filename extension, and an unknown extension falls back to `PdfProvider`.

This detection happens after byte-stream inputs have been copied to a temporary `.pdf` file. Callers that supply non-PDF bytes therefore need to use a real path with the appropriate source suffix; uploaded interfaces preserve the upload suffix when writing their own temporary file.

## Native providers

### PDF

`PdfProvider` opens documents through PDFium under a process-wide reentrant lock. Initialization validates the configured zero-based page range and records each rendered page's effective width and height. This size comes from PDFium after page rotation, so the page polygon and resulting image use the same coordinate space.

Each `get_images()` call reopens the document, renders selected pages at `dpi / 72`, converts them to RGB PIL images, and closes page, bitmap, and document resources. Form rendering is enabled by default. PDF embedded text is not extracted by this provider; all pages proceed as images to structured extraction.

### Images

`ImageProvider` treats a single image as one page. Its polygon uses native pixel dimensions. Requests at more than 96 DPI return a Lanczos-upscaled copy; lower requests return the original image. It supplies no page references.

## Formats normalized through PDF

The `full` dependency extra provides the libraries needed by document providers. These providers first create a temporary PDF, then inherit all page rendering and geometry behavior from `PdfProvider`:

| Source | Normalization path |
|---|---|
| DOCX | Mammoth converts to HTML; WeasyPrint renders styled HTML to PDF |
| HTML | WeasyPrint renders the file with the shared font stylesheet |
| EPUB | EbookLib gathers document content and embedded images; Beautiful Soup rewrites image references; WeasyPrint renders to PDF |
| XLSX | OpenPyXL renders worksheets and merged cells into landscape HTML tables; WeasyPrint renders to PDF |
| PPTX | python-pptx converts slide text, lists, tables, grouped shapes, and images to landscape HTML; WeasyPrint renders to PDF |

These conversions normalize content for visual extraction; they do not preserve the original application's object model. The tests assert that every converted format delegates page rendering to the PDF provider.

## Temporary files and optional resources

Each converted-format provider owns a named temporary PDF. It closes the initial file handle before conversion, initializes `PdfProvider` only after conversion succeeds, and removes the temporary path when the provider is destroyed. Conversion errors are wrapped with source-format context.

WeasyPrint-based providers use a shared font CSS helper. That helper downloads the configured Go Noto font when missing, disables ligatures, and configures it for rendered HTML. These dependencies and font access are only needed for formats normalized through HTML and PDF.

## Page ranges, rotation, and thread safety

Page ranges contain zero-based page IDs. PDF initialization rejects empty ranges, negative values, and IDs beyond the last page. Image input supports only page zero.

PDFium access stays on the calling thread and under `PDFIUM_LOCK`. `DocumentBuilder` renders each page before submitting its image to an extraction worker, so PDF rendering never occurs inside its request thread pool. Tests also rotate a PDF page and verify that the provider's page polygon size exactly matches the rendered image.

## Extension points

A provider implementation needs to expose the `BaseProvider` contract: length, page images, page polygon, and source references. Registering a new type also requires adding signature or extension detection in `providers.registry`. If the new provider normalizes to PDF, subclassing `PdfProvider` preserves page validation, rotation handling, rendering, and locking.

## Related pages

- [Document Conversion Workflow](../workflows/document-conversion.md)
- [Configuration, Development, and Testing](../operations/configuration-and-testing.md)
