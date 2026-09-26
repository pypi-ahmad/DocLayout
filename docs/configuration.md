# DocLayout configuration

[Back to README](../README.md) · [Usage](usage.md) · [Development](development.md)

For processor controls beyond the settings below, see
[advanced configuration](#advanced-configuration).

## Downstream field workflow

The GUI runs authorization-field extraction after conversion. The CLI and HTTP
API keep their conversion-only behavior. See [field extraction](field-extraction.md)
for the field schema and persisted review workflow.

| Process environment variable | Default | Meaning |
| --- | --- | --- |
| `DOCLAYOUT_CLASSIFICATION_ENABLED` | `false` | Explicitly enable classification; only `true` or `false`, case insensitive |
| `DOCLAYOUT_FIELD_MAX_INPUT_BYTES` | `900000` | Maximum serialized downstream request bytes; integer from 1 to 900000 |

Set these variables in the launching process. They are read with `os.getenv`, not
from the credential `.env` file or Pydantic `local.env` settings. Editing the category
template never enables classification. Enabled classification needs definitions and
exactly one extraction target; incomplete configuration stops processing.

Classification uses `gpt-6-luna`; field extraction uses `gpt-6-sol`. Both use
medium reasoning, `store=false`, a
180-second timeout, 32,768 output tokens, and two SDK transport retries. The output
budget includes reasoning; the classification response itself is compact strict
JSON. Its score must be >= 0.75, its category supported, and its quote verified.
No model fallback is configured. Oversized requests go to review without splitting.

Artifacts live under `OUTPUT_DIR/field_extraction/`, normally
`conversion_results/field_extraction/`. Originals and previews are retained locally;
SQLite and JSON outputs are not application-encrypted and have no automatic retention
cleanup. Use local storage with suitable access controls.

## Credentials and environment

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required API credential for extraction and document chat |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint; omitted uses the SDK default |

API clients resolve each variable from the process environment first, then from
`.env` in the current working directory. This applies to every entry point and
to both extraction/refinement and document chat. No parent directory, source
checkout fallback, or installed package folder is searched. The resolver does
not modify the process environment.

An explicitly empty environment API key blocks file fallback and produces a
configuration error. An empty or missing selected base URL uses the SDK default.
File values are read literally; `${VARIABLE}` substitution is not performed.
Other `.env` keys do not configure DocLayout application settings.

Copy [`.env.example`](../.env.example) to `.env` in the launch folder and replace
the placeholders, or set credentials in the environment. `launch.cmd` changes
the working directory to the repository root before starting the GUI. Installed
commands read `.env` in the folder from which you invoke them.

After changing Windows user or machine environment variables, open a new terminal
and restart DocLayout. The [README example](../README.md#configure-api-access)
sets values for one PowerShell session. To keep them across sessions, replace
these placeholders and open a new terminal afterward:

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-api-key", "User")
# Optional for a custom compatible endpoint.
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://your-endpoint.example/v1", "User")
```

Check presence without displaying values:

```powershell
[bool]$env:OPENAI_API_KEY
[bool]$env:OPENAI_BASE_URL
```

These presence checks inspect the terminal environment, not `.env`. Restart
DocLayout after editing credentials: the GUI caches its extraction client.
Variables changed in Windows settings are inherited by newly launched terminals
and applications; DocLayout does not read or modify the Windows registry.

The endpoint must support Responses, image input, and structured output for
`gpt-6-sol` for conversion and Markdown field extraction; chat and enabled
classification also require `gpt-6-luna`.
Credentials do not belong
in CLI flags, configuration JSON, source code, or Git.

Application `Settings` reads environment variables and a discovered `local.env`
file through Pydantic Settings. Environment values take precedence. Reading the
file does not export its contents into the process environment, so
`OPENAI_API_KEY` in `local.env` alone does not configure the API clients.

Common application settings from [settings.py](../doclayout/settings.py):

| Setting | Default | Purpose |
| --- | --- | --- |
| `OUTPUT_DIR` | `conversion_results` under the package's parent directory | Default CLI output root |
| `OUTPUT_ENCODING` | `utf-8` | Legacy CLI text/metadata encoding; new file exports always use UTF-8 |
| `OUTPUT_IMAGE_FORMAT` | `JPEG` | Saved crops and API image encoding |
| `LOGLEVEL` | `INFO` | Application logging level |

The settings class also defines font paths and an artifact URL for document
converters. These are application settings, not model settings. Path defaults
are set when the class is defined. Changing a base directory does not recalculate
derived paths, so set the final path explicitly. Model requests send PNG images
regardless of `OUTPUT_IMAGE_FORMAT`.

## Models and request limits

| Task | Model | Request defaults |
| --- | --- | --- |
| Page extraction and optional refinement | `gpt-6-sol` | Medium reasoning; 32,768 output tokens; 180-second timeout; two SDK retries |
| Markdown field extraction | `gpt-6-sol` | Medium reasoning; 32,768 output tokens; 180-second timeout; two SDK retries |
| Optional classification (off by default) | `gpt-6-luna` | Medium reasoning; strict JSON; 180-second timeout; two SDK retries |
| Chat draft and verification | `gpt-6-luna` | Medium reasoning; 8,192 output tokens; 60-second timeout; no retries |

Model names, reasoning effort, and chat request limits are fixed in code. The
Sol settings below are configurable. `use_llm=False` disables extra refinement;
every selected page still uses Sol extraction. There is no local OCR fallback.

## Local layout inference

The local unreleased pipeline runs pinned PP-DocLayoutV3 before each whole-page
Sol request, which includes a compact `given_layout` prior. It uses the official
`PaddlePaddle/PP-DocLayoutV3_onnx` artifact with direct ONNX Runtime. The Windows
AMD64 base dependency is `onnxruntime-gpu==1.30.0`, including CPU execution; there
is no layout extra or GUI on/off switch. NumPy and OpenCV are already base dependencies.

On the first Run needing an uncached conversion, preparation resolves/downloads
the pinned `inference.onnx` and `inference.yml`, verifies hashes and labels, then
executes one synthetic 800×800 RGB warm-up. Its detections are discarded. CUDA
readiness requires an executed CUDA kernel in an ORT profile, not just a reported
GPU/provider name. CPU support for other graph nodes is allowed. In `auto`, CUDA
initialization/execution/verification failure falls back to an exercised CPU
session; later CUDA execution failure also retries that page on CPU. CPU success
is latched. Explicit `cuda` never falls back to CPU. If layout preparation or page
inference fails, conversion continues with whole-page Sol and explicitly records
`sol_fallback`; this does not bypass Sol response validation or sanitization.

CUDA sessions assign the pinned model's single `ScatterND` node to CPU using
ONNX Runtime 1.30's name-based layer placement. Preparation verifies that
assignment before inference; an unverified placement rejects CUDA (CPU fallback
in `auto`, failure in explicit `cuda`). Other eligible operations remain on CUDA.
This avoids the CUDA ScatterND duplicate-index warning path without suppressing
logs or modifying weights. It may add CPU/GPU transfer overhead; it does not
establish better detection accuracy. The execution policy is included in new
conversion fingerprints; historical saved results and field retries are unchanged.

| Setting | Default | Purpose |
| --- | --- | --- |
| `DOCLAYOUT_LAYOUT_DEVICE` | `auto` | `auto` verifies CUDA, then tries CPU on failure; `cuda` never substitutes a CPU session; `cpu` skips CUDA. If the selected engine cannot run, conversion uses Sol with fallback provenance |
| `DOCLAYOUT_LAYOUT_CACHE_DIR` | `<BASE_DIR>/cache/pp-doclayoutv3` | Dedicated, writable Hugging Face model cache |
| `DOCLAYOUT_LAYOUT_MODEL_DIR` | Unset | Exact pinned model directory; overrides Hub cache resolution. Existing files are verified, not silently replaced |
| `DOCLAYOUT_LAYOUT_OFFLINE` | `false` | Refuse network downloads; pinned files must already be cached |

Set these in the process environment or Pydantic `local.env`, then restart.
Credential `.env` does not configure them; its example labels these settings
separately. No model is loaded by opening the GUI, browsing saved results, or
starting the HTTP server. The GUI displays “Preparing layout model…” during
preparation, followed by “PP-DocLayoutV3 · CUDA” or “PP-DocLayoutV3 · CPU” for the
actual exercised device. Warm conversions reuse one serialized engine per process;
additional CLI worker processes each own their own engine.

Missing offline files, corrupt artifacts, unavailable dependencies, unsupported
outputs or provider failure produce a typed error from the low-level engine.
Conversion catches layout errors and keeps Sol content, boxes and order. GUI
readiness shows “Sol fallback · V3 unavailable”; per-page metadata records the
failure stage, unavailable provider, null device/order-source and fallback status.
No failed layout output is presented as a successful empty detection. Failed
preparation is not reprobed for every page. Repair configuration/files before new
conversions; saved fallback results remain saved results, not silently reconverted.
Passive reruns do not retry failed preparation. Saved loading,
CLI skips and field-only retries do not require loading weights. A complete
read-only model directory still needs a writable cache for temporary CUDA health
profiles. Do not delete unrelated caches to repair this model. See the
[layout integration record](layout-v3-plan.md) for pinned artifacts, Windows
provider evidence, matching policy, cache identity and unverified quality claims.

V3 supplies rectangles, binary masks, scores, 25 class labels and observed order
keys, not transcription, HTML or raw polygon vertices. `observed_rank` is a
derived stable sort of model order keys, not a separate prediction. Sol transcribes the
whole image. Matching preserves Sol content; exports use rectangular geometry,
with masks retained separately. Neither detector scores nor order keys are
calibrated accuracy guarantees. Result summaries use stored region/match counts
and summed per-page analysis milliseconds, including queue waiting. This is not
wall-clock document time; separately prepared warm-up time is not included.

Sol blocks with no accepted V3 match retain their own validated geometry and
position as `sol_only`. Ambiguous ties and split/merge overlaps are rejected;
unmatched V3 regions remain diagnostics and never generate Markdown. Matching
thresholds are provisional, and an incorrect detection can still pass them.
See the [matching policy](layout-v3-plan.md#4-deterministic-matching)
for the exact rules and limitations.

## Extraction and rendering

Use these keys in a Python configuration dictionary or JSON configuration file.
CLI flags are available for supported scalar types; list/tuple values generally
belong in JSON or Python. `page_range` has its own CLI parser.

| Setting | Default | Behavior or constraint |
| --- | --- | --- |
| `page_range` | All pages | Zero-based integer list in Python/JSON; comma/range string on CLI/API |
| `highres_image_dpi` | `192` | Positive rendering DPI for page extraction |
| `page_concurrency` | `3` | Integer from 1 to 3; concurrent page extraction requests |
| `timeout` | `180` | Positive Sol request timeout in seconds |
| `max_retries` | `2` | Nonnegative SDK retry count |
| `max_output_tokens` | `32768` | Positive Sol output-token limit per request |
| `use_llm` | `false` | Enable additional refinement requests |
| `flatten_pdf` | `true` | Enable PDF form rendering |
| `extract_images` | `true` | Include crops produced by the renderer |
| `image_extraction_mode` | `highres` | Crop from `highres` or `lowres` page images |
| `keep_pageheader_in_output` | `false` | Retain classified page headers |
| `keep_pagefooter_in_output` | `false` | Retain classified page footers |
| `paginate_output` | `false` | Add renderer-supported page boundaries |
| `add_block_ids` | `false` | Include block IDs in HTML where supported |
| `html_tables_in_markdown` | `false` | Emit HTML tables in Markdown |
| `page_separator` | 48 hyphens | Markdown page separator when pagination is enabled |
| `inline_math_delimiters` | `["$", "$"]` | Markdown inline math delimiters |
| `block_math_delimiters` | `["$$", "$$"]` | Markdown block math delimiters |

Sources: [document builder](../doclayout/builders/document.py),
[Sol service](../doclayout/services/openai.py), [PDF provider](../doclayout/providers/pdf.py),
[base renderer](../doclayout/renderers/__init__.py), and
[Markdown renderer](../doclayout/renderers/markdown.py).

The service permits up to three concurrent Sol requests per process, including
refinement. More folder workers create more processes, each with the same limit.

## CLI and JSON configuration

`doclayout FILE OUTPUT_DIR` accepts individual output flags or
`--all`. See [file exports](usage.md#file-conversion) for the full selection table,
filenames, and overwrite behavior. Folder conversion and `doclayout_single`
retain the settings below. `--output_format` is a single-format alternative for
file input and cannot be combined with new format flags.

Save this as `config.json` in your working directory:

```json
{
  "timeout": 180,
  "max_retries": 2,
  "max_output_tokens": 32768,
  "highres_image_dpi": 192,
  "page_concurrency": 3,
  "extract_images": false
}
```

```powershell
uv run doclayout_single document.pdf --config_json config.json --timeout 90
```

When options conflict, the later value wins. This example uses a 90-second
timeout. If `--timeout 90` comes before `--config_json config.json`, the file's
180-second value wins. Put the file option first when flags should override it.
Common CLI defaults and output/converter selection have their own handling;
use their dedicated flags.

Explicit `false` and zero values survive parsing. Each setting still has to pass
its own validation. Default-false booleans such as `--use_llm` are flags; default-true
booleans take a value, for example `--flatten_pdf false`.

| CLI option | Default | Purpose |
| --- | --- | --- |
| `--output_dir` | `OUTPUT_DIR` for legacy/folder commands | Root for legacy per-document folders; explicit destination alternative for new file conversion |
| `--output_format` | `markdown` | `markdown`, `html`, `json`, or `chunks` |
| `--page_range` | All pages | Example: `0,2-4` selects physical pages 1, 3, 4, 5 |
| `--disable_image_extraction` | Off | Sets `extract_images` to false |
| `--config_json` | None | Load a JSON configuration object |
| `--processors` | Default pipeline | Comma-separated full processor class paths; replaces the default list |
| `--converter_cls` | `PdfConverter` | Full converter class path |
| `--debug` / `-d` | Off | Enable PDF/layout image and JSON debug dumps under the output directory |

Folder-only options:

| Option | Default | Constraint or behavior |
| --- | --- | --- |
| `--workers` | `1` | Positive process count |
| `--num_chunks` | `1` | Positive number of partitions of the sorted file list |
| `--chunk_idx` | `0` | Zero-based partition index, smaller than `num_chunks` |
| `--max_files` | No limit | Positive limit applied after selecting the partition |
| `--skip_existing` | Off | Skip a document when an output representation already exists |

Debug processor settings are `debug_pdf_images`, `debug_layout_images`, and
`debug_json` (all false), plus `debug_data_folder` (default `debug_data`). The
removed uppercase `Settings.DEBUG_DATA_FOLDER` is a separate, retired setting.

## GUI, API, and Python differences

- In the GUI, Start/End pages are one-based and inclusive. Sidebar selections
  override startup values for page range, refinement, and header/footer visibility.
  The Debug checkbox displays results; it does not enable CLI-style debug files.
- The launcher `launch.cmd` binds `127.0.0.1:8471`, stops an existing DocLayout
  listener on that port (other applications require confirmation), and disables
  file watching. Cleanup waits up to five seconds and aborts on failure.
  Restarting discards the browser session and in-progress work, not saved results.
  `doclayout_gui` binds loopback and forwards arguments to the app;
  the CLI launcher leaves existing processes alone.
- The API accepts only the fields below; arbitrary processor/service settings
  are not HTTP parameters. `doclayout_server` defaults to host `127.0.0.1`,
  port `8000`, adjustable with `--host` and `--port`.
- In Python, pass a dictionary to the converter's `config` parameter. Use a
  zero-based integer list for `page_range`; renderer and processor selection
  use the converter's constructor arguments. See [Python usage](usage.md#python-library).

| API field | Default | Meaning |
| --- | --- | --- |
| `filepath` | Required on `/doclayout` | Path inside the configured input root; not accepted on upload route |
| `page_range` | `null` | Zero-based comma/range string |
| `use_llm` | `false` | Extra refinement |
| `paginate_output` | `false` | Renderer pagination |
| `output_format` | `markdown` | `markdown`, `html`, `json`, or `chunks` |

The upload route also requires multipart `file`. Unknown fields are rejected
with HTTP 422. See [HTTP API usage](usage.md#http-api) for requests and responses.

## Security and resource limits

The HTTP API requires `DOCLAYOUT_API_TOKEN`: a separate randomly generated token
of at least 32 non-whitespace ASCII characters. Set it in the process environment
or launch-folder `.env`; an environment value, even blank, takes precedence.
Send `Authorization: Bearer <token>` on every conversion request. Authentication
runs before body parsing. GET documentation remains public.

Filepath requests are disabled unless `DOCLAYOUT_INPUT_ROOT` names an existing,
dedicated directory. Relative paths are resolved there; absolute paths must remain
inside it. Traversal, network paths, alternate streams and hard links are rejected;
the opened file's final location and regular-file status are checked before copying.
Do not put private unrelated files in that directory. Use uploads when possible.

These operator settings use process environment variables or `local.env`, not
request fields or conversion JSON. Values must be positive integers.

| Setting | Default |
| --- | ---: |
| `DOCLAYOUT_MAX_FILE_MIB` | 200 |
| `DOCLAYOUT_MAX_PAGES` | 500 selected pages |
| `DOCLAYOUT_MAX_ARCHIVE_MEMBERS` | 10,000 |
| `DOCLAYOUT_MAX_EXPANDED_MIB` | 1,024 declared archive MiB |
| `DOCLAYOUT_MAX_SOURCE_PIXELS` | 64,000,000 |
| `DOCLAYOUT_MAX_RENDER_PIXELS` | 16,000,000 per rendered page |
| `DOCLAYOUT_MAX_WORKSHEET_CELLS` | 1,000,000 |
| `DOCLAYOUT_MAX_RESOURCE_MIB` | 64 per embedded resource |

The API allows one conversion per process; overlapping submissions receive 429.
Uploads allow one file and four option fields, with a total body allowance of
the file limit plus 1 MiB. Page ranges are checked before expansion. These bounds
reduce work but are not a native-parser sandbox or a total memory/CPU guarantee.
Archive limits inspect declared sizes before format parsing.

Document rendering accepts bounded embedded data resources only: external HTTP,
file and relative resources are disabled. Documents depending on linked images
or styles may render differently. The configured application font may still be
downloaded on first use with bounded streaming and atomic replacement. Model
extraction and chat still send selected content to the configured API endpoint.

All callers sharing a bearer token have the same authority; this is not tenant
isolation. Keep the GUI local. Remote deployments need operator-managed TLS,
access controls, request timeouts and process resource limits; multiple workers
need shared admission/rate controls. The Modal example is not live-validated.

### Fixed chat limits

Chat accepts questions up to 2,000 characters and answers up to 120 words and
2,000 characters. It includes at most six accepted previous turns. Serialized
request data is limited to 200,000 bytes, reserving 30,000 bytes before the draft
for verification overhead. These limits are fixed in code and cannot be changed
through the GUI or JSON settings.
Reduce the selected page range when parsed text exceeds the limit.

## Cost estimates

DocLayout uses these user-supplied USD rates per million tokens, defined in
[usage.py](../doclayout/usage.py):

| Model | Input | Cached input | Cache writes | Output |
| --- | ---: | ---: | ---: | ---: |
| gpt-6-sol | $2.00 | $0.20 | $2.50 | $10.00 |
| gpt-6-luna | $0.10 | $0.01 | $0.125 | $0.50 |

Reported input tokens include cached reads and cache writes. The calculator
subtracts both before pricing ordinary input, so each token is charged once.
Missing cache detail fields count as zero; tokens without a reported cache split
use the ordinary input rate. Output tokens include any reasoning tokens already
included in the provider's output count.

Missing input/output usage, invalid totals, and unpriced models make the estimate
partial. The displayed amount then covers only requests with usable usage.
Reported usage from incomplete or refused responses is retained. SDK retries
and charges absent from endpoint usage cannot be reconstructed. The table above
uses rates supplied for this project. They have not been checked against current
provider pricing, and the estimate is not a provider invoice.

## Advanced configuration

Model-generated tables and direct Markdown/refinement inputs share fixed limits:
positive ASCII integer spans, at most 1,000 rows or columns, and at most 100,000
expanded grid cells or cumulative span cells per table. Invalid or oversized
tables are rejected before grid allocation; merged HTML tables are checked again.
These limits are not browser or request options. They complement input-file and
model-token limits and do not replace deployment-level process resource limits.

```powershell
uv run doclayout_single --help
uv run doclayout_single config --help
uv run doclayout --help
```

The special `config --help` form lists discovered component attributes without
converting a document. Discovery includes advanced processor controls and prompt
attributes; appearance in this inventory does not make a value a supported model
override or an HTTP parameter. Full prompt text may appear in generated help.

Shared names apply to matching attributes across components. A class-specific
key such as `MarkdownRenderer_paginate_output` overrides the shared
`paginate_output` value for that class. Complex values need Python or JSON where
representable. See [configuration discovery](../doclayout/config/crawler.py),
[CLI parsing](../doclayout/config/printer.py), and
[assignment rules](../doclayout/util.py).

Retired OCR routing, local inference, model-selection, and credential controls
are rejected at configuration boundaries. Examples include `force_ocr`,
`disable_ocr`, `mode`, `keep_chars`, `pdftext_workers`, and `openai_model`.
See the [validator](../doclayout/config/validation.py) for the complete rejection
list and the [changelog](../CHANGELOG.md#210-2026-09-23) for retired Python interfaces.
Components can ignore other unknown Python/JSON keys. A setting may have no
effect even when no error appears.
