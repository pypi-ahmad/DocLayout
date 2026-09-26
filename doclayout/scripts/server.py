# Modified for DocLayout; see NOTICE for a summary of changes.
"""Authenticated API with bounded uploads and serialized conversion."""

import base64
import io
import secrets
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import anyio
import click
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException
from starlette.responses import HTMLResponse, JSONResponse

from doclayout.config.parser import ConfigParser
from doclayout.converters.pdf import PdfConverter
from doclayout.credentials import api_configuration
from doclayout.input_files import input_file
from doclayout.models import create_model_dict, shutdown_models
from doclayout.output import text_from_rendered
from doclayout.security import MIB, DocumentLimitError
from doclayout.services.layout import LayoutError, layout_error_message
from doclayout.settings import settings
from doclayout.util import parse_range_str

app_data = {}


@asynccontextmanager
async def lifespan(app):
    token, root = api_configuration()
    app_data.update(token=token, root=root, busy=False)
    try:
        app_data["models"] = create_model_dict()
        yield
    finally:
        try:
            if "models" in app_data:
                shutdown_models(app_data.pop("models"))
        finally:
            app_data.clear()


class RequestGuard:
    """Gate before FastAPI parses JSON or spools multipart uploads."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD"):
            return await self.app(scope, receive, send)
        headers = scope.get("headers", [])
        auth = [v for k, v in headers if k.lower() == b"authorization"]
        expected = app_data.get("token", "").encode("ascii")
        scheme, _, credential = (
            auth[0].partition(b" ") if len(auth) == 1 else (b"", b"", b"")
        )
        if (
            not app_data.get("token")
            or len(auth) != 1
            or scheme.lower() != b"bearer"
            or not secrets.compare_digest(credential, expected)
        ):
            return await JSONResponse(
                {"detail": "Authentication required."},
                401,
                headers={"WWW-Authenticate": "Bearer"},
            )(scope, receive, send)
        limit = (settings.DOCLAYOUT_MAX_FILE_MIB + 1) * MIB
        if scope["path"].rstrip("/") != "/doclayout/upload":
            limit = min(limit, 64 * 1024)
        lengths = [v for k, v in headers if k.lower() == b"content-length"]
        if len(lengths) > 1 or (lengths and not lengths[0].isdigit()):
            return await JSONResponse({"detail": "Invalid content length."}, 400)(
                scope, receive, send
            )
        if lengths and (len(lengths[0]) > 12 or int(lengths[0]) > limit):
            return await JSONResponse(
                {"detail": "Request exceeds the body limit."}, 413
            )(scope, receive, send)
        if app_data.get("busy"):
            return await JSONResponse(
                {"detail": "A conversion is already running."},
                429,
                headers={"Retry-After": "1"},
            )(scope, receive, send)
        # Check and reserve on the same event loop without an intervening await.
        app_data["busy"] = True
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > limit:
                    if scope["path"].rstrip("/") == "/doclayout/upload":
                        # Starlette closes partially spooled files on this type.
                        raise MultiPartException("Request exceeds the body limit.")
                    raise HTTPException(413, "Request exceeds the body limit.")
            return message

        try:
            await self.app(scope, bounded_receive, send)
        finally:
            app_data["busy"] = False


app = FastAPI(title="DocLayout API", lifespan=lifespan)
app.add_middleware(RequestGuard)
bearer = HTTPBearer()


@app.exception_handler(StarletteHTTPException)
async def http_error(request, exc):
    status = 413 if exc.detail == "Request exceeds the body limit." else exc.status_code
    details = {
        400: "Invalid request body.",
        401: "Authentication required.",
        403: "Filepath access is not allowed.",
        404: "Not found.",
        405: "Method not allowed.",
        413: "Document or request exceeds a configured limit.",
        422: "Invalid request fields.",
        429: "A conversion is already running.",
    }
    return JSONResponse(
        {"detail": details.get(status, "Document conversion failed.")},
        status,
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse({"detail": "Invalid request fields."}, 422)


@app.exception_handler(LayoutError)
async def layout_error(request, exc):
    return JSONResponse(
        {"detail": layout_error_message(exc), "code": type(exc).__name__}, 503
    )


@app.get("/")
async def root():
    return HTMLResponse('<h1>DocLayout API</h1><a href="/docs">API documentation</a>')


class ConversionParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page_range: str | None = Field(default=None, max_length=4096)
    use_llm: bool = False
    paginate_output: bool = False
    output_format: Literal["markdown", "json", "html", "chunks"] = "markdown"

    @field_validator("page_range")
    @classmethod
    def valid_pages(cls, value):
        if value is not None:
            parse_range_str(value)
        return value


class CommonParams(ConversionParams):
    filepath: str = Field(min_length=1, max_length=4096)


def _convert_pdf(path, params):
    parser = ConfigParser(params.model_dump(exclude={"filepath"}))
    converter = PdfConverter(
        config=parser.generate_config_dict(),
        artifact_dict=app_data["models"],
        renderer=parser.get_renderer(),
    )
    rendered = converter(str(path))
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


def _copy_limited(source, output):
    size = 0
    while chunk := source.read(64 * 1024):
        size += len(chunk)
        if size > settings.DOCLAYOUT_MAX_FILE_MIB * MIB:
            raise DocumentLimitError("Document exceeds the configured file size limit.")
        output.write(chunk)


def _path_conversion(params):
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / ("document" + Path(params.filepath).suffix)
        try:
            with (
                input_file(params.filepath, app_data["root"]) as source,
                target.open("wb") as output,
            ):
                _copy_limited(source, output)
        except DocumentLimitError:
            raise
        except (OSError, ValueError):
            raise HTTPException(403, "Filepath access is not allowed.") from None
        return _convert_pdf(target, params)


async def _run(function, *args):
    try:
        # Cancellation must not free the slot while the worker is active.
        with anyio.CancelScope(shield=True):
            return await anyio.to_thread.run_sync(
                function, *args, abandon_on_cancel=False
            )
    except (HTTPException, LayoutError):
        raise
    except DocumentLimitError as exc:
        raise HTTPException(413, str(exc)) from None
    except Exception:
        raise HTTPException(500, "Document conversion failed.") from None


@app.post("/doclayout", dependencies=[Depends(bearer)])
async def convert_pdf(params: CommonParams):
    return await _run(_path_conversion, params)


upload_schema = ConversionParams.model_json_schema()
upload_schema["properties"]["file"] = {"type": "string", "format": "binary"}
upload_schema["required"] = ["file"]


@app.post(
    "/doclayout/upload",
    dependencies=[Depends(bearer)],
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"multipart/form-data": {"schema": upload_schema}},
        }
    },
)
async def convert_pdf_upload(request: Request):
    async with request.form(max_files=1, max_fields=4, max_part_size=4096) as form:
        pairs = list(form.multi_items())
        if len({key for key, _ in pairs}) != len(pairs):
            raise HTTPException(422, "Duplicate form fields are not allowed.")
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise HTTPException(422, "One file is required.")
        try:
            params = ConversionParams.model_validate(
                {key: value for key, value in pairs if key != "file"}
            )
        except ValidationError:
            raise HTTPException(422, "Invalid form fields.") from None
        suffix = Path(file.filename or "document.pdf").suffix.lower()
        if not suffix or len(suffix) > 12 or not suffix[1:].isalnum():
            suffix = ".pdf"

        def convert_upload():
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / ("document" + suffix)
                with path.open("wb") as output:
                    _copy_limited(file.file, output)
                return _convert_pdf(path, params)

        return await _run(convert_upload)


@click.command()
@click.option("--port", type=int, default=8000)
@click.option("--host", type=str, default="127.0.0.1")
def server_cli(port, host):
    import uvicorn

    uvicorn.run(app, host=host, port=port)
