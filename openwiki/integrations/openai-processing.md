---
type: Integration
title: Sol extraction and optional processing
description: Whole-page structured Sol extraction, HTML validation, optional correction, and separate document chat.
tags: [sol, extraction, html, chat]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-1daa2a4a6cf32c3b54af104a
    resource: repo://doclayout/processors/llm/llm_page_correction.py
  - id: openwiki-source-d34c8e2d382195ba442be025
    resource: repo://doclayout/schema/extraction.py
  - id: openwiki-source-60f35d388557d37c285d3a4d
    resource: repo://doclayout/services/openai.py
  - id: openwiki-source-71b13599d080c7272e968d44
    resource: repo://doclayout/ui/chat.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# Sol extraction and optional processing

`DocumentBuilder` sends each rendered full-page image to the shared `OpenAIService`. The request uses `gpt-6-sol`, the packaged system and page prompts, and the `ExtractedPage` response schema. A successful V3 result appends `given_layout` to the page prompt; a permitted runtime fallback omits the guide. The image stays whole in either case. The client limits concurrent requests to three and records token usage for the resulting document. See [conversion](../workflows/document-conversion.md).

`ExtractedPage` has a blank flag and a list of `ExtractedBlock` records. A block has a semantic `block_type`, normalized 0–1000 rectangle, and HTML. Validation rejects extra fields, empty text blocks, malformed boxes, and inconsistent blank-page flags. It sanitizes HTML and applies table limits. The layout matcher may replace accepted block geometry and order, but it retains Sol's HTML and semantic type; an unmatched block keeps its Sol estimate. V3-only evidence cannot create a transcription. See [layout alignment](layout-guidance-and-alignment.md) and the [document model](../concepts/document-model.md).

The optional processor chain uses the same Sol service for selected refinement when enabled. Page correction is restricted to HTML rewrites of identified source blocks. Its active protected prompt and response checks forbid changing block IDs, types, boxes, membership, or reading order. The converter checks layout invariants after each processor and sanitizes final HTML. A failed or incomplete structured Sol response raises `ExtractionError` rather than returning partial content.

Document chat is a separate interaction with `gpt-6-luna`. It sends parsed page text to an answer stage, checks each cited quote against the pages locally, then asks an independent verification stage. It does not call the local V3 service or re-extract pages. The chat prompt resources have fingerprint tests so accidental changes are visible.
