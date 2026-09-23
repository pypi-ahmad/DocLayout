# Modified for DocLayout; see NOTICE for a summary of changes.
from doclayout.converters.pdf import PdfConverter
from doclayout.renderers.ocr_json import OCRJSONRenderer


class OCRConverter(PdfConverter):
    default_processors = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.renderer = OCRJSONRenderer

    def prepare_document(self, document):
        # Preserve the extraction's block order and estimated geometry.
        pass
