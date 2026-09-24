"""Prepare uploads and render all results from a single conversion."""

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from doclayout.config.parser import ConfigParser
from doclayout.converters.pdf import PdfConverter
from doclayout.providers.registry import provider_from_filepath
from doclayout.renderers.chunk import ChunkRenderer
from doclayout.renderers.json import JSONRenderer
from doclayout.renderers.markdown import MarkdownRenderer
from doclayout.security import DocumentLimitError, MIB
from doclayout.settings import settings


@dataclass
class Upload:
    data: bytes
    suffix: str
    count: int


def prepare_upload(data: bytes, name: str) -> Upload:
    if len(data) > settings.DOCLAYOUT_MAX_FILE_MIB * MIB:
        raise DocumentLimitError("Document exceeds the configured file size limit.")
    suffix = Path(name).suffix.lower()
    with TemporaryDirectory() as directory:
        path = Path(directory) / ("document" + suffix)
        path.write_bytes(data)
        provider = provider_from_filepath(str(path))(str(path), {"page_range": [0]})
        try:
            count = len(provider)
            if hasattr(provider, "temp_pdf_path"):
                data = Path(provider.temp_pdf_path).read_bytes()
                suffix = ".pdf"
            return Upload(data, suffix, count)
        finally:
            provider.close()


def preview(upload: Upload, page: int):
    with TemporaryDirectory() as directory:
        path = Path(directory) / ("document" + upload.suffix)
        path.write_bytes(upload.data)
        provider = provider_from_filepath(str(path))(str(path), {"page_range": [page]})
        try:
            return provider.get_images([page], 96)[0]
        finally:
            provider.close()


def page_range(start: int, end: int, count: int) -> str:
    if not 1 <= start <= end <= count:
        raise ValueError("Choose pages with 1 ≤ Start page ≤ End page ≤ page count.")
    return f"{start - 1}-{end - 1}"


def run_document(
    upload: Upload, options: dict, models: dict, usage_entries=None
) -> dict:
    # Debug files must never escape the temporary session workspace.
    options = {**options, "output_format": "markdown", "debug": False}
    parser = ConfigParser(options)
    config = parser.generate_config_dict()
    for key in ("debug_pdf_images", "debug_layout_images", "debug_json"):
        config[key] = False
    with TemporaryDirectory() as directory:
        path = Path(directory) / ("document" + upload.suffix)
        path.write_bytes(upload.data)
        converter = PdfConverter(
            artifact_dict=models,
            config=config,
            processor_list=parser.get_processors(),
            renderer=parser.get_renderer(),
        )
        try:
            document = converter.build_document(str(path))
        finally:
            from doclayout.services.openai import OpenAIService

            if usage_entries is not None and isinstance(
                converter.extraction_service, OpenAIService
            ):
                usage_entries.extend(converter.extraction_service.usage)
        markdown = MarkdownRenderer(config)(document)
        json_output = JSONRenderer(config)(document)
        chunks = ChunkRenderer(config)(document)
        pages = {}
        for page in document.pages:
            assert page.page_id is not None
            single = document.model_copy(update={"pages": [page]})
            single._page_index = None
            text = MarkdownRenderer(config)(single).markdown.strip()
            if text and not page.ocr_errors_detected:
                pages[page.page_id + 1] = text
        return {
            "document": document,
            "markdown": markdown.markdown,
            "images": markdown.images,
            "metadata": markdown.metadata,
            "json": json_output.model_dump_json(indent=2),
            "chunks": chunks.model_dump_json(indent=2),
            "pages": pages,
        }
