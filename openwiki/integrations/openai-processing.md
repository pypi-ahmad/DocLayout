---
type: Integration architecture
title: OpenAI processing
description: Sol visual extraction, optional refinement, Luna document chat, and Markdown-only field requests.
tags: [openai, extraction, chat, classification, usage]
sources:
  - id: openwiki-source-5dcb620e5737ce6818a4678d
    resource: repo://doclayout/builders/document.py
  - id: openwiki-source-f8eb525c17b05d929e5c2c00
    resource: repo://doclayout/credentials.py
  - id: openwiki-source-15837773bd4113ac5b1f7ae1
    resource: repo://doclayout/fields.py
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-a7389354844d3d810adc44e8
    resource: repo://doclayout/prompts/extraction.md
  - id: openwiki-source-d34c8e2d382195ba442be025
    resource: repo://doclayout/schema/extraction.py
  - id: openwiki-source-60f35d388557d37c285d3a4d
    resource: repo://doclayout/services/openai.py
  - id: openwiki-source-71b13599d080c7272e968d44
    resource: repo://doclayout/ui/chat.py
  - id: openwiki-source-5e229ac8d28a91c13a465a95
    resource: repo://doclayout/ui/costs.py
  - id: openwiki-source-5cc93531da2d908ce1900895
    resource: repo://tests/test_chat_prompts.py
  - id: openwiki-source-97c2d91c6ec415fd43007ed6
    resource: repo://tests/test_fields.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# OpenAI processing

The conversion service uses `gpt-6-sol` with medium reasoning. `DocumentBuilder` sends one rendered page image and the packaged extraction prompt per selected page. `OpenAIService` requests a parsed `ExtractedPage`, sets `store=False`, and limits concurrent requests to three per process. Invalid or incomplete parsed responses raise `ExtractionError`. Usage records are appended even for failed calls, with unknown token counts represented as partial cost data.

`ExtractedPage` and `ExtractedBlock` enforce block types, nonempty normalized boxes, blank-page consistency, and visible text for non-image blocks. HTML is sanitized against an allowlist. Optional Sol refinement processors run after initial structure building when `use_llm` is enabled. They do not replace mandatory page extraction.

When V3 succeeds, the request appends compact `given_layout` JSON to the packaged prompt and still sends the whole page. Sol supplies visible content and HTML, may add content missed by V3, and treats document text as untrusted. No crop-only transcription request is added. Layout preparation or inference failure sends the page without `given_layout`; Sol and response-validation errors still propagate. The ONNX layout engine does not use OpenAI credentials.

The GUI's document chat uses Luna with medium reasoning in a separate draft and verification flow. The draft cites parsed page text; local checks verify quotes on the declared pages and reject unsupported formatting before a second Luna request approves or rejects the candidate. Context and question limits can stop chat before a model call. The prompt-preservation test compares packaged chat text with recorded hashes.

GUI business-field extraction uses Sol/medium with raw Markdown as input. The configured schema requests all fields and records in one logical call. Local JSON Schema validation, source quote checks, and chunk geometry mapping decide whether a result needs review. `store=False`, a 180-second timeout, two SDK transport retries, and a 32,768-token output cap apply to field requests. An oversized request is retained for review instead of being silently truncated.

Classification uses Luna/medium only when explicitly enabled. Its closed JSON result includes a category, score, ambiguity flag, reason, and source quote. An accepted score must be at least 0.75 and meet the other local checks before the designated category proceeds to extraction. The threshold is a routing decision, not independently measured accuracy.

`openai_credentials()` resolves API key and optional base URL from process variables or the launch folder's `.env`, with each process variable taking precedence. The converter service may share an HTTP client across configured copies while keeping usage ledgers separate. Local cost estimates depend on reported tokens and configured model rates. The GUI shows GPT-6 Sol and GPT-6 Luna subtotals by model; these do not isolate processing stages. Unknown usage remains flagged as partial.

## Related pages

- [Document conversion](../workflows/document-conversion.md)
- [Field extraction](../workflows/field-extraction.md)
- [Configuration and testing](../operations/configuration-and-testing.md)
