---
type: Integration
title: Local layout guidance and alignment
description: The pinned V3 ONNX runtime, native contour decode, bounded guide, current matching rules, and failure behavior.
tags: [layout, onnx, alignment, contours]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-1faf643b9f60547b3495121a
    resource: repo://doclayout/builders/alignment.py
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-3a15c4c875a9f676af798b18
    resource: repo://doclayout/services/layout.py
  - id: openwiki-source-a288c4d4a875a1308ca48472
    resource: repo://doclayout/settings.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# Local layout guidance and alignment

The local service loads `PaddlePaddle/PP-DocLayoutV3_onnx` at revision `46bbdf188bb0a772c08aed74882ce7e51a8f1ea6`. It verifies the size and SHA-256 of `inference.onnx` and `inference.yml`, downloads only absent files into an ignored Hugging Face cache, and reuses a locked, warmed PaddleOCR/PaddleX ONNX Runtime engine. `auto` tries CUDA and keeps CPU after a GPU runtime failure; explicit `cuda` is strict. Python 3.11 or later and the `layout` extra are needed for local V3. See [configuration](../operations/configuration-and-testing.md).

Prediction uses one full-page image at a time with `layout_shape_mode="poly"` and `skip_order_labels=[]`. PaddleOCR/PaddleX retains its preprocessing and postprocessing. The service requires native segmentation masks, checks their shape, and observes the installed decoder's documented rectangle branch to set `geometry_source`. It rejects missing segmentation, malformed contours, and unsupported decoder versions instead of calling a synthesized rectangle a native contour. Each accepted region keeps its class ID, label, confidence, AABB, contour, and dense one-based order. A successful zero-region result is valid. The guide converts every region to normalized 0–1000 coordinates and fails if it would exceed 512 regions or 64 KiB, including contour bytes. See [document model](../concepts/document-model.md).

Sol still receives the whole page and owns transcription, HTML, and semantic block type. The current `alignment_policy` returns `None` when unset; then all Sol blocks retain their boxes and order while V3 evidence remains in metadata. A configured policy requires five complete thresholds. The current matcher uses V3 AABBs, not contour intersection, with overlap, confidence, containment, area-ratio, center-distance, and class gates. Isolated accepted pairs take V3 bbox and order. A split, merge, or many-to-many component is diagnosed and left unmatched, including proposed pairs; ties have stable ordering. Unmatched Sol content is retained once. Unmatched V3 regions add no text. See [conversion](../workflows/document-conversion.md).

V3 runtime failure aborts by default. The operator setting `DOCLAYOUT_LAYOUT_ALLOW_SOL_FALLBACK=true` permits the existing full-page Sol request without `given_layout` for supported runtime failures. Invalid configuration, guide overflow, and downstream layout invariant failures still abort. The current settings do not provide a named default matching policy or `DOCLAYOUT_LAYOUT_REQUIRED` option.
