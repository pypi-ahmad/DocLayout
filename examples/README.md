# DocLayout deployment example

[doclayout_modal_deployment.py](doclayout_modal_deployment.py) builds the current
checkout and serves its FastAPI application on Modal with CPU compute.

Create a Modal secret named `doclayout-openai` containing `OPENAI_API_KEY`,
`DOCLAYOUT_API_TOKEN` (a separate random token of at least 32 ASCII characters),
and, if needed, `OPENAI_BASE_URL`. See [endpoint requirements](../docs/configuration.md#credentials-and-environment).
The deployment reads that secret from its process environment. A `.env` file on
your machine is not copied into the image.

For local setup and package checks, see [development](../docs/development.md).
The Modal CLI is an optional separate tool, outside the project dependency groups.
Once it is installed, run this command to deploy:

```powershell
modal deploy examples/doclayout_modal_deployment.py
```

The service exposes `/docs`, `POST /doclayout`, and `POST /doclayout/upload`.
For uploads, send a multipart `file` and optional `page_range`,
`output_format`, `paginate_output`, or `use_llm` fields.

Page extraction and extra refinement incur API charges. Conversion requests require
`Authorization: Bearer <token>`. Filepath access is disabled by default; use uploads.
Add deployment TLS, request timeouts and resource controls before remote use.
It needs no GPU or model-cache volume. The deployment has not been tested live.

The example image installs the development group, including server dependencies.
It supports PDFs and images. Other document formats need the `full` extra and native WeasyPrint
libraries added to the image before use. The example does not serve the Streamlit
workbench, document chat, annotations, or ZIP downloads.

Keep the root `LICENSE` file; the image copies it. API clients should check HTTP
status codes; conversion errors now return HTTP 500 and policy limits return 413.
See [API usage](../docs/usage.md#http-api).
