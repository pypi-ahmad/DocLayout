---
type: Operations guide
title: Configuration and testing
description: Application settings, field switches, uv checks, and the limits of offline and live evidence.
tags: [configuration, testing, uv, operations]
sources:
  - id: openwiki-source-f8eb525c17b05d929e5c2c00
    resource: repo://doclayout/credentials.py
  - id: openwiki-source-3fc18d2b3bd86c90ce3a3ddd
    resource: repo://doclayout/field_store.py
  - id: openwiki-source-15837773bd4113ac5b1f7ae1
    resource: repo://doclayout/fields.py
  - id: openwiki-source-6c373104051421f3f3c546ea
    resource: repo://doclayout/layout.py
  - id: openwiki-source-60a85b3abffa8ceadae5f4cd
    resource: repo://doclayout/scripts/clear_gui_port.ps1
  - id: openwiki-source-a288c4d4a875a1308ca48472
    resource: repo://doclayout/settings.py
  - id: openwiki-source-4ed424df535efedbec384488
    resource: repo://doclayout/ui/batch.py
  - id: openwiki-source-e7faa3ddaca50993ae19c88a
    resource: repo://launch.cmd
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-e44eab9a26f9187df819fc2a
    resource: repo://pytest.ini
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-97c2d91c6ec415fd43007ed6
    resource: repo://tests/test_fields.py
  - id: openwiki-source-747ce984286d9a8fb9342632
    resource: repo://tests/test_launcher.py
  - id: openwiki-source-302aace0465b65581c3853df
    resource: repo://tests/test_layout_prior.py
  - id: openwiki-source-e21a991204779b8d3c0240c6
    resource: repo://tests/test_layout_readiness.py
  - id: openwiki-source-b1623b7b40e27202adf3b061
    resource: repo://tests/test_layout_runtime.py
generated: { by: "codex", at: "2026-09-26T10:40:37.445Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-09-26T10:40:37.445Z
---

# Configuration and testing

The project declares Python `>=3.11,<4` and uses `uv.lock` for reproducible dependency resolution. The base package contains PDF/image conversion, V3 runtime dependencies, and the CLI; optional `full`, `gui`, and `server` extras add document-format libraries, Streamlit, and FastAPI. Windows AMD64 selects `onnxruntime-gpu==1.30.0`, which also supplies CPU execution; other platforms select `onnxruntime==1.30.0`. There is no layout extra. The development group supplies test and quality tools. The declared Python range does not claim every version has been exercised.

`settings.py` holds output paths, rendering choices, and operator limits, including maximum source size, page count, image pixels, and archive resources. It can read `local.env`. API credentials are resolved separately from process variables or a launch-folder `.env`; process variables take precedence per key. The HTTP token must be at least 32 non-whitespace ASCII characters. Path-based API input requires an existing dedicated `DOCLAYOUT_INPUT_ROOT`.

The field workflow reads `DOCLAYOUT_CLASSIFICATION_ENABLED` directly from the process environment. It defaults to `false`; editing category text alone does not enable classification. `DOCLAYOUT_FIELD_MAX_INPUT_BYTES` defaults to 900000 and must be an integer from 1 through 900000. These process-only switches do not inherit the credential `.env` resolver or Pydantic `local.env` loading.

V3 uses the official `PaddlePaddle/PP-DocLayoutV3_onnx` artifact through direct ONNX Runtime, not the separately available Transformers interface. First preparation resolves two pinned files, verifies SHA-256 and labels, and exercises the session. The default Hub cache is `cache/pp-doclayoutv3` under the checkout; `DOCLAYOUT_LAYOUT_CACHE_DIR` overrides it. `DOCLAYOUT_LAYOUT_MODEL_DIR` selects an exact artifact directory and `DOCLAYOUT_LAYOUT_OFFLINE=true` prohibits downloads. Invalid supplied files are rejected, not silently overwritten.

`DOCLAYOUT_LAYOUT_DEVICE=auto` attempts CUDA, verifies actual execution, and falls back to an exercised CPU session. Explicit `cuda` never substitutes a CPU session; its failure reaches conversion-level Sol fallback instead. The pinned CUDA policy places the single ScatterND node on CPU and verifies its assignment before execution. One locked, process-cached engine serves batch-size-one inference. Ordinary preparation/inference errors produce recorded Sol fallback; they do not prove the model ran on CPU. See the [layout record](../../docs/layout-v3-plan.md) for artifact hashes and output-contract evidence.

Layout tests inject fake engines and sessions to cover download-once behavior, races, device selection, fallback, parsing, matching, and export provenance without downloading weights. These tests do not validate a real GPU, memory fit, speed, or accuracy improvement.

From the repository root, synchronize dependencies with `uv sync --locked --group dev --extra full`. Run the offline suite with `uv run --no-sync python -m pytest` and a focused field check with `uv run --no-sync python -m pytest tests/test_fields.py`. For a browser test, install Playwright's Chromium shell first. `tests/conftest.py` blocks real Responses API calls by default and skips `integration` tests unless `--run-integration` is given. The latter is billable.

Offline tests check page and provider geometry, schema and sanitization, CLI/API behavior, GUI navigation, routing thresholds, grounding, SQLite persistence, cache reuse, and retries. They establish local contracts with generated fixtures and mocks. They do not measure current endpoint access, classification accuracy, field accuracy, or latency on real documents. The separate conversion benchmark uses a local dataset and billable Sol requests; it does not measure downstream fields, classification, or chat.

`launch.cmd` starts the GUI on `127.0.0.1:8471` with file watching disabled. Its PowerShell helper stops a recognized DocLayout listener automatically, asks before stopping another application, rechecks process identity and port ownership, and aborts if cleanup fails. Restarting loses in-progress work and browser state but preserves saved artifacts. Launcher tests mock processes and sockets; they do not terminate real listeners. Use the [verification record](../../docs/documentation-sync.md) for dated check results and known failures.

The GUI retains sources, derived conversion artifacts, JSON, and SQLite below `OUTPUT_DIR/field_extraction`. It has no automatic expiry or application-level encryption; operators should account for that when setting the output directory.

## Related pages

- [Quickstart](../quickstart.md)
- [OpenAI processing](../integrations/openai-processing.md)
- [Field extraction](../workflows/field-extraction.md)
