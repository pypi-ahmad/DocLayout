---
type: core concept
title: Document Model and Structure
description: The typed in-memory graph that represents pages, blocks, geometry, reading order, metadata, and render output throughout DocLayout.
tags: [schema, document-model, blocks, geometry, rendering]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-158c5e2b7d609ae6c42bd1d8
    resource: repo://doclayout/schema/blocks/base.py
  - id: openwiki-source-1f2c2096c8418e0c763c9d17
    resource: repo://doclayout/schema/document.py
  - id: openwiki-source-08de1b0f5602855358eeb1b6
    resource: repo://doclayout/schema/groups/page.py
  - id: openwiki-source-40b7085857583170a97d7e39
    resource: repo://doclayout/schema/polygon.py
  - id: openwiki-source-6619880ebc9c95309464ca18
    resource: repo://doclayout/schema/registry.py
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# Document Model and Structure

DocLayout carries conversion state in a Pydantic model rooted at `Document`. The model separates storage from reading order: a page owns every block in its `children` list, while each block's `structure` contains ordered `BlockId` references to the blocks it semantically contains. Processors can therefore regroup or replace content without copying the underlying blocks.

## Hierarchy and identity

`Document` owns ordered `PageGroup` objects, usage records, an optional table of contents, and a lazily rebuilt page index. A page owns its rendered images, source references, all child blocks, top-level reading order, and aggregate metadata.

Every block has a page number, page-local numeric identifier, `BlockTypes` value, polygon, optional nested structure, extraction provenance, removal state, and optional processing metadata. `BlockId` renders as `/page/{page}` for pages or `/page/{page}/{type}/{id}` for ordinary blocks. This stable textual form is also used by renderer placeholders and image paths.

Page-local identifiers are append-only. Replacing a block adds the replacement as a new child, substitutes its ID anywhere the old ID occurs in structures, and marks the old block removed. This preserves direct indexed lookup into `children` while excluding superseded content through `current_children` and recursive traversal.

## Block families

The schema uses a few behavioral families:

- Pages and groups contain ordered references to other blocks.
- Text primitives represent characters, spans, and lines.
- Semantic blocks represent text, headings, lists, tables, figures, pictures, equations, forms, code, references, and related regions.
- Leaf blocks may carry extracted HTML directly; containers usually assemble child `<content-ref>` placeholders.

The registry maps every `BlockTypes` member to an importable implementation. Builders and processors request classes through this registry, and `PdfConverter.override_map` can register replacement implementations before a document is built. Registry assertions ensure every enum member is registered and that each class declares the matching default block type.

## Geometry

`PolygonBox` stores four clockwise corners beginning at the top left. It exposes a cached axis-aligned bounding box and derived dimensions, center, overlaps, intersection percentage, and minimum gap. Geometry methods return new polygons for expansion, rescaling, and merging, so the cached bounding box remains valid.

Extraction responses express block boxes in a normalized 1000 by 1000 coordinate space. The builder rescales them into page coordinates before constructing blocks. When a renderer or processor needs a crop, `Block.get_image()` rescales the page-space polygon into the selected page image's pixel dimensions. The same model supports rotated pages because the provider supplies the rendered page size and tests require extracted blocks to stay inside those bounds.

## Navigation and traversal

`Document.get_page()` and `Block.structure_index()` maintain self-healing indexes. They validate or rebuild cached entries after mutations. Page and document navigation use the declared structure rather than raw child insertion order, and document-level next/previous lookup crosses page boundaries.

`contained_blocks()` recursively follows structures, skips removed blocks, and can filter by block type. This is the common query used by processors, renderers, annotations, and tests. Raw text follows the same references, recursively joining child text and preserving line boundaries where relevant.

## Rendering contract

Rendering is a recursive two-part operation. Each block first renders its structured children into `BlockOutput` objects. Its `assemble_html()` method then returns HTML containing the block's own content and/or `<content-ref>` placeholders for those children. A `BlockOutput` retains the block ID, polygon, children, and current section hierarchy.

`Document.render()` processes pages in order and carries section hierarchy from one page to the next. Section header blocks update that map by heading level, removing deeper or equal levels before recording themselves. Renderers later resolve the output tree into their target representation; they do not need to reconstruct document semantics from flat text.

## Metadata and invariants

Block metadata counts LLM requests, errors, and tokens, along with selected prior-state fields used by processors. Page aggregation merges metadata from current children. Removed blocks remain addressable in page storage but should not appear in current traversal or output.

The central invariants are:

1. A block ID addresses a child on its declared page and matches the object stored at that index.
2. Structure order defines semantic and rendering order.
3. Geometry stays in page coordinates until explicitly rescaled for an image.
4. Replacement updates structure references and marks the old block removed.
5. Every block type has exactly one currently registered implementation.

## Related pages

- [System Overview](../architecture/system-overview.md)
- [Document Conversion Workflow](../workflows/document-conversion.md)
- [Rendering and Exports](../outputs/rendering-and-exports.md)
