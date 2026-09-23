---
type: output architecture
title: Rendering and Exports
description: How DocLayout turns one structured document into Markdown, HTML, JSON, chunks, images, metadata, annotations, and safe filesystem or ZIP exports.
tags: [rendering, exports, markdown, json, html, safety]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-96e22e9964ec5dc995a862c1
    resource: repo://doclayout/exports.py
  - id: openwiki-source-b785a78cd70fa2704f5d6526
    resource: repo://doclayout/renderers/__init__.py
  - id: openwiki-source-24f0edb7a6f534afb5bf8bd5
    resource: repo://doclayout/renderers/chunk.py
  - id: openwiki-source-13284e888a18e3d44db49105
    resource: repo://doclayout/renderers/html.py
  - id: openwiki-source-4bf827c6803e4aac3683e040
    resource: repo://doclayout/renderers/json.py
  - id: openwiki-source-03df821c6b9ae2c7ec0fe520
    resource: repo://doclayout/renderers/markdown.py
  - id: openwiki-source-154e6a78b00ef865edbb429b
    resource: repo://tests/test_cli_exports.py
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# Rendering and Exports

Renderers consume the final in-memory `Document`; they never repeat extraction. The document first produces a recursive `BlockOutput` tree with HTML templates and `<content-ref>` placeholders. Each renderer resolves that tree into a target shape and attaches shared extraction metadata.

## Shared renderer behavior

`BaseRenderer` controls image-block types, crop extraction, header/footer visibility, output block IDs, and image resolution. Image crops come from figure, picture, and diagram polygons and may remain PIL images or become base64 strings for structured output.

Every renderer metadata object includes raw request usage, estimated cost, extraction method and model, model-estimated geometry, table of contents, and per-page block/LLM statistics. Debug paths are included only when present.

## Output shapes

### Markdown

`MarkdownRenderer` first uses the HTML rendering path, then converts the resolved HTML with project-specific Markdown rules for tables, math, headings, links, and escaping. Its typed result contains `markdown`, extracted PIL images, and metadata. Optional pagination wraps pages and emits page separators; disabled image extraction removes both crops and their image references.

### HTML

`HTMLRenderer` recursively substitutes child placeholders, extracts configured image crops, optionally adds block IDs, merges adjacent formatting/math tags, and returns a complete UTF-8 HTML document plus images and metadata. Page wrappers are added only when pagination is enabled.

The GUI's downloadable HTML is built from exported Markdown. It removes active or unsupported elements, rejects image sources outside the extracted image map, applies a tag/attribute/protocol allowlist, embeds approved images as data URLs, and locally converts sanitized LaTeX fragments to MathML.

### JSON and chunks

`JSONRenderer` preserves the document hierarchy. Each output block has its ID, type, HTML, polygon, bounding box, section hierarchy, optional children, and optional base64 image map.

`ChunkRenderer` reuses JSON extraction, then flattens each page's top-level blocks. Every chunk records its page, geometry, fully assembled HTML, section hierarchy, and recursively collected images. A separate `page_info` map preserves page geometry.

### Annotations and ZIP

Annotations draw estimated leaf-block polygons over high-resolution page images. Invalid, nonfinite, or out-of-bounds boxes are skipped and counted. The result contains numbered PNG images, a raster PDF, and drawn/skipped totals.

The ZIP bundle contains Markdown, sanitized HTML, hierarchical JSON, chunks, metadata, annotated PDF, image crops, and annotated page PNGs. It uses the same timestamped export names as individual CLI and GUI downloads.

## One extraction, many exports

`document_exports()` always renders Markdown because that supplies shared text, images, and metadata. It conditionally adds HTML, JSON, chunks, and annotations. Requesting a ZIP computes the complete GUI bundle, while the returned file map still contains only the requested standalone formats plus the archive.

Export names derive from a sanitized, length-limited source stem and a UTC timestamp. Renaming also updates generated Markdown links and HTML image sources so crops stay reachable.

## Filesystem and archive safety

All intended filesystem targets are resolved before any output is written. A target must stay under the output directory, may not equal the directory, overwrite the input, name an existing directory, collide with another output, or use absolute paths, parent traversal, backslashes, or drive syntax. Only after every target passes validation does `save_document_exports()` create directories and write bytes.

Image crops receive an additional collision check against reserved document export names and the annotation namespace. ZIP creation applies equivalent path validation and rejects duplicate reserved names. Tests prove that an unsafe target leaves existing output untouched and cannot write outside the destination, and that an input/output collision is detected before extraction begins.

Existing intended output files may be replaced after successful extraction and export construction; unrelated files in the destination remain untouched. Extraction, range, or export failures preserve prior output because writes occur only after those stages complete.

## Related pages

- [Document Model and Structure](../concepts/document-model.md)
- [Document Conversion Workflow](../workflows/document-conversion.md)
- [CLI, GUI, and API Interfaces](../interfaces/cli-gui-api.md)
