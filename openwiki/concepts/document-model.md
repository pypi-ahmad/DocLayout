---
type: Core concept
title: Document model and structure
description: Typed pages, blocks, geometry, reading order, and their separation from business results.
tags: [document, schema, blocks, geometry]
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-9852cd86c08b08aceb8cfadb
    resource: repo://doclayout/builders/structure.py
  - id: openwiki-source-3fc18d2b3bd86c90ce3a3ddd
    resource: repo://doclayout/field_store.py
  - id: openwiki-source-15837773bd4113ac5b1f7ae1
    resource: repo://doclayout/fields.py
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-158c5e2b7d609ae6c42bd1d8
    resource: repo://doclayout/schema/blocks/base.py
  - id: openwiki-source-1f2c2096c8418e0c763c9d17
    resource: repo://doclayout/schema/document.py
  - id: openwiki-source-08de1b0f5602855358eeb1b6
    resource: repo://doclayout/schema/groups/page.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-40b7085857583170a97d7e39
    resource: repo://doclayout/schema/polygon.py
  - id: openwiki-source-ac5d0f22367daa23e677df71
    resource: repo://doclayout/ui/exports.py
  - id: openwiki-source-4afc0256a0f8d4961c5343dd
    resource: repo://tests/schema/groups/test_list_grouping.py
  - id: openwiki-source-97c2d91c6ec415fd43007ed6
    resource: repo://tests/test_fields.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# Document model and structure

`Document` is the conversion pipeline's in-memory Pydantic model. It owns ordered pages, reported usage, an optional table of contents, and a lazy page index. Each `PageGroup` owns block objects in `children` and a separate `structure` list of block IDs. Structure order controls reading and rendering order; insertion order alone does not.

`BlockId` renders as `/page/{page}/{type}/{id}` for ordinary blocks. Page-local IDs remain addressable after replacement: processors can add a replacement block, update structure references, and mark the old block removed. `current_children` and traversal exclude removed blocks. The page and structure indexes rebuild if their cached entries no longer match.

Every block has a page identity, semantic type, polygon, optional child structure, extraction provenance, and optional request metadata. `DocumentBuilder` rescales normalized Sol boxes into page coordinates. Cropping rescales page polygons into image pixels. Page rendering preserves the section hierarchy across pages and returns a recursive `BlockOutput` tree with `<content-ref>` placeholders for child content.

`StructureBuilder` creates groups such as lists from extracted regions before processors operate on them. The focused list test checks that existing HTML list content survives this stage.

`Document.layout` records the pipeline manifest, raw V3 regions, and page runtime results separately from the Sol response schema. Regions retain class ID/label, score, page-image pixel rectangles, binary-mask RLE, and the model's order key. `observed_rank` is a derived stable sort, not another model prediction. `Block.layout` records matched, `sol_only`, or processor provenance and source footprints.

Reconciliation transforms V3 pixels into page coordinates. It substitutes accepted V3 rectangles without replacing Sol HTML, and only sorts contiguous matched runs; unmatched Sol blocks remain anchors. Unmatched V3 detections stay diagnostic and do not become Markdown blocks. Later processors can merge geometry or change structure, so exports use the final processed graph. `PolygonBox` still requires four points: annotations use rectangular projections, not mask contours.

Business authorization records are a different model. The GUI sends raw Markdown to field extraction, then saves field/evidence JSON in `FieldStore`'s SQLite tables. Those records do not add SQL columns or new block types to the conversion graph.

Each saved field record retains its extraction model, reasoning effort, and definition version. New model settings create new runs; loading older records preserves their original metadata.

## Related pages

- [System overview](../architecture/system-overview.md)
- [Rendering and exports](../outputs/rendering-and-exports.md)
- [Field extraction](../workflows/field-extraction.md)
