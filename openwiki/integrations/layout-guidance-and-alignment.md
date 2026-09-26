---
type: integration guide
title: Layout Guidance and Alignment
description: How local PP-DocLayoutV3 supplies optional page guidance and how validated Sol blocks are aligned, protected, or retained on fallback.
tags: [layout, pp-doclayoutv3, alignment, fallback, onnx]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:42:04.191Z
sources:
  - id: openwiki-source-1faf643b9f60547b3495121a
    resource: repo://doclayout/builders/alignment.py
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-2fd79989af77129bf0ab8ba7
    resource: repo://doclayout/converters/ocr.py
  - id: openwiki-source-61dc7f9e9ba4f8fa05cfee1d
    resource: repo://doclayout/converters/pdf.py
  - id: openwiki-source-18c4d57897a8ccce6ab6e5af
    resource: repo://doclayout/converters/table.py
  - id: openwiki-source-f9b9ef051ee27ca44899d86a
    resource: repo://doclayout/schema/layout.py
  - id: openwiki-source-3a15c4c875a9f676af798b18
    resource: repo://doclayout/services/layout.py
  - id: openwiki-source-43d75016fb479eccf27963fc
    resource: repo://tests/builders/test_alignment.py
  - id: openwiki-source-07a7daa57e95501145ee49f0
    resource: repo://tests/services/test_layout.py
generated: { by: "codex", at: "2026-09-26T10:42:04.191Z" }
---

# Layout Guidance and Alignment

`LayoutService` runs the revision-pinned `PaddlePaddle/PP-DocLayoutV3_onnx` artifact through PaddleOCR's ONNX Runtime engine. The runtime reads `inference.onnx` and `inference.yml` from an ignored cache, verifies their sizes and hashes, and downloads only absent pinned files. The base package can import without the optional `layout` extra. This interface returns class ID, label, score, a page-pixel rectangle, and a one-based order index; it does not expose an irregular polygon or mask. Four rectangle corners are derived for `PolygonBox`.

## Runtime ownership

Model construction is lazy. Each `(device, resolved cache directory)` pair has one process-shared runtime protected by a lock, so the batch-one detector is safe beside up to three concurrent Sol page requests. `prepare()` and prediction share that session. A real warm-up inference checks the requested provider. `cpu` remains on CPU; `auto` tries CUDA and switches to CPU if setup or inference fails; explicit `cuda` raises a typed error instead of silently switching. The recorded provider is the session's primary execution provider, not proof that every operator ran on GPU. Startup errors remain cached until process restart.

The returned result records model ID and revision, actual device/provider, elapsed time, image dimensions, ordered regions, and fallback details. A direct `LayoutService` call raises typed dependency, cache, artifact, device, or inference errors. `DocumentBuilder` catches runtime errors for conversion, records an unavailable attempt, and still sends the same full page image to Sol without `given_layout`. Invalid policy, guide overflow, Sol failure, and layout invariant errors abort conversion.

## Page request and matching

`DocumentBuilder` renders a selected page at 192 DPI by default and analyzes that image before submitting its Sol request. A successful detector result becomes bounded `given_layout` JSON appended to the existing user request; the full image remains attached. The guide rejects more than 512 regions or more than 64 KiB, rather than silently truncating. Sol transcribes visible content and returns structured blocks with semantic type, HTML, and a box normalized to 0–1000. V3 contributes layout, not the transcription.

After `ExtractedPage` validation, `align_blocks()` converts Sol and V3 geometry into one pixel space. With no evaluated policy, it keeps every Sol box and original Sol order, while retaining V3 regions as diagnostics. A configured policy must provide all five finite values: minimum IoU, minimum score, minimum containment, minimum area ratio, and maximum normalized center distance. These gates are parameters for evaluation, not a universal threshold supplied by the project.

Candidates require positive overlap and either sufficient IoU or bounded containment, area, and center distance. The class compatibility table is explicit. Deterministic ranking reserves one Sol block and one V3 region per proposal. Only isolated, compatible, score-qualified pairs are applied. Candidate components with multiple edges record ambiguity, split/merge, or ties; low scores and class conflicts are diagnostic reasons. A match keeps Sol's HTML and compatible type, takes V3 geometry and reading order, and does not synthesize or duplicate words. Unmatched Sol blocks remain rendered with their validated boxes; unmatched V3 regions remain diagnostic and do not create empty blocks. An empty successful detector result differs from a runtime failure.

## Protection and downstream use

The builder creates page blocks in aligned order and stores their IDs in `page.structure`. `PageLayout` keeps source bindings, original regions, match status, policy, counts, timings, device, and fallback reasons apart from additive block metadata. `PdfConverter` groups blocks, runs processors, and checks that source identity, geometry, membership, and order remain unchanged. Group geometry is derived from members, so a top-level group or chunk box can differ from a matched leaf box. `OCRConverter` shares extraction and alignment but skips default grouping and processors. `TableConverter` records its intentional filtered subsequence.

Optional page correction can change validated HTML only in the normal converter path. A direct processor call can reorder a page or merge HTML, but the converter's invariant checks reject a changed authoritative source order, and it skips table merge. JSON, chunks, Markdown, OCR JSON, and annotations read the resulting document. Annotations draw rectangles: V3-derived for matched leaves and Sol-estimated for unmatched leaves.

Focused offline tests cover cache integrity, warm-up and CPU/CUDA behavior, concurrent callers, ordering, split/merge, class conflicts, blank and graphic-only pages, converter fallback, protected processors, and export geometry. They do not establish production matching thresholds or real-document detector recall.

## Related pages

- [Document Conversion Workflow](../workflows/document-conversion.md)
- [Document Model and Structure](../concepts/document-model.md)
- [OpenAI Extraction and Refinement](openai-processing.md)
- [Configuration, Development, and Testing](../operations/configuration-and-testing.md)
