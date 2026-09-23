# DocLayout configuration

[Back to README](../README.md) · [Usage](usage.md) · [Development](development.md)

For processor-specific controls beyond the settings below, see
[advanced configuration](#advanced-configuration). The examples use the current
implementation and leave extraction prompts unchanged.

## Credentials and environment

| Variable | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | Required API credential for extraction and document chat |
| `OPENAI_BASE_URL` | Optional OpenAI-compatible endpoint; omitted uses the SDK default |

Set credentials in the process environment. After changing Windows user
environment variables, open a new terminal and restart DocLayout. Check presence
without displaying values:

```powershell
[bool]$env:OPENAI_API_KEY
[bool]$env:OPENAI_BASE_URL
```

The endpoint must support Responses, image input, and structured output for
`gpt-6-sol`; document chat also requires `gpt-6-luna`. Credentials do not belong
in CLI flags, configuration JSON, source code, or Git.

Application `Settings` uses Pydantic Settings to read environment variables and
a discovered `local.env` file. Environment values take precedence. Reading the
file does not export its contents into the process environment. Putting
`OPENAI_API_KEY` in `local.env` alone does not configure the application clients.

Common application settings from [settings.py](../doclayout/settings.py):

| Setting | Default | Purpose |
| --- | --- | --- |
| `OUTPUT_DIR` | `conversion_results` under the package's parent directory | Default CLI output root |
| `OUTPUT_ENCODING` | `utf-8` | Saved text and metadata encoding |
| `OUTPUT_IMAGE_FORMAT` | `JPEG` | Saved crops and API image encoding |
| `LOGLEVEL` | `INFO` | Application logging level |

The same settings class defines font paths and an artifact URL used by document
format converters. These advanced settings control the application, not the model.
The class definition sets path defaults. Changing a base-directory setting
does not automatically recompute every derived path. Set the final path
you need explicitly. The model service sends PNG images independently of
`OUTPUT_IMAGE_FORMAT`.

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

The service caps all Sol requests at three concurrent requests per process,
including refinement. Increasing folder workers creates additional processes;
it does not increase that per-process cap.

## CLI and JSON configuration

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

When you supply conflicting options, the later value wins. This example
uses a 90-second timeout. Putting `--timeout 90` before `--config_json config.json`
lets the file replace it with 180. Flags do not always take precedence.
Put the file option first and overrides afterward. Avoid setting the same value
in multiple places. Common CLI defaults and output/converter selection have their
own handling; use dedicated flags for selecting the output format and components.

Explicit `false` and zero values survive parsing. Each setting still has to pass
its own validation. Default-false booleans such as `--use_llm` are flags; default-true
booleans take a value, for example `--flatten_pdf false`.

| CLI option | Default | Purpose |
| --- | --- | --- |
| `--output_dir` | `OUTPUT_DIR` | Root for per-document output folders |
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
list and the [changelog](../CHANGELOG.md#unreleased) for retired Python interfaces.
Components can ignore other unknown Python/JSON keys. A setting may have no
effect even when no error appears.
