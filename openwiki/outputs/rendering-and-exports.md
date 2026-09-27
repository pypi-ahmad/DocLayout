---
type: Output
title: Rendering and exports
description: How one converted document becomes text, structured data, images, and current annotations.
tags: [rendering, exports, metadata]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-96e22e9964ec5dc995a862c1
    resource: repo://doclayout/exports.py
  - id: openwiki-source-24f0edb7a6f534afb5bf8bd5
    resource: repo://doclayout/renderers/chunk.py
  - id: openwiki-source-4bf827c6803e4aac3683e040
    resource: repo://doclayout/renderers/json.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-ac5d0f22367daa23e677df71
    resource: repo://doclayout/ui/exports.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# Rendering and exports

After conversion, the same `Document` feeds Markdown, styled HTML, hierarchical JSON, flattened chunk JSON, OCR JSON, metadata, image crops, annotated pages, and ZIP output. The file exporter renders Markdown once, derives HTML from it, and invokes other renderers only when their formats are requested. A ZIP includes the full GUI bundle. The exporter validates destinations and filenames before writing files. See [interfaces](../interfaces/cli-gui-api.md).

Markdown renders processed HTML into text, tables, math, code, links, and images according to configuration. JSON retains the document/page/block tree with IDs, HTML, established bbox and four-corner `polygon`, plus additive `layout_geometry` on matched source blocks. Chunks flatten top-level blocks and collect member `layout_geometries` by source ID; they do not invent one group contour. OCR JSON lists visible source blocks with the same additive layout geometry. Page layout metadata records original V3 regions, Sol and region alignment decisions, counts, policy, model identity, provider, timing, fallback, and filtered sources. See [document model](../concepts/document-model.md).

The current annotation exporter traverses visible source blocks. It draws a matched native V3 contour in red, or a rectangle for an official rectangle fallback or unmatched Sol block. It labels each drawn source block. It does not draw V3-only evidence and does not use distinct colors for matched versus unmatched sources. V3-only detections still remain in layout metadata and produce no fabricated content. Header/footer visibility in this path follows the source block's semantic type, not the V3 coarse label. These are current output boundaries, not claims about extraction accuracy.
