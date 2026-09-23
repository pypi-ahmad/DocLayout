---
type: architecture overview
title: System Overview
description: How DocLayout turns supported source files into a structured document and multiple export formats, including the ownership and lifecycle of each runtime component.
tags: [architecture, conversion, lifecycle, components]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-6b00bdd493744f272566442a
    resource: repo://doclayout/converters/__init__.py
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-73b91acfbb0cc57dfe3dd29b
    resource: repo://doclayout/models.py
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-b27514b73943dd8df7b45d32
    resource: repo://tests/converters/test_pdf_converter.py
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# System Overview

DocLayout is a Python document conversion system whose central pipeline is `PdfConverter`. User-facing entrypoints create one shared API service, translate interface options into converter configuration, and pass a file or byte stream into that pipeline. The converter chooses an input provider, builds a typed `Document`, enriches it through an ordered processor chain, and resolves a renderer for the requested output.

## Component map

| Layer | Responsibility | Downstream relationship |
|---|---|---|
| Interfaces | Batch CLI, single-file CLI, Streamlit GUI, and FastAPI server | Build configuration, own service lifetime, invoke `PdfConverter`, and serialize or save results |
| Service artifacts | Construct and close the shared `OpenAIService` | Supply structured page extraction and optional LLM refinement to converters |
| Providers | Detect the source format and expose page images, geometry, and page ranges | Give `DocumentBuilder` a uniform page-oriented input |
| Builders | Turn page images and structured extraction responses into pages and blocks, then establish groups | Produce the initial typed document graph |
| Processors | Apply deterministic cleanup and optional LLM refinement in a fixed order | Mutate structure, labels, HTML, metadata, and references before rendering |
| Schema | Own documents, pages, groups, blocks, identifiers, geometry, traversal, and render contracts | Connect every pipeline stage through one in-memory representation |
| Renderers and exports | Traverse the document graph into Markdown, HTML, JSON, chunks, images, metadata, annotations, or ZIPs | Return in-memory results or validated filesystem outputs |

## Runtime flow

1. An interface calls `create_model_dict()`, which creates an `OpenAIService` under the `extraction_service` artifact key. The owner later calls `shutdown_models()` to close it.
2. `PdfConverter` validates configuration, resolves processor and renderer classes, and requires the extraction service artifact. When the artifact is an `OpenAIService`, it creates a configured shallow copy so converters share the HTTP client without sharing per-run usage state.
3. The converter identifies a provider from the actual file, then asks `DocumentBuilder` to render requested pages and obtain schema-validated block extraction for each page.
4. `StructureBuilder` groups related blocks. The converter then runs its processor list in order, sanitizes generated HTML and descriptions, and attaches the run's usage records to the document.
5. The selected renderer receives the final `Document`. Dependency resolution supplies renderer constructor arguments from configuration and artifacts, and the converter returns the renderer's typed output model.

The default renderer is Markdown. Other interfaces select HTML, JSON, or chunk renderers through the same configuration path, while the shared export layer can render several formats from one already extracted document.

## Ownership and lifecycle

The service artifact belongs to the interface or application lifecycle, rather than to an individual conversion. This allows batch conversion and long-lived GUI/API processes to reuse one HTTP client. A converter-specific configured service resets usage collection and settings without mutating another converter's view.

Temporary PDF files created for byte streams live only for the converter call. Format-specific providers may also create normalized temporary PDFs. Their cleanup belongs to the context manager or provider that created them. The completed `Document` is otherwise in-memory; persistence begins only when an interface explicitly serializes or saves renderer/export results.

The FastAPI service adds another serialization boundary: its lifespan creates one service artifact and one asynchronous lock. Every request acquires that lock before construction and conversion because PDFium access is process-local and conversion is intentionally serialized at that interface.

## Failure boundaries

Configuration and dependency resolution fail before extraction when required artifacts or constructor dependencies are missing. Provider and page-range validation fail before page requests. Each page extraction response is validated against `ExtractedPage`; invalid or failed extraction aborts that single conversion. Batch CLI code decides whether later input files continue.

Renderers operate only after all processors finish. This keeps partially processed documents from being saved by the normal conversion path. Tests verify that a failed conversion does not write its output, while batch conversion can report a failed input and continue with subsequent inputs.

## Extension seams

The principal extension points are provider detection, block-class registration, processor selection, and renderer selection. `BaseConverter.resolve_dependencies()` supplies constructor parameters by name from configuration and the artifact dictionary, so custom processors and renderers must declare dependencies that the converter can resolve. Block overrides are registered before document construction, allowing custom block implementations to participate throughout building, processing, and rendering.

## Related pages

- [Document Conversion Workflow](../workflows/document-conversion.md)
- [Document Model and Structure](../concepts/document-model.md)
- [OpenAI Extraction and Refinement](../integrations/openai-processing.md)
- [Rendering and Exports](../outputs/rendering-and-exports.md)
