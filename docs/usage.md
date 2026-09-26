# Using DocLayout

[Back to README](../README.md) · [Configuration](configuration.md) · [Development](development.md)

## Installation

Follow the [README installation steps](../README.md#installation) for uv tool,
manual cloning, pip, uv pip, and release wheels. The base package includes the
CLI/library and all file exports. Add `gui` for Streamlit, `server` for the HTTP
API, or `full` for Office/HTML/EPUB converters. Add `layout` for V3 guidance;
if V3 cannot run, conversion uses Sol. Without an [alignment policy](configuration.md#mandatory-layout-policy),
Sol boxes/order are retained and V3 supplies guidance only.
Guidance is omitted if V3 fails; the result then reports Sol fallback.
Extras can be combined; the layout runtime requires Python 3.11+.
The Git commands in the README install the current `main` branch. The release
wheel installs `v3.0.0`; later changes on `main` are recorded under
[Unreleased](../CHANGELOG.md#unreleased).
An ordinary package install does not include the development group; see
[development setup](development.md#environment) when working on the source.

WeasyPrint requires native libraries for Office/HTML/EPUB conversion. Follow its
[Windows installation instructions](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows).
Installing Python dependencies alone may not provide those libraries. Document
providers can download a font on first use. V3 uses local weights, downloaded
only when absent; CPU execution is supported. If V3 cannot run, Sol still
extracts the page and the result records fallback.

### Installing the application package

For local source or wheel installation, choose one installer in your intended
Python environment:

```powershell
uv pip install ".[gui,layout]"
python -m pip install ".[gui,layout]"
uv build --wheel
uv pip install ".\dist\doclayout-3.0.0-py3-none-any.whl[gui,layout]"
```

See [build checks](development.md#build-and-package-checks) for verification.
Tool-installed commands run directly. In a checkout, prefix commands with
`uv run --extra layout` (plus `--extra gui` or `--extra server` when needed) to use
the project's environment. Python dependencies still need an
available package index or local cache even when DocLayout comes from GitHub.

## Credentials and model settings

Configure credentials before running extraction. DocLayout accepts
environment variables or `.env` in the launch folder. See the
[configuration guide](configuration.md#credentials-and-environment) for precedence,
model choices, request defaults, and controls. Extra refinement is optional;
page extraction always uses Sol.

## Browser workbench

In the source checkout, run `launch.cmd` for the browser on port 8471. It force-stops
any process listening on that port, including unrelated apps or active conversions,
then waits for the port to become free. Cleanup failure aborts startup with an
error. The `doclayout_gui` command also
binds loopback, with Streamlit's default port. It leaves port cleanup
to the caller and forwards extra arguments to the app without
interpreting them as Streamlit server flags.
The launcher selects both `gui` and `layout` extras using the existing frozen
lockfile. A complete evaluated policy enables V3 geometry/order matching;
without one, the GUI reports that it is retaining Sol boxes/order.

1. Upload a PDF, PNG, JPEG, GIF, DOCX, PPTX, XLSX, HTML, or EPUB file.
2. Choose Start page and End page. Both are inclusive and numbered from 1; the
   default selects the entire document. Images are treated as a single page.
3. Optionally enable extra refinement or retain page headers and footers.
4. Select Run DocLayout. Preparation verifies cached V3 weights, downloads absent
   files on first use, and warms up the local model. Readiness shows the actual
   CUDA or CPU provider, or a warning if V3 is unavailable. Each selected whole-page
   image goes to Sol, with a guide when available, to transcribe content and write HTML.
5. Inspect and download the result from the tabs.

Auto mode falls back to CPU if CUDA setup or inference fails; final results show
the device actually used and the fallback reason. Explicit CPU never probes CUDA;
explicit CUDA never falls back to CPU. No compatible GPU is required.
V3 preparation/inference failures produce a visible warning and Sol processes the
full image without a guide, keeping its validated boxes and order. Invalid
configuration, guide limits, and downstream layout-invariant violations remain
errors. Corrupt cached weights trigger fallback. There is no layout toggle.
Preview and downloads do not reload the model.
Debug metadata includes layout timing, region counts, and match counts.

| Tab | Behavior |
| --- | --- |
| Input preview | View a source page; converted office documents use their prepared PDF |
| Markdown | Sanitized theme-aware preview or raw Markdown; copy raw/formatted content or download `.md` |
| HTML | Styled white-page preview generated from the exact Markdown; copy or download HTML |
| Annotated | V3-derived matched boxes and Sol-estimated unmatched boxes; rectangles, not masks; download PNGs or a raster PDF |
| JSON | Hierarchical document output with metadata |
| Chunks | Flattened blocks with page and geometry information |
| Chat | Ask questions against parsed page text; accepted answers include original page numbers |

The Markdown and HTML previews use different styles but share the generated-image-only
resource policy. Remote document images are omitted from both. Exported HTML embeds
known image crops and converts supported LaTeX to MathML; failed conversions
retain readable LaTeX. Formatted copying uses the generated HTML.
Clipboard operations require browser support and permission on localhost/HTTPS.

The ZIP contains Markdown, HTML, document JSON, chunks, metadata, extracted crops,
and annotated PDF/PNGs. All use the [output filename convention](#output-filenames).
It excludes the uploaded source and chat. Annotations are raster copies with
V3-derived matched boxes and Sol-estimated unmatched boxes, not masks. They
contain no searchable PDF text layer.

Switching tabs and downloading files reuse the result without new OCR calls.
Changing the upload, page range, refinement, or header/footer setting clears
results and chat. Running extraction again also starts a fresh result. Debug
shows metadata and raw output; it does not save a GUI run history.

### Document chat

Chat sends parsed text, the question, and up to six accepted previous turns.
It sends no page images. The app checks quotes locally before a second model
verifies the candidate answer.

See [fixed chat limits](configuration.md#fixed-chat-limits) for question,
answer, history, and context limits. Select a smaller page range if the context
is too large. Missing, out-of-scope, unverified, and unavailable answers use fixed
status messages. Chat usage is separate from extraction metadata; Clear chat
removes its local history and usage details. The Session API cost sidebar
retains costs from cleared chats, previous uploads, repeat extractions, and failed
requests in this browser session. Chat costs include both draft and verification
requests. A new browser session starts a new total.

CLI commands print estimated cost per conversion. Metadata exports contain
`usage` records and a `cost` summary for OCR and optional refinement; chat costs
remain in the browser session. Previewing, exporting, and downloading completed
results adds no model cost. See [rates and limitations](configuration.md#cost-estimates).

## Command-line conversion

### File conversion

From a clone:

```powershell
uv run --extra layout doclayout document.pdf output
uv run --extra layout doclayout document.pdf output --all
uv run --extra layout doclayout document.pdf output --markdown --html
uv run --extra layout doclayout document.pdf output --json --chunks --metadata
uv run --extra layout doclayout document.pdf output --annotated-pdf --annotated-images
uv run --extra layout doclayout document.pdf output --zip
uv run --extra layout doclayout document.pdf output --all --page_range 0,2-4 --use_llm
uv run --extra layout doclayout --help
```

After a uv tool install, run the same commands without `uv run --extra layout`.
The file command requires a destination, either the second positional argument
or `--output_dir`. It builds one document and reuses it for every selected
export. CLI page numbers are zero-based; `0,2-4` selects pages 1, 3, 4, and 5.

`BASE` means the source stem plus the extraction timestamp, described below.

| Flag | Files written directly into the destination |
| --- | --- |
| No format flag, or `--markdown` | `BASE.md` and its extracted crops |
| `--html` | `BASE.html`, generated from Markdown with embedded crops and MathML |
| `--json` | `BASE.json`, hierarchical blocks with metadata |
| `--chunks` | `BASE_chunks.json`, flattened blocks with metadata |
| `--metadata` | `BASE_metadata.json` |
| `--images` | Extracted crop files, when present and enabled |
| `--annotated-pdf` | `BASE_annotated.pdf`, a raster PDF with V3-derived matched boxes and Sol-estimated unmatched boxes |
| `--annotated-images` | `annotations/BASE_page-N.png`, using original one-based page numbers |
| `--zip` | `BASE.zip`, containing the complete GUI bundle |
| `--all` | Every file above, including the ZIP |

Combine individual flags to select several outputs. Use `--all` on its own
without other format flags. `--output_format markdown`, `html`, `json`, or
`chunks` is also accepted as a single-format alternative, but cannot be combined
with the selection flags. `--zip` alone creates no loose document files.
`--disable_image_extraction` disables crops even in the full bundle.
Text exports use UTF-8. JSON and chunks use distinct filenames, so they can
coexist in one directory. The ZIP excludes the input document and chat history.

Each extraction gets a new timestamp, so later runs normally retain earlier
outputs in the same directory. An exact filename collision is still overwritten;
unrelated files remain intact.
Extraction and export generation finish before output files are written; their
failures preserve previous output. Filesystem write errors can leave a partial
set of outputs. A run cannot overwrite its own input document.

### Output filenames

For `report.pdf`, one extraction might produce
`report_20260923_143052.md`, `report_20260923_143052.html`,
`report_20260923_143052.json`, and `report_20260923_143052.zip`. The UTC timestamp
has seconds precision. Downloads from one completed GUI result keep the same
timestamp when Streamlit redraws the page.

Chunks and metadata add `_chunks.json` and `_metadata.json`; the annotated PDF
adds `_annotated.pdf`. Annotated images use `annotations/BASE_page-N.png` inside
ZIPs and CLI folders, or `BASE_page-N.png` for individual browser downloads.
Crop filenames also include `BASE`, and Markdown links are updated to match.

The source extension is removed. Spaces and characters other than letters,
numbers, underscores, dots, and hyphens become underscores; source stems are
limited to 140 characters to leave room for export suffixes.

### Folder and legacy single-file conversion

```powershell
uv run --extra layout doclayout documents --output_dir output --workers 1 --skip_existing
uv run --extra layout doclayout_single document.pdf --output_dir output --output_format markdown
uv run --extra layout doclayout_single document.pdf --page_range 0,2-4 --output_format html
```

These commands use a directory per document, with timestamped filenames, crops,
and a separate `_metadata.json` file. Select one format with `--output_format`:
`markdown`, `html`, `json`, or `chunks`. Their HTML comes
from document blocks. The new file command's HTML comes from Markdown, matching
the GUI. Export selection flags such as `--all` are for file input only.

Folder conversion processes files directly inside the input folder; it does not
recurse or filter out unsupported files. `--skip_existing` skips a document if an
output representation already exists. Failures are reported, other files
continue, and the command exits nonzero if any failed. Folder-only process and
partition options are rejected for file input.

For defaults, configuration JSON, argument-order precedence, and advanced
component options, see [configuration](configuration.md#cli-and-json-configuration).

## Python library

```python
from pathlib import Path

from doclayout.converters.pdf import PdfConverter
from doclayout.models import create_model_dict, shutdown_models
from doclayout.output import save_output

models = create_model_dict()
try:
    converter = PdfConverter(models, config={"page_range": [0], "use_llm": False})
    rendered = converter("document.pdf")
    print(rendered.markdown)
    Path("output").mkdir(exist_ok=True)
    save_output(rendered, "output", "document")
finally:
    shutdown_models(models)
```

`PdfConverter` accepts a filepath or PDF `BytesIO`. Its default renderer returns
Markdown, images, and metadata. `TableConverter` selects tables, forms, and
tables of contents; `OCRConverter` returns aligned blocks with HTML, V3-matched
geometry, and flagged Sol-only estimates. Select other renderers by their full
class paths. `OCRConverter` skips grouping and default processors. All converters
use the alignment-policy and Sol-fallback behavior described above.
Fatal layout configuration, guide, or invariant errors raise `LayoutError`
subclasses. V3 runtime failures are handled by conversion and recorded in
`rendered.metadata["layout"]`; direct `LayoutService` calls still raise typed
runtime errors. Other invalid configuration raises `ValueError`, and failed Sol
extraction raises `ExtractionError`.
Close shared models after use to release the HTTP client. Local layout sessions
remain cached for the process lifetime.

## HTTP API

Generate a separate random API token locally, then start the server. Keep it out
of source control and logs. Rotation requires restarting the API process.

```powershell
$env:DOCLAYOUT_API_TOKEN = uv run --no-sync python -c "import secrets; print(secrets.token_urlsafe(32))"
# Optional: an existing dedicated input directory, needed only for filepath requests.
$env:DOCLAYOUT_INPUT_ROOT = 'D:\documents\api-input'
uv run --extra server --extra layout doclayout_server --host 127.0.0.1 --port 8000
```

Interactive API documentation is at `http://127.0.0.1:8000/docs`; the generated
schema is at `/openapi.json`. These GET pages remain public. Keep the server local
unless you configure TLS, ingress access controls and resource limits. Filepath
access is disabled when the input root is unset. In a second terminal, supply the
same token through your protected environment or secret manager.

```powershell
$headers = @{ Authorization = "Bearer $env:DOCLAYOUT_API_TOKEN" }
$body = @{
    filepath = 'document.pdf'
    page_range = '0-1'
    output_format = 'markdown'
    use_llm = $false
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/doclayout' -Headers $headers -ContentType 'application/json' -Body $body

# PowerShell 7 multipart upload; the token is not placed in an external process argument.
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/doclayout/upload' -Headers $headers -Form @{ file = Get-Item 'document.pdf'; page_range = '0-1'; output_format = 'markdown' }
```

See the [API field reference](configuration.md#gui-api-and-python-differences)
for accepted fields, defaults, and page-range syntax. Unknown fields are rejected.

Successful responses contain `success`, `format`, `output`, `images`, and
`metadata`. `output` is a string, including serialized JSON for JSON/chunks;
image values are base64 strings. Clients must check HTTP status: 401 for missing
or invalid authentication, 403 for disallowed filepath access, 413 for resource
limits, 422 for invalid fields, 429 while busy, 503 for fatal layout errors,
and 500 for other conversion failures.
Malformed multipart requests may return 400. Errors omit private exception detail.
V3 runtime failure alone is not an HTTP failure: successful Sol fallback returns
200 with `alignment_mode: sol_fallback` and a sanitized layout `error_code` in
metadata. There is no HTTP parameter to disable V3 or set its device/cache/policy.
The API process runs one conversion at a time. GUI chat, annotations, and ZIP
downloads have no HTTP endpoints. Defaults are 200 MiB and 500 selected pages;
see [security limits](configuration.md#security-and-resource-limits).

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Credentials unavailable | Check the launch folder's `.env`; after changing Windows environment variables, open a new terminal and restart the app |
| Model request fails | Check endpoint support, model access, quota, timeout, and structured-output support |
| Office/HTML/EPUB conversion fails | Install the `full` extra and WeasyPrint's native libraries |
| GUI/API command lacks a module | Reinstall with the `gui` or `server` extra; base installation is CLI/library and exports |
| Port 8471 remains occupied | `launch.cmd` tries to force-stop its listeners; check the cleanup error if it cannot. `doclayout_gui` does not stop listeners |
| V3 unavailable, Sol fallback | Read the layout `error_code`; check the layout extra, model-cache access, or native runtime. Restart after repairing a cached startup failure |
| V3 misses content or disagrees | Sol blocks are retained. Review their `sol_only` reasons; do not invent matching thresholds to force agreement |
| Sol boxes/order, V3 guidance only | No matching policy is configured. This is supported; enable replacements only with a complete evaluated policy |
| Fatal layout error | Check invalid policy/device settings, guide limits, or a processor changing protected layout. These do not trigger Sol fallback |
| Hardlink warning during uv installation | uv falls back to copying across filesystems. `UV_LINK_MODE=copy` suppresses the warning; it does not fix missing packages |
| Clipboard copy unavailable | Use localhost/HTTPS and allow clipboard access, or download the file |
| Results disappear | Upload/processing changes invalidate them; a disconnected/replaced session can lose memory |
| Header or table is wrong | Review the source and try optional refinement; correctness is not guaranteed |
