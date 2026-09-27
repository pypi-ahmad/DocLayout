# Modified for DocLayout; see NOTICE for a summary of changes.
from doclayout.converters.pdf import PdfConverter
from doclayout.schema import BlockTypes


class TableConverter(PdfConverter):
    converter_block_types = (
        BlockTypes.Table,
        BlockTypes.Form,
        BlockTypes.TableOfContents,
    )

    def prepare_document(self, document):
        for page in document.pages:
            page.structure = [
                block_id
                for block_id in page.structure
                if block_id.block_type in self.converter_block_types
            ]
