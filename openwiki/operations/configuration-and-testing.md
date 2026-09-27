---
type: Operations
title: Configuration and verification
description: Runtime extras, operator settings, credentials, and the difference between offline tests and live inference.
tags: [configuration, testing, runtime]
verified:
  - by: openwiki/0.6.0
    at: 2026-09-27T09:43:51.061Z
sources:
  - id: openwiki-source-f8eb525c17b05d929e5c2c00
    resource: repo://doclayout/credentials.py
  - id: openwiki-source-dd442b9660f0eaeb4d42fde8
    resource: repo://doclayout/scripts/server.py
  - id: openwiki-source-3a15c4c875a9f676af798b18
    resource: repo://doclayout/services/layout.py
  - id: openwiki-source-a288c4d4a875a1308ca48472
    resource: repo://doclayout/settings.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-72a55afa95ba2771e1594261
    resource: repo://tests/converters/test_layout_live.py
  - id: openwiki-source-abd31605405249fba84ec342
    resource: repo://tests/test_entrypoints.py
generated: { by: "codex", at: "2026-09-27T09:43:51.061Z" }
---

# Configuration and verification

The package declares Python `>=3.10,<4`, but local V3 execution requires Python 3.11 or later. The `layout` extra pins Hugging Face Hub, PaddleOCR, PaddleX, ONNX Runtime GPU, and Shapely for that runtime. Other extras supply GUI, server, and document-format dependencies. On Windows, use the uv lockfile with the chosen extras. The layout service caches the official pinned ONNX files outside Git, verifies size and SHA-256 before use, and warms a selected provider. See [layout guidance](../integrations/layout-guidance-and-alignment.md).

`Settings` reads operator layout policy, device, fallback, and cache settings from the process environment or `local.env`. `DOCLAYOUT_LAYOUT_DEVICE` defaults to `auto`; `cpu` never probes CUDA and explicit `cuda` does not fall back. `DOCLAYOUT_LAYOUT_ALLOW_SOL_FALLBACK` defaults to false. `DOCLAYOUT_ALIGNMENT_POLICY` has no value by default: a supplied policy must contain all five validated parameters. HTTP request fields cannot override these operator settings. Separate credential loading reads `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` from the process or launch-folder `.env`. The server also needs a separate API bearer token; filepath requests need a dedicated configured input root. See [interfaces](../interfaces/cli-gui-api.md).

Offline pytest fixtures replace the layout engine, set synthetic alignment thresholds, and block unexpected OpenAI calls. Those thresholds are test inputs, not calibrated production defaults. Integration tests are skipped unless `--run-integration` is explicitly passed. The synthetic CPU live test makes a billable Sol request; the GPU layout test does not call Sol. A listed CUDA provider alone is not proof of executed GPU kernels, and synthetic outputs do not establish layout or extraction accuracy on representative documents. The optional olmOCR fixture pages and rules must be supplied separately for that evaluation.

Run the documented focused checks with `uv run --no-sync` after syncing the locked environment. Keep real API requests and model downloads in explicitly selected live checks, and record actual provider, fallback reason, sample coverage, and failures alongside results.
