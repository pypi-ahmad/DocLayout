# DocLayout deployment example

[doclayout_modal_deployment.py](doclayout_modal_deployment.py) builds this checkout and
serves the local FastAPI application on Modal using CPU compute.

Create a Modal secret named `doclayout-openai` containing `OPENAI_API_KEY` and,
if needed, `OPENAI_BASE_URL`. See [endpoint requirements](../docs/configuration.md#credentials-and-environment).
The Modal secret supplies the deployed process environment. Local configuration
files do not supply those values to the deployment.

For local setup and package checks, see [development](../docs/development.md).
The Modal CLI is an optional separate tool, outside the project dependency groups.
Once it is installed, run this command to deploy:

```powershell
modal deploy examples/doclayout_modal_deployment.py
```

The service exposes `/docs`, `POST /doclayout`, and `POST /doclayout/upload`.
For uploads, send a multipart `file` and optional `page_range`,
`output_format`, `paginate_output`, or `use_llm` fields.

Page extraction and extra refinement incur API charges. This example has no
authentication layer; add access controls before exposing sensitive documents.
It needs no GPU or model-cache volume. The deployment has not been tested live.

The example image installs the development group, which includes server dependencies,
and supports the base PDF/image
workflow. Additional document formats need the `full` extra and native WeasyPrint
libraries added to the image before use. The example does not serve the Streamlit
workbench, document chat, annotations, or ZIP downloads.

Keep the root `LICENSE` file; the image copies it. API clients should
check the response's `success` field even after HTTP 200; conversion errors are
returned in the response body. See [API usage](../docs/usage.md#http-api).
