"""Shared document limits and an offline resource policy for HTML rendering."""

import base64
import binascii
import io
import math
from pathlib import Path
from urllib.parse import unquote_to_bytes
from zipfile import BadZipFile, ZipFile, is_zipfile

from PIL import Image, UnidentifiedImageError

from doclayout.settings import settings

MIB = 1024 * 1024
MAX_TABLE_DIMENSION = 1000
MAX_TABLE_CELLS = 100_000


class DocumentLimitError(ValueError):
    """An operator-defined document bound was exceeded; safe to display."""


def check_table(table):
    """Validate spans and bound grid size and span work before expansion.

    Return the row count and span-aware column count without allocating a grid.
    These fixed limits also apply to direct renderer and refinement callers.
    """
    rows = table.find_all("tr")
    if len(rows) > MAX_TABLE_DIMENSION:
        raise DocumentLimitError("Table exceeds the row limit.")
    carried_columns = [0] * len(rows)
    max_columns = work = 0
    for index, row in enumerate(rows):
        columns = carried_columns[index]
        for cell in row.find_all(["td", "th"]):
            spans = []
            for attribute in ("rowspan", "colspan"):
                raw = str(cell.get(attribute, "1"))
                if (
                    len(raw) > len(str(MAX_TABLE_DIMENSION))
                    or not raw.isascii()
                    or not raw.isdecimal()
                    or not 1 <= int(raw) <= MAX_TABLE_DIMENSION
                ):
                    raise DocumentLimitError("Table has an invalid or excessive span.")
                spans.append(int(raw))
            rowspan, colspan = spans
            work += rowspan * colspan
            columns += colspan
            if work > MAX_TABLE_CELLS or columns > MAX_TABLE_DIMENSION:
                raise DocumentLimitError("Table exceeds the expanded cell limit.")
            for next_row in range(index + 1, min(index + rowspan, len(rows))):
                carried_columns[next_row] += colspan
        max_columns = max(max_columns, columns)
    if max_columns > MAX_TABLE_DIMENSION or len(rows) * max_columns > MAX_TABLE_CELLS:
        raise DocumentLimitError("Table exceeds the expanded cell limit.")
    return len(rows), max_columns


def check_file(path):
    """Check compressed size and archive declarations before format parsing."""
    size = Path(path).stat().st_size
    if size > settings.DOCLAYOUT_MAX_FILE_MIB * MIB:
        raise DocumentLimitError("Document exceeds the configured file size limit.")
    if not is_zipfile(path):
        return
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > settings.DOCLAYOUT_MAX_ARCHIVE_MEMBERS:
                raise DocumentLimitError("Archive has too many members.")
            total = 0
            for entry in entries:
                if entry.file_size > settings.DOCLAYOUT_MAX_FILE_MIB * MIB:
                    raise DocumentLimitError("Archive member exceeds the size limit.")
                total += entry.file_size
                if total > settings.DOCLAYOUT_MAX_EXPANDED_MIB * MIB:
                    raise DocumentLimitError("Archive exceeds the expanded size limit.")
    except BadZipFile:
        raise ValueError("Invalid document archive.") from None


def check_pixels(width, height, *, source=False):
    limit = (
        settings.DOCLAYOUT_MAX_SOURCE_PIXELS
        if source
        else settings.DOCLAYOUT_MAX_RENDER_PIXELS
    )
    if (
        not math.isfinite(width)
        or not math.isfinite(height)
        or width <= 0
        or height <= 0
        or math.ceil(width) * math.ceil(height) > limit
    ):
        raise DocumentLimitError("Image exceeds the configured pixel limit.")


def check_resource(raw):
    """Bound resource bytes and raster dimensions before encoding or decoding."""
    if len(raw) > settings.DOCLAYOUT_MAX_RESOURCE_MIB * MIB:
        raise DocumentLimitError("Embedded resource exceeds the size limit.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            check_pixels(*image.size, source=True)
    except UnidentifiedImageError:
        pass


def image_data_uri(raw, mime_type):
    check_resource(raw)
    # Metadata is emitted inside an HTML attribute by the format adapters.
    if not mime_type.startswith("image/") or any(
        c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/.-+"
        for c in mime_type
    ):
        raise ValueError("Invalid image type.")
    return f"data:{mime_type};base64,{base64.b64encode(raw).decode('ascii')}"


def embedded_resource(url):
    """Only data carried by the document may be fetched; never delegate URLs."""
    limit = settings.DOCLAYOUT_MAX_RESOURCE_MIB * MIB
    if not isinstance(url, str) or not url.startswith("data:"):
        raise ValueError("External document resources are disabled.")
    # A percent-encoded byte occupies at most three input characters. Bound the
    # encoded form too, before either URL decoding or base64 allocation.
    if len(url) > limit * 4 + 1024:
        raise DocumentLimitError("Embedded resource exceeds the size limit.")
    header, separator, payload = url[5:].partition(",")
    if not separator or len(header) > 1024:
        raise ValueError("Invalid embedded resource.")
    raw = unquote_to_bytes(payload)
    try:
        if header.lower().endswith(";base64"):
            if len(raw) > ((limit + 2) // 3) * 4:
                raise DocumentLimitError("Embedded resource exceeds the size limit.")
            raw = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        if isinstance(exc, DocumentLimitError):
            raise
        raise ValueError("Invalid embedded resource.") from None
    check_resource(raw)
    return {"string": raw, "mime_type": header.split(";", 1)[0] or "text/plain"}
