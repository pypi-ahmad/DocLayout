"""Lifetime of temporary PDFs shared by the document-format providers."""

import os
import tempfile

from doclayout.providers.pdf import PdfProvider
from doclayout.security import check_file


class ConvertedPdfProvider(PdfProvider):
    conversion_method = ""

    def __init__(self, filepath, config=None):
        self.temp_pdf_path = None
        check_file(filepath)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as output:
            self.temp_pdf_path = output.name
        try:
            getattr(self, self.conversion_method)(filepath)
            super().__init__(self.temp_pdf_path, config)
        except BaseException:
            self.close()
            raise

    def close(self):
        path = self.temp_pdf_path
        if path is not None:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            self.temp_pdf_path = None

    def __del__(self):
        # Fallback for library users; normal callers use explicit close/context.
        if getattr(self, "temp_pdf_path", None) is not None:
            try:
                self.close()
            except OSError:
                pass
