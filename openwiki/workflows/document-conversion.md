---
type: Workflow
title: Document conversion workflow
description: The sequence from validated input to local layout guidance, whole-page Sol extraction, protected blocks, and output.
tags: [conversion, workflow, extraction]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-1faf643b9f60547b3495121a
    resource: repo://doclayout/builders/alignment.py
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-7fedac0f436ee48a3f44eb34
    resource: repo://tests/builders/test_document_builder.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# Document conversion workflow

1. `PdfConverter` validates configuration, chooses a provider for the file, and asks `DocumentBuilder` to render the selected pages. The builder requests a 192 DPI full-page image. PDFium rendering stays on the caller thread; at most three page extraction requests can be in flight. See [input providers](../integrations/input-providers.md).
2. The local V3 service analyzes that same image. Success yields ordered regions with class, score, bbox, contour, and provenance. `given_layout` checks geometry and serializes every region into a 0–1000 guide with a 512-region and 64-KiB cap. The builder appends the guide to the packaged extraction prompt. A successful empty detection still produces a valid empty guide. Runtime failure aborts by default; an explicit operator fallback sends the full image to Sol without the guide. See [layout guidance](../integrations/layout-guidance-and-alignment.md).
3. Sol returns one `ExtractedPage` for the image with validated semantic block types, HTML, and estimated boxes. When a matching policy is configured, the current matcher can replace isolated accepted boxes with V3 AABBs and sort anchored block bundles by V3 order. It does not split or duplicate Sol strings. Without a policy, Sol boxes and order remain. Unmatched V3 regions remain evidence, not text.
4. The builder maps the final block boxes into page coordinates, attaches page-coordinate V3 contours to matched blocks, and records source bindings and diagnostic metadata. `StructureBuilder` groups blocks. The converter checks protected identity, geometry, source membership, and order after grouping and each processor. Explicit filtering is recorded; HTML correction cannot move blocks. See [document model](../concepts/document-model.md).
5. The completed document is sanitized and rendered to the selected output. Other export formats reuse it. Sol extraction errors, invalid responses, guide overflow, configuration errors, and layout invariant errors stop conversion. See [outputs](../outputs/rendering-and-exports.md).

The current matcher evaluates rectangular V3 overlap and leaves ambiguous split and merge components unmatched. Its synthetic tests prove preservation and deterministic behavior for those cases; they are not threshold calibration on representative documents.
