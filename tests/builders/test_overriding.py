from doclayout.converters.pdf import PdfConverter
from doclayout.schema import BlockTypes
from doclayout.schema.blocks import SectionHeader
from doclayout.schema.registry import register_block_class


class NewSectionHeader(SectionHeader):
    pass


def test_overriding(model_dict, temp_doc):
    try:
        converter = PdfConverter(
            model_dict,
            config={"override_map": {BlockTypes.SectionHeader: NewSectionHeader}},
        )
        document = converter.build_document(temp_doc.name)
        assert isinstance(
            document.pages[0].get_block(document.pages[0].structure[0]),
            NewSectionHeader,
        )
    finally:
        register_block_class(BlockTypes.SectionHeader, SectionHeader)
