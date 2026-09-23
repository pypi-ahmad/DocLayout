---
type: integration architecture
title: OpenAI Extraction and Refinement
description: How DocLayout resolves credentials, performs structured visual extraction and optional refinement, accounts for API usage, and verifies document-only chat answers.
tags: [openai, extraction, llm, chat, credentials, usage]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T13:33:56.448Z
sources:
  - id: openwiki-source-f8eb525c17b05d929e5c2c00
    resource: repo://doclayout/credentials.py
  - id: openwiki-source-4cd6cc33e7cef347ec20fa31
    resource: repo://doclayout/processors/llm/__init__.py
  - id: openwiki-source-d34c8e2d382195ba442be025
    resource: repo://doclayout/schema/extraction.py
  - id: openwiki-source-60f35d388557d37c285d3a4d
    resource: repo://doclayout/services/openai.py
  - id: openwiki-source-71b13599d080c7272e968d44
    resource: repo://doclayout/ui/chat.py
  - id: openwiki-source-77d01944c1fed62d8db62fb5
    resource: repo://doclayout/usage.py
  - id: openwiki-source-7b0b22b2193b94b73f408517
    resource: repo://tests/processors/test_llm_processors.py
  - id: openwiki-source-71c635c50a72cebab2a1bc58
    resource: repo://tests/test_credentials.py
  - id: openwiki-source-341b7e1151d80ba1f6c41762
    resource: repo://tests/test_usage.py
generated: { by: "codex", at: "2026-09-23T13:33:56.448Z" }
---

# OpenAI Extraction and Refinement

DocLayout has two separate OpenAI flows. Every conversion uses GPT-6 Sol to extract structured blocks from page images. The `use_llm` option enables additional GPT-6 Sol refinement processors after extraction. The Streamlit document chat uses GPT-6 Luna in a separate draft-and-verify flow over parsed page text.

## Credentials and client lifecycle

Both flows call `openai_credentials()`. For each setting independently, a process environment variable takes precedence over the launch folder's `.env` file. The resolver reads only that exact file, disables interpolation, does not search parent folders, and does not mutate `os.environ`. `OPENAI_API_KEY` is required; a blank environment key intentionally blocks file fallback. `OPENAI_BASE_URL` defaults to the official endpoint.

Client initialization failures are converted to credential errors that omit secret values. Extraction interfaces normally create one `OpenAIService`, reuse its HTTP client across conversions, and close it at application shutdown. Each converter receives a configured copy with isolated usage state.

## Structured page extraction

`DocumentBuilder` sends the extraction prompt and one rendered page image to `OpenAIService`, requesting an `ExtractedPage` result. The service calls the Responses API with model `gpt-6-sol`, medium reasoning, the packaged system prompt, a configured output limit, and `store=False`.

The service has two concurrency guards: the builder schedules at most three page requests, and `OpenAIService` uses a class-wide bounded semaphore of three. A request records block request/error/token metadata when a block is supplied. It returns only a completed parsed response; incomplete, refused, limited, transport, and validation failures become `ExtractionError` without exposing provider response content.

`ExtractedPage` forbids extra fields and enforces a consistent blank-page flag. Each block must use an allowed semantic type, a nonempty normalized bounding box within 0–1000, and sanitized HTML. Non-image blocks must contain visible text. Script, style, iframe, object, and embed elements are removed, and remaining tags, attributes, and URL protocols are allowlisted.

## Optional refinement processors

The default processor list contains table, equation, form, handwriting, image-description, page-correction, section-header, and other LLM-capable processors. They are inert unless `use_llm` is true. Simple block processors contribute prompts to one meta-processor so their requests can share a bounded thread pool. Complex processors manage their own block selection and bounded request pool.

Refinement runs after initial structure construction. It may rewrite HTML, descriptions, block types, or reading order depending on the processor. Errors are logged and contained at the processor boundary. Tests verify that a failed table refinement preserves the original extracted document instead of replacing it with partial output.

## Usage and cost accounting

Every extraction service call appends a usage entry in `finally`, including failed requests. Entries are marked known only when nonnegative integer input and output token counts are available. Reported cached reads and cache writes are separated from ordinary input so cost calculation does not double count them.

Costs are local estimates from the rates in `usage.py`. Unknown usage, invalid counts, impossible cache subdivisions, or unknown models make the subtotal partial rather than treating the request as free. Converter-specific service copies keep concurrent or sequential runs isolated, and a reused converter clears its usage at the beginning of a new document.

## Verified document chat

Document chat receives parsed page text, a question of at most 2,000 characters, and up to six previously answered turns. It rejects empty documents, invalid questions, and contexts that exceed the byte budget before making paid requests.

The first GPT-6 Luna request produces a strict `Draft`: an answer, not-found decision, or out-of-scope decision with statement-level page quotations. Local validation requires every quote to occur in the declared parsed page, rejects links and markup, limits statements/evidence, and caps the rendered answer. A second independent request receives the candidate and returns only an approval boolean. The answer is shown only after both local evidence validation and verifier approval.

Chat uses `store=False`, medium reasoning, no automatic retries, and a 60-second timeout. Provider errors, raw completions, and rejected drafts are never returned to the user. Usage and stage diagnostics remain available to the UI for cost reporting and operational status.

## Operational consequences

- Converting any page requires API credentials and network access, even when `use_llm` is false.
- Enabling `use_llm` adds refinement requests after mandatory extraction.
- Page extraction and refinements are bounded to three concurrent service calls per process.
- Chat has its own model, client lifetime, usage records, validation schemas, and context limit.
- Cost metadata is an estimate based on reported tokens and may explicitly be partial.

## Related pages

- [Document Conversion Workflow](../workflows/document-conversion.md)
- [CLI, GUI, and API Interfaces](../interfaces/cli-gui-api.md)
- [Configuration, Development, and Testing](../operations/configuration-and-testing.md)
