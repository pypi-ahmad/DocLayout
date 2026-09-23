# DocLayout configuration

[Back to README](../README.md) · [Usage](usage.md) · [Development](development.md)

For processor controls beyond the settings below, see
[advanced configuration](#advanced-configuration).

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
`gpt-6-sol`; document chat also requires `gpt-6-luna`. Credentials do not belong
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
converters. These control the application rather than the model. Path defaults
are set when the class is defined. Changing a base directory does not recalculate
derived paths, so set the final path explicitly. Model requests send PNG images
regardless of `OUTPUT_IMAGE_FORMAT`.

## Models and request limits

| Task | Model | Request defaults |
| --- | --- | --- |
| Page extraction and optional refinement | `gpt-6-sol` | Medium reasoning; 32,768 output tokens; 180-second timeout; two SDK retries |
| Chat draft and verification | `gpt-6-luna` | Medium reasoning; 8,192 output tokens; 60-second timeout; no retries |

Model names, reasoning effort, and chat request limits are fixed in code. The
Sol settings below are configurable. `use_llm=False` disables extra refinement;
every selected page still uses Sol extraction. There is no local OCR fallback.

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
- The launcher `launch.cmd` binds `127.0.0.1:8471`, stops an existing listener,
  and disables file watching. These values are written in the launcher.
  `doclayout_gui` uses Streamlit defaults and forwards arguments to the app;
  it does not implement the launcher's port cleanup.
- The API accepts only the fields below; arbitrary processor/service settings
  are not HTTP parameters. `doclayout_server` defaults to host `127.0.0.1`,
  port `8000`, adjustable with `--host` and `--port`.
- In Python, pass a dictionary to the converter's `config` parameter. Use a
  zero-based integer list for `page_range`; renderer and processor selection
  use the converter's constructor arguments. See [Python usage](usage.md#python-library).

| API field | Default | Meaning |
| --- | --- | --- |
| `filepath` | `null` | Server-readable path for `/doclayout`; upload route supplies a temporary path |
| `page_range` | `null` | Zero-based comma/range string |
| `use_llm` | `false` | Extra refinement |
| `paginate_output` | `false` | Renderer pagination |
| `output_format` | `markdown` | `markdown`, `html`, `json`, or `chunks` |

The upload route also requires multipart `file`. Unknown fields are rejected
with HTTP 422. See [HTTP API usage](usage.md#http-api) for requests and responses.

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
