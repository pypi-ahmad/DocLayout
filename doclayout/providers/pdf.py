# Modified for DocLayout; see NOTICE for a summary of changes.
"""PDF rendering without embedded-text extraction or OCR routing."""

from contextlib import contextmanager
from threading import RLock
from typing import Annotated

import pypdfium2 as pdfium

from doclayout.providers import BaseProvider
from doclayout.schema.polygon import PolygonBox
from doclayout.security import DocumentLimitError, check_file, check_pixels
from doclayout.settings import settings

PDFIUM_LOCK = RLock()


class PdfProvider(BaseProvider):
    page_range: Annotated[list[int] | None, "Zero-based pages to process."] = None
    flatten_pdf: Annotated[bool, "Render PDF form fields."] = True

    def __init__(self, filepath, config=None):
        super().__init__(filepath, config)
        check_file(filepath)
        if self.page_range is not None:
            if len(self.page_range) > settings.DOCLAYOUT_MAX_PAGES:
                raise DocumentLimitError("Too many selected pages.")
            if any(type(page) is not int for page in self.page_range):
                raise ValueError("page_range must contain integers")
            self.page_range = list(dict.fromkeys(self.page_range))
        with self.get_doc() as doc:
            self.page_count = len(doc)
            selected_count = (
                len(doc) if self.page_range is None else len(self.page_range)
            )
            if selected_count > settings.DOCLAYOUT_MAX_PAGES:
                raise DocumentLimitError("Too many selected pages.")
            self.page_range = (
                list(range(len(doc)))
                if self.page_range is None
                else list(self.page_range)
            )
            if not self.page_range or any(
                p < 0 or p >= len(doc) for p in self.page_range
            ):
                raise ValueError(
                    f"page_range must contain pages between 0 and {len(doc) - 1}"
                )
            self.page_bboxes = {}
            for page_id in self.page_range:
                page = doc[page_id]
                try:
                    # Rendering coordinates start at the top left, including rotated pages.
                    width, height = page.get_size()
                    self.page_bboxes[page_id] = [0, 0, width, height]
                finally:
                    page.close()

    @contextmanager
    def get_doc(self):
        with PDFIUM_LOCK:
            doc = pdfium.PdfDocument(self.filepath)
            try:
                if self.flatten_pdf:
                    doc.init_forms()
                yield doc
            finally:
                doc.close()

    def __len__(self):
        return self.page_count

    def get_images(self, idxs, dpi):
        images = []
        with self.get_doc() as doc:
            for idx in idxs:
                page = doc[idx]
                try:
                    width, height = page.get_size()
                    check_pixels(width * dpi / 72, height * dpi / 72)
                    bitmap = page.render(
                        scale=dpi / 72, may_draw_forms=self.flatten_pdf
                    )
                    try:
                        images.append(bitmap.to_pil().convert("RGB"))
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        return images

    def get_page_bbox(self, idx):
        return PolygonBox.from_bbox(self.page_bboxes[idx])

    def get_page_refs(self, idx):
        return []
