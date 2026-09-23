# DocLayout deployment example

[doclayout_modal_deployment.py](doclayout_modal_deployment.py) builds this checkout and
serves the local FastAPI application on Modal using CPU compute.

Create a Modal secret named `doclayout-openai` containing `OPENAI_API_KEY` and,
if needed, `OPENAI_BASE_URL`. The endpoint must support GPT-6 Sol image input,
Responses and structured outputs. Do not place credentials in source files.

With the optional Modal CLI installed, deployment is explicit:

```powershell
modal deploy examples/doclayout_modal_deployment.py
```

The service exposes `/docs`, `POST /doclayout`, and `POST /doclayout/upload`.
For uploads, send a multipart `file` and optional `page_range`,
`output_format`, `paginate_output`, or `use_llm` fields.

Page extraction and extra refinement incur API charges. This example has no
authentication layer; add access controls before exposing sensitive documents.
It needs no GPU or model-cache volume. Deployment has not been live-verified.

The example image installs the development group and supports the base PDF/image
workflow. Additional document formats need the `full` extra and native WeasyPrint
libraries added to the image before use. The example does not serve the Streamlit
workbench, document chat, annotations, or ZIP downloads.

The root `LICENSE` must be present because the image copies it. API clients should
check the response's `success` field even after HTTP 200; conversion errors are
returned in the response body. See [API usage](../docs/usage.md#http-api).
