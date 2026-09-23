# Using DocLayout

[Back to README](../README.md) · [Configuration](configuration.md) · [Development](development.md)

## Installation

Follow the [README installation steps](../README.md#installation) for uv tool,
manual cloning, pip, uv pip, and release wheels. The base package includes the
CLI/library and all file exports. Add `gui` for Streamlit, `server` for the HTTP
API, or `full` for Office/HTML/EPUB converters. Extras can be combined.
The commands pinned to v2.1.0 install the published release. Changes listed as
[Unreleased](../CHANGELOG.md#unreleased) currently exist only in this checkout.
An ordinary package install does not include the development group; see
[development setup](development.md#environment) when working on the source.

WeasyPrint requires native libraries for Office/HTML/EPUB conversion. Follow its
[Windows installation instructions](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows).
Installing Python dependencies alone may not provide those libraries. Document
providers can download a font on first use. PDF and image extraction needs no GPU
or local model weights.

### Installing the application package

For local source or wheel installation, choose one installer in your intended
Python environment:

```powershell
uv pip install ".[gui]"
python -m pip install ".[gui]"
uv build --wheel
uv pip install ".\dist\doclayout-2.1.0-py3-none-any.whl[gui]"
```

See [build checks](development.md#build-and-package-checks) for verification.
Tool-installed commands run directly. In a checkout, prefix commands with
`uv run` to use the project's environment. Python dependencies still need an
available package index or local cache even when DocLayout comes from GitHub.

## Credentials and model settings

Configure credentials before running extraction. The current source accepts
environment variables or `.env` in the launch folder. See the
[configuration guide](configuration.md#credentials-and-environment) for precedence,
model choices, request defaults, and controls. Extra refinement is optional;
page extraction always uses Sol.

## Browser workbench

In the source checkout, run `launch.cmd` for the browser on port 8471. It stops
the previous port listener before launching. The `doclayout_gui` command also
starts the GUI, but uses Streamlit's default server settings; it does not provide
the launcher's port cleanup. It forwards extra arguments to the app without
interpreting them as Streamlit server flags.

1. Upload a PDF, PNG, JPEG, GIF, DOCX, PPTX, XLSX, HTML, or EPUB file.
2. Choose Start page and End page. Both are inclusive and numbered from 1; the
   default selects the entire document. Images are treated as a single page.
3. Optionally enable extra refinement or retain page headers and footers.
4. Select Run DocLayout. Each selected page is sent for extraction.
5. Inspect and download the result from the tabs.

| Tab | Behavior |
| --- | --- |
| Input preview | View a source page; converted office documents use their prepared PDF |
| Markdown | Native theme-aware rendering or raw Markdown; copy raw/formatted content or download `.md` |
| HTML | Styled white-page preview generated from the exact Markdown; copy or download HTML |
| Annotated | Estimated region boxes over page images; download individual PNGs or a raster PDF |
| JSON | Hierarchical document output with metadata |
| Chunks | Flattened blocks with page and geometry information |
| Chat | Ask questions against parsed page text; accepted answers include original page numbers |

The Markdown and HTML previews use different styles. Exported HTML embeds
known image crops and converts supported LaTeX to MathML; failed conversions
retain readable LaTeX. Formatted copying uses the generated HTML.
Clipboard operations require browser support and permission on localhost/HTTPS.

The ZIP contains Markdown, HTML, document JSON, chunks, metadata, extracted crops,
and annotated PDF/PNGs. All use the [output filename convention](#output-filenames).
It excludes the uploaded source and chat. Annotations are raster copies with
estimated boxes. They contain no searchable PDF text layer.

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
uv run doclayout document.pdf output
uv run doclayout document.pdf output --all
uv run doclayout document.pdf output --markdown --html
uv run doclayout document.pdf output --json --chunks --metadata
uv run doclayout document.pdf output --annotated-pdf --annotated-images
uv run doclayout document.pdf output --zip
uv run doclayout document.pdf output --all --page_range 0,2-4 --use_llm
uv run doclayout --help
```

After a uv tool install, run the same commands without `uv run`.
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
| `--annotated-pdf` | `BASE_annotated.pdf`, a raster PDF with estimated region boxes |
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

For `report.pdf`, an extraction might produce
`report_20260923_143052.md`, `report_20260923_143052.html`,
`report_20260923_143052.json`, and `report_20260923_143052.zip`. The UTC timestamp
has seconds precision. GUI downloads keep the same timestamp across reruns.

Chunks and metadata add `_chunks.json` and `_metadata.json`; the annotated PDF
adds `_annotated.pdf`. Annotated images use `annotations/BASE_page-N.png` inside
ZIPs and CLI folders, or `BASE_page-N.png` for individual browser downloads.
Crop filenames also include `BASE`, and Markdown links are updated to match.

The source extension is removed. Spaces and characters other than letters,
numbers, underscores, dots, and hyphens become underscores; source stems are
limited to 140 characters to leave room for export suffixes.

### Folder and legacy single-file conversion

```powershell
uv run doclayout documents --output_dir output --workers 1 --skip_existing
uv run doclayout_single document.pdf --output_dir output --output_format markdown
uv run doclayout_single document.pdf --page_range 0,2-4 --output_format html
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
tables of contents; `OCRConverter` returns ordered blocks with HTML and estimated
geometry. Select other renderers by their full class paths.
Invalid configuration raises `ValueError`; failed model extraction raises
`ExtractionError`. Close shared models after use to release the HTTP client.

## HTTP API

```powershell
uv run doclayout_server --host 127.0.0.1 --port 8000
```

Interactive API documentation is at `http://127.0.0.1:8000/docs`; the generated
schema is at `/openapi.json`. Keep the server local unless you add authentication
and access controls. The filepath endpoint reads paths accessible to the server.

```powershell
$body = @{
    filepath = 'D:\documents\document.pdf'
    page_range = '0-1'
    output_format = 'markdown'
    use_llm = $false
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/doclayout' -ContentType 'application/json' -Body $body

curl.exe -X POST http://127.0.0.1:8000/doclayout/upload -F 'file=@document.pdf' -F 'page_range=0-1' -F 'output_format=markdown'
```

See the [API field reference](configuration.md#gui-api-and-python-differences)
for accepted fields, defaults, and page-range syntax. Unknown fields are rejected.

Successful responses contain `success`, `format`, `output`, `images`, and
`metadata`. `output` is a string, including serialized JSON for JSON/chunks;
image values are base64 strings. Conversion failures return HTTP 200 with
`success: false` and `error`; clients must check `success`. Invalid fields and
request validation errors return HTTP 422. The API process runs one conversion
at a time. GUI chat, annotations, and ZIP downloads have no HTTP endpoints.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Credentials unavailable | Check the launch folder's `.env`; after changing Windows environment variables, open a new terminal and restart the app |
| Model request fails | Check endpoint support, model access, quota, timeout, and structured-output support |
| Office/HTML/EPUB conversion fails | Install the `full` extra and WeasyPrint's native libraries |
| GUI/API command lacks a module | Reinstall with the `gui` or `server` extra; base installation is CLI/library and exports |
| Port 8471 remains occupied | Check permission to stop its listener; the launcher reports failures |
| Clipboard copy unavailable | Use localhost/HTTPS and allow clipboard access, or download the file |
| Results disappear | Upload/processing changes invalidate them; a disconnected/replaced session can lose memory |
| Header or table is wrong | Review the source and try optional refinement; correctness is not guaranteed |
