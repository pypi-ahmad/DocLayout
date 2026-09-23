# Modified for DocLayout; see NOTICE for a summary of changes.
"""Local API. Conversion is serialized because PDFium is not thread safe."""

import asyncio
import base64
import io
import os
import tempfile
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import click
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.responses import HTMLResponse

from doclayout.config.parser import ConfigParser
from doclayout.converters.pdf import PdfConverter
from doclayout.models import create_model_dict, shutdown_models
from doclayout.output import text_from_rendered
from doclayout.settings import settings

app_data = {}


@asynccontextmanager
async def lifespan(app):
    app_data["models"] = create_model_dict()
    app_data["lock"] = asyncio.Lock()
    try:
        yield
    finally:
        shutdown_models(app_data.pop("models"))
        app_data.pop("lock")


app = FastAPI(title="DocLayout API", lifespan=lifespan)


@app.get("/")
async def root():
    return HTMLResponse('<h1>DocLayout API</h1><a href="/docs">API documentation</a>')


class CommonParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filepath: str | None = None
    page_range: str | None = None
    use_llm: bool = False
    paginate_output: bool = False
    output_format: Literal["markdown", "json", "html", "chunks"] = "markdown"


async def _convert_pdf(params):
    async with app_data["lock"]:
        try:
            parser = ConfigParser(params.model_dump())
            converter = PdfConverter(
                config=parser.generate_config_dict(),
                artifact_dict=app_data["models"],
                renderer=parser.get_renderer(),
            )
            rendered = converter(params.filepath)
            text, _, images = text_from_rendered(rendered)
            encoded = {}
            for name, image in images.items():
                stream = io.BytesIO()
                image.save(stream, format=settings.OUTPUT_IMAGE_FORMAT)
                encoded[name] = base64.b64encode(stream.getvalue()).decode()
            return {
                "success": True,
                "format": params.output_format,
                "output": text,
                "images": encoded,
                "metadata": rendered.metadata,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)}


@app.post("/doclayout")
async def convert_pdf(params: CommonParams):
    return await _convert_pdf(params)


@app.post("/doclayout/upload")
async def convert_pdf_upload(
    request: Request,
    file: Annotated[UploadFile, File()],
):
    form = await request.form()
    try:
        params = CommonParams.model_validate(
            {key: value for key, value in form.items() if key != "file"}
        )
    except ValidationError:
        raise HTTPException(
            status_code=422,
            detail="Invalid form fields. Use page_range, use_llm, paginate_output, output_format.",
        ) from None
    # Never use the upload's filename as a filesystem path.
    suffix = os.path.splitext(file.filename or ".pdf")[1]
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "document" + suffix)
        with open(path, "wb") as output:
            output.write(await file.read())
        return await _convert_pdf(params.model_copy(update={"filepath": path}))


@click.command()
@click.option("--port", type=int, default=8000)
@click.option("--host", type=str, default="127.0.0.1")
def server_cli(port, host):
    import uvicorn

    uvicorn.run(app, host=host, port=port)
