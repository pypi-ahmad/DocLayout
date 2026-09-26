---
type: architecture overview
title: System Overview
description: How DocLayout turns supported source files into a structured document and multiple export formats, including the ownership and lifecycle of each runtime component.
tags: [architecture, conversion, lifecycle, components]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:42:04.191Z
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
generated: { by: "codex", at: "2026-09-26T10:42:04.191Z" }
---

# System Overview

DocLayout is a Python document conversion system whose central pipeline is `PdfConverter`. User-facing entrypoints create shared Sol and lazy local layout services, translate interface options into converter configuration, and pass a file or byte stream into that pipeline. The converter chooses an input provider, builds a typed `Document`, runs an ordered processor chain, and resolves a renderer. `OCRConverter` and `TableConverter` specialize the same conversion path.

## Component map

| Layer | Responsibility | Downstream relationship |
|---|---|---|
| Interfaces | Batch CLI, single-file CLI, Streamlit GUI, and FastAPI server | Build configuration, own service lifetime, invoke `PdfConverter`, and serialize or save results |
| Service artifacts | Construct the shared `OpenAIService` and process-shared lazy `LayoutService`; close the HTTP client | Supply local V3 layout guidance, structured Sol extraction, and optional refinement |
| Providers | Detect the source format and expose page images, geometry, and page ranges | Give `DocumentBuilder` a uniform page-oriented input |
| Builders | Render each page, attempt V3, send the full image to Sol, validate and align blocks; group for `PdfConverter` | Produce the initial typed document graph with layout diagnostics |
| Processors | Apply deterministic cleanup and optional LLM refinement in a fixed order | Mutate structure, labels, HTML, metadata, and references before rendering |
| Schema | Own documents, pages, groups, blocks, identifiers, geometry, traversal, and render contracts | Connect every pipeline stage through one in-memory representation |
| Renderers and exports | Traverse the document graph into Markdown, HTML, JSON, chunks, images, metadata, annotations, or ZIPs | Return in-memory results or validated filesystem outputs |

## Runtime flow

1. An interface calls `create_model_dict()`, which creates an `OpenAIService` under `extraction_service` and a lazy `LayoutService` under `layout_service`. `shutdown_models()` closes the HTTP service; layout sessions remain cached for the process.
2. `PdfConverter` validates configuration, resolves processor and renderer classes, and requires the extraction service artifact. When the artifact is an `OpenAIService`, it creates a configured shallow copy so converters share the HTTP client without sharing per-run usage state.
3. The converter identifies a provider from the actual file. `DocumentBuilder` renders requested pages at 192 DPI by default, attempts local V3 on each whole-page image, and sends that image with bounded layout guidance to Sol when V3 is available. V3 runtime failures send the image without a guide.
4. After `ExtractedPage` validation, deterministic alignment builds source blocks in reading order. With an evaluated matching policy, confident one-to-one matches take V3 rectangles and order while retaining Sol HTML and type. Without a policy, Sol geometry and order remain authoritative. Missed or ambiguous content stays in Sol blocks; V3-only regions stay diagnostic.
5. `StructureBuilder` groups related blocks for `PdfConverter`; `OCRConverter` skips default grouping and processing. The converter runs its processor list in order, checks layout invariants, sanitizes generated HTML and descriptions, and attaches the run's usage records to the document.
6. The selected renderer receives the final `Document`. Dependency resolution supplies renderer constructor arguments from configuration and artifacts, and the converter returns the renderer's typed output model.

The default renderer is Markdown. Other interfaces select HTML, JSON, or chunk renderers through the same configuration path, while the shared export layer can render several formats from one already extracted document.

## Ownership and lifecycle

The service artifacts belong to the interface or application lifecycle, rather than to an individual conversion. Batch conversion and long-lived GUI/API processes reuse one HTTP client. A converter-specific configured service resets usage collection and settings without mutating another converter's view. Identical layout device/cache settings share one locked, batch-one local runtime.

Temporary PDF files created for byte streams live only for the converter call. Format-specific providers may also create normalized temporary PDFs. Their cleanup belongs to the context manager or provider that created them. The completed `Document` is otherwise in-memory; persistence begins only when an interface explicitly serializes or saves renderer/export results.

The FastAPI lifespan creates model artifacts; its request guard allows one active conversion at a time and rejects another with HTTP 429. API requests use the same converter path and return layout metadata when conversion succeeds.

## Failure boundaries

Configuration and dependency resolution fail before extraction when invalid. Provider and page-range validation fail before page requests. Layout dependency, cache, artifact, device, and inference failures are reported as Sol fallback with the full image, provided Sol conversion succeeds. Invalid layout policy, guide overflow, Sol extraction failure, and protected-layout invariant violations abort conversion. Batch CLI code decides whether later input files continue.

Renderers operate only after all processors finish. This keeps partially processed documents from being saved by the normal conversion path. Tests verify that a failed conversion does not write its output, while batch conversion can report a failed input and continue with subsequent inputs.

## Extension seams

The principal extension points are provider detection, block-class registration, processor selection, and renderer selection. `BaseConverter.resolve_dependencies()` supplies constructor parameters by name from configuration and the artifact dictionary, so custom processors and renderers must declare dependencies that the converter can resolve. Block overrides are registered before document construction, allowing custom block implementations to participate throughout building, processing, and rendering.

## Related pages

- [Document Conversion Workflow](../workflows/document-conversion.md)
- [Document Model and Structure](../concepts/document-model.md)
- [Layout Guidance and Alignment](../integrations/layout-guidance-and-alignment.md)
- [OpenAI Extraction and Refinement](../integrations/openai-processing.md)
- [Rendering and Exports](../outputs/rendering-and-exports.md)
