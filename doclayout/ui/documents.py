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
    """Prepared source bytes, normalized suffix, and total page count.

    Attributes:
        data (bytes): Original bytes or an Office provider's converted PDF.
        suffix (str): Lowercase extension used for temporary input files.
        count (int): Number of pages available before selection.
    """

    data: bytes
    suffix: str
    count: int


def prepare_upload(data: bytes, name: str) -> Upload:
    """Inspect an upload and normalize Office inputs to PDF without model calls.

    Args:
        data (bytes): Uploaded file contents.
        name (str): Filename used to select a provider by extension.

    Returns:
        Upload: Prepared bytes and page count; temporary files are removed.

    Raises:
        DocumentLimitError: Input exceeds the configured byte limit.
        ValueError: Provider validation rejects the input.
        OSError: Temporary file or provider I/O fails.
    """
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
    """Render one zero-based page at 96 DPI without an extraction request.

    Args:
        upload (Upload): Prepared source document.
        page (int): Zero-based page index accepted by the provider.

    Returns:
        PIL.Image.Image: Rendered page after provider resources are closed.

    Raises:
        ValueError: Provider rejects the document or page selection.
        OSError: Source loading or rendering fails.
    """
    with TemporaryDirectory() as directory:
        path = Path(directory) / ("document" + upload.suffix)
        path.write_bytes(upload.data)
        provider = provider_from_filepath(str(path))(str(path), {"page_range": [page]})
        try:
            return provider.get_images([page], 96)[0]
        finally:
            provider.close()


def page_range(start: int, end: int, count: int) -> str:
    """Translate an inclusive one-based UI selection to a zero-based range.

    Args:
        start (int): First selected page, starting at one.
        end (int): Last selected page, inclusive.
        count (int): Total available pages.

    Returns:
        str: Converter range such as ``0-1``.

    Raises:
        ValueError: The range is reversed or outside the document.
    """
    if not 1 <= start <= end <= count:
        raise ValueError("Choose pages with 1 ≤ Start page ≤ End page ≤ page count.")
    return f"{start - 1}-{end - 1}"


def run_document(
    upload: Upload, options: dict, models: dict, usage_entries=None
) -> dict:
    """Convert selected pages once and render the in-memory export payloads.

    Args:
        upload (Upload): Prepared document bytes.
        options (dict): Converter options; debug output is forcibly disabled.
        models (dict): Shared converter service configuration.
        usage_entries (list | None): Optional ledger receiving extraction usage,
            including usage reported before a conversion failure.

    Returns:
        dict: Document, Markdown, images, metadata, JSON, chunks, and readable
        one-based page text. No persistent export files are written here.

    Raises:
        ValueError: Configuration or source validation fails.
        OSError: Temporary input I/O fails.
        ExtractionError: The configured extraction service fails.
    """
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
