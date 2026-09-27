---
type: Concept
title: Document model and layout provenance
description: How pages, extracted blocks, coordinate frames, and protected layout evidence fit together.
tags: [schema, geometry, provenance]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-1f2c2096c8418e0c763c9d17
    resource: repo://doclayout/schema/document.py
  - id: openwiki-source-80451e29d4603d2883c6f0cc
    resource: repo://doclayout/schema/geometry.py
  - id: openwiki-source-08de1b0f5602855358eeb1b6
    resource: repo://doclayout/schema/groups/page.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-71971718d5ae24bf00a8552f
    resource: repo://tests/test_contour_geometry.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# Document model and layout provenance

A `Document` contains ordered `PageGroup` objects. Each page has its rendered image, page polygon, children, and a structure list that defines content order. Extracted blocks retain Sol's HTML and semantic block type. Their established `PolygonBox` is a four-corner representation of a rectangle. See [conversion](../workflows/document-conversion.md) and [exports](../outputs/rendering-and-exports.md).

V3 region evidence is separate from those block polygons. Each `LayoutRegion` records class ID, original label, confidence, page-image-pixel AABB, arbitrary-length contour, one-based order, and `geometry_source`. The two sources are `native_contour` and `rectangle_fallback`; a native contour may itself have four points. A matched block receives an immutable `LayoutGeometry` in page coordinates. An unmatched Sol block keeps its own estimated box, while unmatched V3 regions remain in the page's layout metadata without text blocks.

`convert_points` and `convert_bbox` map between image pixels, normalized 0–1000 guide coordinates, page coordinates, and annotation-image coordinates using independent x and y scales and frame origins. `validate_contour` checks finite point pairs, a simple polygon with positive area, and containment within its page and AABB. A declared rectangle fallback must equal its bbox corners exactly. The helpers do not repair or simplify native contours. See [layout guidance](../integrations/layout-guidance-and-alignment.md).

`PageLayout` records every Sol-to-block source binding, every V3 region and alignment decision, filtered sources, and diagnostic events. It takes a value snapshot of protected evidence. `check_layout` runs around the processor chain and rejects changes to source identity, geometry, contour provenance, page coordinates, or source order. Explicit filtering can remove a source from visible structure while its original binding remains protected. Group geometry is derived from its member blocks.
